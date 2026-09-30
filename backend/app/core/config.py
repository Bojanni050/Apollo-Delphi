from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Apollo"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./apollo.db"

    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 25
    allowed_extensions: list[str] = [".pdf", ".docx", ".txt", ".md"]

    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    embedding_provider: str = "mock"
    embedding_model: str = "mock-embedder"
    embedding_dimensions: int = 64

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    github_token: str = Field(default="", validation_alias="APOLLO_GITHUB_TOKEN")

    chunk_size_chars: int = 1200
    chunk_overlap_chars: int = 150
    search_top_k: int = 8

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_upload_dir(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
