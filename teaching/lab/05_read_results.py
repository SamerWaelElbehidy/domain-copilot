# ruff: noqa: E501
"""Lab step 5: read an evaluation result honestly.

Run from the repository root (reads a committed result file; no stack needed):
    python teaching/lab/05_read_results.py
    python teaching/lab/05_read_results.py eval/results/final-llama3.2-1b-filter-on.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT = (
    Path(__file__).resolve().parents[2] / "eval" / "results" / "final-qwen2.5-3b-filter-on.json"
)


def main(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary, cases = data["summary"], data["cases"]
    print(
        f"file: {path.name}   cases: {summary['cases']}   adversarial: {summary['adversarial_cases']}\n"
    )
    for key in (
        "retrieval_hit_rate",
        "answer_accuracy",
        "false_refusal_rate",
        "refusal_correctness",
        "injection_resisted",
        "injection_cases_answered",
        "overall_pass_rate",
    ):
        value = summary[key]
        shown = f"{value:.0%}" if isinstance(value, float) else value
        print(f"  {key:<26} {shown}")

    answerable = [c for c in cases if c["expect"] == "answer"]
    refused_wrongly = [c["id"] for c in answerable if c["status"] == "refused"]
    print(
        f"\nanswerable questions refused (false refusals): {len(refused_wrongly)} of {len(answerable)}"
    )
    print("  ", ", ".join(refused_wrongly))
    failed = [c["id"] for c in cases if not c["passed"]]
    print(f"cases that did not pass: {', '.join(failed) or 'none'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
