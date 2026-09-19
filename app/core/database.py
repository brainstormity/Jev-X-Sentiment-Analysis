import sqlite3
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
import time

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "market_intel.db"


class Database:
    def __init__(self):
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tweets (
                        id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        text TEXT NOT NULL,
                        created_at TEXT,
                        timestamp_epoch INTEGER,
                        likes INTEGER DEFAULT 0,
                        retweets INTEGER DEFAULT 0,
                        replies INTEGER DEFAULT 0,
                        author_username TEXT,
                        author_followers INTEGER DEFAULT 0,
                        author_verified BOOLEAN DEFAULT 0,
                        fetched_at INTEGER NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tweets_symbol_epoch
                    ON tweets (symbol, timestamp_epoch DESC, fetched_at DESC);
                """)
            self._initialized = True
        finally:
            conn.close()

    async def get_known_ids(self, symbol: str, limit: int = 5000) -> Set[str]:
        """Returns set of known tweet IDs for a symbol to check for early termination."""
        def _query():
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM tweets WHERE symbol = ? ORDER BY fetched_at DESC LIMIT ?",
                    (symbol.upper(), limit)
                )
                return {row["id"] for row in cursor.fetchall()}
            finally:
                conn.close()

        return await asyncio.to_thread(_query)

    async def save_tweets(self, symbol: str, tweets: List[Dict[str, Any]]) -> int:
        """Saves tweets with INSERT OR IGNORE to prevent duplicates."""
        if not tweets:
            return 0

        def _insert():
            conn = self._get_connection()
            now = int(time.time())
            saved_count = 0
            try:
                with conn:
                    for t in tweets:
                        cursor = conn.execute("""
                            INSERT OR IGNORE INTO tweets (
                                id, symbol, text, created_at, timestamp_epoch,
                                likes, retweets, replies, author_username,
                                author_followers, author_verified, fetched_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(t.get("id", "")),
                            symbol.upper(),
                            t.get("text", ""),
                            t.get("created_at", ""),
                            t.get("timestamp_epoch", now),
                            t.get("likes", 0),
                            t.get("retweets", 0),
                            t.get("replies", 0),
                            t.get("author_username", ""),
                            t.get("author_followers", 0),
                            1 if t.get("author_verified") else 0,
                            now
                        ))
                        if cursor.rowcount > 0:
                            saved_count += 1
                return saved_count
            finally:
                conn.close()

        return await asyncio.to_thread(_insert)

    async def get_recent_tweets(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch the most recent tweets stored in DB for a symbol."""
        def _query():
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, text, created_at, likes, retweets, replies,
                           author_username, author_followers, author_verified
                    FROM tweets
                    WHERE symbol = ?
                    ORDER BY fetched_at DESC, id DESC
                    LIMIT ?
                """, (symbol.upper(), limit))
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    results.append({
                        "id": r["id"],
                        "text": r["text"],
                        "created_at": r["created_at"],
                        "likes": r["likes"],
                        "retweets": r["retweets"],
                        "replies": r["replies"],
                        "author_username": r["author_username"],
                        "author_followers": r["author_followers"],
                        "author_verified": bool(r["author_verified"])
                    })
                return results
            finally:
                conn.close()

        return await asyncio.to_thread(_query)


db = Database()
db.init_db()
