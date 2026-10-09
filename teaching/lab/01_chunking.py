"""Lab step 1: chunking is a safety decision.

Run from the repository root:
    python teaching/lab/01_chunking.py            # how the system chunks the router manual
    python teaching/lab/01_chunking.py --fixed 400  # what naive fixed-size windows would do
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from application.use_cases.ingest_document import ingest_markdown_document  # noqa: E402
from application.use_cases.ingestion.extract_markdown import extract_markdown_document  # noqa: E402

MANUAL = ROOT / "corpus" / "cnc-wood-router-dwr2200" / "manual-rev-c.md"
NEEDLE = "dust extraction hose connection"
QUALIFIER = "green zone"


def structure_aware() -> None:
    chunks = ingest_markdown_document(MANUAL.read_text(encoding="utf-8"))
    print(
        "chunks per section type:",
        dict(sorted(Counter(c.section_type.value for c in chunks).items())),
    )
    hose = [c for c in chunks if NEEDLE in c.content]
    print(f"\nchunks that mention '{NEEDLE}': {len(hose)}")
    for chunk in hose:
        print(f"  - {chunk.section_title} | {chunk.source_ref}")
        print(f"    contains '{QUALIFIER}': {QUALIFIER in chunk.content}")


def fixed_windows(size: int) -> None:
    body = extract_markdown_document(MANUAL.read_text(encoding="utf-8")).body
    windows = [body[i : i + size] for i in range(0, len(body), size)]
    print(f"fixed windows of {size} characters: {len(windows)} windows")
    with_needle = [i for i, w in enumerate(windows) if NEEDLE in w]
    with_qualifier = [i for i, w in enumerate(windows) if QUALIFIER in w]
    print(f"windows mentioning '{NEEDLE}': {with_needle or 'none (it was cut across a boundary)'}")
    print(f"windows mentioning '{QUALIFIER}': {with_qualifier or 'none'}")
    together = set(with_needle) & set(with_qualifier)
    print(f"safety step and its qualifier in the SAME window: {bool(together)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixed", type=int, default=0, help="use fixed-size windows of N characters"
    )
    args = parser.parse_args()
    fixed_windows(args.fixed) if args.fixed else structure_aware()
