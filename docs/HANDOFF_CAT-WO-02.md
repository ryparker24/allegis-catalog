# CAT-WO-02 handoff · Datum look, Datum lists, new label fields, two-way label sync

*2026-11-17. Codes, IDs and counts only: no LP, individual or file names. Rulings R-021…R-024: Ryan accepted the defaults.*

**Status (draft, kept current):**
- **Part 1** is built and reviewed on branch `cat-wo-02` (`f408e52`). It is held for the CAT-WO-01.1 hotfix, per Ryan: it must ship with the hotfix commit, and the Review screen is built on top of the fix.
- **Part 2** is built on `cat-wo-02-p2` against the throwaway branch only. Nothing is published, nothing is deployed, and the only Drive writes were the pilot-file guard tests, each restored.

Throwaway Neon branch: `catwo02-test-throwaway` = `br-red-band-bd2d79yz` (endpoint `ep-billowing-truth-bdj6gzs7`) on `curly-sunset-06555843`, taken from main at 2026-11-17 22:58 UTC. Main was never written.

---

## Part 1 · screens (items 1–4)

### What was built
- **Datum family look (item 1).**
  - Tokens are copied, not linked, from Datum Core's `src/app/globals.css` and `packages/finance-ui/src/tokens.css`, and the Allegis wordmark and emblem SVGs were copied from its `public/` folder (R-024; read only).
  - The rail is dark, with the brand, CATALOG in green small-caps mono, a collapse control, Find, Review queue with an open-count badge, and Gaps greyed out as `R-006`.
  - Saved views sit in the rail as a tree with a PINNED group.
  - The top bar is dark, with search (`/` focuses it), Labels and the avatar.
  - The page header has a mono breadcrumb, a serif title with an ⓘ chip, a green primary button, white secondary buttons and a `…` menu.
- **Find.**
  - Datum filter bar: a Filters toggle, "No filters / N filters", and mono field captions.
  - Active-filter chips.
  - Columns / Download CSV / **Download Excel**.
  - Row checkboxes and an Actions menu, empty until Part 2.
  - Per page 10 / 25 / 100 with page buttons and "1–25 of N files".
  - Kept from v0.1: the "N not shown (no access)" count, the Drive preview panel, the Handling badge and the Review status column.
- **Lists (item 2).**
  - Columns can be resized (drag the edge), reordered (drag the header) and sorted (server-side, ↕ ↑ ↓).
  - Each header has a filter by type: a code multi-select for pick-lists, from/to for years and dates, contains for text, and yes/no/any for flags.
  - Widths, sort, order, visibility and filters are saved with a view. The last state is remembered per user in `app.user_pref`; search text is never stored.
- **Labels panel (item 3).**
  - Built from `labels_schema.json` plus vocab plus `ref` through the app views. It is read-only.
  - It lists every label and field in plain words with every choice as code and meaning (`k1` → K-1), and tags each field as Editable / Machine-set / Read-only.
- **Folders (item 4).**
  - `app.view_folder` (owner, name, parent, sort order), plus `saved_view.folder_id` and `.pinned`.
  - Two levels at most, enforced in the database by a trigger that locks the parent row.
  - Create, rename, delete-only-when-empty, drag-drop and "Move to…", pin.
  - Seed folders: Tax (K-1s TY2025); Agreements (ACCSO subscription docs, Unsigned side letters); Close (MTV-II FY2025 close). Migration 003 also files Ryan's existing seed views on main into them.

### Reviews (designer + coder) and what changed
- **Designer:** 4 must-fix, 9 should-fix and 4 nits; all fixed except #12 (Review counter-card markup), which waits for the hotfix. Fixes:
  - rail menus moved to fixed position, so they are no longer clipped;
  - one menu per pinned copy of a view;
  - green focus rings on the dark chrome;
  - a keyboard-usable tree;
  - "Editable after Part 2" tags;
  - focus trap in the drawer;
  - the real wordmark;
  - phone-width rail;
  - contrast fixes.
- **Coder:** 2 defects and 11 minor/notes. Fixes:
  - Excel export capped at 10,000 rows (413 → use CSV), so the Worker can't run out of memory;
  - popovers no longer reopen when you click their own trigger;
  - rename commits once;
  - saving over a view also moves its folder;
  - stored specs never keep search text;
  - prefs size limit;
  - seeding races;
  - Drive name-search failures fall back to codes only;
  - the start-up race;
  - Find follows a rename or delete made in the rail.
- **Tests:** 65/65 unit tests on `cat-wo-02`, `tsc` clean, and DB guard checks 25/25 on the branch (privilege matrix extended for `view_folder` and `user_pref`).

### Deviations / notes (Part 1)
- **Datum source vs the order.** Datum's local source has no serif title, no green primary button, no top-bar search and no pinned group. The order asks for these from Ryan's screenshots of the deployed site, so the order wins: the serif is Faculty Glyphic (Allegis brand serif) and the primary button is #43EF8C with dark text (contrast about 11:1).
- **Name search.** Names are not in the catalog DB (privacy rule), so the top-bar search finds names through a Drive `files.list` run as the user. It returns IDs only, capped at 2,000, and Find says so when the cap is hit.
  - Codes and kind meanings are searched in SQL.
  - Drive's `name contains` matches word prefixes, not any substring.
- **Shared components.** `SidePanel` was restyled and `client.ts` gained review-status display. The Review page uses both; its page and server code are untouched.
- **Local proofs.**
  - `scripts/dev_proxy.ts` (local only) injects a session minted in memory from Ryan's local token, so the real Worker can be screenshotted with names masked (`?mask=1`). It rewrites Origin, so it must never face a network.
  - My local Worker ran on :8797/:8798, because another tab's Worker was already on :8787.

### Pending (blocked on CAT-WO-01.1)
- Review queue screen: Datum counter cards (caption, big number, one-line explanation), Datum list behaviour on the queue, and screenshots.
- Rebase onto main, then `git merge-base --is-ancestor <hotfix sha> HEAD` (quoted at release), deploy, and `CATWO02-P1 RELEASED <sha>`.

---

## Part 2 · labels and data (items 0, 5–9) — built on `cat-wo-02-p2`, not released

### Item 0 · measurements (read-only; counts only; branch = main as of 22:58 UTC)
**0.1 K-1 parties.** 7,216 labelled K-1s.
- **Before:** 0 issuing / 0 receiving (the fields don't exist).
- **Rules** (`pipeline/derive_wo02.py`):

  | Rule | What it reads | Issuing | Receiving | K-1s |
  |---|---|---|---|---:|
  | K1-R3 issued to LPs | a K-1 container folder (K-1s / tax returns / investor package) holding ≥3 K-1s, one fund/SPV on the file | the fund/SPV | `LP` | 3,042 |
  | K1-R2 GP's K-1 from its fund | "GP entities" / "GPs" folders, or a GP-only entity outside a many-K-1 folder | the GP's fund (`X (GP)` → `X`) | the GP | 309 |
  | K1-R2, fund ambiguous (e.g. MTV-IV (GP): A or B) | same | blank | the GP | 143 |
  | K1-R1 management company received | "Mgmt Co / … Investments in …" | — | — | 0 (see proposal P-K1 below) |
  | unknown → Review queue | | blank | blank | 3,722 |

- **After** (applied on the branch, counted per file through `app.v_find_x`, so copies of a K-1 count too):
  - issuing set 3,385 · receiving set 3,527 · both 3,385, out of 7,216;
  - issuing by type: fund 3,233, SPV 118;
  - receiving: LP 3,042, GP 452.
- **Why lower than the first count** (3,660 / 4,010): the coder review asked that a GP-only file in a folder holding many K-1s not be read as "received". Such a folder may be a GP issuing K-1s to its own members, so those files now stay unknown.

**0.2 Status markers.** Measured on the 46,259 labelled files. Markers use letter boundaries, so `Report_FINAL` and `Draft_v2` are caught.

| Marker | Files | Top kinds |
|---|---:|---|
| name "final" | 3,396 | k1 1,398 · (none) 737 · tax_return 439 · tax_form 381 · correspondence 201 |
| folder "Final" | 1,403 | (none) 844 · quarterly_report 149 · tax_return 104 · k1 103 · tax_form 95 |
| name "draft" | 1,254 | (none) 523 · k1 220 · tax_return 179 · tax_form 147 · correspondence 121 |
| name "v2 / ver 2 / rev 3" | 477 | (none) 242 · k1 118 · pbc_request 30 · valuation_memo 22 · financial_statements 20 |
| name "signed / executed" | 538 | (none) 204 · legal_agreement 58 · tax_form 50 · tax_return 48 |
| folder "Drafts" | 385 | (none) 165 · tax_form 51 · k1 50 · tax_return 49 |
| name "redline / blackline" | 42 | lpa 14 · (none) 9 · subscription_agreement 8 |
| name / folder "issued" | 1 | (none) 1 |

Resulting Status:
- **Final 5,611**, of which 696 are fully executed agreements (R-022: fully executed implies Final).
- **Draft 1,348.**
- **In review 356.**
- **Issued 1.**
- **Conflicting markers (draft with final): 51**, left blank and routed to Review.
- **No marker: 38,892**, left blank.
- Executable kinds only ever get Final, and only when fully executed. Their signing progress stays in Stage.
- **Version-marker fix:** the first count (1,040 files) also matched roman-numeral fund names such as "MTV-V 10.31.24". The marker now needs "v" fused to the number ("v2", "v3.1") or "ver" / "rev".
- **Set on the branch:** Status on 7,252 files (per file, through `v_find_x`).

**0.3 Label drift since release.** All 46,259 labelled files were read live (Drive 200 for all 46,259, 420 s):
- every one still carries the Allegis Document label;
- Catalog Review is "Needs review" with no reviewer on all 46,259;
- live ≠ machine-expected = **0 on every field** (kind, entity, portco, fiscal year, period, effective date, workstream, issuer, stage, executed date, tier, contains).

So the read-back's first run has nothing person-set to pick up.

**0.4 Re-sync size.**
- **0 today.** `ops.run` shows no incremental crawl since the full crawls of 11-15, and every labelled document was last updated before the bulk label run finished. So no catalog value has changed since labelling.
- **Once Parties and Status are published**, the re-sync pushes the new values: issuing 3,385 · receiving 3,527 · status 7,252 files (branch-derived).
- **Note:** the "nightly `drive_crawl.py incremental`" has never run. Ryan may want to schedule it.

### What was built (Part 2)
- **R-021 / R-022 data:**
  - `db/migrations/004_wo02_part2.sql` adds `cat.document` issuing / receiving / status / issued-date `*_auto` and `*_confirmed`, plus entity/portco `*_confirmed`.
  - It also adds `ops.label_state` (the read-back's memory: last machine write, last live read, person-owned fields) and `ops.label_sync_run` (per-run report).
  - `app.v_find_x` is `app.v_find` (secret tier excluded there) plus the new fields; Find, facets, export and group-by read it.
  - `review_event` gains `source` and `edits`.
  - Applied twice on the branch (idempotent).
- **Labels (item 5/6):** `pipeline/labels_setup_wo02.py` designs L11 Parties and Status & Execution through the labels_setup.py flow. Only `--check` was run (output below); nothing was created or published.
- **Derivation:** `pipeline/apply_derive_wo02.py` writes `*_auto` only (a person's `*_confirmed` always wins). It ran with `--apply` on the branch. No-kind rules run only with `--nokind-ruled`, after Ryan's ruling.
- **Find (items 5/6):** Issuing entity, Receiving entity, Status and Issued date columns, header filters, facets and export.
- **Labels panel:** Parties and Status / Issued date appear as "Not published yet" with their full choice lists. Issuing has 184 choices: 37 entities, 146 portcos and EXTERNAL. Receiving has 39: 37 entities, LP and EXTERNAL.
- **Edit in the app (item 8).**
  - Single edits run from Find's side panel (`EditForm`).
  - Bulk edits run from **Actions → Set kind / entity / fiscal year / status…**, with a preview showing the count and the change, a confirm step, and a done / skipped / failed report.
  - Server flow (`src/lib/edit.ts`, `editflow.ts`):
    1. Check the request against the R-023 fields.
    2. Check the file is in catalog scope (`v_find_x`).
    3. Check access live as the user (opens, `canModifyLabels`, live tier not secret).
    4. Write `modifyLabels` as the user.
    5. For a **single** edit only, set Catalog Review to Confirmed with Reviewed by.
    6. Insert one `app.review_event` row per file: `confirmed` for single edits, `edited` for bulk.
  - Bulk is capped at 500 and writes in batches of 25 with the labels_sync.py retry rules.
  - Bulk audit rows are written after each batch, and a retry budget of 100 keeps a job within the Worker's subrequest limit.
  - Bulk does not stamp Confirmed. Stamping it on 500 unreviewed files would freeze every field on them against the re-sync (CISO review). The bulk-edited field is still protected, because it now differs from the machine write.
  - Handling is never written, and any Handling key in a request is refused.
  - Parties / Status are refused until published.
- **Two-way sync (item 7):** `pipeline/label_sync_wo02.py`.
  - `readback` reads labels for every in-scope file and stores a person's values as `*_confirmed`.
    - A value counts as the person's if live ≠ the last machine write (set or cleared), or if Catalog Review is Confirmed or Wrong with Reviewed by.
    - On first sight of a file, its machine snapshot is seeded from its live labels, so stale catalog values are never taken for edits.
    - A second edit to an owned field is captured too.
    - Secret-tier files are dropped, and unknown Drive choices are skipped and counted.
    - It keeps `ops.label_state` and refills `app.labelled_file` from Drive.
  - `resync` writes only files the read-back has already seen, and refuses to run without that state.
    - It re-reads and re-plans each batch just before writing it, so an edit made mid-run wins.
    - It never overwrites person-owned fields (skipped and counted) or secret-tier files.
    - It uses the same batching, capped retry and modifiedTime sampling as labels_sync.py.
    - A re-run simply recomputes the difference, so it is safe to resume.
  - Both need an explicit `--db-url-file`, so they can never pick up main by default. Both stream Drive results per batch, which keeps memory flat.

### Guard tests (Part 2)
- **G-E1 `test_edit_writes_only_allowed_labels`** (`test/wo02_part2.test.ts`):
  - an edit touches doc / exec / review only, never Handling;
  - a Handling key (`tier`, `Handling`, `contains`, `lp_pii`, `pii_lp`) is refused before any Drive or DB call;
  - unknown fields, bad codes and an executed date without "fully executed" are refused;
  - Parties / Status are refused until published.
- **G-E3 `test_bulk_respects_500_cap`:**
  - 501 files are refused before anything is read or written; 500 previews;
  - bulk offers only kind / entity / fiscal year / status;
  - a confirmed bulk skips no-access and out-of-scope files and retries a 503;
  - a 403 counts as no access and is not retried.
- **Unit totals:** `npx vitest run` → **79 passed (79)**; `py pipeline\test_label_sync_wo02.py` → **22/22 passed**.
  - The pipeline set includes: a person clearing a value isn't re-filled; a file marked Wrong isn't re-synced; a stale catalog value isn't taken as person-owned on first sight.
- **G-E2 modifiedTime after a single and a bulk edit.** Live on ONE pilot-folder file through the app's own `editOne` / `editBulk`; review events on the branch; restored afterwards.
  - Re-run on the post-review code: bulk no longer touches Catalog Review, so AFTER2 still shows the Confirmed set by the single edit just before.
  - The script now accepts only the throwaway endpoint (an upper-cased main endpoint → `refusing: not the throwaway branch endpoint`) and restores in a `finally`.
```
BEFORE   {"file_id":"180DfKiZCFvBptMVPfYEzyQsETkbBkmtw","modifiedTime":"2023-08-14T23:01:09.192Z","kind":"subscription_agreement","fiscal_year":null,"entities":["ACCSO"],"stage":"fully_executed","tier":"normal","review_status":"needs_review"}
SINGLE   {"http":200,"ok":true,"labels":["doc","review"]}
AFTER1   {"modifiedTime":"2023-08-14T23:01:09.192Z",...,"fiscal_year":2020,...,"review_status":"confirmed"}
BULK     {"http":200,"report":{"done":1,"skipped_no_access":0,"skipped_check_failed":0,"skipped_not_in_scope":0,"failed":0,"events_failed":false}}
AFTER2   {"modifiedTime":"2023-08-14T23:01:09.192Z",...,"fiscal_year":2019,...}
RESTORE  {"http":200}
FINAL    {"modifiedTime":"2023-08-14T23:01:09.192Z",...,"fiscal_year":null,...,"review_status":"needs_review"}
PASS  G-E2 modifiedTime unchanged by the single edit, the bulk edit and the restore: 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z
PASS  G-E2 restore: Allegis Document / Execution / Catalog Review fields identical to BEFORE
PASS  G-E2 Handling label untouched throughout
```
- **G-E4 `test_edited_value_not_overwritten_by_resync`.** Unit (22/22 above), plus live on the same pilot file.
  - The app set fiscal year 2020; the catalog has it blank.
  - The real `--resync` ran on the post-review code, after the first applied read-back (it now refuses to run without one).
```
EDITED   {"http":200,"modifiedTime":"2023-08-14T23:01:09.192Z",...,"fiscal_year":2020,...,"review_status":"confirmed"}
RESYNC DRY RUN (nothing written): read 1 · confirmed by a person 0 · re-synced 0 · skipped as person-owned 1 · errors 0
RESYNC APPLIED: read 1 · confirmed by a person 0 · re-synced 0 · skipped as person-owned 1 · errors 0   (by field: skipped_person fiscal_year 1)
RESTORE  {"http":200,"modifiedTime":"2023-08-14T23:01:09.192Z",...,"fiscal_year":null,...,"review_status":"needs_review"}
PASS  restored to BEFORE (fields identical, modifiedTime 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z)
```
- **Per-run sync report** (item 7.3, throwaway branch, `ops.label_sync_run`):
```
READBACK APPLIED: read 46,259 · confirmed by a person 0 · re-synced 0 · skipped as person-owned 0 · errors 0
  labelled 46,259; read but without the Allegis Document label 0      -> app.labelled_file: 46,259 rows, source drive_readback
RESYNC APPLIED (--only pilot): read 1 · re-synced 0 · skipped as person-owned 1 (fiscal_year) · errors 0 · never read back 0
```
- **labels_setup check** (`py pipeline\labels_setup_wo02.py --check --db-url-file <branch>`):
```
limits: 10 fields per label, 200 choices per field   (limits endpoint 400 -> documented limits, as in labels_setup.py)
existing labels: Allegis Document, Catalog Review, Execution, Handling
Parties (L11): not created - issuing 184 choices (37 entities + 146 active portcos + EXTERNAL), receiving 39 choices (37 entities + LP + EXTERNAL)
Execution: 3 fields now; + Status (5 choices) + Issued date = 5; title -> 'Status & Execution'
design check: OK
--check: nothing created, nothing published.
```

### Reviews (coder + CISO, Part 2)
Both reviews ran read-only on `f408e52..cat-wo-02-p2`. Each finding and its fix is in commit `4204e57`.
- **CISO: no high-severity findings.** Fixed:
  - the re-sync re-plans per batch (a mid-run edit could be overwritten);
  - bulk audit rows per batch, plus a retry budget;
  - bulk no longer stamps Confirmed;
  - name words checked before the allow-list in masking;
  - `Object.hasOwn` on choices;
  - secret tier skipped;
  - unknown choices skipped;
  - a Parties code-only CHECK;
  - one generic `no_access`;
  - guard-script allow-list and `finally`;
  - a read-only fallback session.
  - Left as info: bulk has no per-user rate limit beyond the 500 cap (Ryan is the only user).
- **Coder: 7 defects, all fixed.**
  - Find was reading `v_find` with the new columns, so every request returned 500.
  - The first read-back seeding (above).
  - Second edits were not captured.
  - Clearing a value was undone.
  - An executed date alone was refused even on fully executed files.
  - Unknown choices were stored.
  - An idle connection was held through the long Drive read.
  - Minors also fixed: capped retries, re-sync needs state, mtime counts recorded, derive writes only changes and clears non-K-1 parties, the version-marker false positive, the K1-R2 gate, and regex sentinels.
  - Carried to the Review-queue work after the hotfix:
    - app edits must not take files out of the queue unless they are `confirmed` / `wrong`;
    - the Review form must route through the same executed-date and unset rules.
- **Not changed (by design / noted):**
  - A person's *blank* is kept on the label and protected from the re-sync. The catalog still shows the rule value until a reviewer sets a value, because `*_confirmed` NULL falls back to auto.
  - Period `month` / `as_of` / `n_a` has no catalog column, so it is kept on the label only.

### For Ryan to rule on (nothing below is applied)
**Item 9 · proposed no-kind rules** (F-018). 18,417 no-kind labelled files. First match wins, in this order. Counts are the files each rule would set.

| Rule | Sets kind | Would set | What it reads |
|---|---|---:|---|
| NK01 | k1 | 3,289 | a folder named for K-1s (e.g. `…/<FY> K-1s from PwC/…`, `…/Final K-1s/…`) |
| NK02 | invoice | 255 | "invoice" / "inv #" in the name |
| NK03 | bank_stmt | 664 | "statement" in the name, inside a `…Statements` folder (e.g. `…/Mgmt Co/…/<x> Statements/<FY>/`) |
| NK04 | tax_form | 467 | a tax-form number (1042, 1099, 8804/8805, W-9/W-8, 7004, 8868) or "extension" in the name |
| NK05 | tax_return | 274 | 1065 / 1120 / 990 / "return" in the name, inside a `…Tax Returns…` folder |
| NK06 | valuation_memo | 620 | "valuation" / 409A in the name |
| NK07 | quarterly_report | 816 | "report" in the name, inside a `…Reports…` folder |
| NK08 | receipt | 11 | "receipt" in the name |
| NK09 | wire_confirmation | 39 | "wire" in the name |
| NK10 | capital_call_notice | 0 | "capital call" in the name |
| NK11 | distribution_notice | 0 | "distribution notice" in the name |
| NK12 | workpaper | 528 | inside a `…Workpapers…` or `…PBC…` folder |
| — | stays no-kind → Review | 11,454 | |

After the ruling: `py pipeline\apply_derive_wo02.py --db-url-file <db> --apply --nokind-ruled NK01,…`, then `--resync`, then report the no-kind count before and after.

**P-K1 · management company K-1s** (the "Mgmt Co / … Investments in …" folders, 407+ K-1s). The files carry no single manco entity, so K1-R1 sets nothing. If Ryan names the management company those folders belong to, a rule can set receiving = that manco and issuing = the fund on the file.

### Deviations / notes (Part 2)
- **Item 7 hooks.** The read-back and re-sync live in the repo (`pipeline/`). The order names `drive_crawl.py incremental` and `labels_sync.py --resync`, but those scripts sit outside the repo and connect to main through `catalog_db_url.txt`, so wiring them in now would have written to main before release. They are called from those scripts at release (R-steps).
- **Labels not published.** Parties and the Status / Issued date fields are not created or published (Ryan's instruction). Until they are:
  - the app refuses edits to those fields (`label_not_published`);
  - Find shows their catalog values instead of live label values;
  - the re-sync skips them.
- **Item 6 / 8 Review pieces deferred** until the hotfix is on main: the Review queue's "Status unknown" lane, and Stage-or-Status in the Review form.
- **One read on main.** The labels_setup check's first run read `ref.entity` / `ref.portco` codes from main through `drive_crawl.db()` (read-only). It now takes `--db-url-file` and was re-run against the branch with the same result.

### Appendix A · item 9, top 50 folder paths among no-kind files (codes and generic words only)

| Files | Folder path |
|---:|---|
| 875 | `…/finance * allegis accounting/mgmt co/*/*/* statements/<FY>/*/` |
| 273 | `…/finance * allegis accounting/vendors/*/` |
| 247 | `…/finance * allegis accounting/vendors/*/<FY>/` |
| 225 | `…/finance * allegis accounting/vendors/* old ap files/ap <FY>/*/` |
| 202 | `…/finance * allegis accounting/vendors/* old ap files/ap <FY>/ap */` |
| 173 | `…/finance * allegis accounting/legal/* entities <FY> */<ENT:MTV-V (A)>/lp */*/` |
| 162 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/` |
| 143 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* 1s from pwc/<ENT:MTV-I> * 1s/` |
| 133 | `…/finance * allegis accounting/systems and gl/*/*/` |
| 129 | `…/finance * allegis accounting/mgmt co/payroll/<FY>/` |
| 122 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* 1s from pwc/<ENT:MTV-V (MTEF)> iii * 1s/` |
| 117 | `…/finance * allegis accounting/taxes/<FY>/<FY> final * package/<ENT:CIP-I> ii <FY> */` |
| 102 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* 1s from pwc/<ENT:MTV-V (MTEF)> ii * 1s/` |
| 88 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/<FY> q3/valuation/` |
| 87 | `…/finance * allegis accounting/audit/<FY> audit/*/` |
| 84 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/tax returns final/<ENT:CIP-II>/*/` |
| 82 | `…/finance * allegis accounting/mgmt co/<FY>/*/` |
| 70 | `…/finance * allegis accounting/legal/* agreements/<FY> to <FY>/` |
| 69 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/<FY> tax returns final/<ENT:MTV-III (MTEF)>/<ENT:MTV-V (MTEF)> iii <FY> * ups/` |
| 66 | `…/finance * allegis accounting/vendors/* old ap files/ap <FY>/*/*/` |
| 64 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/<FY> q4/annual report covers/` |
| 64 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/<FY> q4/valuation/*/` |
| 61 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/annual report covers/` |
| 61 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/*/` |
| 60 | `…/finance * allegis accounting/vendors/*/<FY>/*/` |
| 58 | `…/finance * allegis accounting/valuation/<FY>/valuation support q4 <FY>/*/` |
| 57 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/` |
| 57 | `…/finance * allegis accounting/mgmt co/*/* investments in */* investments <FY>/*/` |
| 56 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* files/* files updated by allegis/` |
| 56 | `…/finance * allegis accounting/systems and gl/*/*/* of * <FY>/` |
| 55 | `…/finance * allegis accounting/vendors/*/* backups * <FY>/* files/* <ENT:MTV-V (MTEF)> v * files/letters templates/* letters/` |
| 55 | `…/finance * allegis accounting/taxes/<FY>/* and */` |
| 54 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* 1s from pwc/*/` |
| 51 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/<FY> q2/valuation/gp */` |
| 49 | `…/finance * allegis accounting/vendors/* old ap files/ap <FY>/` |
| 48 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/tax returns final/<FY> * 1s by */*/` |
| 48 | `…/finance * allegis accounting/systems and gl/*/*/* <FY>/` |
| 47 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/<FY> tax returns drafts/` |
| 47 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* 1s from pwc/<ENT:MTV-I> iii * 1s/` |
| 45 | `…/finance * allegis accounting/vendors/* bank/*/* <FY> */` |
| 45 | `…/finance * allegis accounting/taxes/<FY>/form 1042/final package/<ENT:CIP-I> ii lp <FY> */` |
| 43 | `…/finance * allegis accounting/* reports/<FY> <FY>/<FY>/<FY> financial reporting/<FY> q2/valuation/` |
| 43 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/tax */` |
| 42 | `…/finance * allegis accounting/vendors/*/q2 <FY> */* <FY>/` |
| 42 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/<FY> allegis partners */*/` |
| 41 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/* files/* files from pwc */` |
| 41 | `…/finance * allegis accounting/mgmt co/*/*/* statements/* <FY> <FY>/<FY>/*/` |
| 41 | `…/finance * allegis accounting/* reports/<FY> q3/report letters/archive/` |
| 41 | `…/finance * allegis accounting/taxes/<FY>/tax returns final pwc */1042/allegis capital * lp */<ENT:CIP-II>/` |
| 41 | `…/finance * allegis accounting/taxes/<FY> <FY>/<FY>/<FY> tax returns final/<ENT:MTV-V (MTEF)>/<ENT:MTV-V (MTEF)> v <FY> * cutups/` |

### Appendix B · item 9, top 50 name patterns among no-kind files

| Files | Name pattern |
|---:|---|
| 1,383 | `*` |
| 644 | `* statement _ <FY> - * - * _ *` |
| 600 | `* - *` |
| 140 | `* _ *` |
| 128 | `<FY> - <ENT:MTV-I (GP)> iv - *` |
| 111 | `* - * iii - *` |
| 109 | `* <FY> - * - *` |
| 99 | `* - * - *` |
| 95 | `<FY> - <ENT:MTV-I (GP)> v - *` |
| 73 | `<ENT:MTV-I> iv - * report *` |
| 71 | `<FY> - <ENT:MTV-V (MTEF)> v - *` |
| 70 | `invoice _ <FY> _ * _ * _ from _ *` |
| 66 | `<FY> - <ENT:MTV-I (GP)> iv annex - *` |
| 64 | `* _ * _ *` |
| 64 | `<FY> - <ENT:MTV-I (GP)> iii pf - *` |
| 64 | `* ( * )` |
| 61 | `<FY> - * - *` |
| 60 | `<ENT:MTV-I> v - * - * - *` |
| 58 | `payroll _ * - *` |
| 56 | `* report *` |
| 55 | `* - * export * - * - <FY>` |
| 50 | `allegis capital - <FY> - ca *` |
| 48 | `* q4 - <FY>` |
| 46 | `<FY> - * partners ii lp - *` |
| 42 | `* _ * _ * _ *` |
| 41 | `<FY> - allegis * - *` |
| 40 | `valuations ( * )` |
| 39 | `<ENT:MTV-I> iii funds * - * - * valuations` |
| 39 | `allegis capital * extension *` |
| 38 | `allegis * - <FY> - * - * report` |
| 37 | `<ENT:MTV-II> funds * - * - * valuations` |
| 37 | `<ENT:MTV-I> iii * report *` |
| 36 | `<ENT:MTV-I> iv - * report * annual` |
| 36 | `<FY> - <ENT:MTV-I> iii pf - *` |
| 36 | `* , * - *` |
| 35 | `<ENT:MTV-V (MTEF)> iii * report *` |
| 35 | `* - * report - * <FY>` |
| 34 | `allegis *` |
| 34 | `<ENT:MTV-I> * funds * - * - * valuations` |
| 34 | `<ENT:MTV-I> iv funds * - * - * valuations` |
| 32 | `<FY> - <ENT:MTAV> v - *` |
| 31 | `<ENT:MTV-I> v - * report *` |
| 30 | `* - ( allegis * iii * ) - ( * )` |
| 30 | `* _ * _ * - * _ <FY> _ ca _ *` |
| 30 | `* _ * _ * - * _ <FY> _ * _ *` |
| 30 | `* <FY> *` |
| 30 | `<FY> - <ENT:MTV-I (GP)> iv annex - * , *` |
| 30 | `<FY> - allegis capital management company , llc - *` |
| 29 | `* - - * - * - * - - * - * - * - - * - * - - * - - * - *` |
| 28 | `<ENT:MTV-V (MTEF)> v * report *` |

