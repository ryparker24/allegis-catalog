# CAT-WO-03.1 handoff · edits reach the catalog at once, audited FS, row search, Location

*2026-11-19. Codes, IDs and counts only: no LP, individual, file or folder names. Ryan's follow-ups to CAT-WO-03 (found live).*

**Status (kept current):** built on git branch `cat-wo-03.1` and tested on the throwaway Neon branch `catwo03-throwaway-2` (`br-hidden-bread-bdzgdudh`). Release steps are in "Release log".

## Hotfix first (on main): the label read-back crashed on the first person edit
- **Symptom:** the read-back Ryan asked for (to bring tonight's Status = Issued edits into filters and sort) stopped with `UnboundLocalError: confirms`, before writing anything.
- **Cause:** a Python scoping bug in Part 2's `label_sync_wo02.readback()`: `confirms += …` inside the nested `one()` made `confirms` local. It only runs when a person edit is found, and until tonight no read-back had ever met one (0 person-owned every run), so **every nightly read-back from now on would have crashed the same way**.
- **Fix:** `confirms.extend(…)` + regression test **G-RB1**, which runs `readback()` end to end with a Status edit. It fails on the old code with the exact production error and passes on the fix.
- Main `a3e5452` (pushed), and `C:\DriveCatalog\app-main` (the nightly's checkout) was moved to it.

## 1 · Read-back on main now (done, with the hotfix)
- `readback_20261118_232752`: read 46,259, errors 0. **Person edits found on 85 files.**
- By field: Status 69, Kind 46, Effective date 32, Period 32, Entity 14.
- **68 documents changed in the catalog:**
  - Status 52, all now **Issued**;
  - Kind 29 (26 set to Audit Report on "Annual Report" documents);
  - Effective date 32, fiscal-year period 32, Entity 14.
- Your Issued edits now drive filters and sort.

## 2 · App edits reach the catalog at once (bug)
- **Cause:** single and bulk edits wrote the Drive label and an `app.review_event`, but the catalog value that filters and sort use (`cat.document.*_confirmed`) was only set by the next nightly read-back. So the Status filter said "issued: 1" while the column (live from Drive) showed many Issued, and sorting by Status looked scrambled.
- **Fix (`006_wo031.sql`):** an `AFTER INSERT` trigger on `app.review_event` (owner, `SECURITY DEFINER`). When an event records a write Drive accepted (`labels_written` not empty), the same INSERT copies its values into the document's `*_confirmed` columns, as person-set, exactly as the read-back would:
  - kind, entities, portcos, fiscal year, period (q1–q4 / fy, the read-back's split), effective date;
  - issuing / receiving entity, Subject code(s) (`[]` stays `'{}'` = "none") and Subject (person);
  - Status, Issued date, Stage and Executed date (from the edit, or the Review form's own stage / executed-date columns).
- **Safety:**
  - `catalog_app` gains no privilege: it still only INSERTs events.
  - A value the catalog refuses never blocks the audit event: the event lands and the read-back applies the value later.
  - Guards G-A0..G-A6 (8/8), including a real `catalog_app` INSERT.
- **"Changed in Drive" marker:**
  - **Why it never showed on Status:** the comparison list (`COMPARED`) only had kind / entity / portco / FY / period / workstream / issuer / stage / tier.
  - **Fix:** it now also covers Status, Issued date, Issuing / Receiving entity and Subject code(s) / (person). Dates are compared as YYYY-MM-DD.
  - **No false markers:** fields are compared only once published, only on a file with the Allegis Document label, and only when the view selects the column.
  - **Where it shows:** every Review column (it was Stage only), and Status / Issued date / Parties in the side panel.

## 3 · Proposal: a bulk edit counts as a person confirmation, default **not** taken (a problem found)
- **The problem:** stamping Catalog Review = Confirmed (with Reviewed by) makes the read-back treat **every** field on the file as person-owned, not only the one that was set. A bulk "Status = Issued" on 500 files would then freeze kind, entity, FY, period and parties on all 500 against every future machine fix and re-sync. That's why bulk edits were built not to confirm (CISO review, CAT-WO-02).
- **What happens instead:** the bulk-set field itself is a person confirmation, field by field. It is person-set in the catalog at once (item 2), and the read-back marks just that field person-owned. Lanes that depend on that field update by themselves; for example, a file given a Status leaves Status unknown.
- A single edit still confirms the file, as before. Test: "bulk edit stays a field-level confirmation".

## 4 · Audited financial statements (Ryan)
**The CIP-I FY2025 report you named:** it is two catalog documents (22130 and 72407; not all copies are one document). Every copy was kind `quarterly_report`, no entity (the CIP-I legal-name rule was held), FY 2025, period q4, no status. That's why the row search, limited to the row's entity, found nothing.

**Measured before building** (`scripts/measure_wo031_afs.py`, main, read-only):
- 494 documents have "Annual Report" in a file name.
- Your two shapes matched 309: A 39, B 270. Today's kinds: quarterly_report 188, audit_report 121.
- **Neither shape matched any FY2024 report.** Those are named "<legal name> … 2024 Annual Report", outside `_Final Reports`. Ryan approved **shape C**: "Annual Report" + exactly one Datum legal name + one year.

**Built:**
- **New kind `audited_financial_statements`**, "Audited Financial Statements" on the Kind label. Drafted by `pipeline/labels_setup_wo031.py`, **Ryan publishes**.
- **Rule `derive_wo02.afs_rule()`**, applied after every derive by `apply_derive_wo02`:
  - **Shapes:** A, B and C as above.
  - **Exclusions:** drafts, redlines, versions, letters, covers, decks, presentations, summaries.
  - **Which documents:** only those with a machine kind among the report kinds; a person's kind is never touched.
  - **What it sets:** kind = AFS; FY = the report year (from the name, else the year folder); period = **annual**, not the "2025-Q4" folder it was filed in.
- **CIP-I legal-name rule ENT-027 / ENT-027P** ("Cyber Innovation Partners", turned on by Ryan): never when the name or folder has "II", "III" or a standalone "2". Legal names in a file name are matched as whole words, so a name nested in a longer one belongs to the longer one. Two different funds in one name stay ambiguous.
- **AUD-01 (`AUDITED-FS` v2)** accepts only `audited_financial_statements`, with an annual period (fiscal year or none, never a quarter) and Status Final / Issued.
  - `financial_statements` / `audit_report` stay candidates, shown as "not the satisfying kind".
  - A quarter reads `not_annual`.
- **Branch result** (full nightly derive end to end):
  - The rule took 277 documents: A 36, B 157, C 84.
  - **27 of the 36 AUD-01 rows now have an audited-FS best document**, including CIP-I FY2025 and every FY2024.
  - They read "on file, status unknown" until a Status is set. Ryan's Issued edits tonight are on main, not on this branch.
  - Still without one: CIP-I 2022 / 2023, IVY 2022–2024 and TM 2022 / 2023 (financial statements / audit opinion only); NL-II 2022 and X 2022 (missing).
- Tests: G-F1..G-F8 (8/8).

## 5 · Row search = the whole catalog; choosing labels the document
- **"Link another document"** searches the whole catalog (any kind, entity or year) with a Drive name search as the user. Each hit shows its kind, entity, FY, period and Location.
- **"This is the one"** (a candidate or a search hit) links the document **and** writes its labels to match the requirement, as the person (single edit = Catalog Review Confirmed):
  - **Kind:** the rule's kind (audited FS / subscription agreement / side letter / K-1 / capital statement), only once the label can hold it.
  - **Entity:** + the row's entity, kept with any others.
  - **FY and period:** the row's FY; annual for audited FS, the quarter for a PCAP.
- The values reach the catalog at once (item 2, source `checklist_link`), and the override is recorded last.
- The user must be able to open **and** label the file.

## 6 · Location (Ryan)
- **What it shows:** drive › folder path of the document's **primary copy**, from the crawl's own path data (never a label).
  - It is precomputed in `cat.document_location` by `ops.refresh_document_location()`, which runs in the migration and after every derive (nightly).
  - Precomputing keeps Find at its normal speed: a per-row lookup cost +0.4 s on every Find query.
- **Find:** a "Location" column, truncated with the full path on hover, linking to the parent folder in Drive.
  - "+N other locations" when copies sit in other folders.
  - "Path contains" filter, sortable, **Group by Location**.
- **Review queue:** the same column, sortable, with a "path contains" filter.
- **Checklists:** on candidates and on link-search hits.
- **Side panel (Find and Review):** every location of the document, each copy live-checked as the user (`/api/locations`). A copy you can't open is counted, never shown.
- **Access rule, "shown only for rows that pass the live access check, same as names":**
  - Rows reach the browser only after the live check.
  - **Group-by headers are paths too:** each group carries one of its files and is shown only if that file opens for you now. The rest are pooled as "(locations you can't open)".
  - Hidden in screenshot mode (`?mask=1`). Never logged (counts only), never written to a label.

## Tests
- pipeline `test_wo03` 36/36 · `test_wo031` 8/8 · sync `test_label_sync_wo02` 32/32 (+ G-RB1)
- vitest 119/119 · `tsc` clean
- DB guards: `test_wo031_guards` 8/8 · `test_wo03_guards` 13/13

## Release log
1. **Hotfix `a3e5452` on main** (pushed); `app-main` moved to it. Read-back re-run (item 1).
2. **Restore point** `pre-catwo031` = `br-curly-heart-bd5f7ugv` (main at LSN 2/CA591520, after the read-back, before 006).
3. **`006_wo031.sql` on main:** trigger, source `checklist_link`, ENT-027/027P, AUD-01 AFS satisfying, AUDITED-FS v2, `cat.document_location` + refresh (128,446 documents), `v_find_x` / `v_review_queue` + Location, `v_document_location`.
4. **Full derive on main with the release code** (process lesson: after the last code commit, before the dry run): `drive_crawl.derive` → `apply_derive` (audited FS **251**: A 10, B 157, C 84) → roster → subject → requirements (3,163 rows).
   - **AUD-01 on main:**
     - **met 7**: every fund's FY2024 (ASOF, CIP-II, CSOP, NL-I, NL-II, TM, X);
     - **on file, status unknown 11**: audited FS without a Status yet, incl. CIP-I FY2024;
     - **not the satisfying kind 16**: audit_report 10, which are mostly the **FY2025 reports Ryan set to Audit Report by hand tonight** (CIP-I FY2025 included), and financial_statements 6;
     - **missing 2**: NL-II 2022, X 2022.
   - Only 10 shape-A documents (36 on the branch): Ryan's bulk kind edit tonight set Audit Report on 26 "Annual Report" documents, and a person's kind is never overridden by a rule.
   - **K-1 parties also moved: K1-R3 3,189, crowded K1-R2 1,169** (was 4,520 / 841 after the CAT-WO-03 release). **Not CAT-WO-03.1:**
     - The same full derive with main's *released* code (`a3e5452`, no 006) on a copy of pre-release main (`catwo031-attrib-test` = `br-shiny-moon-bdl5tpzf`) gives K1-R3 3,172 and crowded 1,169.
     - No crawl or derive has run on main since Nov 15. Part 2's rules inserted after its derive had only ever run partially (apply_derive alone). It is the process lesson again; tonight's nightly would have made the same change.
     - CAT-WO-03.1 adds 17 K1-R3 documents through ENT-027.
5. **Labels:** `labels_setup_wo031.py --create-drafts --release` → Allegis Document: 1 unpublished Kind choice ("Audited Financial Statements"); permissions Ryan only. **STOP: Ryan publishes in Label manager.**

## Rulings of 2026-11-19 (Ryan) and how they are applied
1. **One kind, "Audited Financial Statements" (amended ruling 1).** No new kind.
   - In the pending Allegis Document draft, my separately added choice (`dc349ac2ce`, never published) was **deleted**.
   - The existing Kind choice **"Audit Report" (`33143e5d03`) is renamed "Audited Financial Statements"**, same ID. Every file carrying it updates by itself, including Ryan's 26 hand edits.
   - **STOP: Ryan publishes this one draft.**
   - **Code rename `audit_report` → `audited_financial_statements`** (`006b_wo031_rename_audit_kind.sql`, *prepared, not yet applied*: Ryan asked for any split before the rename):
     - documents (machine and person values);
     - the read-back snapshot (so the rename is not read as a person's edit);
     - KND-025 v2;
     - AUD-01;
     - `vocab.ts`;
     - after the publish, `labels_schema.json` via `labels_setup_wo031.py --read-published`.
2. **Requirement years start at each entity's first year** (the earliest `commitment_date` in the Datum roster export; Datum has no first-close date). An entity without roster dates keeps the rule's start.
   - **7 rows drop:** AUDITED-FS NL-II FY2022 and X FY2022 (both were "missing"; first commitments 2023); ATTOTUDE (first commitment 2026): K1-SET FY2025 and PCAP-Q 2025 Q1–Q4. Test G-F9.
3. **Test copies deleted:** `catwo03-throwaway-2`, `catwo031-attrib-test`. `pre-catwo03` and `pre-catwo031` kept.
4. **Nightly:**
   - Windows scheduled task **"Allegis Catalog nightly"** runs `C:\Python314\python.exe C:\DriveCatalog\app-main\scripts\nightly.py --apply` in `C:\DriveCatalog`.
   - Steps: crawl → derive → read-back → re-sync (apply) → roster / subject / requirements. Each step is logged; the run stops at the first error.
   - **When it runs:** daily **22:00**. The ThinkPad's own power history (14 days) shows it awake at 22:00 on 84% of days, against 7–18% between 01:00 and 05:00. When 22:00 is missed (asleep), it runs at the next wake. Allowed on battery, 4 h limit, never two at once.
   - **How a failed night shows:**
     1. a red-orange banner in the app ("The nightly catalog run failed at step …", or "No successful nightly catalog run since …" after 36 h);
     2. a Windows notification;
     3. `ops.nightly_run.status = failed` with the step and error class;
     4. Task Scheduler's Last Run Result ≠ 0x0;
     5. the log `C:\DriveCatalog\logs\nightly_YYYYMMDD_HHMM.log`.
   - **Safety:** a Google token that can't refresh silently fails the step instead of opening a browser.
   - **Registered DISABLED** until the CAT-WO-03.1 code is on `app-main`.

## Proposals for Ryan (kinds that overlap; nothing moved yet)
Measured on main, by document (primary copy), name patterns in memory:

| kind today | docs | what is in it |
|---|---:|---|
| `audit_report` | 339 | pdf 275 · Word 31 · **email 23** · sheet 8 · other 2. By name: "audited financial / financial statements" 291, "Annual Report" 27 (26 your hand edits), "audit report" 10, drafts / markups 6, other 5. **No engagement, representation or management letters, and no confirmations.** |
| `audited_financial_statements` (my rule, merges into the renamed kind) | 251 | pdf 119 · Word 29 · **email 103** |
| `financial_statements` with "audited" in the name | 110 | pdf 45 · **email 32** · sheet 27 |
| `quarterly_report` still named "Annual Report" (no legal name / year, or not in `_Final Reports`) | 170 | |
| `workpaper` | 1,826 | KND-042 / 044 (work papers, reconciliations, rollforwards) |
| `pbc_request` | 441 | KND-043 |

- **P1 (ruled):** `audit_report` + my temporary `audited_financial_statements` → one kind, **Audited Financial Statements** (the renamed choice).
- **P2 · emails out:** the **158 email documents** (23 + 103 + 32) are correspondence *about* the audited statements, not the statements. Move them to the existing kind **`correspondence`**, and teach KND-025 / the audited-FS rule to skip email files. Alternative: a new kind `audit_correspondence`, if you want audit mail findable on its own.
- **P3 · spreadsheets:** the 8 + 27 sheets named "audited" are workbooks. They stay or go to **`financial_statements`**, per your rule that unaudited statements and workbooks stay there.
- **P4 · Word documents (31 + 29):** drafts of the statements / annual reports. Keep them **Audited Financial Statements** with Status = **Draft**; they never satisfy AUD-01, which needs Final / Issued.
- **P5 · `financial_statements` PDFs named "audited" (45):** move to **Audited Financial Statements**.
- **P6 · rule hygiene:** drop "annual report" from KND-005 (it still sends annual reports to `quarterly_report` before the audited-FS rule corrects them). The 170 "Annual Report" `quarterly_report` documents the rule doesn't reach stay as they are until named or linked by hand.

## Nightly, run once by hand as a dry run (2026-11-19 09:12, code `84a2c56`, re-sync without `--apply`)
`C:\DriveCatalog\logs\nightly_20261119_0912_dry.log`: **NIGHTLY OK**, every step passed, 49 min.

| step | time | result |
|---|---:|---|
| crawl | 61 s | first crawl since Nov 15: new 211, changed 2,484, removed 496; live 202,248 |
| derive | 236 s | audited FS 153 (see the slip below), parties / status for 39,190 documents |
| readback | 1,341 s | read 46,431, errors 0, 0 new person edits |
| resync (dry) | 1,269 s | would re-sync 1,911 files: Issuing 1,600 / Receiving 1,604 (the K-1 parties catch-up), Entity 155, Period 148 (audited FS → annual), Effective date 34, Issuer 21, Workstream 18, Subject codes 6, Kind 3, Status 3, FY 1; 16 period changes skipped as person-owned; errors 0 |
| checklists | 48 s | 3,156 requirements (the first-year rule removed 7) |

- **Slip, found and fixed in the same session:** preparing the rename, I had already removed `audit_report` from the audited-FS rule's source kinds. 006b isn't applied yet, so KND-025 still sets `audit_report`, and 98 reports, the FY2024 ones among them, were no longer converted: **AUD-01 Met fell 7 → 0** in this run.
- Restored (`audit_report` stays a source kind until 006b renames it; harmless after). Derive + checklists were re-run on main: audited FS 251, **AUD-01 Met 7**, on file without a status 11, not the satisfying kind 16.
- The re-sync plan above was computed on the slipped state. The CAT-WO-03.1 dry run after the publish is the one that counts.
