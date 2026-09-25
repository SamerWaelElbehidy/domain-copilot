"""Container entrypoint: wait for dependencies, migrate, seed, then serve.

Everything here is idempotent, so restarting the container is always safe.
Seeding demo users and the sample corpus is what makes `docker compose up`
a working demo with no manual steps (README, 5-minute path).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def wait_for(name: str, check, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if check():
                log(f"{name} is ready")
                return True
        except Exception:  # noqa: BLE001 - any failure just means "not yet"
            pass
        time.sleep(2)
    log(f"{name} was not ready after {seconds}s")
    return False


def postgres_ready() -> bool:
    import asyncio

    import asyncpg

    async def probe() -> bool:
        conn = await asyncpg.connect(
            user=os.environ.get("POSTGRES_USER", "domain_copilot"),
            password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
            database=os.environ.get("POSTGRES_DB", "domain_copilot"),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5433")),
            timeout=3,
        )
        await conn.close()
        return True

    return asyncio.run(probe())


def embed_model_ready() -> bool:
    import json

    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    wanted = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as response:
        names = [m["name"] for m in json.load(response).get("models", [])]
    return any(n == wanted or n.startswith(wanted + ":") for n in names)


def flag(name: str, default: bool) -> bool:
    """A boolean setting from the environment. Unset or empty means the default,
    because compose passes unset variables through as empty strings, and an empty
    string must never turn a default-on setting off (or a default-off one on)."""
    value = (os.environ.get(name) or "").strip().lower()
    return default if not value else value == "true"


def ingested_documents() -> int:
    import asyncio

    import asyncpg

    async def count() -> int:
        conn = await asyncpg.connect(
            user=os.environ.get("POSTGRES_USER", "domain_copilot"),
            password=os.environ.get("POSTGRES_PASSWORD", "domain_copilot_dev"),
            database=os.environ.get("POSTGRES_DB", "domain_copilot"),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5433")),
        )
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM manual_documents WHERE ingestion_status = 'ingested'"
            )
        finally:
            await conn.close()

    return asyncio.run(count())


def needs_corpus_seed(mode: str, ingested: int, expected: int) -> bool:
    """`SEED_CORPUS`: `true` (default) seeds only when the bundled corpus is not
    fully ingested yet, so restarting a container does not re-embed everything;
    `force` always re-ingests; `false` never does."""
    if mode == "false":
        return False
    return mode == "force" or ingested < expected


def run_script(name: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / name)], check=False).returncode


def main() -> None:
    if not wait_for("postgres", postgres_ready, 90):
        sys.exit("postgres never became ready")
    if run_script("migrate.py") != 0:
        sys.exit("migrations failed")

    development = os.environ.get("APP_ENV", "development") == "development"
    # Default: demo accounts only in development, so a production start never
    # creates accounts with a published password.
    if flag("SEED_DEMO_USERS", default=development):
        run_script("seed_users.py")

    expected = len(list((ROOT / "corpus").rglob("*.md")))
    mode = (os.environ.get("SEED_CORPUS") or "true").strip().lower()
    if not needs_corpus_seed(mode, ingested_documents(), expected):
        log("corpus already ingested (set SEED_CORPUS=force to re-ingest)")
    else:
        # The corpus has to be embedded, so wait for the embedding model. A
        # failure here is logged, not fatal: /ready will show the state and the
        # corpus can be ingested later from the admin page.
        if wait_for("embedding model", embed_model_ready, 900):
            if run_script("seed.py") != 0:
                log("corpus seeding reported failures; see output above")
        else:
            log("skipping corpus seed; upload documents from the admin page later")

    log("starting the API")
    os.execvp(
        "uvicorn",
        [
            "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000",
            "--proxy-headers", "--no-server-header",
        ],
    )


if __name__ == "__main__":
    main()
