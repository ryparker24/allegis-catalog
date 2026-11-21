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
- pipeline `test_wo05` 22/22 (G-P1 no portal writes; G-P2a–e no names; G-P4 dates as "YYYY-MM-DD"; G-M1 batches of 2,000; mapping, periods, Issued date, kind conflicts, rules, veto)
- DB `test_wo05_guards` 10/10 on the branch (G-D0 privileges; G-D1 security_barrier; G-P2 no names in the DB / L10; G-P5 re-run changes nothing and no updated_at churn; G-P3 person Status survives; G-S1 person Subject wins; G-M1 memory)
- unchanged suites: label sync 34/34 · wo03 36/36 · wo031 12/12 · wo04 13/13 · DB wo04 11/11 · wo031 8/8 · wo03 13/13 · vitest 137/137 · tsc clean

## Release log
1. L10 **Published To** created as a DRAFT (`labels_setup_wo05.py --create-drafts --release`), Ryan-only permissions. **STOP 1: Ryan publishes in Label manager.**
