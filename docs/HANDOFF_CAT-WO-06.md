# CAT-WO-06 handoff · First-page reading (K-1s, PCAPs, subscriptions, side letters → Datum partner codes)

*2026-11-21. Codes, IDs and counts only: no LP, GP member, employee or file names, no page text, no TINs. Order: `orders/CAT-WO-06_First_Page_Reading.md`. Rulings R-033 – R-038 proposed with defaults; Ryan can veto any at the dry-run stop.*

**Status (kept current):** built on git branch `cat-wo-06` from main `31880e0` (= `b6d86a9` + the docs-only RELEASED line), one squashed commit (an earlier commit carried an invented TIN-shaped test value; the branch was never pushed). Tested on the throwaway Neon branch `catwo06-throwaway` (`br-misty-paper-bd23sm4c`, endpoint `ep-spring-unit-bds6x67g`, from main at 2026-11-21 20:54, created by Ryan / the coordinator on Ryan's approval). Migration 009 ran twice (idempotent), 19 CNT rules seeded. **Ready for main, waiting on the 2026-11-21 22:00 nightly** (nothing has touched main, Drive labels or the portals).

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

## Release log
*Not started: waits for the 22:00 nightly and the coordinator's go.*
