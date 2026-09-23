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
