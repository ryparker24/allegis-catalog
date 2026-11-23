# CAT-WO-05 handoff · Portal postings → Issued + Published To, and Status rules

*2026-11-20 / 21. Codes, IDs and counts only: no LP, individual, file or folder names. Order: `orders/CAT-WO-05_Portal_Postings_and_Status_Rules.md`. Rulings R-030, R-031 and R-032 approved as written (Ryan).*

**Status (kept current):** built on git branch `cat-wo-05` from main `d376fa9`, tested on the throwaway Neon branch `catwo05-throwaway` (`br-dark-thunder-bdbjgkgh`, from main after the 2026-11-20 22:00 nightly). Release steps are in "Release log".

## Portal access (read-only)
- **What exists:** LP portal = Neon project *LP Portal*, schema `lp_portal` (`document`, `fund`, `investor`); GP portal = project *GP Portal* (`dry-sound-60253557`), schema `portal` (`document`, `member`, `fund`). Neither has a "posted" timestamp (see defaults 3–4).
- **Used now: the fallback.** Dated CSV exports in `C:\DriveCatalog\portal_exports\` (`lp_postings_2026-11-20.csv` 451 rows, `gp_postings_2026-11-20.csv` 1,160 rows, `gp_member_xwalk_2026-11-20.csv` 51 rows), written from SELECT-only queries. The LP file was checked against the portal with an md5 over every row (match). No partner name is in any file: LP partners are LP-#### codes, GP members are the portal's member number plus two md5 hashes of the normalized name.
- **Proposed read-only logins (Ryan's step; until then the exports are refreshed by hand).** In each portal's SQL editor:
  - LP portal:
    ```sql
    CREATE ROLE catalog_portal_reader LOGIN PASSWORD '<generate in the console>';
    ALTER ROLE catalog_portal_reader SET default_transaction_read_only = on;
    GRANT USAGE ON SCHEMA lp_portal TO catalog_portal_reader;
    GRANT SELECT (document_id, storage_provider, storage_ref, lp_id, fund_id, doc_type, period, published, loaded_at)
      ON lp_portal.document TO catalog_portal_reader;
    ```
  - GP portal (a key view so the login never reads `member`):
    ```sql
    CREATE VIEW portal.v_catalog_member_key AS
      WITH m AS (SELECT id, trim(regexp_replace(lower(display_name), '[^a-z0-9]+', ' ', 'g')) n FROM portal.member)
      SELECT id::text AS member_ref, md5(n) AS key_md5,
             md5((SELECT string_agg(t, ' ' ORDER BY t) FROM regexp_split_to_table(n, ' ') t)) AS key_sorted_md5 FROM m;
    CREATE ROLE catalog_portal_reader LOGIN PASSWORD '<generate in the console>';
    ALTER ROLE catalog_portal_reader SET default_transaction_read_only = on;
    GRANT USAGE ON SCHEMA portal TO catalog_portal_reader;
    GRANT SELECT (id, member_id, doc_type, doc_year, drive_file_id, modified_at, fund_id, period, published)
      ON portal.document TO catalog_portal_reader;
    GRANT SELECT ON portal.v_catalog_member_key TO catalog_portal_reader;
    ```
  - Then put each connection string (role `catalog_portal_reader`) in `C:\DriveCatalog\lp_portal_url.txt` / `gp_portal_url.txt`. The nightly `portals` step then writes that day's exports itself (`portals_wo05.export_from_portals`, READ ONLY session) before loading.

## Item 0 · measure (main's data on the throwaway branch; `scripts/measure_wo05_item0.py`)
- **Postings:** 1,611.
  - LP 451: capital statements (CRR) 2025 62 · 2026 294; quarterly reports 2025 10 · 2026 34; tax documents 2024 5 · 2025 46.
  - GP 1,160: capital calls 2019–2026 729 (65 / 84 / 88 / 75 / 97 / 133 / 105 / 82); K-1s 2024 148 · 2025 171; quarterly reports 2024 15 · 2025 48 · 2026 33; statements 10; carried interest agreements 3; GP legal 1; W-2 1; other 1.
- **Posted files the catalog knows:** 1,610 of 1,611 by file ID (1 GP legal file unknown). md5 adds no documents: the 2,543 md5 copies of posted files already sit in the same catalog documents.
- **Documents that become Issued: 1,550** (668 labelled), plus 22 already Issued; a person's other Status kept: 0.
  - By kind: capital call notices 729 · K-1 360 · capital statements 271 · no kind 94 · quarterly reports 47 · financial statements 38 · audited FS 7 · legal agreements 2 · tax form 1 · operating agreement 1.
  - From today's Status: blank 1,529 · Final 21.
- **Portal partners → Datum roster:** LP 76 exact / 8 unmapped (24 postings); GP 41 via the name-hash crosswalk / 2 ambiguous (8 postings) / 3 unmapped (76 postings). 1,361 documents get a mapped partner (4 of them by resolving an ambiguous member against the document's own GP entity).
- **Checklist rows that change (portal effect alone):**
  - K-1 (K1-SET): 47 rows; Met 0 → 45 (on file / unknown → Met 42, missing → Met 3).
  - PCAP (PCAP-Q): 166 rows; Met 0 → 166 (on file / unknown → Met 133, missing → Met 33).
  - Audited FS: 1 row → Met.
  - Quarterly letters and capital notices: no checklist rule exists yet, so 0.

## Status rules (R-032) · measured on the branch (`scripts/measure_wo05_rules.py`)
*(the dry-run stop repeats this on main with the checklist effect per rule)*

## Defaults taken (for Ryan's review)
1. **Access:** the read-only logins need DDL on each portal (a write), so they are Ryan's step (exact SQL above). The build uses the dated CSV fallback, written from SELECT-only queries.
2. **GP partner mapping by name hash.** The GP portal has no Datum code. The export carries md5 hashes of the member's normalized name (exact and word-order-free); the roster's names (already in `ref.party`) are hashed in memory. One hit = crosswalk; several roster codes (Datum keeps one code per relationship) → GP-roster codes preferred, then the posting's GP, then the document's own GP entity; otherwise no code.
3. **LP posted date = the portal's `loaded_at` date** (no posted timestamp exists).
4. **GP posted date = the file's `modified_at` the portal recorded** (no posted timestamp; null on 6 postings).
5. **Issued date only for timely postings:** the first posted date no later than 270 days after the period end. Bulk back-loads (e.g. 2019 capital calls loaded in 2026) are Issued with a Published To date but no Issued date: 1,014 documents get a date, 558 do not.
6. **Unpublished portal rows are not postings** (8 GP library rows).
7. **Posting IDs:** `LPD-<n>` / `GPD-<n>` (the portal's document ID), so they can't be mistaken for LP-#### partner codes.
8. **Fund map:** LP "MTV-V (EF)" = catalog MTV-V (MTEF); LS-III and FP-2026 have no catalog entity yet (postings load without an entity). Editable in `ref.portal_fund_map`.
9. **Kind conflicts:** the portals file annual / audited statements under "Quarterly Reports", so financial statements and audited FS agree with that type. Conflicts: 70 → **3 documents** (capital statement posting on a K-1 ×2, legal agreement on an operating agreement ×1). A blank catalog kind is not a conflict, and the posting does not set it (94 posted documents have no kind; a follow-up could use the posting type).
10. **Order in derive:** posted documents get Issued in the status loop (no nightly churn), the new rules fill only non-executable documents still blank after the released rules, and the posting step runs again after version families so a posted member stays Issued (Issued wins over a machine Superseded).
11. **Nightly order:** `crawl → portals → derive → readback → resync → checklists`. The partner mapping uses last night's roster (the roster loads in `checklists`).
12. **L10 is not read back** into the catalog (like L6): a person's L10 edit is never overwritten and the catalog keeps the portal's values.
13. **Status rules are seeded from code** (`portals_wo05.STATUS_RULES` → `ops.decomposition_rule`, `applies_to = 'status'`, provisional). Only provisional rows are ever re-seeded; after the dry run Ryan's vetoes set `active = false` and rulings set `provisional = false`, and the seed never touches those rows again.
14. **"Working" Status: proposed, not built.** Two rules (`ST5-WORKING`, `ST5-WORKING-KIND`) measure working spreadsheets and leave them blank; adding the choice is a Label manager change.
15. **Spot-check sheet instead of an eyeballed sample:** person-set statuses are sparse (~60), so per-rule precision against them is thin. `C:\DriveCatalog\proofs\catwo05\rule_spotcheck_*.csv` holds 25 random matches per rule (catalog ID, kind, Drive link; no names) for Ryan to open.

## Tests
- pipeline `test_wo05` 23/23 (G-P1 no portal writes; G-P2a–e no names; G-P4 dates as "YYYY-MM-DD"; G-M1 batches of 2,000; mapping, periods, Issued date, kind conflicts, rules, veto)
- DB `test_wo05_guards` 12/12 on the branch (G-S2 no duplicate Subject codes; G-P6 posted never Superseded; G-D0 privileges; G-D1 security_barrier; G-P2 no names in the DB / L10; G-P5 re-run changes nothing and no updated_at churn; G-P3 person Status survives; G-S1 person Subject wins; G-M1 memory)
- unchanged suites: label sync 34/34 · wo03 36/36 · wo031 12/12 · wo04 13/13 · DB wo04 11/11 · wo031 8/8 · wo03 13/13 · vitest 137/137 · tsc clean

## Reviews (coder + CISO, before release)
- **CISO:** (1) side-panel postings now live-checked as the user before any read; (2) `portal_exports` restricted to Ryan / SYSTEM / Administrators (the GP key hashes are unsalted md5, so treat them as names; an HMAC with a key shared with the portal view is the better long-term form); (3) every export cell is code-checked, refused by line and column without echoing the value, plus a CHECK on `fund_ref`; (4) a portal login that can write is refused before any export. Open for Ryan: the portal URL files will sit in `C:\DriveCatalog`, which (like `catalog_db_url.txt` today) grants Authenticated Users modify; (5) Find's CSV / Excel export now includes the Published To codes (intended).
- **Coder:** (1) the `portals` step never stops the nightly (a bad or missing export keeps the last loaded postings); (2) Subject codes de-duplicated (a duplicate would have made the label look person-edited); (3) the family step never makes a posted document Superseded (no nightly flip; guard G-P6); a person's Draft / Final never shows a machine Issued date. Noted: the R-032 rules apply as soon as the code runs, so the nightly stays disabled from the migration until Ryan's "apply".
- **Lapse to report:** while exploring the GP portal schema, one read-only grouping query returned the `member.interco_account` labels, which contain individual names, into this session's transcript. Nothing was written anywhere; every later query and export is codes / hashes only.

## Release log
1. L10 **Published To** created as a DRAFT (`labels_setup_wo05.py --create-drafts --release`), Ryan-only permissions. **STOP 1: Ryan publishes in Label manager.**
2. Ryan published L10; `labels_setup_wo05.py --read-published --release` → `src/lib/labels_schema.json` (commit 69f270a).
3. Disabled the task "Allegis Catalog nightly" for the release window (last run 2026-11-20 22:00, OK).
4. Restore point `pre-catwo05` = `br-gentle-darkness-bd84w7qh` (main LSN 5/ECA7D3A8), taken before the migration.
5. On main: `008_wo05.sql`; `portals_wo05.py --seed-rules --release` (15 provisional rules); `--apply --release` (1,611 postings loaded).
6. `nightly.py --only derive,checklists` from 69f270a: NIGHTLY OK.
7. Dry-run reports on main (`wo05_dryrun_report_main.log`, `wo05_rules_main.log`): 0 contradictions on every rule; re-sync dry run (`nightly_20261120_2354_dry.log`): read 46,259 · would re-sync 18,192 · person-owned skipped 0 · errors 0 · peak 233 MB. **STOP 2: Ryan vetoed none;** approved every ST5 rule as measured, including ST5-FIN-K1PDF and ST5-FIN-REPORTPDF, and accepted the 6 "vN"-tagged files that come out Final.
8. All 15 status rules ruled on main (`provisional = false`, all `active = true`). A second Claude session did this and its own release dry run (`nightly_20261121_0908_dry.log`), then ran the apply below; this session checked that no other job was running before continuing.
9. **Re-sync APPLY** (`nightly_20261121_0932.log`, code 69f270a): read 46,259 · **re-synced 18,192** · person-owned skipped 0 · **errors 0** · Entity held 1 · modifiedTime changed on 0 of 739 sampled · 6,873 s · peak 237 MB. By field: Status 18,103 · Issued date 829 · Subject codes 472 · Published To Channel 842 / Posted date 834 / Posting ID 842 · Version role 93 · Supersedes 60 (identical to the approved dry run).
10. Post-apply derive from 69f270a (`wo05_release_postapply_check_console.txt`): portal step changed 0 · cleared 0; posted documents 1,572 (Issued date 1,014 · back-load 558) · person Status kept 0 · kind conflicts 3. Readback: read 46,466 · errors 0 · 9 Status values newly set by a person on Drive (the person's value now wins). The run was stopped by the host for low memory during the follow-up re-sync **dry run** (read-only), before checklists; Ryan chose to release and let the 22:00 nightly do the re-sync and checklists.
11. Merged `cat-wo-05` into main (fast-forward), pushed, Worker deployed; `app-main` moved to the release commit; nightly task re-enabled.

**Final counts (main, 2026-11-21):**
- Catalog Status (all documents): blank 105,357 · Final 18,978 · Issued 1,702 · Draft 1,441 · Superseded 993 · In review 285. Labelled documents still without a Status: 14,335 (was 31,197).
- Portal: 1,611 postings · 1,572 posted documents · Issued date on 1,014 · Portal kind conflicts 3.
- Checklists (2026-11-20 23:49 rebuild; refreshed by tonight's nightly): Audited FS Met 31 / on file 3 · K-1 Met 48 / on file 20 / missing 345 / no roster 15 · PCAP Met 168 / on file 8 / missing 1,878 / no roster 49 · LP-SUB, LP-SIDE, GP-COMMIT unchanged.
- Restore points to delete after two clean nightlies: `pre-catwo05`; throwaway branch `catwo05-throwaway` (`br-dark-thunder-bdbjgkgh`).

**CATWO05 RELEASED b6d86a9752e72129056f390a3f882ec374abb10c** (2026-11-21): main + `app-main` on this commit, Worker version `59aa5b9f-f40e-4cc7-8895-241745dab513`, nightly task re-enabled (next run 2026-11-21 22:00 from `app-main`). This line was added in a docs-only commit after the release commit.

**Clean-up (2026-11-23):** two clean nightlies after release (2026-11-21 22:00 and 2026-11-22 22:00, both NIGHTLY OK). Neon branches deleted at 2026-11-23 07:18 UTC by the coordinator session on Ryan's approval: throwaway `catwo05-throwaway` (`br-dark-thunder-bdbjgkgh`) and restore point `pre-catwo05` (`br-gentle-darkness-bd84w7qh`). Confirmed gone from the project's branch list.
