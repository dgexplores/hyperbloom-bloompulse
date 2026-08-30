"""Typed config — FREE-FIRST, offline by default."""
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0-pulse"
    secret_key: str = "change-me-pulse"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"
    redis_url: str = "redis://localhost:6379/0"
    embedding_provider: Literal["openai", "local"] = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    llm_provider: Literal["offline", "ollama", "hf", "openai"] = "offline"
    llm_model: str = "offline-extractive"
    ollama_url: str = "http://localhost:11434"
    openai_api_key: str = ""
    hf_api_key: str = ""
    vector_store: Literal["pgvector", "memory"] = "memory"
    confidence_threshold: float = 0.70
    retrieve_top_k: int = 20
    rerank_top_k: int = 8
    @property
    def is_prod(self): return self.app_env == "production"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
