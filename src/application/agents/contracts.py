"""Typed contracts between agents (FR-4): agents exchange these frozen
dataclasses, never free-form text."""

from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.citation import Citation


@dataclass(frozen=True)
class SymptomMatchResult:
    equipment_id: str
    document_ids: tuple[str, ...]
    manual_revision: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True)
class DiagnosticPlan:
    diagnostic_steps: tuple[str, ...]
    safety_checklist: tuple[str, ...]
    citations: tuple[Citation, ...]


@dataclass(frozen=True)
class WorkOrderDraftResult:
    work_order_id: str
