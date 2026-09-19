import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.market_service import market_service
from app.services.twitter_service import twitter_service
from app.services.stats_service import stats_service
from app.services.typesafe_service import typesafe_service


async def test_pipeline():
    print("\n--- 1. Testing Market Service ---")
    market = await market_service.get_market_data("BTC")
    assert "price" in market, "Market data must contain price"
    assert market["price"] > 0, "Price must be positive"
    print(f"✅ Market data fetched: {market['symbol']} Price=${market['price']} 24h={market['change_24h_pct']}% Funding={market['funding_rate_pct']}% Candles={len(market['candles'])}")

    print("\n--- 2. Testing Twitter Service ---")
    twitter_res = await twitter_service.fetch_tweets("BTC", target_count=50)
    tweets = twitter_res.get("tweets", [])
    assert len(tweets) > 0, "Tweets list should not be empty"
    print(f"✅ Tweets fetched: {len(tweets)} tweets (is_mock={twitter_res.get('is_mock')})")

    print("\n--- 3. Testing Stats Pre-Processing ---")
    stats = stats_service.process_tweets(tweets)
    assert "polarity_score" in stats
    assert "author_diversity_pct" in stats
    print(f"✅ Stats computed: Polarity={stats['polarity_score']} Sentiment={stats['sentiment_label']} Diversity={stats['author_diversity_pct']}%")

    print("\n--- 4. Testing TypeSafe Decision Service ---")
    decision = await typesafe_service.evaluate_decision("BTC", market, stats)
    assert "action" in decision
    assert "trade_levels" in decision
    assert decision["confidence_pct"] > 0
    print(f"✅ Decision generated: Action={decision['action']} Confidence={decision['confidence_pct']}% SqueezeRisk={decision['squeeze_risk_pct']}%")
    print(f"   Entry: {decision['trade_levels']['entry_range']} StopLoss: {decision['trade_levels']['stop_loss']} TP1: {decision['trade_levels']['target_1']}")

    print("\n--- 5. Testing FastAPI /api/v1/analyze Endpoint ---")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/analyze", json={"symbol": "SOL", "sample_size": 100})
        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["symbol"] == "SOL"
        assert "decision" in data
        assert "market" in data
        print(f"✅ API Endpoint responded 200 OK for SOL! Action: {data['decision']['action']} Price: ${data['market']['price']}")

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
