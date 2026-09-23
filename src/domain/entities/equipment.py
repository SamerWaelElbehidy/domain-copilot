from dataclasses import dataclass


@dataclass(frozen=True)
class Equipment:
    equipment_id: str
    name: str
    model_number: str
    category: str
