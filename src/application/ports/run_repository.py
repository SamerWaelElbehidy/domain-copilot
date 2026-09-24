from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.run import Run


class RunRepository(ABC):
    """Persists a Run and its hash-chained steps (ADR-0006). Saving is an
    upsert of run state plus an append of any steps not yet stored, so a run
    is inspectable while it is still executing."""

    @abstractmethod
    async def save(self, run: Run) -> None: ...

    @abstractmethod
    async def get(self, run_id: str) -> Run | None: ...
