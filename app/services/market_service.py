import ccxt.async_support as ccxt
import logging
from typing import Dict, Any, List, Optional
import time
from app.core.cache import market_cache

logger = logging.getLogger(__name__)


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI) across price series."""
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    if len(gains) < period:
        return 50.0

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


class MarketService:
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        sym = symbol.upper().replace("$", "")
        pair = f"{sym}/USD"
        cache_key = f"market_{sym}"

        cached = await market_cache.get(cache_key)
        if cached:
            return cached

        # Use Kraken for spot ticker & OHLCV, Kraken Futures for real perpetual funding rate & open interest
        exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 8000})
        futures_exchange = ccxt.krakenfutures({"enableRateLimit": True, "timeout": 8000})

        try:
            # 1. Fetch Spot Ticker
            ticker = await exchange.fetch_ticker(pair)
            price = float(ticker.get("last") or ticker.get("close") or 0.0)
            change_24h = float(ticker.get("percentage") or 0.0)
            high_24h = float(ticker.get("high") or price * 1.05)
            low_24h = float(ticker.get("low") or price * 0.95)
            volume_24h = float(ticker.get("quoteVolume") or (ticker.get("baseVolume", 0) * price if ticker.get("baseVolume") else 0.0))

            # 2. Fetch OHLCV candles (last 48 1h candles)
            candles_raw = await exchange.fetch_ohlcv(pair, timeframe="1h", limit=48)
            candles = []
            close_prices = []
            for c in candles_raw:
                candles.append({
                    "time": int(c[0] // 1000),  # TradingView expects unix seconds
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5])
                })
                close_prices.append(float(c[4]))

            rsi = calculate_rsi(close_prices, 14)

            # 3. Fetch Real Perpetuals Funding Rate & Open Interest
            funding_rate_pct = None
            open_interest_usd = None
            has_perpetuals = False

            try:
                futures_pair = f"{sym}/USD:USD"
                fr_info = await futures_exchange.fetch_funding_rate(futures_pair)
                raw_rate = fr_info.get("fundingRate")
                if raw_rate is not None:
                    funding_rate_pct = round(float(raw_rate) * 100, 4)
                    has_perpetuals = True

                info_block = fr_info.get("info", {})
                raw_oi = info_block.get("openInterest")
                if raw_oi is not None:
                    oi_val = float(raw_oi)
                    open_interest_usd = round(oi_val * price, 2) if price > 0 else round(oi_val, 2)
            except Exception as fe:
                logger.info(f"Kraken Futures perpetual contract unavailable for {sym}: {fe}")

            # 4. Explicitly labeled 24h momentum bucket
            momentum_bucket = "bullish" if change_24h > 3 else ("bearish" if change_24h < -3 else "neutral")

            result = {
                "symbol": sym,
                "pair": pair,
                "price": round(price, 4) if price < 10 else round(price, 2),
                "change_24h_pct": round(change_24h, 2),
                "high_24h": round(high_24h, 2),
                "low_24h": round(low_24h, 2),
                "volume_24h_usd": round(volume_24h, 0),
                "rsi_14": rsi,
                "funding_rate_pct": funding_rate_pct,
                "open_interest_usd": open_interest_usd,
                "has_perpetuals": has_perpetuals,
                "momentum_bucket": momentum_bucket,
                "candles": candles,
                "fetched_at": int(time.time()),
                "is_fallback": False
            }

            await market_cache.set(cache_key, result, ttl=60)
            return result

        except Exception as e:
            logger.warning(f"Error fetching from Kraken for {pair}: {e}. Trying fallback.")
            return self._generate_fallback_data(sym)
        finally:
            await exchange.close()
            await futures_exchange.close()

    def _generate_fallback_data(self, symbol: str) -> Dict[str, Any]:
        """Realistic fallback when exchange API is unreachable or rate limited."""
        defaults = {
            "BTC": (76500.0, -1.2, 44.5),
            "SOL": (152.40, +4.1, 58.2),
            "ETH": (2560.0, -0.8, 46.2),
        }
        base_price, change, rsi = defaults.get(symbol.upper(), (100.0, 0.0, 50.0))
        now = int(time.time())
        candles = []
        p = base_price * 0.98
        for i in range(48):
            t = now - (48 - i) * 3600
            o = p
            c = o * (1.0 + (0.002 if i % 2 == 0 else -0.0018))
            h = max(o, c) * 1.003
            l = min(o, c) * 0.997
            p = c
            candles.append({
                "time": t,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": 12000.0
            })

        momentum_bucket = "bullish" if change > 3 else ("bearish" if change < -3 else "neutral")

        return {
            "symbol": symbol.upper(),
            "pair": f"{symbol.upper()}/USD",
            "price": base_price,
            "change_24h_pct": change,
            "high_24h": round(base_price * 1.04, 2),
            "low_24h": round(base_price * 0.96, 2),
            "volume_24h_usd": 1500000000.0,
            "rsi_14": rsi,
            "funding_rate_pct": None,
            "open_interest_usd": None,
            "has_perpetuals": False,
            "momentum_bucket": momentum_bucket,
            "candles": candles,
            "fetched_at": now,
            "is_fallback": True
        }


market_service = MarketService()
