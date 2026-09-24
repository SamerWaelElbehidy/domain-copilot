from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ApprovalToken:
    """Proof that a named human approved one specific work order.
    Only the orchestrator's approval-gate path constructs this; agents
    never receive one, so they cannot invoke gated tools."""

    work_order_id: str
    approved_by: str
    approved_at: datetime
