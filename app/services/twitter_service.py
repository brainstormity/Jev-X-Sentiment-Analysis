import httpx
import logging
from typing import List, Dict, Any, Optional
import time
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.core.config import settings
from app.core.cache import social_cache
from app.core.database import db

logger = logging.getLogger(__name__)

TWITTER_API_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"
SYMBOL_REGEX = re.compile(r"^[A-Z0-9]{1,15}$")


def parse_twitter_timestamp(ts_str: Optional[str]) -> int:
    """Parse various Twitter date formats into unix integer seconds."""
    if not ts_str:
        return int(time.time())
    try:
        # ISO 8601 (e.g. 2026-09-22T04:00:00.000Z)
        if ts_str.endswith("Z"):
            return int(datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
        elif "T" in ts_str:
            return int(datetime.fromisoformat(ts_str).timestamp())
        # RFC 2822 (e.g. Tue Sep 22 04:00:00 +0000 2026)
        dt = parsedate_to_datetime(ts_str)
        return int(dt.timestamp())
    except Exception:
        return int(time.time())


class TwitterService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TWITTER_API_KEY

    def _build_query(self, symbol: str) -> str:
        sym = symbol.upper().replace("$", "").strip()
        if not SYMBOL_REGEX.match(sym):
            raise ValueError(f"Invalid symbol '{symbol}' for query builder. Must be 1-15 alphanumeric characters.")

        names = {
            "BTC": "Bitcoin",
            "SOL": "Solana",
            "ETH": "Ethereum",
            "DOGE": "Dogecoin",
            "XRP": "Ripple",
            "ADA": "Cardano",
            "AVAX": "Avalanche",
            "NEAR": "Near",
            "SUI": "Sui"
        }
        full_name = names.get(sym, sym)
        if sym == full_name:
            return f"${sym} lang:en -is:retweet min_faves:2"
        return f"(${sym} OR {full_name}) lang:en -is:retweet min_faves:2"

    async def fetch_tweets(self, symbol: str, target_count: int = 100) -> Dict[str, Any]:
        """
        Fetches up to target_count tweets for a given symbol.
        
        Cost-Saving Ingestion Algorithm:
        1. Checks database for existing known tweet IDs for this symbol.
        2. Queries TwitterAPI.io page by page (ordered latest first).
        3. EARLY STOPPING: As soon as a returned tweet already exists in our database,
           we STOP calling the TwitterAPI immediately to save API credits!
        4. Saves newly fetched tweets to the database.
        5. Fills the remaining required count directly from the local database so the user
           gets their full requested sample size at minimal API cost.
        """
        sym = symbol.upper().replace("$", "").strip()
        if not SYMBOL_REGEX.match(sym):
            raise ValueError(f"Invalid crypto symbol '{symbol}'. Must be 1-15 alphanumeric characters.")

        cache_key = f"tweets_{sym}_{target_count}"

        # 1. Check in-memory short TTL cache (e.g. within 60s)
        cached = await social_cache.get(cache_key)
        if cached:
            logger.info(f"In-memory cache hit for tweets: {cache_key}")
            return cached

        # 2. Check known tweet IDs in local database
        known_ids = await db.get_known_ids(sym, limit=5000)

        # 3. If API Key not set, generate simulated tweets and save to DB
        if not self.api_key or self.api_key.strip() == "":
            logger.info("TWITTER_API_KEY not configured. Checking database or generating simulated tweets.")
            db_tweets = await db.get_recent_tweets(sym, limit=target_count)
            if len(db_tweets) >= target_count:
                result = {
                    "symbol": sym,
                    "count": len(db_tweets),
                    "target_count": target_count,
                    "is_mock": True,
                    "api_calls_made": 0,
                    "cost_saved": True,
                    "yield_deficit": False,
                    "tweets": db_tweets
                }
                await social_cache.set(cache_key, result, ttl=30)
                return result

            # Otherwise generate sample and save to DB
            simulated_data = self._generate_simulated_tweets(sym, target_count)
            await db.save_tweets(sym, simulated_data["tweets"])
            await social_cache.set(cache_key, simulated_data, ttl=30)
            return simulated_data

        # 4. Call TwitterAPI.io with Early-Stopping Deduplication
        new_tweets: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        headers = {"X-API-Key": self.api_key}
        query = self._build_query(sym)

        early_stopped = False
        api_pages_called = 0
        # Allow sufficient pages even if vendor returns fewer than 40 tweets per page
        max_pages = min(35, max(5, (target_count // 15) + 3))

        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            while len(new_tweets) < target_count and api_pages_called < max_pages:
                api_pages_called += 1
                params = {
                    "query": query,
                    "queryType": "Latest"
                }
                if cursor:
                    params["cursor"] = cursor

                try:
                    res = await client.get(TWITTER_API_URL, headers=headers, params=params)
                    if res.status_code != 200:
                        logger.error(f"TwitterAPI.io returned {res.status_code}: {res.text}")
                        break

                    data = res.json()
                    raw_tweets = data.get("tweets") or data.get("data") or []
                    if not raw_tweets:
                        break

                    for t in raw_tweets:
                        tid = str(t.get("id", ""))
                        
                        # EARLY STOPPING CHECK:
                        # If this tweet is already in DB, stop paginating! Older tweets are already in DB!
                        if tid in known_ids:
                            logger.info(f"Early stop triggered! Tweet {tid} already in DB. Halting API pagination.")
                            early_stopped = True
                            break

                        author = t.get("author") or {}
                        created_at_raw = t.get("createdAt") or t.get("created_at") or ""
                        epoch_ts = parse_twitter_timestamp(created_at_raw)

                        normalized = {
                            "id": tid,
                            "text": t.get("text", ""),
                            "created_at": created_at_raw,
                            "timestamp_epoch": epoch_ts,
                            "likes": int(t.get("likeCount") or t.get("likes") or 0),
                            "retweets": int(t.get("retweetCount") or t.get("retweets") or 0),
                            "replies": int(t.get("replyCount") or t.get("replies") or 0),
                            "author_username": author.get("userName") or author.get("username") or "anonymous",
                            "author_followers": int(author.get("followers") or author.get("followersCount") or 0),
                            "author_verified": bool(author.get("isBlueVerified") or author.get("verified") or False)
                        }
                        new_tweets.append(normalized)

                    if early_stopped:
                        break

                    cursor = data.get("next_cursor") or data.get("cursor") or data.get("has_next_page")
                    if not cursor:
                        break

                except Exception as e:
                    logger.error(f"Error querying TwitterAPI.io: {e}")
                    break

        # Save any new tweets to the local database
        if new_tweets:
            await db.save_tweets(sym, new_tweets)
            logger.info(f"Saved {len(new_tweets)} newly fetched tweets to local DB for {sym}")

        # If we need more tweets to fulfill target_count (e.g. user requested 500, but only 30 were new)
        combined_tweets = list(new_tweets)
        if len(combined_tweets) < target_count:
            needed = target_count - len(combined_tweets)
            db_historical = await db.get_recent_tweets(sym, limit=target_count * 2)
            existing_ids = {t["id"] for t in combined_tweets}
            for dbt in db_historical:
                if dbt["id"] not in existing_ids:
                    combined_tweets.append(dbt)
                    existing_ids.add(dbt["id"])
                    if len(combined_tweets) >= target_count:
                        break

        yield_deficit = len(combined_tweets) < target_count
        if yield_deficit:
            logger.warning(
                f"Target count {target_count} requested for {sym}, but only {len(combined_tweets)} "
                "available from live search and local database combined."
            )

        result = {
            "symbol": sym,
            "count": len(combined_tweets),
            "newly_fetched_count": len(new_tweets),
            "target_count": target_count,
            "api_pages_called": api_pages_called,
            "early_stopped": early_stopped,
            "yield_deficit": yield_deficit,
            "is_mock": False,
            "tweets": combined_tweets
        }
        await social_cache.set(cache_key, result, ttl=settings.CACHE_TTL_SECONDS)
        return result

    def _generate_simulated_tweets(self, symbol: str, count: int) -> Dict[str, Any]:
        """Generates realistic crypto sentiment tweets for testing when no API key is provided."""
        import random
        templates = [
            f"${symbol} holding key support beautifully on the 4h timeframe. Bullish consolidation.",
            f"Panic sellers dumping ${symbol} right into institutional bid blocks. Classic retail mistake.",
            f"Perpetual funding rate for ${symbol} just flipped negative while spot volume spikes. Short squeeze imminent.",
            f"If ${symbol} loses this level we are heading straight to local support. Watch your stop losses.",
            f"Massive whale transfer of ${symbol} spotted heading off exchange into cold storage.",
            f"Solana and ${symbol} leading the market recovery today. Narrative shift underway.",
            f"Funding is deeply negative on ${symbol} futures. Bears are getting greedy here.",
            f"Breaking: Major protocol milestone reached on ${symbol} ecosystem testnet.",
            f"Taking partial profits on my ${symbol} swing long at resistance, trailing stop to entry.",
            f"Extreme fear in the sentiment index for ${symbol}. Historically this is where generational bottoms form.",
            f"${symbol} volume divergence setting up. Price consolidating while RSI prints bullish divergence.",
            f"Market makers hunting liquidations below support on ${symbol}. Don't get chopped up."
        ]

        authors = [
            ("QuantAlphaX", 145000, True),
            ("CryptoPulseLead", 89000, True),
            ("MacroTrader_Dan", 34000, False),
            ("OnChainAlerts", 210000, True),
            ("SolanaVibe", 12000, False),
            ("DeFiAnalyst99", 54000, False),
            ("WhaleStatsFeed", 410000, True),
            ("ChartWizardCrypto", 76000, True)
        ]

        now = int(time.time())
        generated = []
        for i in range(min(count, 1000)):
            text = random.choice(templates)
            author = random.choice(authors)
            generated.append({
                "id": f"tweet_{symbol.lower()}_{now - i*60}_{i}",
                "text": text,
                "created_at": "Recent",
                "timestamp_epoch": now - i * 60,
                "likes": random.randint(5, 3400),
                "retweets": random.randint(1, 450),
                "replies": random.randint(0, 120),
                "author_username": author[0],
                "author_followers": author[1],
                "author_verified": author[2]
            })

        return {
            "symbol": symbol,
            "count": len(generated),
            "newly_fetched_count": len(generated),
            "target_count": count,
            "api_pages_called": 0,
            "early_stopped": False,
            "is_mock": True,
            "tweets": generated
        }


twitter_service = TwitterService()
