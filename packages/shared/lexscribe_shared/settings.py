"""Process-wide settings loaded from env vars (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config. Override via ``LEXSCRIBE_*`` env vars."""

    model_config = SettingsConfigDict(
        env_prefix="LEXSCRIBE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service
    env: str = "dev"
    service_name: str = "lexscribe"
    service_version: str = "0.1.0"
    log_level: str = "INFO"

    # Storage
    database_url: str = "postgresql+psycopg://lex:lex@localhost:5432/lexscribe"
    redis_url: str = "redis://localhost:6379/0"

    # Object store
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "lexscribe"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"
    s3_region: str = "us-east-1"

    # Providers — interface-only; FakeProvider is used when keys are blank.
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    generation_model: str = "claude-sonnet-4-7"
    rerank_model: str = "rerank-english-v3.0"

    # Worker caps
    parse_concurrency: int = 4
    embed_concurrency: int = 8
    classify_concurrency: int = 2

    # OTel
    otlp_endpoint: str = "http://localhost:4317"
    otel_enabled: bool = False

    # Costs (USD per 1K tokens, used for cost accounting)
    cost_in_per_1k: float = 0.003
    cost_out_per_1k: float = 0.015
    cost_embed_per_1k: float = Field(default=0.00002)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
