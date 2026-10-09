# Learning outcomes and assessment map

**Session:** *RAG beyond the demo: building an assistant that knows when to refuse* (90 minutes, post-graduate)
**Audience:** graduates who can build a basic RAG pipeline and want to make one trustworthy.
**Prerequisites:** Python reading skills, Git, a terminal, Docker installed. No prior LLM security or evaluation experience.

## Outcomes, where they are taught, and how they are assessed

Levels use Bloom's taxonomy. Every outcome has at least one taught moment, one hands-on task and one assessed item, so nothing is assessed that was not practised.

| # | By the end, the trainee can... | Level | Taught in (slides) | Practised in (lab) | Assessed by |
|---|---|---|---|---|---|
| LO1 | Explain why chunking is a safety decision and choose a strategy for a structured corpus | Analyse, Evaluate | 5 to 7 | Step 1 | Quiz Q1, Q2; lab check 1 |
| LO2 | Explain hybrid retrieval and Reciprocal Rank Fusion, and predict when dense or keyword retrieval fails | Understand, Apply | 8 to 10 | Step 2 | Quiz Q3, Q4; lab check 2 |
| LO3 | Design guards that let a RAG system refuse: relevance threshold, citation mapping, support check | Apply, Create | 11 to 14 | Step 4 | Quiz Q5, Q6; lab check 4 |
| LO4 | Distinguish direct from indirect prompt injection and defend in layers, stating each layer's limit | Analyse | 15, 16 | Step 3 | Quiz Q7, Q8; lab check 3 |
| LO5 | Read an evaluation honestly: adversarial cases, lenient metrics, false refusals, tuning on the test set | Evaluate | 17, 18 | Step 5 | Quiz Q9, Q10; lab check 5 |
| LO6 | Explain why human approval and safety checks must be structural, and audit a run | Understand, Analyse | 19, 20 | Stretch 4 | Quiz Q11; stretch check |

## Assessment instruments

### A. Lab checks (formative, during the session)

Each is a single observable result the instructor can verify at the trainee's terminal in under a minute. The answer key has the expected output.

| Check | The trainee shows... | Outcome |
|---|---|---|
| 1 | The output of `01_chunking.py --fixed 400` and explains in one sentence what went wrong for the technician | LO1 |
| 2 | A query of their own where dense and keyword lists disagree, and which one the fused list favoured | LO2 |
| 3 | A payload that passes the scan, plus the list of other layers that would still stop it | LO4 |
| 4 | An answered question with its citations and a refused question with its reason, from the API | LO3 |
| 5 | The list of false refusals from the 3B result file and a proposed cause for two of them | LO5 |

### B. Quiz (summative, 10 minutes, 11 questions, closed book)

| Q | Question | Outcome | Marks |
|---|---|---|---|
| 1 | A manual step says "check the hose is seated and the gauge reads in the green zone". Fixed 400-character windows separate the two halves. Describe what the technician is told and why nobody notices. | LO1 | 2 |
| 2 | Name a unit of meaning that must never be split in (a) this corpus, (b) a contract, (c) a case-law database. | LO1 | 3 |
| 3 | Give one query that dense retrieval handles better than keyword, and one for the reverse. | LO2 | 2 |
| 4 | Two chunks: A is rank 1 in dense and absent from keyword; B is rank 3 in both. With RRF, k = 60, which ranks higher? Show the arithmetic. | LO2 | 2 |
| 5 | Why does the answer prompt ask for excerpt numbers rather than chunk ids? | LO3 | 2 |
| 6 | A top dense score is below the threshold. What happens next and why is the model not called? | LO3 | 2 |
| 7 | Explain indirect prompt injection and why it is a bigger risk for a knowledge-base assistant than a direct attack. | LO4 | 2 |
| 8 | Name three layers of defence used in the repository and one way each can fail. | LO4 | 3 |
| 9 | Accuracy is 64% but mean groundedness is 0.08. What do you suspect and what do you do first? | LO5 | 2 |
| 10 | Why must "injection resisted: 100%" be reported next to "injection cases actually answered"? | LO5 | 2 |
| 11 | Give two reasons a confirmation dialog is not an approval control, and one mechanism that is. | LO6 | 2 |

**Total 24 marks.** Pass at 16. Rubric: full marks need the mechanism and its consequence; half marks for a correct statement without the reason.
The answer key for the quiz is in [`ANSWER-KEY.md`](ANSWER-KEY.md).

### C. Stretch challenges (extension, unmarked or bonus)

Four, in the lab sheet. They assess LO3 to LO6 at the Create level.

## Alignment check

Every outcome appears in the slides, the lab and the assessment. Outcomes deliberately **not** assessed: operating Docker, reading FastAPI code, and any specific model's behaviour (models change; the reasoning does not).

## Suggested timing

| Minutes | Activity | Outcomes |
|---|---|---|
| 0 to 10 | Failure scenario, outcomes, the demo-versus-system table (slides 1 to 4) | all |
| 10 to 25 | Pipeline, chunking, retrieval, fusion (slides 5 to 10) | LO1, LO2 |
| 25 to 37 | Grounding, refusal, citation versus support, live demo (slides 11 to 14) | LO3 |
| 37 to 45 | Injection and defence in depth (slides 15, 16) | LO4 |
| 45 to 55 | Evaluation, the human gate, audit and replay (slides 17 to 20) | LO5, LO6 |
| 55 to 82 | Lab steps 1 to 5 (about 4, 5, 5, 7 and 6 minutes), instructor circulating (slide 21) | LO1 to LO5 |
| 82 to 90 | Misconceptions, recap, quiz handed out for homework (slides 22 to 24) | all |

The 10-minute teaching video delivers the slice from slides 6 to 9 and lab step 1.
