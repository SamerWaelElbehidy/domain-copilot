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
