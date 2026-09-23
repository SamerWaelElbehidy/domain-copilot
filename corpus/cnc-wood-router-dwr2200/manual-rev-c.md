---
equipment_id: eq-cnc-router-dwr2200
equipment_name: CNC Wood Router DWR-2200
document_id: doc-cnc-router-dwr2200-rev-c
revision: Rev. C
effective_date: 2025-11-01
---

# CNC Wood Router DWR-2200 — Maintenance & Operations Manual (Rev. C)

## Overview & Specifications

The DWR-2200 is a 3-axis CNC wood router used at Dawlia Furniture Works'
Damietta facility for cutting, carving, and drilling flat-panel furniture
components (MDF, plywood, solid hardwood up to 60mm). Work envelope:
2200mm x 1300mm x 200mm. Spindle: 9kW air-cooled, 6,000-24,000 RPM.
Dust extraction port: 120mm, must be connected to the shop's central dust
collection system (see DCS-800 manual) whenever the spindle is running.

This revision (Rev. C) supersedes Rev. B by adding the mandatory
pre-start vacuum check in Safety Prerequisites §3, following a near-miss
incident in the Rev. B period involving a partially blocked dust port.

## Safety Prerequisites

1. Confirm the emergency stop button is unobstructed and tested (press
   and release) before every shift start.
2. Verify the dust extraction system (DCS-800) is running and showing
   normal suction pressure on its gauge before starting the spindle. Never
   run the spindle with dust extraction offline.
3. Check that the dust extraction hose connection at the router head is
   fully seated with no visible gaps, and that the DCS-800 pressure gauge
   reads within the green zone, before every job start (added Rev. C).
4. Ensure all four vacuum table zones show full hold-down pressure on the
   control panel before beginning any cut — a workpiece that lifts during
   a high-speed pass is a projectile hazard.
5. Do not open the enclosure door while the spindle is rotating, even if
   the current cut appears finished. Wait for the "SPINDLE STOPPED"
   indicator.
6. Wear hearing protection and a properly fitted dust mask (minimum
   FFP2) at all times during operation — MDF dust is a respiratory
   hazard and the ambient noise exceeds 85dB during routing passes.
7. Before any maintenance or blade/bit change, engage the physical
   lockout-tagout switch on the main power panel, not just the on-screen
   stop — the spindle can retain rotational energy for several seconds
   after a software stop.

## Installation & Setup

Mount the DWR-2200 on a leveled concrete pad rated for at least 1,800kg.
Connect the 120mm dust port to the DCS-800 trunk line using the supplied
clamp fitting; do not use flexible ducting longer than 3 meters between
the router and the trunk line, as this measurably reduces suction
pressure at the head. Connect three-phase power (400V, 32A) through a
lockable isolator switch mounted within arm's reach of the operator
station. Run the built-in axis calibration routine (Settings > Calibrate
Axes) before first use and after any relocation of the machine.

## Operating Procedures

Load the cut program via USB or the shop network share. Confirm the
material thickness entered in the control panel matches the actual
stock, since an incorrect Z-zero will either crash the bit into the
vacuum table or leave material uncut. Run a single air pass (spindle off,
Z raised 20mm) before the first cut of a new program to visually confirm
the toolpath matches the workpiece. Start the dust extraction system at
least 10 seconds before starting the spindle, so suction is stable
before dust generation begins.

## Maintenance Schedule

Daily: clear chip tray, wipe down linear rails, visually inspect dust
hose for kinks or tears. Weekly: grease the X/Y linear bearings per the
lubrication chart in Appendix A, check belt tension on all three axes.
Monthly: inspect spindle collet for wear and replace if runout exceeds
0.05mm, verify vacuum table zone seals, recalibrate axes. Every 2,000
spindle-hours: full spindle bearing inspection by a certified technician.

## Diagnostic & Troubleshooting

1. Symptom: spindle overheating (thermal shutdown) during long runs.
   Likely cause: coolant/air flow restricted, or ambient shop temperature
   above 35C. Corrective action: check spindle air-cooling intake for
   dust blockage, confirm shop ventilation is operating, allow spindle to
   cool for 30 minutes before resuming; if the issue recurs within the
   same shift, escalate to a certified technician rather than continuing
   to restart the spindle.
2. Symptom: reduced dust pickup at the router head despite DCS-800
   running normally. Likely cause: hose kink, partial blockage, or a
   loose clamp fitting at the head. Corrective action: inspect the full
   hose run per Safety Prerequisite §3 before resuming any cut; do not
   resume spindle operation until suction is confirmed restored.
3. Symptom: vacuum table failing to hold a zone (workpiece shifts during
   cut). Likely cause: a worn zone seal, or a workpiece smaller than the
   active zone leaving an unsealed gap. Corrective action: switch to a
   smaller matching zone size or add a sacrificial spoilboard sized to
   the workpiece; inspect the zone seal and replace if visibly worn.
4. Symptom: inconsistent cut depth across a panel. Likely cause: vacuum
   table surface not flush (spoilboard warped or debris trapped
   underneath), or Z-axis calibration drift. Corrective action: clear
   and inspect the table surface, re-run axis calibration (Settings >
   Calibrate Axes); if drift recurs within a week of calibration,
   escalate for a certified technician inspection of the Z-axis
   ballscrew.

## Parts Catalog

- Spindle collet set (6mm/8mm/12mm) — part no. DWR-COL-SET
- Dust hose clamp fitting, 120mm — part no. DWR-DHC-120
- Vacuum table zone seal (per zone) — part no. DWR-VTS-01
- X/Y linear bearing set — part no. DWR-LB-XY

## Revision History

- Rev. A (2024-03-15): initial release.
- Rev. B (2025-02-10): updated maintenance schedule intervals; added
  Diagnostic & Troubleshooting §3 (vacuum table zone).
- Rev. C (2025-11-01): added Safety Prerequisite §3 (dust hose
  connection check) following a near-miss incident; clarified §2 wording.
