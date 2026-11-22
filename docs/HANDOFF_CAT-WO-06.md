# CAT-WO-06 handoff · First-page reading (K-1s, PCAPs, subscriptions, side letters → Datum partner codes)

*2026-11-21. Codes, IDs and counts only: no LP, GP member, employee or file names, no page text, no TINs. Order: `orders/CAT-WO-06_First_Page_Reading.md`. Rulings R-033 – R-038 proposed with defaults; Ryan can veto any at the dry-run stop.*

**Status (kept current):** built on git branch `cat-wo-06` from main `31880e0` (= `b6d86a9` + the docs-only RELEASED line), one squashed commit (an earlier commit carried an invented TIN-shaped test value; the branch was never pushed). Tested on the throwaway Neon branch `catwo06-throwaway` (`br-misty-paper-bd23sm4c`, endpoint `ep-spring-unit-bds6x67g`, from main at 2026-11-21 20:54, created by Ryan / the coordinator on Ryan's approval). Migration 009 ran twice (idempotent), 19 CNT rules seeded. **Gate passed** (2026-11-21 22:00 nightly OK, portals exported directly, no banner). **Released to main up to STOP 2 (dry run); waiting for Ryan's apply.** Nightly disabled. (nothing has touched main, Drive labels or the portals).

## What was built (branch `cat-wo-06`)
| Piece | Where | Notes |
|---|---|---|
| Reader | `pipeline/pages_wo06.py` | `--backfill` / `--incremental` (`--limit`, `--apply`), batches of 200, download to memory, PyMuPDF text layer, local Tesseract OCR through a pipe (stdin → TSV on stdout; no file written), net guard (Google APIs + Neon only) |
| Rules as data (R-038) | `pages_wo06.CNT_RULES` → `ops.decomposition_rule` `applies_to='content'` (`--seed-rules`) | 19 rules: CNT-K1-HDR / PI / PII / YEAR / AMENDED / FINAL, CNT-PCAP-TITLE / PARTNER / TOP / PERIOD / FUND, CNT-SUB-LBL / TOP / SIG / FUND, CNT-SL-DEAR / ADDR / FUND, CNT-ALL-TIN. `--review-only <ids>` writes a new version with `mode: review_only` |
| Classification (R-036) | `pages_wo06.classify` | high = one EXACT roster alias inside a certain anchor of an apply-mode rule; medium = normalised match / uncertain anchor / review-only rule; low = MULTIPLE, NOT_IN_FUND; none = NO_ROSTER_MATCH |
| Merge into Subject (R-034, R-035) | `subject_wo03.merge_content` | person wins (CONFLICT_PERSON → lane), portal wins (CONFLICT_PORTAL → lane), content high replaces folder / name / parties, one `cat.doc_party` row per partner with page range; medium / MULTIPLE → low rows (lane); NOT_IN_FUND lane only; NO_ROSTER_MATCH lane only for checklist candidates |
| Label fit | `subject_wo03.fits_label` | a code list over 20 codes or 100 characters is written as none; the DB keeps the page map |
| Content check | `pages_wo06.apply_content` | FY / quarter fill BLANK machine fields; disagreements (FY, period, entity) → `content_disagrees` → Content disagrees lane, never overwritten |
| Handling (R-037) | `cat.document.content_flags` → `catalog_labels.handling_raise` | Contains + Tax ID / LP PII, tier unchanged; a flag in the machine snapshot that a person removed is never added back |
| Amended K-1 | `families_wo04` / `versions_wo04` | the Amended K-1 box read from page 1 counts as a version marker (joins the original's family) |
| Checklists | `requirements_wo03` | `best_page` + candidate `page`; content matches count like any `doc_party` row |
| Nightly | `apply_derive_wo02` → `pages_wo06.nightly_step` | after kinds, before families / subject / requirements; incremental, cap 500; a Drive / OCR failure prints `pages NOT run` and never stops the nightly |
| Migration | `db/migrations/009_wo06.sql` | `cat.doc_page_read`, `cat.doc_content_match` (codes only, CHECKs on every text column), content columns on `cat.doc_content_check`, `doc_party` page / anchor / reason + method `content`, `content_flags`, `ops.requirement.best_page`, `party_alias` source `lane`, views |
| App | `src/lib/content.ts`, `/api/content`, `ContentMatches.tsx`, `ReviewClient`, `ChecklistsClient` | side panel "Matched from content, p. N–M" (codes), Match subject reason codes, Content disagrees lane + KPI, "p. N" beside the best document |

## Item 0 · measure (throwaway branch; `scripts/measure_wo06_item0.py`, extractor `cnt-3`; log `logs/wo06_item0_*.log`)
- **In scope: 16,314 documents.** K-1 12,205 PDF · 1 Google Doc · 201 Word/Excel · 2 image · 1,099 other; PCAP 2,303 PDF · 31 Word/Excel · 1 other; subscription 285 PDF · 42 Word/Excel · 1 other · 2 no file; side letter 83 PDF · 58 Word/Excel. Readable (PDF / Google Doc): 14,877. By drive: K-1 labelled scope 9,472 / no shared drive 4,022 / other 14; PCAP no shared drive 1,736 / labelled scope 587 / other 12; subscription labelled scope 242 / no shared drive 55 / D-1 33; side letter D-1 65 / labelled scope 49 / no shared drive 27 (drive names other than the labelled scope are not printed).
- **Sample: 683 documents** (200 per kind; all 83 side letters), read in 31 min.

| Kind | n | text layer | OCR used | encrypted | anchor found | high | medium | low | none |
|---|---|---|---|---|---|---|---|---|---|
| K-1 | 200 | 84.0% | 0 | 32 | 27.0% | 16 | 0 | 13 | 171 |
| PCAP | 200 | 94.5% | 0 | 11 | 86.0% | 9 | 133 | 30 | 28 |
| Subscription | 200 | 63.5% | 85 | 0 | 60.0% | 12 | 23 | 44 | 121 |
| Side letter | 83 | 92.8% | 6 | 0 | 66.3% | 0 | 26 | 27 | 30 |

- `ocr_needed` / `ocr_partial` in the sample: **0** (Tesseract installed; every scanned page was OCR'd). Too large: 1. Encrypted (password-protected) PDFs: 43 (counted, never opened).
- **K-1 anchor rate is low because most sampled K-1 "documents" are not a federal Schedule K-1 page 1:** of the 119 K-1s without an anchor, 104 carry "1065" text but only ~20 carry the Part I / II form labels (state K-1 equivalents, footnote / supplemental pages, cover letters, K-1 summaries). K-1s whose partner block names an Allegis entity (K-1s *received* by a fund from a portfolio partnership) are now recognised and kept out of the lane.
- **Precision of HIGH matches** vs portal-derived codes, person-set Subject codes and existing folder / name high matches (taken before the read): **CNT-K1-PII 8/8, CNT-PCAP-PARTNER 7/7, CNT-SUB-LBL 2/2 → 17/17 = 100%** (37 high in all; 20 had no reference to measure against). **No rule under 97%.**
- **MEDIUM candidates (lane) for the dry-run rulings:** CNT-PCAP-TOP 101/105 = 96.2% (134 medium) · CNT-SUB-TOP 12/14 = 85.7% · CNT-SL-ADDR 6/6 (26 medium). Proposed: keep all three review-only (lane) as designed; CNT-PCAP-TOP is the candidate Ryan may promote to apply (it is just under 97%).
- **Packages / bundles (sample):** K-1 bundles 6 of 200 (3%), pages median 14 / max 51, statements found ÷ roster size median 4.0; PCAP packages 2 of 200 (1%), 2 pages each. (Earlier cnt-1 pass: bundles of 55–96 pages.)
- **Checklists, effect of the sample alone** (K1-SET, PCAP-Q from FY2025; LP-SUB): K1-SET Met 48 → 48 · PCAP-Q 168 → 168 · LP-SUB Met 66 → 69, on file 56 → 62, missing 156 → 147. Projected at full scope: K1-SET ~0, PCAP-Q ~0, LP-SUB ~+4 Met (straight scaling of the sample; the dry run on main after the full backfill gives the real numbers). **Finding:** the sampled K-1 / PCAP matches mostly hit documents that are older than FY2025 or already Met through the portal (R-031), so the checklist lift the order hoped for is not visible in the sample.
- **Timing:** mean 2.33 s per document (median 0.79 s, max 60.6 s, OCR-heavy subscriptions slowest) → **backfill of 14,877 documents ≈ 9.6 h**; the nightly sees ~196 new in-scope documents a night ≈ **7.6 min** (cap 500 → at most ~19 min). Memory peak 508 MB (a 50+ page bundle), under the 489 MB-era nightly peak + headroom on a 31.5 GB machine.

## Targeted measure · FY2025-onward candidates (throwaway; `scripts/measure_wo06_targeted.py`; log `logs/wo06_targeted_20261121_1712.log`)
- Candidates: 1,066 (K-1 / PCAP with FY >= 2025 or blank FY in a roster entity, plus all subscriptions and side letters); readable 949 (K-1 304, PCAP 277, subscription 285, side letter 83). **Read in 66 min (4.15 s each)**: ok 779, no anchor 166, too large 4. Content check: FY filled 1; disagreements 22 (entity 19, FY 3).
- **Checklists before -> after, as designed** (K1-SET / PCAP-Q from FY2025): K1-SET Met 48 -> 48 · PCAP-Q Met 168 -> 176 (+8), On file 8 -> 2, Missing 1,878 -> 1,876 · LP-SUB Met 66 -> 70 (+4), On file 56 -> 62, Missing 156 -> 146. No roster unchanged (15 / 49 / 7).
- **As if CNT-PCAP-TOP were promoted** (96 medium rows simulated as high, then reverted): identical numbers (the promoted rows land on documents outside the FY2025+ rows or already Met).
- **Missing rows from FY2025 (2,221), by cause:**
  - K1-SET (345): (a) no K-1 for that entity-period in the catalog 181 (top FUNDAM 2025 25, MTV-V (MTEF) 2025 20, MTV-IV (GP) 2025 19, MTV-III (PF) 2025 14, CIP-II (GP) / MTV-IV (Annex) (GP) / X (GP) 2025 13 each) · (b2) a K-1 exists with its anchor read but no roster name for that partner 37 (MTV-IV (Annex) 15, ACCSO 8, MTV-V (A) 8) · (b3) the entity-period's K-1s carry a name of a partner of another fund 127 (CIP-II 2025 118). (b1) no anchor: 0.
  - PCAP-Q (1,876): (a) no PCAP for that entity-period 1,713 (CIP-II 2025 357 and 2026 357, FUNDAM 2025 100 / 2026 75, MTV-V (MTEF) 2025 60, ACCSO 56, MTV-III (PF) 56, IVY 52) · (b2) 119 (CIP-II 2025) · (b3) 44 (MTV-IV (Annex), MTV-V (B), MTV-IV (A) 2025-26).
  - (c) matched but not final / issued (On file): K1-SET partner unconfirmed 14, unknown 6; PCAP-Q partner unconfirmed 2.
  - The (b) split is per entity-period (any of its documents with a NOT_IN_FUND name puts the period in b3), so b3 is an upper bound. **CIP-II 2025 (118 K-1 rows, 119 PCAP rows) is one pattern worth a look:** its documents name partners that the Datum roster carries under another entity code.
- **Conclusion:** most Missing rows are documents the catalog does not have (K-1 52%, PCAP 91%), not unmatched documents. First-page reading adds +8 PCAP-Q and +4 LP-SUB Met in the FY2025+ scope; K1-SET none.

## Per-rule counts and precision
Sample (item 0): above. Full counts per rule: *at the dry run on main (full backfill).*

## Checklists before / after
Before (post CAT-WO-05): K1-SET Met 48 / On file 20 / Missing 345 / No roster 15 · PCAP-Q Met 168 / On file 8 / Missing 1,878 / No roster 49. After: *pending*.

## Review lane sizes
*Pending.*

## ocr_needed
Sample: 0. Full backfill: *at the dry run.*

## Nightly added run time
Projected from item 0: ~7.6 min a night (≈196 documents), at most ~19 min at the 500 cap. Measured: *after release.*

## Tests
- pipeline `test_wo06` 48/48 (offline, synthetic PDFs with invented names): K-1 single / bundle (page ranges), NOT_IN_FUND, MULTIPLE, medium, GP row, review-only and vetoed rules, PCAP package (period → FY/Q), PCAP top-only medium, subscription signature page, side letter Dear line, OCR of a scanned K-1 (local Tesseract, no file written), no-text → ocr_needed, unreadable → open_error, reprs carry no text, written rows hold no alias / address / TIN, no outside service, Drive read-only, logs format no text, temp folder emptied (incl. a killed run's leftover), network guard, merge rules (person / portal conflicts, package rows, lane rules), label fit, R-037 flags
- unchanged suites: label sync 34/34 (stub updated for the new `handling_raise` signature) · wo03 36/36 · wo031 12/12 · wo04 13/13 · wo05 23/23 · vitest 142/142 (wo06 5 new; review query test updated for the two new columns) · tsc clean
- DB guards `db/tests/test_wo06_guards.py` **15/15 on the throwaway**: G-S1 no new column can hold text (every text column CHECKed, no json/bytea) · G-T2 no TIN pattern in the tables · G-S2 no alias string stored, doc_page_read holds no free text · G-L1 no alias / TIN in the CAT-WO-06 and nightly logs (24 files) · G-L2 proofs · G-L3 commits (added lines and messages) · G-L4 no TIN in label state · G-D0 privileges · G-D1 security_barrier · G-SEC Secret / trashed / shortcut never in scope (16,312 files) · G-I1 a re-run over 300 read documents downloads nothing and changes nothing · G-TMP temp empty · G-P1 a person-set Subject survives, disagreement → CONFLICT_PERSON · G-P2 a person-removed flag stays removed. The alias scans look for LP / member names: aliases of the funds' own GP rows and Allegis entity / company names are left out (they are fund names printed in code and logs), and git's Author lines are not scanned (the committer identity matches a roster alias).
- pipeline `test_wo06` now 50/50 (+ anchor recorded without a name, K-1 received by an entity); network guard and memory: peak 508 MB measured in item 0

## Defaults taken (for Ryan's review)
1. **Tesseract** installed with winget's official `UB-Mannheim.TesseractOCR` package (v5.4.0), English only, run as a local process fed through a pipe; no file is written.
2. **Reader lives in the app repo** (`pipeline/pages_wo06.py`), not in `C:\DriveCatalog\drive_crawl.py` (that file is outside git and the 22:00 nightly imports it). At release, `drive_crawl.py pages --backfill | --incremental` is added as a thin mode that calls the pipeline module (release step, after the nightly).
3. **Content matches are stored durably** in a new `cat.doc_content_match` (codes, pages, reasons) because `subject_wo03` rebuilds `cat.doc_party` every night; the Subject step copies them into `doc_party` with method `content`.
4. **Which copy is read:** the primary copy when it is readable (not trashed / shortcut / Secret / noise), else another readable copy, PDFs before others.
5. **Google Docs** are exported to PDF (Drive's 10 MB export limit applies); a Google Doc's version key is its revision ID (no md5).
6. **Files over 60 MB** are counted `too_large` and not downloaded; at most 60 pages OCR'd per document (`ocr_partial` beyond).
7. **Packages:** statement starts are found from the top 35% of every page (OCR'd at 150 dpi when scanned); the start page is then read in full.
8. **Calendar fiscal years** for content FY / quarter (as the checklists already assume); a 31 Dec period end = Q4.
9. **Entity is checked, not filled:** entities come from file signals; a content entity that disagrees goes to Content disagrees; a document with no entity uses the content entity only as its roster gate.
10. **NOT_IN_FUND candidates never become `doc_party` rows** (lane only); medium / MULTIPLE roster candidates become low rows so the checklist shows "partner match not confirmed".
11. **Label text limit:** 20 codes (the DB CHECK) and 100 characters, until measured on the live label.
12. **"Corrections stick":** when a person picks one code in the lane for a content candidate, the next nightly re-reads that document and adds the anchor's name text as an alias (`ref.party_alias` source `lane`, DB only). A multi-code pick teaches nothing.
13. **Content disagrees** closes for a document on any review / edit made after the read.
14. **The fund's own GP row** is matched from content only inside a K-1's partner block.
15. **A K-1 received by a catalog entity** (its partner block names an Allegis fund / GP / SPV) gets no code and no reason and stays out of the lane.
16. **Encrypted PDFs** are counted `encrypted` and never opened (no password is tried).
17. **The extractor is versioned** (`cnt-3` now); a change to the extraction code bumps it and re-reads everything once.
18. **The DB session is kept alive** through long reads (a ping a minute) and a dropped session is reopened for the batch write (the first item-0 run lost its session to a compute restart).

## CIP-II diagnosis (throwaway, read-only)
- Datum carries a CIP-II fund roster of **119 partners** (plus CIP-II (GP) 13, CIP-I 6, CIP-I (GP) 13); no CIP-II partner sits under another entity code.
- CIP-II FY2025 K-1 / PCAP documents in the catalog: **32** (K-1 30, PCAP 2); read ok 28, no anchor 1, too large 2. Page 1 entity: CIP-II 2, none 27. Document entities: CIP-II 30, also CIP2A 12; issuing entity set on 4.
- Their partner blocks: **no roster name on 28** (NO_ROSTER_MATCH); only **2 names of another fund's partners** (2 partner codes, each on GP / fund rosters such as ASOF (GP), CIP-I (GP), CIP-II (GP), MTV-* (GP), IVY, TM). The "b3 = 118" in the targeted measure came from the per-entity-period rule (one document with such a name puts every row of the period in b3).
- **Reading: these are not CIP-II's investor K-1s** (most look like K-1s received by the fund or by its admin entity, whose partner name is a fund-name variant not in the entity aliases). **A mapping correction would move ~0 K1-SET / PCAP-Q rows**; the CIP-II 2025 investor K-1s / PCAPs (118 + 476 Missing rows) are not in the catalog.

## Dry run on main (STOP 2) · `logs/wo06_dryrun_report_main.log`, `nightly_20261122_0029_dry.log`, `nightly_20261122_0037_dry.log`
- **Read on main:** the 949 FY2025+ candidates in 50 min: ok 779 · no anchor 166 · too large 4 · OCR on 131 (subscriptions / side letters). Backlog ~13.9k left to the nightly cap.
- **By CNT rule (rows):** CNT-PCAP-PARTNER high 114 · medium 4 · NOT_IN_FUND 15 · MULTIPLE 8 · CNT-PCAP-TOP medium 96 · NOT_IN_FUND 48 · MULTIPLE 10 · CNT-SUB-LBL high 18 · CNT-SUB-TOP medium 31 · NOT_IN_FUND 29 · CNT-SL-ADDR medium 26 · CNT-K1-PII high 2 · medium 5 · NOT_IN_FUND 13 · NO_ROSTER_MATCH 266 (K-1 page read, partner not on the roster) · received by an entity 1.
- **Precision vs references taken before the read:** CNT-PCAP-PARTNER high 104/104 · CNT-SUB-LBL high 4/4 · CNT-K1-PII high 2/2 → **110/110 = 100%**. Medium: CNT-PCAP-TOP 96/96, CNT-SL-ADDR 6/6, CNT-K1-PII 5/5, CNT-PCAP-PARTNER 2/2, CNT-SUB-TOP 18/20 = 90%. No high rule under 97%.
- **Subject codes to write:** re-sync dry run → **22 files** (Subject code(s)); documents SUBJ-CONTENT 22 / SUBJ-CONTENT-LOW 16 (labelled); content-high documents 134 (all single statements); code lists too long for the label: 0.
- **Handling flags to write:** **578 files** (Contains + Tax ID on 293 labelled documents, + LP PII on 248; tier unchanged).
- **Re-sync dry run:** read 46,259 · would re-sync 590 files (subject_codes 22, Handling 578) · person-owned skipped 1 · errors 0 · peak 220 MB.
- **Lanes:** Match subject 1,311 files (164 from content, 1,147 as before); content lane documents by reason NO_ROSTER_MATCH 138 · NOT_IN_FUND 54 · MEDIUM 34 · MULTIPLE 6. Content disagrees: 3 files (16 documents disagree on entity; the rest are not labelled).
- **Checklists before -> after (all years):** K1-SET 48 / 20 / 345 / 15 unchanged · **PCAP-Q Met 168 -> 176**, On file 8 -> 2, Missing 1,878 -> 1,876 · **LP-SUB Met 66 -> 70**, On file 56 -> 62, Missing 156 -> 146 · LP-SIDE On file 9 -> 13, None found 264 -> 260 · GP-COMMIT, AUDITED-FS unchanged. Rows showing p. N: 203.

## Release log
1. 2026-11-21 22:00 nightly OK (gate; clean nightly 1 of 2 for CAT-WO-05).
2. Task "Allegis Catalog nightly" **disabled** for the release window.
3. Restore point **`pre-catwo06`** = `br-tiny-recipe-bd90no1v` (main LSN 7/1A805BF0), no compute, taken before the migration.
4. `cat-wo-06` fast-forwarded into main **locally** (not pushed, Worker not deployed: that follows Ryan's apply).
5. On main (owner): `009_wo06.sql`; `pages_wo06 --seed-rules --release` (19 provisional rules).
6. `nightly.py --only derive,checklists` from main with the pages step off: NIGHTLY OK, checklists unchanged (baseline).
7. FY2025+ candidates read on main (`release_wo06_targeted_read.py --release --apply`).
8. `nightly.py --only derive,checklists` (code 126b9c6): NIGHTLY OK; `nightly.py --only resync` (dry run): would re-sync 590, errors 0.
9. **STOP 2.** Nothing written to Drive.
- Stale `ops.nightly_run` row `nightly_20261121_1151_dry` (status running) is listed, not changed: the status CHECK has no "aborted", so marking it would need a constraint change.
- If no apply by 21:30 on 2026-11-22: re-enable the task from `app-main` at `b6d86a9` (that code runs safely on the migrated schema: the new columns are nullable, the views only gained columns).
