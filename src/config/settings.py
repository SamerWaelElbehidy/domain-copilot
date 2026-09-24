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
            ollama_chat_model=env("OLLAMA_CHAT_MODEL", "llama3.2:1b"),
            ollama_embed_model=env("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        )
