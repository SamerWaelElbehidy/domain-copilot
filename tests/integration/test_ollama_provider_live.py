import asyncio

import httpx
import pytest

from application.ports.llm_provider import Message
from infrastructure.llm.ollama_provider import OllamaProvider


def _ollama_available() -> bool:
    try:
        httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_available(), reason="Ollama server not reachable at localhost:11434"
)


@requires_ollama
def test_embed_returns_real_vectors_from_local_model():
    provider = OllamaProvider(embed_model="nomic-embed-text")

    vectors = asyncio.run(provider.embed(["dust extraction safety check"]))

    assert len(vectors) == 1
    assert len(vectors[0]) > 0
    assert all(isinstance(v, float) for v in vectors[0])


@requires_ollama
def test_complete_returns_a_real_response_from_local_model():
    provider = OllamaProvider(chat_model="llama3.2:1b")
    messages = [Message(role="user", content="Reply with exactly the word: PONG")]

    result = asyncio.run(provider.complete(messages))

    assert result.content.strip() != ""
    assert result.output_tokens > 0
