---
equipment_id: eq-dust-extraction-dcs800
equipment_name: Dust Extraction & Collection System
document_id: doc-dust-extraction-dcs800-rev-a
revision: Rev. A
effective_date: 2025-03-18
---

# Dust Extraction & Collection System DCS-800 — Maintenance & Operations Manual (Rev. A)

## Overview & Specifications

The DCS-800 is the central dust collection system serving the CNC
router, edge bander, and general sanding stations at Dawlia Furniture
Works' Damietta facility. Type: cyclone pre-separator with a baghouse
filter bank. Airflow capacity: 8,000 m3/h. The system includes a spark
detection and fast-acting fire suppression module in the ductwork ahead
of the baghouse, and static-grounding bonding on all metal ducting.
Fine wood dust is a combustible dust hazard: an accumulated dust cloud
can explode if ignited, which is why grounding, spark detection, and
housekeeping controls in this manual are treated as safety-critical, not
optional maintenance items.

## Safety Prerequisites

1. Confirm all ductwork grounding/bonding straps show continuity
   (weekly test, logged) before relying on the system for a shift —
   ungrounded ducting can accumulate static charge capable of igniting
   dust.
2. Verify the spark detection and suppression module status light shows
   "armed" before starting any connected machine that generates dust.
3. Never run a connected machine (router, edge bander, sanders) with the
   DCS-800 offline or in fault status — this duplicates the per-machine
   requirement in each connected machine's own manual.
4. Do not open the hopper access door to clear a blockage or empty
   collected dust without first engaging the hopper's lockout switch and
   confirming the auger has fully stopped.
5. Check baghouse differential pressure gauge before each shift; a
   reading outside the normal band can indicate filter blinding (fire
   risk from restricted airflow) or a torn bag (dust escaping filtration).
6. Keep collected dust hoppers below the marked maximum fill line —
   an overfull hopper increases both fire load and the risk of dust
   escaping during emptying.
7. No hot work (welding, grinding, open flame) within 10 meters of any
   DCS-800 ducting or the baghouse without a issued hot-work permit and
   a dedicated fire watch.

## Installation & Setup

Route all ductwork with continuous metal-to-metal bonding and a single
point grounding connection to the facility grounding grid, per the
electrical contractor's bonding diagram. Position the spark detection
sensors per the manufacturer's spacing specification along the main
trunk line, upstream of the baghouse. Commission the fire suppression
module with a certified test discharge (non-destructive test mode)
before connecting any production machine to the system.

## Operating Procedures

Start the DCS-800 and confirm normal airflow (green zone on the facility
dashboard) at least 10 seconds before starting any connected machine's
dust-generating operation, matching the startup sequence documented in
each connected machine's own manual. Monitor the facility dashboard
during production for any fault or pressure-band alarm. On any spark
detection alarm, the suppression module activates automatically; do not
attempt to manually override or silence an active suppression event.

## Maintenance Schedule

Daily: check differential pressure gauge, check hopper fill levels.
Weekly: test grounding/bonding continuity per Safety Prerequisite §1,
visually inspect ducting for damage or loose clamps. Monthly: inspect
baghouse filter bags for visible wear via the access port, test spark
detection sensor response with the manufacturer's test tool. Quarterly:
certified inspection and non-destructive test of the fire suppression
module; full baghouse filter bank inspection.

## Diagnostic & Troubleshooting

1. Symptom: baghouse differential pressure reading above the normal
   band. Likely cause: filter blinding from a heavy dust load, or a
   partially closed damper somewhere in the ducting. Corrective action:
   schedule filter inspection/replacement per the monthly checklist;
   do not continue running connected machines if pressure remains above
   the alarm threshold, since this both reduces extraction at the
   connected machines and increases fire risk in the baghouse.
2. Symptom: differential pressure reading below the normal band. Likely
   cause: a torn filter bag allowing air to bypass filtration, or a
   duct disconnection. Corrective action: inspect filter bags via the
   access port, inspect ducting joints for separation; treat this as
   a filtration-integrity issue, not just an airflow issue, since dust
   may be escaping to atmosphere.
3. Symptom: grounding continuity test fails at one or more ducting
   sections. Likely cause: a loosened bonding strap, or corrosion at a
   bonding point. Corrective action: do not connect production machines
   to the affected duct run until continuity is restored and re-tested;
   this is a Safety Prerequisite §1 item, not a deferred maintenance
   item.
4. Symptom: spark detection module shows a sensor fault (not an active
   alarm). Likely cause: sensor lens contamination, or a wiring fault.
   Corrective action: schedule certified technician inspection before
   the next shift; connected machines should not run with an unverified
   spark detection system per Safety Prerequisite §2.

## Parts Catalog

- Baghouse filter bag (per unit) — part no. DCS-FLB-01
- Grounding/bonding strap — part no. DCS-GBS-01
- Spark detection sensor — part no. DCS-SDS-02
- Hopper lockout switch assembly — part no. DCS-HLS-01

## Revision History

- Rev. A (2025-03-18): initial release.
