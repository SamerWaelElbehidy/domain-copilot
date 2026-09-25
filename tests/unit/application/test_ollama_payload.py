from application.ports.llm_provider import Message
from infrastructure.llm.ollama_provider import OllamaProvider


def test_requests_are_deterministic_by_default():
    payload = OllamaProvider()._build_chat_payload([Message("user", "hi")], None, stream=False)

    assert payload["options"] == {"temperature": 0.0, "seed": 42}


def test_temperature_and_seed_are_configurable():
    provider = OllamaProvider(temperature=0.7, seed=None)

    assert provider._build_chat_payload([Message("user", "hi")], None, False)["options"] == {
        "temperature": 0.7
    }
