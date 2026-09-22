from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import asyncio
import re

from app.core.config import settings
from app.services.market_service import market_service
from app.services.twitter_service import twitter_service
from app.services.stats_service import stats_service
from app.services.typesafe_service import typesafe_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Analysis"])

KEY_REGEX = re.compile(r"^[A-Za-z0-9_\-\.]{8,128}$")
SYMBOL_REGEX = re.compile(r"^[A-Z0-9]{1,15}$")


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., json_schema_extra={"example": "BTC"}, description="Crypto symbol (e.g. BTC, SOL, ETH)")
    sample_size: int = Field(100, ge=50, le=1000, description="Tweet sample count: 50, 100, 250, 500, or 1000")


@router.post("/analyze")
async def analyze_asset(req: AnalyzeRequest) -> Dict[str, Any]:
    """
    On-demand market intelligence & decision generation.
    1. Fetches live market data (CCXT Kraken / Kraken Futures).
    2. Ingests N tweets (TwitterAPI.io with pagination).
    3. Runs Tier 1 statistical aggregation & stratified sampling.
    4. Evaluates state with TypeSafe Jev System One.
    """
    sym = req.symbol.strip().upper().replace("$", "")
    if not SYMBOL_REGEX.match(sym):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid crypto symbol '{req.symbol}'. Symbol must be 1-15 alphanumeric characters."
        )

    sample_size = req.sample_size

    try:
        # Run market data & tweet ingestion concurrently
        market_task = market_service.get_market_data(sym)
        tweets_task = twitter_service.fetch_tweets(sym, target_count=sample_size)

        market_data, twitter_res = await asyncio.gather(market_task, tweets_task)

        tweets = twitter_res.get("tweets", [])

        # Tier 1: Statistical processing
        social_stats = stats_service.process_tweets(tweets)

        # Tier 2: TypeSafe Jev System One evaluation
        decision = await typesafe_service.evaluate_decision(
            symbol=sym,
            market_data=market_data,
            social_stats=social_stats
        )

        return {
            "symbol": sym,
            "status": "success",
            "market": market_data,
            "social_stats": social_stats,
            "decision": decision,
            "tweets_sample": tweets[:100],  # Return up to 100 representative tweets for UI explorer
            "is_twitter_mock": twitter_res.get("is_mock", False),
            "is_typesafe_mock": decision.get("is_mock", False)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze {sym}: {str(e)}")


@router.get("/market/{symbol}")
async def get_market_summary(symbol: str) -> Dict[str, Any]:
    """Quick market data lookup for an asset."""
    sym = symbol.strip().upper().replace("$", "")
    if not SYMBOL_REGEX.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid symbol '{symbol}'. Must be alphanumeric.")
    try:
        return await market_service.get_market_data(sym)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SettingsUpdate(BaseModel):
    typesafe_api_key: Optional[str] = None
    twitter_api_key: Optional[str] = None


@router.get("/settings")
async def get_settings_status() -> Dict[str, Any]:
    return {
        "has_typesafe_key": bool(settings.TYPESAFE_API_KEY),
        "has_twitter_key": bool(settings.TWITTER_API_KEY)
    }


@router.post("/settings")
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")
) -> Dict[str, Any]:
    """
    Update API keys with authentication and input sanitization.
    Permits access from localhost or with a valid X-Admin-Token header.
    """
    client_host = request.client.host if request.client else "unknown"
    is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    has_valid_admin_token = bool(settings.ADMIN_TOKEN and x_admin_token == settings.ADMIN_TOKEN)

    if not (is_local or has_valid_admin_token):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Settings modification is restricted to localhost or authenticated requests."
        )

    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"

    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    if payload.typesafe_api_key is not None and payload.typesafe_api_key.strip():
        k = payload.typesafe_api_key.strip()
        if not KEY_REGEX.match(k):
            raise HTTPException(status_code=400, detail="Invalid TypeSafe API key format.")
        settings.TYPESAFE_API_KEY = k
        typesafe_service.api_key = k
        env_vars["TYPESAFE_API_KEY"] = k

    if payload.twitter_api_key is not None and payload.twitter_api_key.strip():
        k = payload.twitter_api_key.strip()
        if not KEY_REGEX.match(k):
            raise HTTPException(status_code=400, detail="Invalid TwitterAPI key format.")
        settings.TWITTER_API_KEY = k
        twitter_service.api_key = k
        env_vars["TWITTER_API_KEY"] = k

    env_content = "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n"
    env_path.write_text(env_content)

    return {
        "status": "success",
        "has_typesafe_key": bool(settings.TYPESAFE_API_KEY),
        "has_twitter_key": bool(settings.TWITTER_API_KEY)
    }

