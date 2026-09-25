from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Externalised configuration (brief section 4). Everything comes from
    environment variables; .env.example lists them all."""

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int
    qdrant_url: str
    qdrant_collection: str
    embedding_dim: int
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    relevance_threshold: float
    llm_provider_chain: tuple[str, ...] = ("ollama",)
    embedding_provider: str = "ollama"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 120.0
    llm_failure_threshold: int = 3
    llm_max_output_tokens: int = 1024
    llm_cooldown_seconds: float = 30.0

    @staticmethod
    def from_env() -> Settings:
        env = os.environ.get
        return Settings(
            postgres_user=env("POSTGRES_USER", "domain_copilot"),
            postgres_password=env("POSTGRES_PASSWORD", "domain_copilot_dev"),
            postgres_db=env("POSTGRES_DB", "domain_copilot"),
            postgres_host=env("POSTGRES_HOST", "localhost"),
            postgres_port=int(env("POSTGRES_PORT", "5433")),
            qdrant_url=env("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=env("QDRANT_COLLECTION", "chunks"),
            embedding_dim=int(env("EMBEDDING_DIM", "768")),
            ollama_base_url=env("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_chat_model=env("OLLAMA_CHAT_MODEL", "qwen2.5:3b"),
            ollama_embed_model=env("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            # Calibrated for nomic-embed-text cosine scores on the golden set
            # (docs/EVALUATION.md); recalibrate if the embedding model changes.
            relevance_threshold=float(env("RELEVANCE_THRESHOLD", "0.73")),
            llm_provider_chain=tuple(
                n.strip() for n in env("LLM_PROVIDER_CHAIN", "ollama").split(",") if n.strip()
            ),
            embedding_provider=env("EMBEDDING_PROVIDER", "ollama"),
            openai_api_key=env("OPENAI_API_KEY", ""),
            openai_base_url=env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_chat_model=env("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            llm_timeout_seconds=float(env("LLM_TIMEOUT_SECONDS", "120")),
            llm_failure_threshold=int(env("LLM_FAILURE_THRESHOLD", "3")),
            llm_max_output_tokens=int(env("LLM_MAX_OUTPUT_TOKENS", "1024")),
            llm_cooldown_seconds=float(env("LLM_COOLDOWN_SECONDS", "30")),
        )
