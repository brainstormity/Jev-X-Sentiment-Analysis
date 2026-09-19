from typing import List, Dict, Any


FEAR_KEYWORDS = {
    "crash", "dump", "liquidation", "sell", "selling", "dead", "bear", "bearish",
    "scam", "rekt", "drop", "loss", "bleeding", "panic", "fear", "down", "dip", "fall"
}

GREED_KEYWORDS = {
    "pump", "moon", "ath", "buy", "buying", "gem", "bull", "bullish", "breakout",
    "rally", "gain", "accumulate", "rocket", "up", "long", "hold", "squeeze"
}


class StatsService:
    @staticmethod
    def process_tweets(tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Tier 1 Deterministic Pre-Processing across all N ingested tweets.
        Calculates engagement velocity, author diversity, polarity score,
        and extracts a stratified sample for TypeSafe System One evaluation.
        """
        if not tweets:
            return {
                "sample_size": 0,
                "unique_authors_count": 0,
                "author_diversity_pct": 0.0,
                "total_likes": 0,
                "total_retweets": 0,
                "avg_engagement": 0.0,
                "fear_mentions": 0,
                "greed_mentions": 0,
                "polarity_score": 0.0,
                "sentiment_label": "Neutral",
                "stratified_sample": []
            }

        total_likes = 0
        total_retweets = 0
        total_replies = 0
        authors = set()
        fear_count = 0
        greed_count = 0

        for t in tweets:
            likes = t.get("likes", 0)
            retweets = t.get("retweets", 0)
            replies = t.get("replies", 0)

            total_likes += likes
            total_retweets += retweets
            total_replies += replies

            username = t.get("author_username") or "unknown"
            authors.add(username.lower())

            # Text polarity check
            text_lower = t.get("text", "").lower()
            words = set(text_lower.replace("$", "").replace("#", "").split())

            fear_hits = len(words.intersection(FEAR_KEYWORDS))
            greed_hits = len(words.intersection(GREED_KEYWORDS))

            fear_count += fear_hits
            greed_count += greed_hits

        sample_size = len(tweets)
        unique_authors = len(authors)
        diversity_pct = round((unique_authors / sample_size) * 100.0, 1)
        avg_engagement = round((total_likes + total_retweets * 2) / sample_size, 1)

        total_polar = fear_count + greed_count
        if total_polar > 0:
            # Score from -1.0 (extreme fear) to +1.0 (extreme greed)
            polarity_score = round((greed_count - fear_count) / total_polar, 2)
        else:
            polarity_score = 0.0

        if polarity_score <= -0.4:
            sentiment_label = "Extreme Panic"
        elif polarity_score < -0.1:
            sentiment_label = "Bearish / Fearful"
        elif polarity_score <= 0.1:
            sentiment_label = "Neutral / Mixed"
        elif polarity_score < 0.4:
            sentiment_label = "Bullish / Optimistic"
        else:
            sentiment_label = "Euphoric / Greedy"

        # Stratified sampling: Top 25 engaged + 25 latest
        sorted_by_engagement = sorted(
            tweets,
            key=lambda x: x.get("likes", 0) + x.get("retweets", 0) * 2,
            reverse=True
        )
        top_engaged = sorted_by_engagement[:25]

        # Use first 25 as latest (assuming latest order)
        latest_tweets = tweets[:25]

        # Merge and deduplicate by ID
        seen_ids = set()
        stratified_sample = []

        for t in top_engaged:
            tid = t.get("id")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                stratified_sample.append({
                    "author": t.get("author_username"),
                    "text": t.get("text"),
                    "likes": t.get("likes"),
                    "type": "high_engagement"
                })

        for t in latest_tweets:
            tid = t.get("id")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                stratified_sample.append({
                    "author": t.get("author_username"),
                    "text": t.get("text"),
                    "likes": t.get("likes"),
                    "type": "latest_breaking"
                })

        return {
            "sample_size": sample_size,
            "unique_authors_count": unique_authors,
            "author_diversity_pct": diversity_pct,
            "total_likes": total_likes,
            "total_retweets": total_retweets,
            "avg_engagement": avg_engagement,
            "fear_mentions": fear_count,
            "greed_mentions": greed_count,
            "polarity_score": polarity_score,
            "sentiment_label": sentiment_label,
            "stratified_sample": stratified_sample
        }


stats_service = StatsService()
