from __future__ import annotations

from application.llm_fallback import FallbackLLMProvider
from application.llm_recording import RecordingLLMProvider
from application.ports.llm_call_repository import LLMCallRepository
from application.ports.llm_provider import LLMProvider
from config.settings import Settings
from infrastructure.llm.ollama_provider import OllamaProvider
from infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider


def build_llm(settings: Settings, llm_calls: LLMCallRepository) -> FallbackLLMProvider:
    """Builds the configured provider chain (`LLM_PROVIDER_CHAIN`, first is
    preferred). Every provider is wrapped in its own recorder, so each attempt
    (including a failed one that triggered a failover) is accounted under the
    provider that made it. Misconfiguration fails at startup, not on the first
    request."""
    providers: list[tuple[str, LLMProvider]] = []
    for name in settings.llm_provider_chain:
        inner: LLMProvider
        if name == "ollama":
            inner = OllamaProvider(
                base_url=settings.ollama_base_url,
                chat_model=settings.ollama_chat_model,
                embed_model=settings.ollama_embed_model,
                timeout_seconds=settings.llm_timeout_seconds,
                max_output_tokens=settings.llm_max_output_tokens,
            )
        elif name == "openai":
            if not settings.openai_api_key:
                raise RuntimeError(
                    "LLM_PROVIDER_CHAIN includes 'openai' but OPENAI_API_KEY is empty"
                )
            inner = OpenAICompatibleProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                chat_model=settings.openai_chat_model,
                embed_dimensions=settings.embedding_dim,
                timeout_seconds=settings.llm_timeout_seconds,
                max_output_tokens=settings.llm_max_output_tokens,
            )
        else:
            raise RuntimeError(f"unknown provider '{name}' in LLM_PROVIDER_CHAIN")
        providers.append((name, RecordingLLMProvider(
                inner, llm_calls, provider_name=name, prices=settings.llm_prices
            )))
    return FallbackLLMProvider(
        providers,
        embedding_provider=settings.embedding_provider,
        failure_threshold=settings.llm_failure_threshold,
        cooldown_seconds=settings.llm_cooldown_seconds,
    )
