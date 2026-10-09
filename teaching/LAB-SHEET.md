# Lab sheet: RAG beyond the demo

**Time:** about 25 minutes in class (steps 1 to 5), stretch challenges as homework.
**You need:** the repository, Python 3.11, and for steps 2 and 4 the stack running (`docker compose up`, see the README). Steps 1, 3 and 5 need no stack, so nobody is blocked.
**Work from the repository root.** Each step says what to run, what you should see, and one thing to answer. Show the instructor your answer to each check.

```bash
git clone https://github.com/SamerWaelElbehidy/domain-copilot.git && cd domain-copilot
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

---

## Step 1 (5 min): chunking is a safety decision

Run the system's own chunking on the CNC router manual, then a naive fixed-window split of the same text.

```bash
python teaching/lab/01_chunking.py
python teaching/lab/01_chunking.py --fixed 400
```

**Expected.** The first command reports seven `safety_prerequisite` chunks and exactly one chunk mentioning `dust extraction hose connection`, and that chunk contains `green zone: True`.
The second reports the step in one window and `green zone` in the next, and `safety step and its qualifier in the SAME window: False`.

**Explore.** Try `--fixed 200`, `300`, `500`, `600`, `800`. Which sizes keep the step and its qualifier together?

> **Check 1.** In one sentence: what would a technician be told if retrieval returned only the window containing the step, and why would nobody notice?

---

## Step 2 (5 min): dense, keyword and fused retrieval

This runs against the real embedding model and database (stack running). It searches only **current** manual revisions, as the product does.

```bash
python teaching/lab/02_retrieval.py "DWR-2200 spindle overheating"
python teaching/lab/02_retrieval.py "the machine gets too hot when running for hours"
```

**Expected.** Three lists per query: dense (meaning), keyword (words), and the fused list built from **ranks only**. The router's diagnostic item about spindle overheating appears at or near the top of the fused list for both.
Your exact scores will differ a little with the model.

**Explore.** Write two queries of your own: one that uses an identifier (a model number or a code) and one that describes the fault in your own words.

> **Check 2.** Show a query where the dense and keyword lists disagree. Which one was right, and what did fusion do?

---

## Step 3 (5 min): the injection scan is one layer, not a wall

```bash
python teaching/lab/03_injection_scan.py
python teaching/lab/03_injection_scan.py "your own payload text"
```

**Expected.**

```
benign manual step     -> passes the scan
benign policy text     -> passes the scan
classic override       -> FLAGGED (1 pattern)
addressed to the AI    -> FLAGGED (2 patterns)
polite and indirect    -> passes the scan
```

**Explore.** Write a payload that tries to make an assistant say "APPROVED" and that passes the scan. It should be easy.

> **Check 3.** Your payload passed. List the *other* layers in the system that would still limit the damage, and say which layer you think is the real control.

---

## Step 4 (7 min): ask through the API

With the stack running and the demo accounts seeded:

```bash
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"technician1","password":"demo-password-change-me"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s localhost:8000/ask -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"Below what temperature must the edge banding glue pot be before cleaning or contact?"}'

curl -s localhost:8000/ask -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"What is the capital of France?"}'
```

**Expected.** The first returns `"status":"answered"`, a one-sentence answer that restates the fact with its unit, and a `citations` list whose `document_id` is a current manual.
The second returns `"status":"refused"` with a `reason`, and comes back in about a second because the model was not called.

**Explore.** Ask one question the manuals answer, one they do not, and one that is ambiguous ("How long should I wait before opening the door?"). Read the `reason` field on each refusal.

> **Check 4.** Show one answered question with its citation and one refusal with its reason. For the refusal, say which guard fired.

---

## Step 5 (6 min): read an evaluation honestly

No stack needed. These are the recorded results for two models.

```bash
python teaching/lab/05_read_results.py
python teaching/lab/05_read_results.py eval/results/final-llama3.2-1b-filter-on.json
```

**Expected.** The 3B model: 100% retrieval hit-rate, 73% answer accuracy, 23% false refusals, 100% refusal correctness, 100% injection resisted (2 injection cases actually answered).
The 1B model: 55% accuracy and 32% false refusals. Both lists name the false refusals and the cases that did not pass.

> **Check 5.** From the 3B result: choose two false refusals (for example `Q02` and `Q06`), read their entries in `eval/results/final-qwen2.5-3b-filter-on.md`, and propose a cause for each. Then name the number in the table you trust least and say why.

---

## Stretch challenges (homework)

1. **Add a golden case.** Write a question the current system gets wrong (or that you predict it will), add it to `eval/golden_set.json`, run the evaluation on the full stack, and explain the result. Say whether writing the case *after* seeing the failure makes it a fair test.
2. **Sweep the threshold.** Run the evaluation with `--min-dense-score` at 0.70, 0.73, 0.75 and 0.80. Plot false-refusal rate against refusal correctness and argue for a value. What would you do so the choice is not made on the same questions you report?
3. **Beat the scan, then fix it.** Take your payload from step 3. Add a detection pattern to `src/application/use_cases/injection_scan.py` that catches it, and write a test showing the two benign lines from step 3 still pass. Then write down what your fix does *not* stop.
4. **Tamper with a run and replay it.** Complete one workflow run in the UI (technician, then supervisor). Replay it with `docker compose exec app python scripts/replay.py <run-id>`. Try to edit a step with a plain `UPDATE`, then bypass the protection and edit it, and replay again. Explain which layer stopped each attempt and what neither layer can stop.

The answer key (instructors only) is [`ANSWER-KEY.md`](ANSWER-KEY.md).
