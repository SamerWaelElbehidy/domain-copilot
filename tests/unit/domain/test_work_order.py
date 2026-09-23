from datetime import datetime

import pytest

from domain.entities.work_order import WorkOrder, WorkOrderStatus
from domain.errors.domain_errors import (
    MissingSafetyPrerequisiteError,
    UnapprovedDispatchError,
)


def make_work_order(safety_checklist=None) -> WorkOrder:
    return WorkOrder(
        work_order_id="wo-1",
        equipment_id="eq-cnc-router-01",
        symptom_description="Spindle overheating during long runs.",
        diagnostic_steps=["Check coolant flow", "Inspect bearing wear"],
        safety_checklist=safety_checklist or [],
        citations=[],
        created_at=datetime(2026, 1, 1),
    )


def test_submit_without_safety_checklist_is_refused():
    work_order = make_work_order(safety_checklist=[])

    with pytest.raises(MissingSafetyPrerequisiteError):
        work_order.submit_for_approval()

    assert work_order.status == WorkOrderStatus.DRAFT


def test_submit_with_safety_checklist_moves_to_pending_approval():
    work_order = make_work_order(safety_checklist=["Lock out power before inspection"])

    work_order.submit_for_approval()

    assert work_order.status == WorkOrderStatus.PENDING_APPROVAL


def test_dispatch_before_approval_is_refused():
    work_order = make_work_order(safety_checklist=["Lock out power before inspection"])
    work_order.submit_for_approval()

    with pytest.raises(UnapprovedDispatchError):
        work_order.dispatch()


def test_full_approve_then_dispatch_flow():
    work_order = make_work_order(safety_checklist=["Lock out power before inspection"])
    work_order.submit_for_approval()

    work_order.approve(approved_by="supervisor-1", at=datetime(2026, 1, 2))
    assert work_order.status == WorkOrderStatus.APPROVED
    assert work_order.approved_by == "supervisor-1"

    work_order.dispatch()
    assert work_order.status == WorkOrderStatus.DISPATCHED


def test_approve_out_of_sequence_is_refused():
    work_order = make_work_order(safety_checklist=["Lock out power before inspection"])

    with pytest.raises(UnapprovedDispatchError):
        work_order.approve(approved_by="supervisor-1", at=datetime(2026, 1, 2))
