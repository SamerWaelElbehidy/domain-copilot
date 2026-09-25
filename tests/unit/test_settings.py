import asyncio

import pytest

from application.llm_recording import RecordingLLMProvider
from application.ports.llm_provider import CompletionResult
from config.settings import Settings
from tests.fakes.fake_llm_provider import FakeLLMProvider
from tests.fakes.in_memory import InMemoryLLMCallRepository


def test_prices_parse_from_json_per_thousand_tokens():
    prices = Settings.parse_prices('{"gpt-4o-mini": [0.00015, 0.0006], "other": [1, 2]}')

    assert prices == {"gpt-4o-mini": (0.00015, 0.0006), "other": (1.0, 2.0)}


def test_no_prices_means_an_empty_map_and_zero_cost():
    assert Settings.parse_prices("") == {} and Settings.parse_prices("  ") == {}


@pytest.mark.parametrize(
    "bad", ["not json", "[1, 2]", '{"m": 5}', '{"m": ["x", "y"]}', '{"m": [1]}']
)
def test_a_malformed_price_map_is_a_startup_error_not_silent_zero_cost(bad):
    with pytest.raises(ValueError, match="LLM_PRICES"):
        Settings.parse_prices(bad)


def test_configured_prices_turn_recorded_tokens_into_cost():
    repository = InMemoryLLMCallRepository()
    inner = FakeLLMProvider(
        responses=[
            CompletionResult(
                content="x", input_tokens=2000, output_tokens=500, model="gpt-4o-mini"
            )
        ]
    )
    prices = Settings.parse_prices('{"gpt-4o-mini": [0.00015, 0.0006]}')
    llm = RecordingLLMProvider(inner, repository, provider_name="openai", prices=prices)

    asyncio.run(llm.complete([]))

    (call,) = repository.calls
    assert call.cost_usd == round(2 * 0.00015 + 0.5 * 0.0006, 6)
    assert call.provider == "openai"
