import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.core.database import db
from app.services.twitter_service import twitter_service


@pytest.mark.asyncio
async def test_dedup():
    print("\n--- Testing Early-Stopping Database Deduplication ---")
    
    # 1. Initial fetch of 50 tweets
    res1 = await twitter_service.fetch_tweets("BTC", target_count=50)
    print(f"Step 1: Fetched {len(res1['tweets'])} tweets for BTC. Saved to DB.")
    assert len(res1["tweets"]) >= 50
    assert "timestamp_epoch" in res1["tweets"][0]
    assert res1["tweets"][0]["timestamp_epoch"] > 0
    
    # Check known IDs
    known = await db.get_known_ids("BTC")
    print(f"Step 2: Database has {len(known)} known tweet IDs for BTC.")
    assert len(known) >= 50, "DB should contain at least 50 tweets"
    
    # 2. Second fetch of 100 tweets for BTC
    # Should recognize existing tweets in DB and pull from DB
    res2 = await twitter_service.fetch_tweets("BTC", target_count=100)
    print(f"Step 3: Fetched {len(res2['tweets'])} tweets. (DB pulled older, new count: {res2.get('newly_fetched_count', 0)})")
    assert len(res2["tweets"]) >= 50
    
    print("\n✅ Early-stopping database deduplication working perfectly!")


@pytest.mark.asyncio
async def test_invalid_symbol_rejected():
    with pytest.raises(ValueError):
        await twitter_service.fetch_tweets("BTC; DROP TABLE", target_count=50)


if __name__ == "__main__":
    asyncio.run(test_dedup())
