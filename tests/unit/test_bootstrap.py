"""The container entrypoint's environment handling. It once mis-read an empty
SEED_DEMO_USERS (what compose passes for an unset variable) as "false" and the
demo accounts silently did not exist."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.py"
spec = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.mark.parametrize(
    "value,default,expected",
    [
        (None, True, True),
        (None, False, False),
        ("", True, True),  # compose passes unset variables as empty strings
        ("", False, False),
        ("   ", True, True),
        ("true", False, True),
        ("TRUE", False, True),
        ("false", True, False),
        ("no", True, False),
    ],
)
def test_flags_treat_unset_and_empty_as_the_default(monkeypatch, value, default, expected):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    if value is not None:
        monkeypatch.setenv("SOME_FLAG", value)

    assert bootstrap.flag("SOME_FLAG", default=default) is expected


@pytest.mark.parametrize(
    "mode,ingested,expected,seeds",
    [
        ("true", 0, 30, True),  # a fresh database
        ("true", 12, 30, True),  # partly ingested
        ("true", 30, 30, False),  # restarting must not re-embed everything
        ("true", 31, 30, False),  # extra uploaded documents do not trigger a re-seed
        ("force", 30, 30, True),
        ("false", 0, 30, False),
    ],
)
def test_the_corpus_is_seeded_only_when_it_is_not_already_ingested(mode, ingested, expected, seeds):
    assert bootstrap.needs_corpus_seed(mode, ingested, expected) is seeds
