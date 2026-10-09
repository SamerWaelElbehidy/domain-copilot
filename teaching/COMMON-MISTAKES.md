# Common trainee mistakes: five misconceptions and how to correct each

Session: *RAG beyond the demo*. Each correction points at something the trainee can run, because a claim they reproduced sticks and one they were told does not.

**1. "If the answer has citations, it is grounded."**
*Truth:* a citation says where the model claims to have looked, not that the answer follows from it. An early version of this project scored 64% accuracy with mean groundedness 0.08: answers like "1" and "Paris", each with a real citation.
*Correct it:* ask how a fluent, cited, wrong answer passes their pipeline; then show the support check (the answer's own words must appear in the cited text) and lab step 5.
*Listen for:* "we check the citation exists". Existing is not supporting.

**2. "Retrieving more chunks is always safer."**
*Truth:* extra chunks add noise and cost, and give a stale or injected passage more chances to reach the prompt. Here, hit-rate was already 100% at top 5; the failures were in the answer step.
*Correct it:* lab step 2 with their own queries; have them count how often the relevant chunk is outside the top 3, then ask which failure raising `top_k` would fix.
*Listen for:* "just raise top_k".

**3. "A good accuracy number means it works."**
*Truth:* the number is only as honest as its metric and question set. Lenient scoring flatters, a set without out-of-corpus or adversarial cases hides the dangerous failures, and tuning on the reported questions makes it optimistic. "Injection resisted 100%" is empty if the system refuses everything.
*Correct it:* give them two result files (lab step 5): which number is most flattering, which most worrying?
*Listen for:* one figure quoted without how it was measured.

**4. "Telling the model to ignore instructions in documents solves prompt injection."**
*Truth:* it is one layer, and models can be talked out of it. The defence is separation of data from instructions, quarantine, support checks, control over who adds documents, and a human before anything consequential. Each layer can fail.
*Correct it:* have them write a payload that evades their own defence (lab step 3), then list which other layers still stop it.
*Listen for:* "we added a line to the prompt".

**5. "The model can check its own safety work" and "approval is a button."**
*Truth:* anything the model can skip is a suggestion. Here the checklist is copied by code, dispatch needs a signed token bound to one work order, agents are never told the tool exists, and a UI dialog can be bypassed by calling the API.
*Correct it:* ask, "if the model returned an empty checklist, what happens?" Then show the domain rule and the database constraint that refuse it.
*Listen for:* "we ask the model to double-check".

**Use:** show the five statements (slide 22) without the corrections and ask for a show of hands on which they believed last week. That admission is the teaching moment.
