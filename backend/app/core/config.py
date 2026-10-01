from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Apollo"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./apollo.db"
    # The same as APOLLO_DATABASE_URL in the environment, but also read from backend/.env (which the desktop app uses).
    apollo_database_url: str = ""

    upload_dir: str = "./uploads"
    workspaces_root: str = "./workspaces"
    max_upload_size_mb: int = 25
    # Comma separated (".pdf,.docx") or a JSON list.
    allowed_extensions: Annotated[list[str], NoDecode] = [".pdf", ".docx", ".txt", ".md"]

    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    embedding_provider: str = "mock"
    embedding_model: str = "mock-embedder"
    embedding_dimensions: int = 64
    # Dimensions above are only used by the mock provider; real models report theirs (and are
    # validated against it), so a model change never mixes incompatible vectors.
    # OpenAI-compatible /embeddings endpoint (hosted, Ollama, llama-server, Jina, ...). Empty = OpenAI.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    # Which local runtime manages embedding model downloads: "ollama" or "llamacpp".
    embedding_runtime: str = Field(default="ollama", pattern="^(ollama|llamacpp)$")
    # Where llama.cpp GGUF files are downloaded to (default ./models).
    llamacpp_models_dir: str = ""
    # Lets the setup wizard's folder picker list the server's folders (names only). Switch off on a shared host.
    folder_browse_enabled: bool = True
    # Where a llama-server can be reached from here; what "Kiezen" fills in as Base URL for a llama.cpp model.
    # In docker-compose that is the llama service, not localhost.
    llamacpp_base_url: str = "http://localhost:8080/v1"

    openai_api_key: str = ""
    # Base URL of an OpenAI-compatible endpoint; set for local runtimes, e.g. http://localhost:11434/v1 (Ollama).
    llm_base_url: str = ""
    # Model for bulk work (claim extraction, Delphi Pulse); empty = the main model.
    background_llm_model: str = ""
    llm_timeout_seconds: float = 120.0
    # Main tier key (any provider). Falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY.
    llm_api_key: str = ""
    # Background tier: each field left empty follows the main tier (see core.llm.tier_config).
    background_llm_provider: str = ""
    background_llm_base_url: str = ""
    background_llm_api_key: str = ""
    anthropic_api_key: str = ""
    github_token: str = Field(default="", validation_alias="APOLLO_GITHUB_TOKEN")

    chunk_size_chars: int = 1200
    chunk_overlap_chars: int = 150
    search_top_k: int = 8
    # Hybrid search: Reciprocal Rank Fusion constant, and how many candidates each leg fetches per wanted result.
    search_rrf_k: int = Field(default=60, ge=1, le=1000)
    search_candidate_multiplier: int = Field(default=5, ge=1, le=50)
    # Question answering: how many fragments are offered to the model as numbered sources.
    ask_top_k: int = Field(default=8, ge=1, le=30)
    # Follow-up questions: how many earlier question/answer pairs of the conversation are given as context.
    ask_history_turns: int = Field(default=3, ge=1, le=10)

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _split_extensions(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [part.strip() for part in v.split(",") if part.strip()]
        return v

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def effective_llamacpp_models_dir(self) -> str:
        return self.llamacpp_models_dir or str(Path("./models").resolve())

    def ensure_upload_dir(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
