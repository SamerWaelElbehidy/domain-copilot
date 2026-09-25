from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ApprovalToken:
    """Proof that a named human approved one specific work order.

    Constructing one by hand proves nothing: the registry only accepts a
    token whose signature was produced by its ApprovalAuthority, and only
    for the work order named inside it."""

    work_order_id: str
    approved_by: str
    approved_at: datetime
    signature: str
