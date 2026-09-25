"""The dependency rule as an executable test (ADR-0001).

The brief's acceptance test for Clean Architecture: swapping the LLM provider,
embedding model or vector store must need configuration plus one adapter, never
a change to business logic. That is only true while the inner layers import none
of the outer layers or any vendor SDK, so this test fails the build the moment
one does."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
STDLIB = set(__import__("sys").stdlib_module_names)

# Third-party packages the inner layers may never touch: web frameworks,
# HTTP clients, database and vector-store drivers, model SDKs, crypto/JWT.
VENDOR = {
    "fastapi", "starlette", "uvicorn", "httpx", "requests", "aiohttp", "asyncpg", "psycopg",
    "sqlalchemy", "qdrant_client", "openai", "anthropic", "ollama", "pypdf", "jwt", "pydantic",
}
LAYERS = {
    "domain": {"application", "infrastructure", "api", "config"},
    "application": {"infrastructure", "api"},
    "infrastructure": {"api"},
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def violations(layer: str) -> list[str]:
    problems = []
    for path in sorted((SRC / layer).rglob("*.py")):
        for module in imported_modules(path):
            if module in LAYERS[layer]:
                problems.append(f"{path.relative_to(SRC)} imports the outer layer '{module}'")
            if layer in ("domain", "application") and module in VENDOR:
                problems.append(f"{path.relative_to(SRC)} imports vendor package '{module}'")
    return problems


def test_domain_depends_on_nothing_but_the_standard_library():
    problems = violations("domain")
    third_party = [
        f"{path.relative_to(SRC)} imports '{module}'"
        for path in (SRC / "domain").rglob("*.py")
        for module in imported_modules(path)
        if module not in STDLIB and module != "domain"
    ]

    assert not problems and not third_party, problems + third_party


def test_application_does_not_import_infrastructure_api_or_any_vendor_sdk():
    assert violations("application") == []


def test_infrastructure_does_not_import_the_api_layer():
    assert violations("infrastructure") == []


def test_the_only_place_that_names_concrete_adapters_is_the_composition_root():
    """Routes depend on ports and use cases. Only api/main.py (the composition
    root) and infrastructure itself may import an adapter."""
    offenders = []
    for path in sorted((SRC / "api").rglob("*.py")):
        if path.name == "main.py":
            continue
        if any(m == "infrastructure" for m in imported_modules(path)):
            offenders.append(str(path.relative_to(SRC)))

    assert offenders == []
