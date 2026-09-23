from enum import Enum


class RunState(str, Enum):
    RECEIVED = "received"
    MATCHING_SYMPTOM = "matching_symptom"
    DIAGNOSING = "diagnosing"
    DRAFTING_WORK_ORDER = "drafting_work_order"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPATCHED = "dispatched"
    REFUSED_LOW_EVIDENCE = "refused_low_evidence"
    DEGRADED_PLAIN_RAG = "degraded_plain_rag"
    FAILED = "failed"


# Fixed adjacency table (ADR-0005). Empty set = terminal state.
ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.RECEIVED: frozenset(
        {RunState.MATCHING_SYMPTOM, RunState.REFUSED_LOW_EVIDENCE}
    ),
    RunState.MATCHING_SYMPTOM: frozenset(
        {RunState.DIAGNOSING, RunState.REFUSED_LOW_EVIDENCE,
         RunState.DEGRADED_PLAIN_RAG, RunState.FAILED}
    ),
    RunState.DIAGNOSING: frozenset(
        {RunState.DRAFTING_WORK_ORDER, RunState.REFUSED_LOW_EVIDENCE,
         RunState.DEGRADED_PLAIN_RAG, RunState.FAILED}
    ),
    RunState.DRAFTING_WORK_ORDER: frozenset(
        {RunState.PENDING_APPROVAL, RunState.FAILED}
    ),
    RunState.PENDING_APPROVAL: frozenset(
        {RunState.APPROVED, RunState.REJECTED}
    ),
    RunState.APPROVED: frozenset({RunState.DISPATCHED}),
    RunState.REJECTED: frozenset(),
    RunState.DISPATCHED: frozenset(),
    RunState.REFUSED_LOW_EVIDENCE: frozenset(),
    RunState.DEGRADED_PLAIN_RAG: frozenset(),
    RunState.FAILED: frozenset(),
}
