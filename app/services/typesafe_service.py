import logging
from typing import Dict, Any, Optional
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score
from app.core.config import settings

logger = logging.getLogger(__name__)


class TypeSafeService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TYPESAFE_API_KEY

    async def evaluate_decision(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        social_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate market microstructure + social sentiment state using TypeSafe Jev System One.
        """
        sym = symbol.upper().replace("$", "")
        price = market_data.get("price", 100.0)
        funding_rate = market_data.get("funding_rate_pct", 0.0)
        rsi = market_data.get("rsi_14", 50.0)
        change_24h = market_data.get("change_24h_pct", 0.0)
        sample_size = social_stats.get("sample_size", 0)

        # Build structured state
        state = {
            "asset": sym,
            "market": {
                "current_price": price,
                "change_24h_pct": change_24h,
                "rsi_14": rsi,
                "funding_rate_pct": funding_rate,
                "volume_24h_usd": market_data.get("volume_24h_usd", 0)
            },
            "social_stats": {
                "sample_size": sample_size,
                "author_diversity_pct": social_stats.get("author_diversity_pct", 0),
                "total_likes": social_stats.get("total_likes", 0),
                "polarity_score": social_stats.get("polarity_score", 0),
                "sentiment_label": social_stats.get("sentiment_label", "Neutral")
            },
            "representative_tweets": social_stats.get("stratified_sample", [])
        }

        # Questions for TypeSafe System One
        questions = {
            "trade_action": Choice(
                instructions=(
                    "Given `market` data (RSI, price change, funding rate) and `social_stats` "
                    "across `sample_size` tweets, what is the best immediate trading action for `asset`?"
                ),
                criteria={
                    "STRONG_BUY": "High-conviction long (e.g. short squeeze setup, capitulation bottom, or major verified breakout).",
                    "BUY": "Favorable risk-to-reward long entry with positive upside expectation.",
                    "HOLD": "Neutral, range-bound, or consolidating; no clear asymmetric statistical edge.",
                    "TAKE_PROFIT": "Market is overbought or meeting heavy resistance; secure existing gains.",
                    "SELL": "Bearish breakdown, deteriorating momentum, or high downside continuation risk.",
                    "STRONG_SELL": "Crowded top exhaustion, extreme positive funding, or severe fundamental catalyst breakdown."
                }
            ),
            "sentiment_spectrum": Score(
                instructions="Rate the prevailing social mood in `social_stats` and `representative_tweets`.",
                criteria=[
                    "Extreme Panic / Capitulation",
                    "Cautious / Bearish",
                    "Neutral / Mixed",
                    "Optimistic / Bullish",
                    "Euphoric / Greedy"
                ]
            ),
            "is_short_squeeze_risk": Noul(
                instructions=(
                    "Does the state show negative `market.funding_rate_pct` clashing with "
                    "`social_stats.sentiment_label` panic at support, indicating a short squeeze risk?"
                )
            ),
            "catalyst_impact": Score(
                instructions="Rate the significance of any events or breaking news described in `representative_tweets`.",
                criteria=[
                    "No news or pure retail noise",
                    "Minor routine update or rumors",
                    "Moderate ecosystem milestone",
                    "Major market-shifting catalyst"
                ]
            )
        }

        # Check if API key is provided
        if self.api_key and self.api_key.strip() != "":
            try:
                async with AsyncTypeSafeClient(api_key=self.api_key) as client:
                    response = await client.system_one(state=state, questions=questions)

                action_ans = response.answers.get("trade_action")
                sentiment_ans = response.answers.get("sentiment_spectrum")
                squeeze_ans = response.answers.get("is_short_squeeze_risk")
                catalyst_ans = response.answers.get("catalyst_impact")

                trade_action = getattr(action_ans, "choice", "HOLD")
                action_conf = round(float(getattr(action_ans, "confidence", 0.75)) * 100, 1)
                raw_probs = getattr(action_ans, "probabilities", {}) or {}

                action_probabilities = {}
                if raw_probs:
                    for k, v in raw_probs.items():
                        val = float(v)
                        if 0.0 < val <= 1.0:
                            val = val * 100.0
                        action_probabilities[k] = round(val, 1)
                else:
                    action_probabilities = {trade_action: action_conf}

                sentiment_score_val = getattr(sentiment_ans, "score", 2.0)
                sentiment_levels = [
                    "Extreme Panic / Capitulation",
                    "Cautious / Bearish",
                    "Neutral / Mixed",
                    "Optimistic / Bullish",
                    "Euphoric / Greedy"
                ]
                sentiment_idx = min(max(0, int(round(sentiment_score_val))), len(sentiment_levels) - 1)
                sentiment_text = sentiment_levels[sentiment_idx]

                squeeze_prob = round(float(getattr(squeeze_ans, "noul", 0.15)) * 100, 1)
                catalyst_score_val = getattr(catalyst_ans, "score", 0.0)

                return self._build_decision_output(
                    symbol=sym,
                    price=price,
                    trade_action=trade_action,
                    confidence=action_conf,
                    action_probabilities=action_probabilities,
                    sentiment_text=sentiment_text,
                    sentiment_score=sentiment_score_val,
                    squeeze_prob=squeeze_prob,
                    catalyst_score=catalyst_score_val,
                    funding_rate=funding_rate,
                    rsi=rsi,
                    change_24h=change_24h,
                    is_mock=False
                )

            except Exception as e:
                logger.error(f"TypeSafe API evaluation failed: {e}. Using deterministic decision fallback.")

        # Fallback if no API key or API call failed
        logger.info("Using deterministic quantitative decision model (TYPESAFE_API_KEY not configured or failed).")
        return self._deterministic_decision(sym, price, change_24h, rsi, funding_rate, social_stats)

    def _build_decision_output(
        self,
        symbol: str,
        price: float,
        trade_action: str,
        confidence: float,
        sentiment_text: str,
        sentiment_score: float,
        squeeze_prob: float,
        catalyst_score: float,
        funding_rate: float,
        rsi: float,
        change_24h: float,
        action_probabilities: Optional[Dict[str, float]] = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Formulates actionable trade levels, probability distribution, and rationale."""
        all_actions = ["STRONG_BUY", "BUY", "HOLD", "TAKE_PROFIT", "SELL", "STRONG_SELL"]
        
        # Ensure full 100% normalized distribution across all 6 actions
        normalized_probs = {}
        if action_probabilities and len(action_probabilities) >= 2:
            total_raw = sum(action_probabilities.values()) or 1.0
            for act in all_actions:
                val = action_probabilities.get(act, 0.0)
                normalized_probs[act] = round((val / total_raw) * 100.0, 1)
        else:
            # Distribute based on winner confidence
            winner_pct = min(max(float(confidence), 30.0), 92.0)
            remainder = 100.0 - winner_pct
            other_actions = [a for a in all_actions if a != trade_action]
            weights = [0.4, 0.3, 0.15, 0.1, 0.05]
            normalized_probs[trade_action] = round(winner_pct, 1)
            for idx, act in enumerate(other_actions):
                normalized_probs[act] = round(remainder * weights[idx], 1)

        # Fix minor rounding to exactly 100.0
        diff = round(100.0 - sum(normalized_probs.values()), 1)
        if diff != 0 and trade_action in normalized_probs:
            normalized_probs[trade_action] = round(normalized_probs[trade_action] + diff, 1)

        # Calculate levels based on action
        if trade_action in ["STRONG_BUY", "BUY"]:
            entry_min = round(price * 0.995, 2)
            entry_max = round(price * 1.002, 2)
            stop_loss = round(price * 0.962, 2)
            tp1 = round(price * 1.045, 2)
            tp2 = round(price * 1.085, 2)
            sl_pct = round(((stop_loss - price) / price) * 100, 2)
            tp1_pct = round(((tp1 - price) / price) * 100, 2)
            tp2_pct = round(((tp2 - price) / price) * 100, 2)
            rr_ratio = round(abs(tp2_pct / sl_pct), 2) if sl_pct != 0 else 2.5
        elif trade_action in ["SELL", "STRONG_SELL"]:
            entry_min = round(price * 0.998, 2)
            entry_max = round(price * 1.005, 2)
            stop_loss = round(price * 1.038, 2)
            tp1 = round(price * 0.955, 2)
            tp2 = round(price * 0.915, 2)
            sl_pct = round(((stop_loss - price) / price) * 100, 2)
            tp1_pct = round(((tp1 - price) / price) * 100, 2)
            tp2_pct = round(((tp2 - price) / price) * 100, 2)
            rr_ratio = round(abs(tp2_pct / sl_pct), 2) if sl_pct != 0 else 2.5
        elif trade_action == "TAKE_PROFIT":
            entry_min = round(price * 0.99, 2)
            entry_max = round(price * 1.01, 2)
            stop_loss = round(price * 0.98, 2)
            tp1 = round(price * 1.02, 2)
            tp2 = round(price * 1.05, 2)
            sl_pct = -2.0
            tp1_pct = +2.0
            tp2_pct = +5.0
            rr_ratio = 2.5
        else:  # HOLD
            entry_min = price
            entry_max = price
            stop_loss = round(price * 0.95, 2)
            tp1 = round(price * 1.05, 2)
            tp2 = round(price * 1.10, 2)
            sl_pct = -5.0
            tp1_pct = +5.0
            tp2_pct = +10.0
            rr_ratio = 2.0

        # Build dynamic rationale
        reasons = []
        if squeeze_prob > 60:
            reasons.append(f"Short squeeze probability is elevated ({squeeze_prob}%) due to negative funding ({funding_rate}%).")
        if rsi < 35:
            reasons.append(f"RSI-14 indicates oversold conditions ({rsi}).")
        elif rsi > 68:
            reasons.append(f"RSI-14 indicates overbought momentum ({rsi}).")

        if "Panic" in sentiment_text or "Fear" in sentiment_text:
            reasons.append(f"Social sentiment reflects prevailing fear/panic ({sentiment_text}), presenting contrarian absorption.")
        elif "Euphoric" in sentiment_text:
            reasons.append(f"Social sentiment shows high euphoria ({sentiment_text}), warranting cautious position sizing.")

        if catalyst_score >= 2.0:
            reasons.append("Significant ecosystem or market-moving catalyst detected in recent discussions.")

        if not reasons:
            reasons.append("Market momentum and social sentiment are balanced with no extreme divergence.")

        rationale = " ".join(reasons)

        return {
            "symbol": symbol,
            "action": trade_action,
            "confidence_pct": normalized_probs.get(trade_action, round(confidence, 1)),
            "action_probabilities": normalized_probs,
            "sentiment_label": sentiment_text,
            "sentiment_score": round(float(sentiment_score), 2),
            "squeeze_risk_pct": squeeze_prob,
            "catalyst_impact_score": round(float(catalyst_score), 2),
            "trade_levels": {
                "entry_range": [entry_min, entry_max],
                "stop_loss": stop_loss,
                "stop_loss_pct": sl_pct,
                "target_1": tp1,
                "target_1_pct": tp1_pct,
                "target_2": tp2,
                "target_2_pct": tp2_pct,
                "risk_reward_ratio": rr_ratio
            },
            "rationale": rationale,
            "is_mock": is_mock
        }

    def _deterministic_decision(
        self,
        symbol: str,
        price: float,
        change_24h: float,
        rsi: float,
        funding_rate: float,
        social_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rule-based quantitative model fallback when TypeSafe API key is not yet set."""
        polarity = social_stats.get("polarity_score", 0.0)

        # Logic for short squeeze
        if funding_rate < -0.01 and polarity < -0.2:
            action = "STRONG_BUY"
            confidence = 88.5
            squeeze_prob = 84.0
            sentiment_text = "Extreme Panic / Capitulation"
            sentiment_score = 0.5
            catalyst_score = 2.1
        elif rsi < 35 and polarity < -0.1:
            action = "BUY"
            confidence = 81.0
            squeeze_prob = 62.0
            sentiment_text = "Cautious / Bearish"
            sentiment_score = 1.2
            catalyst_score = 1.0
        elif rsi > 70 and funding_rate > 0.03:
            action = "STRONG_SELL"
            confidence = 86.0
            squeeze_prob = 10.0
            sentiment_text = "Euphoric / Greedy"
            sentiment_score = 4.0
            catalyst_score = 1.5
        elif change_24h > 12 and rsi > 65:
            action = "TAKE_PROFIT"
            confidence = 79.0
            squeeze_prob = 20.0
            sentiment_text = "Euphoric / Greedy"
            sentiment_score = 3.8
            catalyst_score = 1.8
        elif change_24h < -8 and rsi < 40:
            action = "BUY"
            confidence = 77.5
            squeeze_prob = 55.0
            sentiment_text = "Cautious / Bearish"
            sentiment_score = 1.0
            catalyst_score = 0.8
        else:
            action = "HOLD"
            confidence = 72.0
            squeeze_prob = 25.0
            sentiment_text = social_stats.get("sentiment_label", "Neutral / Mixed")
            sentiment_score = 2.0
            catalyst_score = 0.5

        return self._build_decision_output(
            symbol=symbol,
            price=price,
            trade_action=action,
            confidence=confidence,
            sentiment_text=sentiment_text,
            sentiment_score=sentiment_score,
            squeeze_prob=squeeze_prob,
            catalyst_score=catalyst_score,
            funding_rate=funding_rate,
            rsi=rsi,
            change_24h=change_24h,
            is_mock=True
        )


typesafe_service = TypeSafeService()
