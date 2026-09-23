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

| Document type | Count | Status |
|---|---|---|
| Equipment Ops & Maintenance Manuals (current) | 7 | ✅ done |
| Equipment LOTO/safety cards | 7 | ✅ done |
| Equipment service bulletins | 7 | ✅ done |
| Stale/superseded revisions (CNC router Rev. B, DCS-800 Rev. 0) | 2 | ✅ done |
| Facility-wide policy documents | 7 | ✅ done |
| **Total** | **30** | ✅ **target met** |

All 30 documents ingest cleanly and are verified by
`tests/integration/test_ingest_full_corpus.py`
(`test_corpus_meets_the_thirty_document_floor` asserts the floor is met).
Next: embed + index stages (ADR-0003/0004 adapters), then retrieval.
