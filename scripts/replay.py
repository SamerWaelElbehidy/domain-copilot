"""T4 replay command: plays back a recorded run from its persisted steps.

Usage: python scripts/replay.py <run-id> [--json]

Reads only the audit log. It never calls an LLM, the vector store or a tool,
so the output is identical every time it is run. The hash chain is verified
first; a run whose log was edited is refused.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.use_cases.replay_run import replay_run  # noqa: E402
from domain.errors.domain_errors import TamperedRunError  # noqa: E402
from infrastructure.persistence.postgres_pool import create_pool  # noqa: E402
from infrastructure.persistence.postgres_run_repository import PostgresRunRepository  # noqa: E402


async def main(run_id: str, as_json: bool) -> int:
    pool = await create_pool()
    try:
        run = await PostgresRunRepository(pool).get(run_id)
    finally:
        await pool.close()
    if run is None:
        print(f"no such run: {run_id}", file=sys.stderr)
        return 2
    try:
        frames = list(replay_run(run))
    except TamperedRunError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    if as_json:
        print(json.dumps([dataclasses.asdict(f) for f in frames], indent=2, sort_keys=True))
        return 0

    print(f"run {run.run_id}  state={run.state.value}  equipment={run.equipment_id}")
    print(f"audit chain: verified ({len(frames)} steps)\n")
    for frame in frames:
        who = frame.agent_name or "system"
        print(f"[{frame.step_index}] {frame.name:22} {frame.status:8} by {who}"
              f"  tokens in/out {frame.input_tokens}/{frame.output_tokens}")
        for call in frame.output_snapshot.get("tool_trace", []):
            print(f"      tool {call['tool']}({json.dumps(call['arguments'])})")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(64)
    sys.exit(asyncio.run(main(args[0], "--json" in sys.argv)))
