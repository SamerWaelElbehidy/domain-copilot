-- Persists the WorkOrder domain entity (src/domain/entities/work_order.py).
-- status mirrors WorkOrderStatus; the CHECK constraint is a second,
-- database-level line of defense behind the domain entity's own
-- enforcement (defense in depth, not a replacement for it).

CREATE TABLE work_orders (
    work_order_id       TEXT PRIMARY KEY,
    equipment_id         TEXT NOT NULL REFERENCES equipment(equipment_id),
    symptom_description  TEXT NOT NULL,
    diagnostic_steps     JSONB NOT NULL,
    safety_checklist     JSONB NOT NULL,
    citations            JSONB NOT NULL,
    status                TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected', 'dispatched')),
    created_at            TIMESTAMPTZ NOT NULL,
    approved_by           TEXT,
    approved_at           TIMESTAMPTZ,
    CONSTRAINT work_order_requires_safety_checklist_before_approval
        CHECK (status = 'draft' OR jsonb_array_length(safety_checklist) > 0)
);

CREATE INDEX idx_work_orders_equipment ON work_orders(equipment_id);
CREATE INDEX idx_work_orders_status ON work_orders(status);
