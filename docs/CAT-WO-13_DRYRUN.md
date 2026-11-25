# CAT-WO-13 · PCAP cadence per fund · dry run (throwaway)

Run 2026-11-24 18:23 local, build date 2026-11-24. Throwaway branch `catwo13-throwaway`; main untouched. Codes and counts only.

Before = the checklist build with PCAP-Q v1 (every quarter from FY2025). After = migration `013_wo13.sql` (ops.requirement_cadence seeded per R-058, PCAP-Q v2 with `entity_filter.cadence`) and the same build.

## Totals (PCAP-Q)

| | Expected rows | Met | On file | Missing | No roster |
|---|---:|---:|---:|---:|---:|
| Before (v1) | 2,103 | 358 | 22 | 1,674 | 49 |
| After (v2) | 588 | 358 | 22 | 201 | 7 |
| Change | -1,515 | +0 | +0 | -1,473 | -42 |

Met + On file: 380 -> 380.

## Rule versions

| Version | Active | entity_filter |
|---|---|---|
| 1 | True | `{'company_kind': ['fund', 'spv']}` |
| 2 | True | `{'cadence': 'ops.requirement_cadence', 'company_kind': ['fund', 'spv']}` |

Rows built after: rule_version [2]. Other rules' row counts after (CAT-WO-13 changes only PCAP-Q's subjects): AUDITED-FS 34, GP-COMMIT 21, K1-SET 428, LP-SIDE 285, LP-SUB 285.

## Cadence (ops.requirement_cadence, R-058)

| Entity | Cadence | First period |
|---|---|---|
| ACCSO | quarterly | 2025 Q4 |
| ATTOTUDE | quarterly | 2025 Q4 |
| LS-I | quarterly | 2025 Q4 |
| LS-II | quarterly | 2025 Q4 |
| MTV-IV (A) | quarterly | 2025 Q4 |
| MTV-IV (Annex) | quarterly | 2025 Q4 |
| MTV-IV (B) | quarterly | 2025 Q4 |
| MTV-V (A) | quarterly | 2025 Q4 |
| MTV-V (B) | quarterly | 2025 Q4 |
| MTV-V (MTEF) | quarterly | 2025 Q4 |
| MTV-VI | quarterly | 2025 Q4 |
| ASOF | annual | 2025 Q4 |
| CIP-I | annual | 2025 Q4 |
| CIP-II | annual | 2025 Q4 |
| CSOP | annual | 2025 Q4 |

No row -> annual fallback (Q4 only, FY2025+): CIP-III, FUNDAM, IVY, MTV-I, MTV-II, MTV-II (MTEF), MTV-III, MTV-III (MTEF), MTV-III (PF), NL-I, NL-II, TM, X, XI.

## Per entity x quarter (before -> after)

Cells: expected rows, then Met / On file / Missing / No roster. `-` = no rows.

| Entity | Cadence | Period | Before: rows (M/OF/Mi/NR) | After: rows (M/OF/Mi/NR) |
|---|---|---|---|---|
| ACCSO | quarterly | 2025 Q1 | 14 (0/0/14/0) | - |
| ACCSO | quarterly | 2025 Q2 | 14 (0/0/14/0) | - |
| ACCSO | quarterly | 2025 Q3 | 14 (0/0/14/0) | - |
| ACCSO | quarterly | 2025 Q4 | 14 (13/0/1/0) | 14 (13/0/1/0) |
| ACCSO | quarterly | 2026 Q1 | 14 (0/0/14/0) | 14 (0/0/14/0) |
| ACCSO | quarterly | 2026 Q2 | 14 (0/0/14/0) | 14 (0/0/14/0) |
| ACCSO | quarterly | 2026 Q3 | 14 (0/0/14/0) | 14 (0/0/14/0) |
| ASOF | annual | 2025 Q1 | 2 (0/0/2/0) | - |
| ASOF | annual | 2025 Q2 | 2 (0/0/2/0) | - |
| ASOF | annual | 2025 Q3 | 2 (0/0/2/0) | - |
| ASOF | annual | 2025 Q4 | 2 (1/0/1/0) | 2 (1/0/1/0) |
| ASOF | annual | 2026 Q1 | 2 (0/0/2/0) | - |
| ASOF | annual | 2026 Q2 | 2 (0/0/2/0) | - |
| ASOF | annual | 2026 Q3 | 2 (0/0/2/0) | - |
| ATTOTUDE | quarterly | 2026 Q1 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| ATTOTUDE | quarterly | 2026 Q2 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| ATTOTUDE | quarterly | 2026 Q3 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| CIP-I | annual | 2025 Q1 | 6 (0/0/6/0) | - |
| CIP-I | annual | 2025 Q2 | 6 (0/0/6/0) | - |
| CIP-I | annual | 2025 Q3 | 6 (0/0/6/0) | - |
| CIP-I | annual | 2025 Q4 | 6 (2/3/1/0) | 6 (2/3/1/0) |
| CIP-I | annual | 2026 Q1 | 6 (0/0/6/0) | - |
| CIP-I | annual | 2026 Q2 | 6 (0/0/6/0) | - |
| CIP-I | annual | 2026 Q3 | 6 (0/0/6/0) | - |
| CIP-II | annual | 2025 Q1 | 119 (0/0/119/0) | - |
| CIP-II | annual | 2025 Q2 | 119 (0/0/119/0) | - |
| CIP-II | annual | 2025 Q3 | 119 (0/0/119/0) | - |
| CIP-II | annual | 2025 Q4 | 119 (98/17/4/0) | 119 (98/17/4/0) |
| CIP-II | annual | 2026 Q1 | 119 (0/0/119/0) | - |
| CIP-II | annual | 2026 Q2 | 119 (0/0/119/0) | - |
| CIP-II | annual | 2026 Q3 | 119 (0/0/119/0) | - |
| CIP-III | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| CIP-III | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| CIP-III | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| CIP-III | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| CIP-III | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| CIP-III | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| CIP-III | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| CSOP | annual | 2025 Q1 | 2 (0/0/2/0) | - |
| CSOP | annual | 2025 Q2 | 2 (0/0/2/0) | - |
| CSOP | annual | 2025 Q3 | 2 (0/0/2/0) | - |
| CSOP | annual | 2025 Q4 | 2 (1/0/1/0) | 2 (1/0/1/0) |
| CSOP | annual | 2026 Q1 | 2 (0/0/2/0) | - |
| CSOP | annual | 2026 Q2 | 2 (0/0/2/0) | - |
| CSOP | annual | 2026 Q3 | 2 (0/0/2/0) | - |
| FUNDAM | annual | 2025 Q1 | 25 (0/0/25/0) | - |
| FUNDAM | annual | 2025 Q2 | 25 (0/0/25/0) | - |
| FUNDAM | annual | 2025 Q3 | 25 (0/0/25/0) | - |
| FUNDAM | annual | 2025 Q4 | 25 (0/0/25/0) | 25 (0/0/25/0) |
| FUNDAM | annual | 2026 Q1 | 25 (0/0/25/0) | - |
| FUNDAM | annual | 2026 Q2 | 25 (0/0/25/0) | - |
| FUNDAM | annual | 2026 Q3 | 25 (0/0/25/0) | - |
| IVY | annual | 2025 Q1 | 13 (0/0/13/0) | - |
| IVY | annual | 2025 Q2 | 13 (0/0/13/0) | - |
| IVY | annual | 2025 Q3 | 13 (0/0/13/0) | - |
| IVY | annual | 2025 Q4 | 13 (0/0/13/0) | 13 (0/0/13/0) |
| IVY | annual | 2026 Q1 | 13 (0/0/13/0) | - |
| IVY | annual | 2026 Q2 | 13 (0/0/13/0) | - |
| IVY | annual | 2026 Q3 | 13 (0/0/13/0) | - |
| LS-I | quarterly | 2025 Q1 | 1 (0/0/1/0) | - |
| LS-I | quarterly | 2025 Q2 | 1 (0/0/1/0) | - |
| LS-I | quarterly | 2025 Q3 | 1 (0/0/1/0) | - |
| LS-I | quarterly | 2025 Q4 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-I | quarterly | 2026 Q1 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-I | quarterly | 2026 Q2 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-I | quarterly | 2026 Q3 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-II | quarterly | 2025 Q1 | 1 (0/0/1/0) | - |
| LS-II | quarterly | 2025 Q2 | 1 (0/0/1/0) | - |
| LS-II | quarterly | 2025 Q3 | 1 (0/0/1/0) | - |
| LS-II | quarterly | 2025 Q4 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-II | quarterly | 2026 Q1 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-II | quarterly | 2026 Q2 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| LS-II | quarterly | 2026 Q3 | 1 (0/0/1/0) | 1 (0/0/1/0) |
| MTV-I | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| MTV-I | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| MTV-I | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| MTV-I | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| MTV-I | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| MTV-I | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| MTV-I | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| MTV-II | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| MTV-II | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| MTV-II (MTEF) | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| MTV-II (MTEF) | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| MTV-III | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| MTV-III | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| MTV-III (MTEF) | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| MTV-III (MTEF) | annual | 2026 Q3 | 1 (0/0/0/1) | - |
| MTV-III (PF) | annual | 2025 Q1 | 14 (0/0/14/0) | - |
| MTV-III (PF) | annual | 2025 Q2 | 14 (0/0/14/0) | - |
| MTV-III (PF) | annual | 2025 Q3 | 14 (0/0/14/0) | - |
| MTV-III (PF) | annual | 2025 Q4 | 14 (0/0/14/0) | 14 (0/0/14/0) |
| MTV-III (PF) | annual | 2026 Q1 | 14 (0/0/14/0) | - |
| MTV-III (PF) | annual | 2026 Q2 | 14 (0/0/14/0) | - |
| MTV-III (PF) | annual | 2026 Q3 | 14 (0/0/14/0) | - |
| MTV-IV (A) | quarterly | 2025 Q1 | 16 (0/0/16/0) | - |
| MTV-IV (A) | quarterly | 2025 Q2 | 16 (0/0/16/0) | - |
| MTV-IV (A) | quarterly | 2025 Q3 | 16 (0/0/16/0) | - |
| MTV-IV (A) | quarterly | 2025 Q4 | 16 (13/0/3/0) | 16 (13/0/3/0) |
| MTV-IV (A) | quarterly | 2026 Q1 | 16 (13/0/3/0) | 16 (13/0/3/0) |
| MTV-IV (A) | quarterly | 2026 Q2 | 16 (13/0/3/0) | 16 (13/0/3/0) |
| MTV-IV (A) | quarterly | 2026 Q3 | 16 (14/0/2/0) | 16 (14/0/2/0) |
| MTV-IV (Annex) | quarterly | 2025 Q1 | 16 (0/0/16/0) | - |
| MTV-IV (Annex) | quarterly | 2025 Q2 | 16 (0/0/16/0) | - |
| MTV-IV (Annex) | quarterly | 2025 Q3 | 16 (0/0/16/0) | - |
| MTV-IV (Annex) | quarterly | 2025 Q4 | 16 (12/0/4/0) | 16 (12/0/4/0) |
| MTV-IV (Annex) | quarterly | 2026 Q1 | 16 (12/0/4/0) | 16 (12/0/4/0) |
| MTV-IV (Annex) | quarterly | 2026 Q2 | 16 (12/0/4/0) | 16 (12/0/4/0) |
| MTV-IV (Annex) | quarterly | 2026 Q3 | 16 (13/0/3/0) | 16 (13/0/3/0) |
| MTV-IV (B) | quarterly | 2025 Q1 | 4 (0/0/4/0) | - |
| MTV-IV (B) | quarterly | 2025 Q2 | 4 (0/0/4/0) | - |
| MTV-IV (B) | quarterly | 2025 Q3 | 4 (0/0/4/0) | - |
| MTV-IV (B) | quarterly | 2025 Q4 | 4 (3/0/1/0) | 4 (3/0/1/0) |
| MTV-IV (B) | quarterly | 2026 Q1 | 4 (3/0/1/0) | 4 (3/0/1/0) |
| MTV-IV (B) | quarterly | 2026 Q2 | 4 (3/0/1/0) | 4 (3/0/1/0) |
| MTV-IV (B) | quarterly | 2026 Q3 | 4 (3/0/1/0) | 4 (3/0/1/0) |
| MTV-V (A) | quarterly | 2025 Q1 | 9 (0/0/9/0) | - |
| MTV-V (A) | quarterly | 2025 Q2 | 9 (0/0/9/0) | - |
| MTV-V (A) | quarterly | 2025 Q3 | 9 (0/0/9/0) | - |
| MTV-V (A) | quarterly | 2025 Q4 | 9 (8/0/1/0) | 9 (8/0/1/0) |
| MTV-V (A) | quarterly | 2026 Q1 | 9 (8/0/1/0) | 9 (8/0/1/0) |
| MTV-V (A) | quarterly | 2026 Q2 | 9 (8/0/1/0) | 9 (8/0/1/0) |
| MTV-V (A) | quarterly | 2026 Q3 | 9 (8/0/1/0) | 9 (8/0/1/0) |
| MTV-V (B) | quarterly | 2025 Q1 | 9 (0/0/9/0) | - |
| MTV-V (B) | quarterly | 2025 Q2 | 9 (0/0/9/0) | - |
| MTV-V (B) | quarterly | 2025 Q3 | 9 (0/0/9/0) | - |
| MTV-V (B) | quarterly | 2025 Q4 | 9 (4/1/4/0) | 9 (4/1/4/0) |
| MTV-V (B) | quarterly | 2026 Q1 | 9 (4/1/4/0) | 9 (4/1/4/0) |
| MTV-V (B) | quarterly | 2026 Q2 | 9 (5/0/4/0) | 9 (5/0/4/0) |
| MTV-V (B) | quarterly | 2026 Q3 | 9 (6/0/3/0) | 9 (6/0/3/0) |
| MTV-V (MTEF) | quarterly | 2025 Q1 | 20 (0/0/20/0) | - |
| MTV-V (MTEF) | quarterly | 2025 Q2 | 20 (0/0/20/0) | - |
| MTV-V (MTEF) | quarterly | 2025 Q3 | 20 (0/0/20/0) | - |
| MTV-V (MTEF) | quarterly | 2025 Q4 | 20 (18/0/2/0) | 20 (18/0/2/0) |
| MTV-V (MTEF) | quarterly | 2026 Q1 | 20 (18/0/2/0) | 20 (18/0/2/0) |
| MTV-V (MTEF) | quarterly | 2026 Q2 | 20 (19/0/1/0) | 20 (19/0/1/0) |
| MTV-V (MTEF) | quarterly | 2026 Q3 | 20 (19/0/1/0) | 20 (19/0/1/0) |
| MTV-VI | quarterly | 2025 Q1 | 5 (0/0/5/0) | - |
| MTV-VI | quarterly | 2025 Q2 | 5 (0/0/5/0) | - |
| MTV-VI | quarterly | 2025 Q3 | 5 (0/0/5/0) | - |
| MTV-VI | quarterly | 2025 Q4 | 5 (4/0/1/0) | 5 (4/0/1/0) |
| MTV-VI | quarterly | 2026 Q1 | 5 (0/0/5/0) | 5 (0/0/5/0) |
| MTV-VI | quarterly | 2026 Q2 | 5 (0/0/5/0) | 5 (0/0/5/0) |
| MTV-VI | quarterly | 2026 Q3 | 5 (0/0/5/0) | 5 (0/0/5/0) |
| NL-I | annual | 2025 Q1 | 2 (0/0/2/0) | - |
| NL-I | annual | 2025 Q2 | 2 (0/0/2/0) | - |
| NL-I | annual | 2025 Q3 | 2 (0/0/2/0) | - |
| NL-I | annual | 2025 Q4 | 2 (0/0/2/0) | 2 (0/0/2/0) |
| NL-I | annual | 2026 Q1 | 2 (0/0/2/0) | - |
| NL-I | annual | 2026 Q2 | 2 (0/0/2/0) | - |
| NL-I | annual | 2026 Q3 | 2 (0/0/2/0) | - |
| NL-II | annual | 2025 Q1 | 2 (0/0/2/0) | - |
| NL-II | annual | 2025 Q2 | 2 (0/0/2/0) | - |
| NL-II | annual | 2025 Q3 | 2 (0/0/2/0) | - |
| NL-II | annual | 2025 Q4 | 2 (0/0/2/0) | 2 (0/0/2/0) |
| NL-II | annual | 2026 Q1 | 2 (0/0/2/0) | - |
| NL-II | annual | 2026 Q2 | 2 (0/0/2/0) | - |
| NL-II | annual | 2026 Q3 | 2 (0/0/2/0) | - |
| TM | annual | 2025 Q1 | 6 (0/0/6/0) | - |
| TM | annual | 2025 Q2 | 6 (0/0/6/0) | - |
| TM | annual | 2025 Q3 | 6 (0/0/6/0) | - |
| TM | annual | 2025 Q4 | 6 (0/0/6/0) | 6 (0/0/6/0) |
| TM | annual | 2026 Q1 | 6 (0/0/6/0) | - |
| TM | annual | 2026 Q2 | 6 (0/0/6/0) | - |
| TM | annual | 2026 Q3 | 6 (0/0/6/0) | - |
| X | annual | 2025 Q1 | 7 (0/0/7/0) | - |
| X | annual | 2025 Q2 | 7 (0/0/7/0) | - |
| X | annual | 2025 Q3 | 7 (0/0/7/0) | - |
| X | annual | 2025 Q4 | 7 (0/0/7/0) | 7 (0/0/7/0) |
| X | annual | 2026 Q1 | 7 (0/0/7/0) | - |
| X | annual | 2026 Q2 | 7 (0/0/7/0) | - |
| X | annual | 2026 Q3 | 7 (0/0/7/0) | - |
| XI | annual | 2025 Q1 | 1 (0/0/0/1) | - |
| XI | annual | 2025 Q2 | 1 (0/0/0/1) | - |
| XI | annual | 2025 Q3 | 1 (0/0/0/1) | - |
| XI | annual | 2025 Q4 | 1 (0/0/0/1) | 1 (0/0/0/1) |
| XI | annual | 2026 Q1 | 1 (0/0/0/1) | - |
| XI | annual | 2026 Q2 | 1 (0/0/0/1) | - |
| XI | annual | 2026 Q3 | 1 (0/0/0/1) | - |

## Per entity (before -> after)

| Entity | Cadence | Rows | Met | On file | Missing |
|---|---|---|---|---|---|
| ACCSO | quarterly | 98 -> 56 | 13 -> 13 | 0 -> 0 | 85 -> 43 |
| ASOF | annual | 14 -> 2 | 1 -> 1 | 0 -> 0 | 13 -> 1 |
| ATTOTUDE | quarterly | 3 -> 3 | 0 -> 0 | 0 -> 0 | 3 -> 3 |
| CIP-I | annual | 42 -> 6 | 2 -> 2 | 3 -> 3 | 37 -> 1 |
| CIP-II | annual | 833 -> 119 | 98 -> 98 | 17 -> 17 | 718 -> 4 |
| CIP-III | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| CSOP | annual | 14 -> 2 | 1 -> 1 | 0 -> 0 | 13 -> 1 |
| FUNDAM | annual | 175 -> 25 | 0 -> 0 | 0 -> 0 | 175 -> 25 |
| IVY | annual | 91 -> 13 | 0 -> 0 | 0 -> 0 | 91 -> 13 |
| LS-I | quarterly | 7 -> 4 | 0 -> 0 | 0 -> 0 | 7 -> 4 |
| LS-II | quarterly | 7 -> 4 | 0 -> 0 | 0 -> 0 | 7 -> 4 |
| MTV-I | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| MTV-II | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| MTV-II (MTEF) | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| MTV-III | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| MTV-III (MTEF) | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| MTV-III (PF) | annual | 98 -> 14 | 0 -> 0 | 0 -> 0 | 98 -> 14 |
| MTV-IV (A) | quarterly | 112 -> 64 | 53 -> 53 | 0 -> 0 | 59 -> 11 |
| MTV-IV (Annex) | quarterly | 112 -> 64 | 49 -> 49 | 0 -> 0 | 63 -> 15 |
| MTV-IV (B) | quarterly | 28 -> 16 | 12 -> 12 | 0 -> 0 | 16 -> 4 |
| MTV-V (A) | quarterly | 63 -> 36 | 32 -> 32 | 0 -> 0 | 31 -> 4 |
| MTV-V (B) | quarterly | 63 -> 36 | 19 -> 19 | 2 -> 2 | 42 -> 15 |
| MTV-V (MTEF) | quarterly | 140 -> 80 | 74 -> 74 | 0 -> 0 | 66 -> 6 |
| MTV-VI | quarterly | 35 -> 20 | 4 -> 4 | 0 -> 0 | 31 -> 16 |
| NL-I | annual | 14 -> 2 | 0 -> 0 | 0 -> 0 | 14 -> 2 |
| NL-II | annual | 14 -> 2 | 0 -> 0 | 0 -> 0 | 14 -> 2 |
| TM | annual | 42 -> 6 | 0 -> 0 | 0 -> 0 | 42 -> 6 |
| X | annual | 49 -> 7 | 0 -> 0 | 0 -> 0 | 49 -> 7 |
| XI | annual | 7 -> 1 | 0 -> 0 | 0 -> 0 | 0 -> 0 |

## Build log

```
BEFORE (v1, rolled back): met=358  missing=1,674  no_roster=49  on_file:draft=1  on_file:partner_unconfirmed=21
REQUIREMENTS APPLIED: 1,641 rows · run req_20261124_182300 · 5s
  AUDITED-FS n=   34  on_file:not_satisfying_kind=3  met=31
  GP-COMMIT  n=   21  missing=14  no_roster=7
  K1-SET     n=  428  missing=167  on_file:unknown=6  on_file:partner_unconfirmed=40  met=200  no_roster=15
  LP-SIDE    n=  285  on_file:unknown=1  on_file:partner_unconfirmed=10  on_file:final_unexecuted=2  none_found=260  met=5  no_roster=7
  LP-SUB     n=  285  missing=146  on_file:unknown=23  on_file:partner_unconfirmed=37  on_file:final_unexecuted=2  met=70  no_roster=7
  PCAP-Q     n=  588  missing=201  on_file:draft=1  on_file:partner_unconfirmed=21  met=358  no_roster=7
```
