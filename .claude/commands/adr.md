---
description: Draft an Architecture Decision Record from a decision just made
argument-hint: <short title of the decision>
---

Draft `docs/adr/NNNN-<slug>.md` for this decision: $ARGUMENTS

1. Find the next number: `ls docs/adr`.
2. Read two existing ADRs (for example 0005 and 0007) and follow their structure: Status, Context, Decision, Consequences, Alternatives considered.
3. Context must name the requirement or failure that forced the decision. Decision must be specific enough to test. Alternatives must say **why each was rejected**, not just list them.
4. Be candid in Consequences about what the decision costs and what it does not solve.
5. Add the ADR to the table in `docs/ARCHITECTURE.md` (section 10) and, if it changes scope, to the gap table in `docs/SYSTEM-DESIGN.md`.

Do not edit an accepted ADR to change history; if a decision is reversed, write a new ADR that supersedes it.
