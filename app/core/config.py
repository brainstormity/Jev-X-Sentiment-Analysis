from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Jev X Sentiment Analysis"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # External APIs
    TYPESAFE_API_KEY: Optional[str] = None
    TWITTER_API_KEY: Optional[str] = None

    # Caching
    CACHE_TTL_SECONDS: int = 600  # 10 minutes default cache for social data

    # Market Data
    DEFAULT_EXCHANGE: str = "binance"
    REQUEST_TIMEOUT: float = 20.0

    # Security
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8787,http://127.0.0.1:8787"
    ADMIN_TOKEN: Optional[str] = None


settings = Settings()
