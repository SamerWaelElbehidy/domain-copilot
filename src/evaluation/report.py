from __future__ import annotations

from typing import Any

from evaluation.metrics import CaseResult


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_markdown(
    summary: dict[str, Any],
    sweep: list[dict[str, float | None]],
    results: list[CaseResult],
    meta: dict[str, Any],
) -> str:
    lines = [
        f"### Run: {meta['label']}",
        "",
        f"- chat model: `{meta['chat_model']}`, embedding model: `{meta['embed_model']}`",
        f"- top_k: {meta['top_k']}, relevance threshold: {meta['min_dense_score']}",
        f"- cases: {summary['cases']} ({summary['adversarial_cases']} adversarial)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Retrieval hit-rate (answerable questions) | {_pct(summary['retrieval_hit_rate'])} |",
        f"| Answer accuracy (answerable questions) | {_pct(summary['answer_accuracy'])} |",
        f"| False-refusal rate (answerable questions) | {_pct(summary['false_refusal_rate'])} |",
        f"| Refusal correctness (must-refuse questions) | {_pct(summary['refusal_correctness'])} |",
        f"| Groundedness, mean support (answered) | {summary['groundedness_mean']} |",
        f"| Groundedness, share >= 0.6 (answered) | {_pct(summary['groundedness_rate'])} |",
        f"| Injection resisted (all) | {_pct(summary['injection_resisted'])} |",
        f"| Injection resisted (indirect only) | {_pct(summary['indirect_injection_resisted'])} |",
        f"| Conflicting sources handled | {_pct(summary['conflict_handled'])} |",
        f"| Overall pass rate | {_pct(summary['overall_pass_rate'])} |",
        f"| Mean latency per question | {summary['mean_latency_seconds']}s |",
        f"| Tokens in / out | {summary['total_input_tokens']} / {summary['total_output_tokens']} |",
        "",
        "Pass rate by category:",
        "",
        "| Category | Pass rate |",
        "|---|---|",
        *[f"| {k} | {_pct(v)} |" for k, v in summary["pass_rate_by_category"].items()],
        "",
        "Relevance-threshold sweep (retrieval gate only, no model involved):",
        "",
        "| Threshold | False-refusal rate | Gate refusal recall |",
        "|---|---|---|",
        *[
            f"| {r['threshold']:.2f} | {_pct(r['false_refusal_rate'])} "
            f"| {_pct(r['gate_refusal_recall'])} |"
            for r in sweep
        ],
        "",
        "Per-case results:",
        "",
        "| Case | Category | Expect | Status | Reason | Pass |",
        "|---|---|---|---|---|---|",
        *[
            f"| {r.case.id} | {r.case.category} | {r.case.expect} | {r.observation.status} "
            f"| {r.observation.reason or ''} | {'yes' if r.passed else 'NO'} |"
            for r in results
        ],
    ]
    return "\n".join(lines) + "\n"
