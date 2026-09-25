---
description: Run the golden-set evaluation and compare it with the recorded baseline
argument-hint: <label for this run>
---

Run the evaluation and report what changed. Requires the full stack (`docker compose up -d`, models pulled).

1. `python scripts/evaluate.py --label $ARGUMENTS --chat-model qwen2.5:3b`
2. Compare `eval/results/$ARGUMENTS.json` with the baseline in `docs/EVALUATION.md` section 2 (`eval/results/after-conflict-guard-qwen2.5-3b.json` is the latest).
3. Report every metric that moved, **including the ones that got worse**: retrieval hit-rate, answer accuracy, false-refusal rate, refusal correctness, groundedness, injection resisted and injection cases actually answered, conflicting sources handled.
4. List each case whose result flipped, with its id and the reason.
5. Do not tune the relevance threshold or a prompt against these same questions and then report the result as a fresh measurement. If a change was tuned on the golden set, say so.

If numbers changed, update `docs/EVALUATION.md` with the run label, the table and the interpretation.
