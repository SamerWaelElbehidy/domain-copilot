---
equipment_id: eq-edge-bander-ebm150
equipment_name: Edge Banding Machine
document_id: doc-edge-bander-ebm150-sb-01
revision: Rev. A
effective_date: 2025-11-18
---

# Service Bulletin SB-EBM-150-01 — Glue Pot Thermocouple Failure Mode

## Overview & Specifications

Applies to all EBM-150 units. Field reports indicate the glue pot
thermocouple can fail in a mode that shows a plausible but incorrect
(usually low) temperature reading, rather than failing to an obvious
error state. This is distinct from the normal cold/hot glue symptoms
already covered in the manual's Diagnostic & Troubleshooting section —
this bulletin covers the specific case where the displayed temperature
does not match the pot's actual state.

## Diagnostic & Troubleshooting

1. Symptom: control panel shows a stable, in-range glue pot temperature,
   but banding bond quality is poor in a pattern consistent with an
   underheated pot (per the manual's Diagnostic §1). Likely cause: a
   failing thermocouple reporting a plausible but incorrect reading,
   masking the real underheating. Corrective action: verify actual pot
   temperature with an independent handheld thermometer if bond quality
   issues persist despite an in-range panel reading; do not assume the
   panel reading is correct by default.
2. Symptom: independent thermometer and panel reading disagree by more
   than 10C. Likely cause: thermocouple drift or failure. Corrective
   action: replace the thermocouple per manufacturer procedure before
   resuming production; do not attempt to compensate by manually
   offsetting the temperature set point, since drift is not
   predictable over time.

## Parts Catalog

- Glue pot thermocouple (replacement) — part no. EBM-GTC-01

## Revision History

- Rev. A (2025-11-18): initial bulletin release.
