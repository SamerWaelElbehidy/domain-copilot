from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.work_order import WorkOrder


class WorkOrderRepository(ABC):
    @abstractmethod
    async def save(self, work_order: WorkOrder) -> None: ...

    @abstractmethod
    async def get(self, work_order_id: str) -> WorkOrder | None: ...
