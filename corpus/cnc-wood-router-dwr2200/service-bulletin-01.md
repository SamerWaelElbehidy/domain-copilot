---
equipment_id: eq-cnc-router-dwr2200
equipment_name: CNC Wood Router DWR-2200
document_id: doc-cnc-router-dwr2200-sb-01
revision: Rev. A
effective_date: 2026-01-15
---

# Service Bulletin SB-DWR-2200-01 — Intermittent Emergency-Stop Circuit Fault

## Overview & Specifications

Applies to DWR-2200 units commissioned before 2025-09-01 (serial prefix
DWR22-A and DWR22-B only; units DWR22-C onward are not affected). Field
reports indicate the emergency-stop circuit can, in rare cases, fail to
latch after a press-and-release test, showing "READY" on the control
panel despite the button remaining physically engaged. This does not
affect units covered by manual Rev. C's standard safety checks if the
daily E-stop test in Safety Prerequisite §1 is performed correctly, but
technicians should be aware of this specific failure mode.

## Diagnostic & Troubleshooting

1. Symptom: after the daily E-stop press-and-release test, the control
   panel shows "READY" but the physical button does not visibly spring
   back to its released position. Likely cause: a worn E-stop relay
   contact on affected serial ranges. Corrective action: do not rely on
   the panel status alone for affected serials — visually and manually
   confirm the button has physically released before resuming
   operation; if the button does not release, tag the machine out of
   service and escalate to a certified technician for relay
   replacement, do not attempt to force the button.
2. Symptom: E-stop circuit relay replaced but fault recurs within one
   week. Likely cause: an upstream wiring fault rather than the relay
   itself. Corrective action: escalate to the equipment manufacturer's
   technical support line rather than replacing the relay a second
   time; this pattern indicates a wiring-level fault outside routine
   field service scope.

## Parts Catalog

- E-stop circuit relay (affected serials only) — part no. DWR-ESR-01

## Revision History

- Rev. A (2026-01-15): initial bulletin release.
