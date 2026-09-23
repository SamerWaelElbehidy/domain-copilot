from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from domain.errors.domain_errors import (
    MissingSafetyPrerequisiteError,
    UnapprovedDispatchError,
)
from domain.value_objects.citation import Citation


class WorkOrderStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPATCHED = "dispatched"


@dataclass
class WorkOrder:
    """The output of the D5 workflow. Approval and safety are enforced
    here, in the domain layer, so no agent, prompt, or API route can
    bypass them by omission."""

    work_order_id: str
    equipment_id: str
    symptom_description: str
    diagnostic_steps: list[str]
    safety_checklist: list[str]
    citations: list[Citation]
    created_at: datetime
    status: WorkOrderStatus = WorkOrderStatus.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None

    def submit_for_approval(self) -> None:
        if not self.safety_checklist:
            raise MissingSafetyPrerequisiteError(
                f"Work order {self.work_order_id} has diagnostic steps but "
                "no safety checklist attached — refusing to submit."
            )
        self.status = WorkOrderStatus.PENDING_APPROVAL

    def approve(self, approved_by: str, at: datetime) -> None:
        if self.status != WorkOrderStatus.PENDING_APPROVAL:
            raise UnapprovedDispatchError(
                f"Work order {self.work_order_id} cannot be approved from "
                f"status {self.status.value}."
            )
        self.status = WorkOrderStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = at

    def reject(self, rejected_by: str, at: datetime) -> None:
        if self.status != WorkOrderStatus.PENDING_APPROVAL:
            raise UnapprovedDispatchError(
                f"Work order {self.work_order_id} cannot be rejected from "
                f"status {self.status.value}."
            )
        self.status = WorkOrderStatus.REJECTED
        self.approved_by = rejected_by
        self.approved_at = at

    def dispatch(self) -> None:
        if self.status != WorkOrderStatus.APPROVED:
            raise UnapprovedDispatchError(
                f"Work order {self.work_order_id} cannot be dispatched "
                f"without prior approval (status={self.status.value})."
            )
        self.status = WorkOrderStatus.DISPATCHED
