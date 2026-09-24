class DomainError(Exception):
    """Base class for all domain-layer errors."""


class LowEvidenceError(DomainError):
    """The corpus does not contain enough evidence to answer.
    Binding principle 1: grounded, never guessing — refusal is a correct,
    required answer, not a failure mode to suppress."""


class MissingSafetyPrerequisiteError(DomainError):
    """A work order would be submitted for a diagnostic procedure without
    its required safety prerequisites attached.
    D5's central risk: safety must be structurally enforced, never left to
    the model to remember."""


class UnapprovedDispatchError(DomainError):
    """An attempt to approve or dispatch a work order out of sequence.
    Binding principle 2: the human holds the pen."""


class InvalidRunTransitionError(DomainError):
    """An orchestration state transition the state machine does not
    allow (ADR-0005) -- illegal jumps would break replay determinism."""


class TamperedRunError(DomainError):
    """A persisted RunStep's hash chain does not verify (ADR-0006) --
    the audit log was edited after the fact."""


class AgentOutputError(DomainError):
    """An agent's model output was not the typed JSON its contract requires."""


class AgentIterationLimitError(DomainError):
    """An agent hit its max-iteration breaker without producing a result
    (FR-5: unbounded consumption control)."""


class ToolNotAllowedError(DomainError):
    """An agent tried to call a tool outside its allow-list.
    OWASP LLM Top 10: excessive agency."""


class InvalidToolArgumentsError(DomainError):
    """Tool arguments failed schema validation before execution.
    OWASP LLM Top 10: insecure output handling."""


class ApprovalRequiredError(DomainError):
    """A side-effecting tool was invoked without a human approval token.
    Binding principle 2: the human holds the pen."""
