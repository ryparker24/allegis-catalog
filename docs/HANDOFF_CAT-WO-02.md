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
- **Labels panel:** Parties and Status / Issued date appear as "Not published yet" with their full choice lists. Issuing has 183 choices: 36 active entities (CYBER-II retired), 146 portcos and EXTERNAL. Receiving has 38: 36 entities, LP and EXTERNAL.
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

### Review queue pieces (items 6 and 8, built after the CAT-WO-01.1 rebase)
- **Only a review takes a file out of the queue.** `app.v_find.reviewed` now counts only `confirmed` / `wrong` events, so a bulk edit (`edited`) leaves the file in the queue. "Reviewed today" / "reviewed total" count reviews only. This is in 004, which restates `security_barrier`: a first run without it dropped the option on the branch, and the run with it restored it.
- **"Status unknown" lane (R-022):** a kind is known, it is not an executable kind, and it has no Status.
  - **26,498** labelled files on the branch; the other lanes are 331 / 329 / 12,996.
  - It is shown after "Stage unknown" (card, lane filter, Why text), as the order says.
  - It is ranked **last** in the default queue order (`queue_rank` 4), so the small lanes stay first. A lane filter shows it on its own.
  - The list has a sortable **Status** column.
- **Form: Stage or Status.** Stage (Execution label) for executable kinds and the "Stage unknown" lane; Status (Status & Execution) for the rest. The Status-unknown lane always gets Status.
  - Until the Status field is published, the select is disabled with a note, and `/api/review/confirm` refuses `doc_status` (`label_not_published:exec.status`). Confirm still records the review.
  - A write never carries both Stage and Status. The Status written is logged in `review_event.edits`.
- **Item 8 in the Review form:** the same Edit labels form as Find, logged with `source = review_edit`. Saving marks the file Confirmed, so it leaves the queue on the next load.
- **Tests:** vitest 91/91, covering the lane and sort whitelist, the page columns, the `doc_status` refusals, Stage vs Status in the form, and the card order.
- **Checked on the branch as `catalog_app`:**
  - a Status-unknown page returns 25 rows, with `requires_execution` false or NULL and no status;
  - the queue count runs in 0.6 s.

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

### Ruled (Ryan, 2026-11-17)
- **Item 9 re-kind rules** (implemented on the throwaway branch only; the two new kinds publish with Part 2):
  - **RK1:** approved. It runs before NK07.
  - **RK2:** approved with changes. Amendments and restatements → `operating_agreement_amendment` (Datum FORM-05); the rest → `operating_agreement` (FORM-04). The 11 correspondence files are excluded.
  - **RK3:** approved as kind `template`. No new Status choice.
  - **RK4:** approved.
  - **Superseded:** the CAT-WO-03 prep's suggested FORM-04/05 → `lpa` / `legal_agreement` mapping. FORM-04 → `operating_agreement` and FORM-05 → `operating_agreement_amendment` from now on.
- **Fiscal-year folder rules and the `v_file_best` tie-break** (from CAT-WO-03 prep `eda7a0e`, approved). Both are in `004_wo02_part2.sql` and release with Part 2's derive + re-sync.
  - **Rule numbering:** `PER-009` year **before** Tax / Taxes / Tax Return(s) / Audit / K-1; **`PER-014`** year **after** them.
    - The prep file named the second rule `PER-010`, but `PER-010` v1 already exists on main as a `fiscal_quarter` rule, and the prep's insert uses `ON CONFLICT DO NOTHING`. So it is `PER-014` here, with a guard that refuses to run if either id belongs to a different rule.
  - **Tie-break:** `cat.v_file_best` ORDER BY gains `s.rule_id, s.value`.
  - **Measured on the branch** (fiscal-year winners snapshotted, 004 applied, then `drive_crawl.derive()` run against the branch, 192 s):
    - **775** catalog files change fiscal year: 586 had none and get one; 189 move to the nearer folder's year. **212** of them are K-1s.
    - **0** files move into or out of FY2022.
    - Rules deciding the changed files: PER-009 436, PER-014 338, PER-004 1.
    - Two consecutive reads of `v_file_best` are now **identical** (before the fix, the same diff gave 774 / 775 / 776).
    - Labelled files (as Find shows them): **386** change fiscal year.
    - Part 2's Status (7,252) and Parties (3,385) values are intact after the derive.
- **T1 · state partnership returns are `tax_return`** (Ryan, second ruling round). In `004_wo02_part2.sql`; measured on the branch after a full `derive` (189 s):
  - **KND-024 v2** = the same pattern at **priority 24**, so it beats KND-041 (25) by the ruling, not by rule-id order. v1 is kept for history.
  - **Exception: state K-1s → `k1`.** No new rule was needed: KND-001 (`K-1` / `K1` / `Schedule K-1` in the name) already runs at priority 20. **1,043** catalog files (**422** labelled) look like a return and a K-1 and stay `k1`.
  - **Exception: vouchers / extensions → `tax_form`.** New **KND-057**, priority 23:
    - form numbers 3537 / 3538 / 7004 / 8868 always;
    - "voucher" / "extension" only next to a tax word or a return number, so a fund-term or lease "extension" is not caught.
    - It decides **144** catalog files (**78** labelled). **136** / **77** of them also look like a return, and **8** / **1** had no kind before.
  - **State returns (both KND-024 and KND-041 match) → `tax_return`:** **1,661** catalog files, **835** labelled.
  - **The re-sync would push 413 kind changes to Drive:** labelled files whose label now says `tax_form` but whose kind is `tax_return`. The tie-break had already picked KND-024 by rule-id order, so compared with the tie-break state only the 8 voucher files change.
  - KND-024 at 24 beats no other kind: 0 files where another priority-25 kind lost to it.
  - Guard: the migration refuses to run if `KND-057` already belongs to a different rule.
- **K1N and K1F approved; they replace NK01.** K1F keeps its skip of spreadsheets and archives.
  - **Code:** `NOKIND_RULES` in `pipeline/derive_wo02.py` (`NOKIND_RULED = {K1N, K1F}`, `NK_FAMILIES`).
  - **`apply_derive_wo02.py`:**
    - applies the ruled rules by default;
    - runs them first and over the **whole catalog**, so a new K-1 also gets its parties and status in the same run;
    - never writes over a person's kind;
    - must run after every `drive_crawl.py derive`.
  - **Measured on the branch** (derive + apply):
    - **3,106** documents → `k1` (K1F 2,850, K1N 256), about **6,938** files.
    - Of the FY2023 gap, **13** files are left: copies whose document's primary copy sits outside a K-1 folder, so the primary decides. The same holds for **47** files across all years.
    - FY2023 K-1-looking files with no kind: **732 → 13**.
  - **Fixed in passing:** NK12's folder pattern was written `<workpapers?>` (a literal "<", left over from the sentinel swap), so it could never match. It is now `‹workpapers?›`.
  - Pipeline guard tests are now **25/25**: G-D8 K1N, G-D9 K1F skips sheets and archives, G-D10 NK01 is gone and NK12 matches.

### Ruled, round 3 (Ryan, 2026-11-18): NK02–NK12, T1, K1N archives, CYBER-II · applied on the throwaway branch
Measured with `scripts/measure_wo02_item9d.py`, run after 004 + `derive` and before `apply_derive_wo02.py --apply`, then applied. Whole catalog = every live catalog file; a document's primary copy decides. Counts only.

**Implementation**
- **Code:** `pipeline/derive_wo02.py`, in `NOKIND_RULES` (all approved = `NOKIND_RULED`), `NK_FAMILIES` / `NK_NOT_FAMILIES`, `nk03_folder()` and `rekind_rule()` for RK2–RK4.
- **`apply_derive_wo02.py` runs the kind passes in this order:**
  1. RK2–RK4, which change a machine kind.
  2. The no-kind rules, on whatever is still blank.
  - Both passes cover the whole catalog, never touch a person's kind, and run before Parties / Status.
- **Migration 004** adds:
  - KNX-006 v2 (priority 39);
  - KND-049 v2 (RK1);
  - ENT-018 / ENT-018P v2 → CIP-II;
  - CYBER-II alias row deleted, `ref.entity` CYBER-II set inactive.
- **Removed:** NK01, NK09, NK10 and NK11, the "extension" half of NK04 and the PBC half of NK12.
- **Guard tests:** pipeline 29/29. New: G-D11 NK03 bank folders, G-D12 file-type limits, G-D13 RK1 before NK07, G-D14 RK2–RK4.

| Rule | As ruled | Files changed: labelled / whole catalog | Kind before → after |
|---|---|---:|---|
| RK2 | "operating agreement" in the name; amendments / restatements → amendment kind; correspondence excluded | 123 / 224 | lpa → operating_agreement 147 · lpa_amendment → operating_agreement_amendment 77 |
| RK3 | subscription booklet / book / package / docs (or counsel blank / form / template), not fully executed | 35 / 68 | subscription_agreement → template 47 · correspondence → template 18 · (none) → template 3 |
| RK4 | certificate of amendment / name change / DE amendment; **correspondence excluded as in RK2** (11 cover emails would otherwise move) | 13 / 30 | (none) → formation_filing 22 · legal_agreement → formation_filing 8 |
| K1N | "K-1" in the name; **archives skipped** | 222 / 436 | (none) → k1 |
| K1F | K-1 folder, PDF / Word / image only | 3,186 / 6,648 | (none) → k1 |
| NK02 | "invoice" / "inv #"; PDF and Word only | 221 / 298 | (none) → invoice |
| NK03 | bank-statement folders only (see below) | **0 / 0** | — |
| NK04 | form numbers only | 323 / 808 | (none) → tax_form |
| NK05 | Tax Returns folder; archives skipped | 260 / 506 | (none) → tax_return |
| NK06 | "valuation" / 409A; PDF and Word only | 123 / 387 | (none) → valuation_memo |
| RK1 | KND-049 v2 frees the 27 pledge-vehicle reports; then a report name with a quarter → quarterly_report, without → financial_statements (before NK07) | 747 / 1,570 | (none) → quarterly_report 883 · (none) → financial_statements 687 (labelled 435 / 312) |
| NK07 | "report" in a Reports folder, after RK1 | 109 / 442 | (none) → quarterly_report |
| NK08 | "receipt" | 11 / 58 | (none) → receipt |
| NK12 | Workpapers folders only | 237 / 502 | (none) → workpaper |
| T1 | rule-ID order, except financial_statements over workpaper | 12 / 15 | workpaper → financial_statements |

**Results on the branch**
- **Documents:** apply changed the machine kind of **5,752** documents.
- **No-kind files:** 84,216 → **72,561** (labelled 18,443 → **13,004**).
- **RK1:** KND-049 now fires on 0 labelled files (it was 27).

**NK03 · narrowed to bank-statement folders: 0 files qualify.** The old NK03 took 858; the ruling leaves them all out.

| Excluded because | Labelled / catalog | What the folders are |
|---|---:|---|
| No "bank", no "account statement", no bank the catalog knows (ISS-004P) | 664 / 783 | **716 sit under Schwab statement folders** (Mgmt Co …/<x> Statements/<FY>/). 38 are credit-card statements. 16 are "Partner Statements" folders; the rest are a few other statement folders. 752 are PDFs. |
| Financial Statements folder | 0 / 75 | `…/Financial Statements/` |

- **No file was excluded for Capital Statements, Partner / Capital Account Statements or K-1 folders.** The old NK03's name check ("statement" in a "…Statements" folder) never reached them, apart from the 16 "Partner Statements" counted above.
- **For Ryan:** Schwab is a brokerage and isn't in the catalog's bank list (ISS-004 issuer = bank: SVB, Chase, JPMorgan, Citizens, First Republic, Mercury, Capital One, Wells Fargo, US Bank).
  - If Schwab statements are bank statements for this purpose, adding Schwab to ISS-004 / ISS-004P makes NK03 take about 716.
  - Otherwise they stay no-kind and go to Review.

**T1 · financial_statements over workpaper: implemented at priority 39, not 24.**
- KNX-006 (financial_statements) and KND-044 (workpaper) are both **priority 40**. My earlier recommendation wrongly assumed 25.
- **At 39**, financial_statements beats workpaper and nothing else: 15 catalog / 12 labelled.
- **Priority 24 would also have flipped 70 files (32 labelled)** away from pbc_request 31, quarterly_report 16, fund_analysis 10, board_materials 9, loc_agreement 2 and journal_import 1. That goes beyond the ruling, so I used 39.
- If Ryan does want 24, it is a one-number change in 004.

**CYBER-II · retired.**
- **What assigned it:**
  - Rules `ENT-018` (name) and `ENT-018P` (folder name), pattern `(?i)AllegisCyber II\y`, priority 30.
  - `ref.entity_alias` row `CYBER-II → CYBER-II` (source `ryan_alias_map_v1`).
  - `ref.entity` row `CYBER-II`, which has no name, type or aliases.
- **Files carrying it:** **1 catalog file, 0 labelled.**
  - Evidence: "AllegisCyber II" in one folder name and the file name. The pattern is `…/fund portfolio */* ii return */* ii - return *`.
  - That is CIP-II naming, so it was re-pointed.
  - No document, label value (live or machine), confirmed entity or party carries CYBER-II.
- **Changes:**
  - ENT-018 / ENT-018P v2 → `CIP-II`. After the derive that file has CIP-II, and CYBER-II signals and file entities are both 0.
  - The alias row is deleted, and `ref.entity` CYBER-II is `active = false` (kept for history).
  - `labels_setup_wo02.py` leaves inactive entities out of the Parties choices.
  - At the Part 2 publish, the Entity choice `CYBER-II` (`7f29c48e5a`) is **disabled, not deleted** (`DISABLE_ENTITY_CHOICES`).
- **Nothing is unclear about CYBER-II, so there is nothing to list for Ryan.**
- **Found while looking (proposal, not applied):** "Cyber Innovation Partners II" spelled out is assigned no entity by any rule.
  - **750** catalog files (**331** labelled) have it in the name or a folder and no CIP-II; 1,314 others get CIP-II some other way.
  - A rule `ENT-019` / `ENT-019P` `(?i)Cyber Innovation Partners,? II\y` → CIP-II would fix them. It needs Ryan's yes, because it adds an entity to files.

**What the Part 2 re-sync will push to Drive** (labelled files whose Find kind now differs from the kind on their label):
- **613 kind changes in total.**
  - Approved for Drive: tax_form → tax_return 413, and the remaining ties: workpaper → financial_statements 9, purchase_agreement → safe_or_note 1. The tie count is 10 where I said 6: at priority 39 the financial_statements fix reaches 9 labels (12 labelled files win, 3 already say financial_statements).
  - From RK1–RK4, all approved:
    - lpa → operating_agreement 93;
    - lpa_amendment → operating_agreement_amendment 30;
    - loc_agreement → quarterly_report 26 and → financial_statements 1;
    - subscription_agreement → template 26;
    - correspondence → template 9;
    - legal_agreement → formation_filing 5.
- **5,421 labels gain a kind** from the approved no-kind rules.
- **The RK2 kinds need the two new Kind choices first.** If the publish has not happened, the re-sync skips those values, because unknown choices are not written.

### Ruled, round 4 (Ryan, 2026-11-18) · applied on the throwaway branch
- **Schwab is now a bank** (`ISS-004` / `ISS-004P` v2: issuer = bank). NK03 takes the Schwab statement folders.
  - **NK03 final: 649 labelled / 716 catalog** (none → bank_stmt).
  - Left for Review, with no kind change: 38 credit-card statements, 16 partner statements, 75 Financial Statements-folder files and 13 others.
  - **Side effect:** issuer = bank on **1,891** catalog files (1,035 labelled) under Schwab folders or with Schwab in the name. The re-sync writes that issuer to 1,045 labels (count below).
- **T1** stays at priority 39.
- **Spelled-out "Cyber Innovation Partners II" → CIP-II:** `ENT-020` / `ENT-020P`. `ENT-019` was taken on main, and the migration guard caught it.
  - **729** catalog files (316 labelled) gain CIP-II.
  - 12 of them also carry CIP-III, 2 CIP-I (GP) and 2 X. They are for a look in Review, not changed.
- **The full Part 2 re-sync is approved** (counts in the release steps).
- **Tie-break, part 2 (found while counting).** `ops.build_documents` picks the document's kind / fiscal year / issuer from its files with its own `DISTINCT ON`, which had no final key. So tied rules were still a coin-flip at the document level: the re-sync diff moved by 3 files between two derives with no rule change.
  - 004 restates the function with one change: final keys `s.rule_id, s.value, s.file_id`.
  - Two derives in a row now give identical results.
  - The diff is **616** kind changes, not 613: ppm → correspondence 4 are now fixed by rule-ID order (emails named for both LPA and PPM), and the invoice / purchase-agreement flips are gone.
- **Re-sync fix (found while planning the counts).** When a value isn't yet a choice on the label (e.g. kind operating_agreement before its choice is published), `expected()` turned it into "blank". The re-sync would then have **cleared** Kind on those files.
  - Such fields are now marked `_unwritable` and skipped, never unset.
  - Guard test G-S9; pipeline 30/30.
- **Label publish code:** `labels_setup_wo02.py --create-drafts --release` and `--publish --release` (they refuse to run without `--release`).
  - **Drafts:** a Parties draft, with the permissions copied from Allegis Document.
  - **Unpublished changes:** Execution → "Status & Execution" (+ Status, + Issued date); Allegis Document Kind + 2 choices; the Entity choice CYBER-II disabled.
  - **`--publish`** publishes the three labels and writes the new IDs into `src/lib/labels_schema.json`. CYBER-II is dropped from the app's Entity choices.
  - Written, not run: running it is a release step.

**Proposed, not applied: one legal-name entity rule per entity, from `company_name` in `datum_exports/datum_partner_roster_2026-11-17.csv`** (`scripts/measure_wo02_legalnames.py`; branch after round 4).
- **Method:**
  - Only the company columns are read from the CSV; partner columns are never used.
  - The pattern is the legal name without L.P. / LLC, as whole words, not followed by a fund number. "Cyber Innovation Partners, L.P." matches "… Partners LP" and "… Partners 2019", but never "… Partners II" / "III" / "2".
  - It reads the file name and every folder name.
- **Count definitions:**
  - Gains = files that would get the entity and don't have it today.
  - Conflicts = gains that would also carry another entity of the same family.

| Entity | Gains: labelled / catalog | Conflicting second entity: labelled / catalog |
|---|---:|---|
| ACCSO | 0 / 0 | – |
| ASOF | 180 / 452 | 0 |
| CIP-I | 167 / 463 | 53 / 85 (CIP-I (GP) 42, CIP-II 27, CIP-III 18) |
| CIP-I (GP) | 3 / 6 | 3 / 6 (CIP-I 6) |
| CIP-II | 17 / 24 | 3 / 3 (CIP-III 3) |
| CSOP | 78 / 276 | 0 |
| IVY | 0 / 0 | – |
| MTV-IV (A) | 169 / 358 | 5 / 5 (MTV-I 5) |
| MTV-IV (Annex) | 114 / 261 | 5 / 14 (MTV-IV (A) 14) |
| MTV-IV (Annex) (GP) | 98 / 286 | 51 / 96 (MTV-IV (Annex) 87, MTV-IV (A) 72, …) |
| MTV-IV (B) | 128 / 278 | 13 / 30 (MTV-IV (A) 27, MTV-I 3) |
| MTV-IV (GP) | 301 / 815 | 191 / 383 (MTV-IV (A) 250, MTV-IV (Annex) (GP) 114, …) |
| MTV-V (A) | 112 / 256 | 5 / 5 (MTV-I 5) |
| MTV-V (B) | 104 / 249 | 16 / 35 (MTV-V (A) 34, MTV-I 1) |
| MTV-V (GP) | 142 / 388 | 82 / 159 (MTV-V (A) 113, MTV-V (MTEF) 46, MTV-V (B) 41, MTV-I 2) |
| MTV-V (MTEF) | 143 / 282 | 8 / 15 (MTV-V (A) 14, MTV-I 1) |
| MTV-VI | 1 / 2 | 0 |
| NL-I | 268 / 948 | 0 |
| NL-II | 114 / 182 | 1 / 3 (NL-I 3) |
| TM | 0 / 0 | – |
| X | 4 / 9 | 0 |

- **Reading the conflicts:**
  - For a GP the "conflict" is often right: a GP's K-1 from its fund sits in the fund's folder and names both.
  - For a fund it is worth a look. CIP-I would add itself to 27 CIP-II and 18 CIP-III files: folder names like "Cyber Innovation Partners – Fund II".
  - My suggestion: approve the fund rules with no conflicts (ASOF, CSOP, NL-I, NL-II, X, MTV-VI), and send the GP and CIP-I rules to Review first.
- **Not mapped** (no catalog entity, or the mapping isn't clear): ASOF (GP), Allegis X (GP), Attotude (SPV), CIP-II (GP), Fundam (SPV), Lightship I / II (SPV), MTV-III (PF), MTV-III (PF) (GP), NL-I (GP), NL-II (GP). MTV-III (PF) may be MTV-III or MTV-III (MTEF); Ryan to say.

**Review screenshots** (local Worker on the throwaway branch, `?mask=1`):
- Before each shot, a check confirmed 0 preview frames and every file name masked.
- Shots:
  1. Queue with the Status-unknown card.
  2. Status-unknown lane with the Status form (disabled until publish).
  3. Edit labels in the Review form.
  4. Stage-unknown lane with the Execution form.
- They are kept outside the repo (`claude-chrome-screenshots-*`). The Worker and proxy were stopped afterwards.
- **Note:** a `workerd` started on 2026-11-17 from `C:\DriveCatalog\app` (not this worktree; likely the hotfix tab's local Worker) was holding port 8787. It was left running, and this run used 8797 / 8798.
- **Small layout defect:** the Review side panel scrolls sideways (content 582 px in a 363 px panel). It's display-only, and a fix is pending.

### Part 2 release steps (run on Ryan's go-ahead, in this order)
0. **Final coder + CISO review** of everything since the last Part 2 review:
   - the rule rounds 2–4;
   - the Review screen;
   - the `build_documents` restatement;
   - the label publish code;
   - the re-sync `_unwritable` fix.
   - Fix the findings.
1. **Check main** hasn't moved from `03d430c` (rebase and re-test if it has): vitest 91, pipeline 30, `tsc`.
2. **Restore point:** a Neon branch `pre-catwo02-p2` from main.
3. **Migration 004 on main** (as the DB owner).
   - Its guards stop the run if a rule ID is taken or the Schwab change doesn't land.
   - Afterwards check `security_barrier` on `v_find` / `v_find_x` / `v_review_queue` and the `catalog_app` grants.
4. **Derive on main:** `drive_crawl.py derive` (about 3 min), then `pipeline/apply_derive_wo02.py --apply`. On the branch apply changed the kind of **6,446** documents and set Parties / Status.
5. **Read-back on main:** `label_sync_wo02.py readback --apply`. It seeds `ops.label_state` from the live labels; the re-sync refuses to run without it.
6. **Labels:**
   - `labels_setup_wo02.py --check`, then `--create-drafts --release`.
   - Ryan looks at the drafts in Admin console → Label manager.
   - `--publish --release`.
   - Commit `src/lib/labels_schema.json`.
   - **Order inside this step:** Parties (new) and Status & Execution (+ Status, Issued date) and Allegis Document (+ 2 Kind choices, CYBER-II disabled) publish together, **before** the re-sync, so the two operating-agreement kinds can be written.
7. **Deploy:** merge `cat-wo-02-p2` into main, push, `opennextjs-cloudflare deploy`.
   - Smoke test Find, the Review queue (lanes, Stage / Status form, Edit labels) and the Labels panel. Status, Issued date and Parties should now be editable.
8. **Re-sync:** `label_sync_wo02.py resync`, first without `--apply`.
   - Compare with the plan below; then `--apply`. It reports read / person-confirmed / re-synced / skipped as person-owned / errors.
   - **The plan** (`scripts/resync_plan_wo02.py`, branch, from the stored read-back) is **16,132** labelled files:

     | Field | Labels written |
     |---|---:|
     | Status | 7,252 |
     | Kind | 6,686 (6,070 blank → kind; 616 kind changes) |
     | Receiving entity | 4,707 |
     | Issuing entity | 4,065 |
     | Issuer | 1,045 (Schwab → bank) |
     | Fiscal year | 472 (the FY folder rules) |
     | Entity | 316 (CIP-II) |
     | Period | 181 |
     | Stage | 16 |

   - Person-owned values are skipped and counted; the branch snapshot has none, so main's read-back decides.
   - Before the publish, the same plan writes 7,763 files and holds back the 123 operating-agreement kinds, leaving them as they are.
9. **Hooks:** wire `readback()` into `drive_crawl.py incremental` and `resync()` into `labels_sync.py --resync` (outside the repo).
10. **Post-checks:** Review counts, no-kind count, a sample of re-synced files. Then update the handoff and post `CATWO02 RELEASED <sha>`.

**P-K1 · management company K-1s** (the "Mgmt Co / … Investments in …" folders, 407+ K-1s). The files carry no single manco entity, so K1-R1 sets nothing. If Ryan names the management company those folders belong to, a rule can set receiving = that manco and issuing = the fund on the file.

**Item 9 · re-kind proposals from Ryan's look at the live Review queue** (`scripts/measure_wo02_item9b.py`; labelled files; counts only). **Ruled: see "Ruled" above** (RK1–RK4 approved, RK2 with changes); kept here for the counts. These overlap with none of each other.

| # | Rule (proposed) | Would change | Kind before → after |
|---|---|---:|---|
| RK1 | Retire the `fin` branch of KND-049 (below). Then a name with "Fin Report" / "Financial Report" / "Fin Rpt" / "Qtr" / "Qtrly" on a no-kind or `loc_agreement` file → `quarterly_report` if it also says Qtr / quarter / Q1–Q4, else `financial_statements` | 747 | (none) → quarterly_report 409 · (none) → financial_statements 311 · loc_agreement → quarterly_report 26 · loc_agreement → financial_statements 1. Left alone: quarterly_report 189, correspondence 2, fund_analysis 1 |
| RK2 | Name "Operating Agreement" → **`operating_agreement`**, a new kind (Datum FORM-04) | 136 | lpa → 97 · lpa_amendment → 28 · correspondence → 11 |
| RK3 | Name "Subscription Booklet / Book / Package / Docs", or (issuer = counsel and "blank" / "form" / "template") → kind **`template`**, unless fully executed | 35 | subscription_agreement → template 26 · correspondence → template 9. Left alone: 6 fully executed booklets. The counsel-blank branch matched 0 files (issuer = counsel is rare on these) |
| RK4 | Name "Certificate of Amendment" / "Name Change" / "DE Amendment" / "Delaware Amendment" / "Amendment to (the) Certificate" → `formation_filing`, except tax returns and forms | 18 | (none) → formation_filing 10 · legal_agreement → formation_filing 8. Already correct: formation_filing 9. Left alone: tax_return 2 |

**Why `loc_agreement` was set (RK1).**
- Rule **KND-049 v1** (name, priority 30, note "MTV pledge vehicles") has the pattern `(?i)pledge (agreement|fin)`. The `fin` branch also matches the MTV pledge vehicles' "Pledge Fin(ancial) Report" names, and priority 30 wins over the report rules.
- KND-049 fires on **27 labelled files, and all 27 are these reports.** So it currently sets no correct `loc_agreement` at all.
- The other loc rule, KND-023 (`line of credit|credit agreement|loan agreement|\yLOC\y`, priority 25), fires on 7 files and isn't involved.
- **Proposed fix:** narrow KND-049 to `(?i)pledge agreement`. That would be a new rule version, then `derive`.

**Decisions inside these, for Ryan:**
- **RK1 vs NK07.** 707 of RK1's 720 no-kind files also match NK07 (the "report in a Reports folder" → quarterly_report proposal). If both are approved, RK1 should run first, because it separates quarterly reports from financial statements.
- **RK2 amendments.** 82 of the 136 are amendments or restatements (54 now `lpa`, 28 `lpa_amendment`); 54 are base agreements. Should amendments become `operating_agreement` too, or a new `operating_agreement_amendment`?
- **RK2 correspondence.** The 11 `correspondence` files may be cover emails about an operating agreement. Should they be excluded?
- **RK2 needs new Kind choices.** Ruled: two choices (operating_agreement, operating_agreement_amendment) on the Allegis Document label (49 → 51 of 200), added at the Part 2 publish (`NEW_KIND_CHOICES`); there is no `ref.vocab` kind list, `labels_schema.json` takes the new choice ids.
- **RK3 is a kind, not a Status.** R-022's Status choices are Draft / In review / Final / Issued / Superseded, with no "template". Since `template` already exists as a **kind**, I proposed the kind. If Ryan wants it as a Status, R-022 needs a sixth choice.

### Deviations / notes (Part 2)
- **Item 7 hooks.** The read-back and re-sync live in the repo (`pipeline/`). The order names `drive_crawl.py incremental` and `labels_sync.py --resync`, but those scripts sit outside the repo and connect to main through `catalog_db_url.txt`, so wiring them in now would have written to main before release. They are called from those scripts at release (R-steps).
- **Labels not published.** Parties and the Status / Issued date fields are not created or published (Ryan's instruction). Until they are:
  - the app refuses edits to those fields (`label_not_published`);
  - Find shows their catalog values instead of live label values;
  - the re-sync skips them.
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

