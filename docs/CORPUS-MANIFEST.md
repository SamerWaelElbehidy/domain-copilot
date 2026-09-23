# Corpus manifest — Dawlia Furniture Works (fictional), Damietta

Synthetic corpus, no real personal data (per brief §2/§9). Target: ≥30
documents / 150+ pages. Tracked here so ingestion progress is checkable
without re-deriving it from the file tree.

## Equipment fleet (7 machines) and their central safety theme

| ID | Equipment | Model | Central hazard |
|---|---|---|---|
| eq-cnc-router-dwr2200 | CNC Wood Router | DWR-2200 | dust/projectile, spindle |
| eq-drying-kiln-kdn500 | Wood Drying Kiln | KDN-500 | fire/heat, possible CO |
| eq-laminating-press-hlp1200 | Hydraulic Laminating Press | HLP-1200 | crush/pinch, hydraulic pressure |
| eq-spray-booth-sfb300 | Spray Finishing Booth | SFB-300 | flammable vapor/explosion |
| eq-edge-bander-ebm150 | Edge Banding Machine | EBM-150 | hot glue burns, nip points |
| eq-dust-extraction-dcs800 | Dust Extraction & Collection System | DCS-800 | combustible dust explosion |
| eq-air-compressor-iac100 | Industrial Air Compressor | IAC-100 | stored pressure energy |

## Per-equipment documents (target 3 each = 21)

1. **Operations & Maintenance Manual** — full 8-section structure (the
   template `cnc-wood-router-dwr2200/manual-rev-c.md` established)
2. **Lockout-Tagout & Safety Card** — equipment-specific safety focus
3. **Service Bulletin / Troubleshooting Supplement** — diagnostic-heavy,
   shorter, represents a follow-up document issued after field issues

## Revision variety (tests D5's "identify manual revision" step)

- `eq-cnc-router-dwr2200`: Rev. B (stale, superseded) **and** Rev. C
  (current) both in-corpus — the evaluation set will include a question
  whose correct answer depends on retrieving Rev. C, not the stale Rev. B

## Facility-wide documents (not tied to one machine, ~6)

Use `equipment_id: eq-facility-general` in frontmatter.

1. General Workshop Safety Policy
2. Company-wide Lockout-Tagout Standard
3. Incident & Near-Miss Reporting Procedure
4. Combustible Dust Management Policy
5. Personal Protective Equipment (PPE) Standard
6. New Technician Onboarding Safety Checklist

## Status

| Document | Status |
|---|---|
| eq-cnc-router-dwr2200 — Ops Manual Rev. C | ✅ done |
| eq-cnc-router-dwr2200 — Ops Manual Rev. B (stale) | pending |
| eq-cnc-router-dwr2200 — LOTO card | pending |
| eq-cnc-router-dwr2200 — Service bulletin | pending |
| eq-drying-kiln-kdn500 — Ops Manual | pending |
| eq-laminating-press-hlp1200 — Ops Manual | pending |
| eq-spray-booth-sfb300 — Ops Manual | pending |
| eq-edge-bander-ebm150 — Ops Manual | pending |
| eq-dust-extraction-dcs800 — Ops Manual | pending |
| eq-air-compressor-iac100 — Ops Manual | pending |
| (+ remaining LOTO cards / bulletins / facility-wide docs) | pending |

This table is updated as documents land.
