# CAT-WO-03 handoff · Checklists: expected documents, best document on file, gaps

*2026-11-18. Codes, IDs and counts only: no LP, individual or file names. Rulings R-025 / R-026 and Ryan's rulings of 2026-11-17/18 (below).*

**Status (kept current):** release in progress. The database is on main; the label drafts are waiting for Ryan to publish in Label manager. See "Release log".

- **Throwaway Neon branches:**
  - `catwo03-throwaway-2` = `br-hidden-bread-bdzgdudh`, from main after Part 2's re-sync (LSN 2/C52FE880). All counts were re-run there.
  - `catwo03-throwaway` = `br-shiny-bar-bdbrp0e1` is the first build branch (from before the re-sync). Kept; delete on Ryan's OK.
- **Restore point:** `pre-catwo03` = `br-gentle-cell-bdflc9ck`, taken from main at the same LSN, before any release write.
- **Old prep branch** `br-gentle-silence-bd3vdeaf`: deleted (Ryan's instruction).
- **Git:** `cat-wo-03` = the prep commit rebased onto main `426a174` (`CATWO02 RELEASED`), plus this build.

## Release log (2026-11-18)
1. Rebased onto `426a174` (main's new commits were Part 2 handoff docs only). Tests: pipeline 35/35, sync 31/31, vitest 110/110, `tsc` clean.
2. New throwaway branch from post-re-sync main, re-run end to end. The counts are identical to the first branch: 3,163 requirements, the same mix, Match subject 1,478 before the defaults. DB guards 13/13.
3. Defaults applied (see "Defaults taken"), then re-run: the mix is unchanged, Match subject is 1,229, and guards are 13/13.
4. Restore branch `pre-catwo03`.
5. **Main** (`--release`, DB owner): `005_wo03.sql` → roster (414/414 mapped) → `005b` → applicability (60) → `apply_derive_wo02` (K1-R2: 841 → unknown) → subject → requirements (3,163 rows, same mix as the branch).
   - Every `app` view keeps `security_barrier`.
   - `catalog_app` cannot read `ref.party`, `ref.party_alias`, `ops.requirement*` or `cat.doc_party`. It can INSERT `app.requirement_override` / `app.review_event`, but cannot read, update or delete them.
6. **Labels:** `--create-drafts --release` made unpublished deltas only:
   - Allegis Document: 11 Entity choices.
   - Parties: 24 changes (entity choices, Subject code(s), Subject (person)).
   - Handling: Contains + Personnel info.
   - Permissions: Ryan only.
7. **Nightly hook** in `C:\DriveCatalog\drive_crawl.py` (outside the repo; backup kept in the session scratchpad): `wo03_checklists()` runs roster → subject (no staff) → requirements.
   - It runs after the read-back in `incremental`, after a `full` crawl, and after `derive`.
   - Tested on the throwaway branch: idempotent (0 documents changed on a second run, same 3,163 rows).
   - The nightly loads the pipeline from `CATALOG_APP_DIR` = `C:\DriveCatalog\app-main`. That checkout moves to the release commit at deploy.
8. **Screenshots** (local Worker on the throwaway branch, `?mask=1`; 0 preview frames and every file name masked before each shot; partner names hidden). Seven are kept outside the repo in `C:\DriveCatalog\proofs\catwo03\`:
   - Checklists (LP subscription agreements);
   - Gaps (AUDITED-FS);
   - a Met row with its side panel and 8 candidates;
   - Review with the Match subject lane (1,229);
   - the Subject form (candidate code, "none", roster picker, staff search).
   - Afterwards the Worker and proxy were stopped, `.dev.vars` and the dev secret were deleted, and the ports were confirmed free.
9. **Ryan published the labels and accepted defaults 1, 2 and 4.** Directory consent (3) is later; staff matching stays out of the nightly run.
   - `--read-published --release` → `labels_schema.json`:
     - Parties: `subject_codes` and `subject_person` fields.
     - Handling Contains: `personnel`.
     - +11 choices on each of Entity, Issuing and Receiving.
   - G-L1 now tests both the pre-publish plan and the published state; pipeline tests 36/36.
   - The first test branch `br-shiny-bar-bdbrp0e1` was deleted (Ryan's instruction).
10. **Deploy:** main fast-forwarded to `14e0f6f` and pushed. Worker version `cf1083df-cf6c-4fca-b636-713b31a13717`.
    - Smoke test: unauthenticated requests to every new route → 302 to Cloudflare Access.
    - Smoke test, signed in (masked; read-only, nothing saved):
      - all six checklists return main's counts;
      - Gaps returns 36 cells; an unknown rule returns 400;
      - Review's Match subject lane = 1,229 with subject columns;
      - Find rows carry `subject_codes` / `subject_person`.
    - `C:\DriveCatalog\app-main` (the nightly's `CATALOG_APP_DIR`) is detached at `14e0f6f`.
11. **Re-sync dry run** (`labels_sync.py --resync`, main, nothing written):
    - read 46,259 · person-owned 0 · errors 0 · Entity held 1 (the Part 2 NL-II hold);
    - **would re-sync 4,595 files**: Subject code(s) 2,300 · Handling raise 3 · Issuing entity 2,449 · Receiving entities 3,071.
    - **Subject code(s) 2,300** (plan ≈2,170): higher because the K1-R2 fix lets more K-1s match on the member's name.
    - **Handling 3:** the personnel documents (Restricted + Personnel info; only ever raises).
    - **Parties unsets (the K1-R2 fix):** Issuing 808 and Receiving 1,430 labelled files, from the 841 crowded documents (several labelled copies each).
    - **Parties sets 1,641 (Issuing and Receiving): Part 2's own K1-R3 rule catching up, not a WO-03 change.**
      - Main's stored parties dated from Part 2's derive run, made before its final commits. The released code was first run on main in this release.
      - Proof, on the restore branch `pre-catwo03` (read-only endpoint `ep-rapid-art-bdbrjxhk`): the released code with the WO-03 fix switched off gives 4,458 K1-R3 documents, against 3,120 stored.
      - The next nightly derive plus re-sync would have made the same writes.
    - **STOPPED for Ryan before `--apply`.**

---

## Rulings applied (Ryan)

| ruling | applied as |
|---|---|
| Entities: 11 new + 10 Datum aliases; CIP-II (GP) its own GP (not CIP2A); MTV-III (PF) its own entity | `005_wo03.sql`; roster maps **414 / 414** (22 exact, 10 alias) |
| Types: X, NL-I, NL-II, XI = fund; TM = spv; CYBER-II stays retired | `005_wo03.sql` |
| Kind mapping as in the prep; PCAP catalog-only | `005b_wo03_seed.sql`; **FORM-04 / FORM-05 → operating_agreement / operating_agreement_amendment** (CAT-WO-02 RK2 superseded the prep's lpa / legal_agreement) |
| Six rules active; K-1 only when matched to the entity's roster; side letters "none found (not tracked in Datum)"; PCAP-Q per partner per quarter from FY2025; K-1 from FY2025 | `005b_wo03_seed.sql` + `pipeline/requirements_wo03.py` |
| Applicability workbook (60 rows, no Unknowns) | `pipeline/applicability_load_wo03.py`: AUD-01 Yes 9 · No 21; OFF-04 Yes 1 · No 7; OFF-05 Yes 22 · No 0 |
| R-026 Subject: Subject code(s) + Subject (person) on Parties; Personnel info on Handling; Match subject lane; no Justworks list | items 3 and 5 below; labels **drafted only** (code ready, not run) |
| Held: CIP-I and GP legal-name entity rules | not touched |
| Prep `006` FY folder rules | dropped here: already released in CAT-WO-02 `004` as PER-009 / PER-014 |

## Item 0 · measurements (throwaway branch)
- **Roster:** 414 rows, 32 Datum companies, all mapped. Per-company table: `docs/CAT-WO-03_PREP.md` (unchanged).
- **Unmapped Datum codes:** none after the ruled aliases.
- **Reverse gap** (catalog entities of a checklist's type with no Datum roster): CIP-III, MTV-I, MTV-II, MTV-II (MTEF), MTV-III, MTV-III (MTEF), XI (funds); MTV-I (GP), MTV-II (GP), MTV-III (GP) (GPs); and the mancos for AUD-03. These show **"no roster in Datum"**.
- **Subject auto-match** (labelled documents, after the fixes in item 3):

  | kind | n | high | low | none | no roster |
  |---|---:|---:|---:|---:|---:|
  | k1 | 9,473 | 1,505 | 1,118 | 1,596 | 5,254 |
  | capital_statement | 506 | 235 | 90 | 86 | 95 |
  | subscription_agreement | 242 | 91 | 52 | 83 | 16 |
  | side_letter | 50 | 12 | 26 | 11 | 1 |
  | GP agreements (legal / operating agreement on a GP entity) | 44 | 8 | 3 | 26 | 6 |

- **PCAPs FY2025+:** 293 capital-statement documents on file, all with a quarter; 106 matched to one partner with high confidence. Against 2,107 expected partner-quarters this is mostly a **real gap on Drive**, not a matching problem.

## Item 1 · roster and document types
- `pipeline/roster_load_wo03.py` (crawl step `roster`, before `derive`): newest dated pair from `C:\DriveCatalog\datum_exports\`.
  - Checks exactly the expected columns; refuses TIN / address / bank / amount / contact columns (guard G-W1a).
  - Refuses any partner code not shaped `LP-` / `GM-` / `GPM-`.
  - Maps by exact code, then `ref.entity_alias`; unmapped stored NULL and listed, never guessed.
  - Seeds `ref.party_alias` from display + legal name (`source = datum`, replaced per load; Ryan's rows `source = ryan` kept).
  - Dry run by default; `--apply` writes.
- All WO-03 steps take an explicit `--db-url-file` and **refuse main unless `--release`** (`pipeline/dbguard_wo03.py`; checked: `REFUSED: this url file points at MAIN`).

## Item 2 · rules and the result mix before any person review (throwaway branch)

| rule | rows | result mix |
|---|---:|---|
| LP-SUB (OFF-03) | 285 | met 66 · on file 56 (partner unconfirmed 33, stage unknown 21, final unsigned 2) · missing 156 · no roster 7 |
| LP-SIDE (OFF-05) | 285 | met 5 · on file 9 · none found (not tracked in Datum) 264 · no roster 7 |
| GP-COMMIT (OFF-04) | 21 | missing 14 · no roster 7 |
| AUDITED-FS (AUD-01) | 36 | met 4 · on file 30 (status unknown 29, audit opinion only 1) · missing 2 |
| K1-SET (AUD-03), FY2025 | 429 | on file 61 (status unknown) · missing 353 · no roster 15 |
| PCAP-Q, 2025 Q1 – 2026 Q3 | 2,107 | on file 143 (status unknown) · missing 1,915 · no roster 49 |

"Status unknown" dominates the fund-level rows because Status (R-022) is set on few FS / K-1 / PCAP files today. That changes after Part 2's re-sync and review.

## Item 3 · Subject (R-026)
- **Data:** `cat.document.subject_codes_auto / _confirmed`, `subject_person_auto / _confirmed`, `personnel_auto`; `cat.doc_party` (document ↔ partner, method, confidence).
  - DB CHECKs: codes only, staff accounts only (G-W7).
- **Matcher** `pipeline/subject_wo03.py`, in order:
  1. a person's decision (label read back, or the app's Match subject event);
  2. a partner's full name in the **file** name;
  3. in a **folder** name;
  4. a distinctive word only (always low).
  - **High** = exactly one partner. Several partners, or a word only, = **low**, which goes to the Match subject lane.
- **Fixes found while measuring** (before them, single partners collected up to 35 K-1s a year):
  - Full-name patterns drop common Allegis file words. A manager row named after the management company matched every Allegis folder.
  - For K-1s / PCAPs with a Parties issuing entity, only the **issuer's** roster is used.
  - The fund's own GP row matches only its full GP name in the **file** name.
  - A K-1 issued by the fund and received by its own GP entity (Parties K1-R2) = the fund's GP row (method `parties`).
- **For Ryan · K1-R2 looks over-broad.** Part 2's K1-R2 marks up to 39 K-1s a year as *received* by CIP-I (GP) / MTV-IV (Annex) (GP). A GP gets one or a few. These are probably K-1s the GP issued to its members.
  - Here, such a fund / GP / year with more than 3 documents goes to Match subject (**254** documents), not to the label.
  - Worth a Part 2 rule look.
- **Personnel:** name markers (offer letter, employment agreement, compensation letter, severance …). **117** catalog documents, **3** labelled.
  - The re-sync raises their Handling to Restricted + Personnel info, and only ever raises (G-T4/T5).
  - The 353 payroll-folder files are invoices / journal imports, not personnel documents, so they are not marked.
- **Staff subjects:** no local token has `directory.readonly`, so the step reports "staff directory not available (skipped)".
  - Running it needs a one-time consent: `--directory-token`.
  - In the app, Subject (person) asks for the scope on first use.
- **Coverage (labelled documents, code / person / both / none):**
  - k1 1,505 / 0 / 0 / 7,968
  - capital_statement 235 / 0 / 0 / 271
  - subscription_agreement 91 / 0 / 0 / 151
  - side_letter 12 / 0 / 0 / 38
- **Match subject lane:** **1,478** labelled files.
- **Re-sync once the Subject fields are published:** Subject code(s) on **2,170** labelled files (1,851 documents); Handling raise on 3.

## Item 4 · requirements build
`pipeline/requirements_wo03.py` (derive, nightly) rebuilds `ops.requirement`. Scoring is in its docstring; the essentials:
- **Eligible:** kind, entity, period, and the partner match for partner subjects; never a document with Catalog Review = Wrong.
- **Ranking:** satisfying first, then a satisfying kind, then person-confirmed, then the primary copy, then the newest date.
- **Results:**
  - A low partner match never makes Met.
  - Overrides (`app.requirement_override`, append-only) always win and are also applied at read time in `app.v_requirement`.

## Item 5 · screens (built; screenshots pending, they need a local Worker: **ask Ryan first**)
- **Checklists** (`/checklists`, rail item; **Gaps** enabled → `/checklists?tab=gaps`):
  - checklist and requirement picker; scope (entity or All); FY and quarter pickers;
  - summary cards: Met / On file / Missing / Not required (+ Not checked), as counts and %;
  - default sort by urgency; sortable, resizable columns; the last state remembered per user;
  - best document with name and link **only after the live check as the user**, otherwise "on file (no access)";
  - Other candidates (n) in the side panel.
  - Row actions: **This is the one** (a candidate, or a Find search in the entity), **Not required** (reason required), **Clear override**.
- **Gaps tab:** entity × period for AUDITED-FS / K1-SET / PCAP-Q; each cell opens its rows.
- **Match subject lane** in the Review queue: card, lane filter, and a form with the candidate codes (+ names from `app.v_party`), the roster, "none", and the staff picker.
- **Find's side panel:** Subject codes from the roster of the document's entities, plus the staff picker.
- **Deviation:** checklist views are remembered per user, but **not saved into the rail's view tree**. Saved views are Find specs today; saving checklist views is a small follow-up if wanted.

## Item 6 · guard tests (outputs)
- **Pipeline** `py pipeline\test_wo03.py` → **31/31 passed** (roster column refusal, applicability Unknown not loaded, matching G-S1–S10, codes-only Subject G-T1–T3, Handling raise only G-T4–T7, scoring G-R1–R9, label plan G-L1–L2). `test_label_sync_wo02.py` still **31/31**.
- **App** `npx vitest run` → **109 passed (109)**. `test/wo03.test.ts`:
  - unopenable best document → `{access:"no_access"}` with no name or link;
  - typed names refused for Subject;
  - a code off the document's roster refused before any Drive call;
  - **directory scope only on the person edit** (sign-in / write scopes exclude it; only the directory route asks for it; only the person picker calls that route);
  - logs hold codes only;
  - override rules; whitelisted, bound queries.
- **DB** `py db\tests\test_wo03_guards.py --db-url-file <branch>` → **13/13 passed**:
```
PASS  G-W3 test_catalog_app_reads_ref_party_only_through_its_view
PASS  G-W3b app.v_party exposes the display name and codes only (no legal name)
PASS  G-W3c catalog_app may INSERT overrides but not read, update or delete them
PASS  G-W4 test_override_survives_two_rebuilds
PASS  G-W4b Clear override returns the row to the machine result
PASS  G-W5 test_document_marked_wrong_is_never_best (nor a candidate anywhere)
PASS  G-W5b restored: the document is best again once Wrong is removed
PASS  G-W6a test_no_lp_name_in_any_pipeline_log_line (roster, applicability, subject, requirements dry runs)
PASS  G-W6b test_no_lp_name_in_any_label_value (Subject codes are codes; events, requirement reasons, override keys hold no name)
PASS  G-W6c test_no_lp_name_in_any_export_file_name (export names are a fixed prefix + timestamp)
PASS  G-W7 test_no_typed_name_reaches_subject_codes (CHECK refuses a name, accepts codes)
PASS  G-W7b cat.doc_party refuses a non-code partner
PASS  G-W8 test_requirement_override_is_append_only (UPDATE / DELETE / TRUNCATE refused, even for the owner)
```
- **Note on G-W6a:** its first run found 10 "names" in the roster load's output. All 10 are the funds' own GP rows, whose roster name *is* the GP company's Datum code (an entity code, printed by design). The test now excludes entity names and codes and stays strict for every other name.

## Labels (drafted, not run): `pipeline/labels_setup_wo03.py`
`--plan` (offline) output:
```
new entity choices: 11 (ASOF (GP), ATTOTUDE, CIP-II (GP), FUNDAM, LS-I, LS-II, MTV-III (PF), MTV-III (PF) (GP), NL-I (GP), NL-II (GP), X (GP))
  Allegis Document Entity: 47 choices · Parties Issuing: 194 · Receiving: 49 (limit 200)
Parties: + subject_codes, subject_person -> 4 fields (limit 10)
Handling Contains: + Personnel info
design check: OK
```
- **Parties Issuing is at 194 of 200 choices.** The next ~6 portcos or entities need a design change (e.g. portcos as codes in a text field).
- **Flow, as in Part 2:**
  1. `--create-drafts --release` makes unpublished deltas only.
  2. **Ryan publishes in Label manager.**
  3. `--read-published --release` writes the IDs into `labels_schema.json`. The script never publishes.

## Defaults taken (for Ryan's review)
Ryan (2026-11-18): "take your own recommendation on each … apply it, and list it here".
1. **K-1 Met = Final or Issued.** Applied as `K1-SET` **v2** in `005b_wo03_seed.sql` (v1, Issued only, kept for history).
   - No K-1 in the catalog carries Issued. Part 2's markers give Final 1,949 · Draft 251 · In review 16 · none 11,292.
   - Draft and In review stay "on file".
   - Today's mix is unchanged: all 61 FY2025 K-1s on file have no status yet.
   - To revert: insert a v3 with `{"status": ["issued"]}`.
2. **K1-R2 narrowed (Part 2 rule).** A GP with **more than 3** "received" K-1s in one fiscal year is crowded; those K-1s go back to unknown issuing/receiving instead of "received by the GP".
   - A GP receives one or a few K-1s a year from its fund. The crowded ones are K-1s the GP issued to its members, or mixed folders.
   - Applied in `pipeline/apply_derive_wo02.py` as a post-pass; the threshold is `derive_wo02.K1R2_MAX = 3`.
   - On main: **841** documents → unknown, **51** keep K1-R2.
   - The re-sync dry run shows the matching Parties Issuing / Receiving unsets on the labelled ones. None of these values was person-confirmed (0 of 1,209).
   - Knock-on effects: those K-1s now match subjects on the member's name in the file name, so K-1 high matches rise from 1,505 to 1,610. The Match subject lane falls from 1,478 to **1,229**.
3. **Directory consent: staff matching stays out of the nightly run** (it reports "staff directory not available (skipped)" and keeps the last values).
   - A one-off run needs Ryan's consent, using `scripts/directory_token_wo03.py`. The steps are below, under "Directory consent".
   - The app's Subject (person) picker asks for the scope on first use.
4. **Checklist views in the rail: later.** Views stay remembered per user (last state). Saving them into the rail's view tree is a small follow-up.

Kept as built (Ryan): partner names next to codes on Checklists rows (only Ryan is on the allowlist).

### Directory consent (one-off staff step), when wanted
1. In Google Cloud console, for the project of the crawl's OAuth client (`C:\DriveCatalog\client_secret.json`):
   - **APIs & Services → Library → "People API" → Enable**, if it is not already on.
   - **OAuth consent screen → Data access → Add scope** `.../auth/directory.readonly`. The app is Internal, so no Google verification is needed.
2. From `C:\DriveCatalog`, run `py app\scripts\directory_token_wo03.py`. Sign in as ryan@allegiscapital.com and allow "See your organization's directory".
   - The token goes to `%TEMP%\catwo03_directory_token.json`, outside the repo.
3. Within the hour: `py app\pipeline\subject_wo03.py --db-url-file <main url file> --release --directory-token %TEMP%\catwo03_directory_token.json --apply`, then `del %TEMP%\catwo03_directory_token.json`.
   - The next re-sync writes Subject (person) to the labels once that field is published.

## Release steps (after `CATWO02 RELEASED`; on Ryan's go-ahead; stop before the re-sync dry run is applied)
0. Fix the coder + CISO findings (below).
1. Rebase `cat-wo-03` onto main; re-run vitest / pipeline tests / `tsc`.
2. **New throwaway branch from post-re-sync main**; re-run 005 → roster → 005b → applicability → subject → requirements → DB guards. Compare the counts with this handoff.
3. **Restore point:** Neon branch `pre-catwo03` from main.
4. On main (`--release`, as the DB owner):
   1. `scripts/run_sql_wo03.py db/migrations/005_wo03.sql`
   2. `roster_load_wo03.py --apply`
   3. `005b_wo03_seed.sql`
   4. `applicability_load_wo03.py --apply`
   5. `subject_wo03.py --apply`
   6. `requirements_wo03.py --apply`
   7. Check `security_barrier` on the replaced views and the `catalog_app` grants (G-W3 on main is read-only).
5. **Labels:** `labels_setup_wo03.py --create-drafts --release`. **Ryan publishes in Label manager.** Then `--read-published --release`; commit `labels_schema.json`.
6. **Deploy:** merge, push, `opennextjs-cloudflare deploy`. Smoke test Checklists, Gaps, the Match subject lane, and Subject in Find.
7. **Hooks:** `roster`, then `subject_wo03` and `requirements_wo03`, after `apply_derive_wo02.py` in the nightly derive (outside the repo).
8. **Re-sync dry run** (`label_sync_wo02.py resync`, no `--apply`): expect Subject code(s) ≈ 2,170 files plus 3 Handling raises. **STOP for Ryan before `--apply`.**
9. Post-checks, then the handoff update and `CATWO03 RELEASED <full sha>`.

## Reviews (coder + CISO), run read-only on `main..cat-wo-03`; all findings fixed except where noted
**CISO** (no high):
1. **Medium · bulk LP-name reads.** `/api/party` now takes a `file_id` and returns only that document's roster. It needs write scope and the live check (the user must be able to open and label the file), and reads are logged as a count.
   - Checklists rows still show the partner's display name beside the code. That is intended (R-026: "the app shows names beside codes"; allow-list = Ryan) and is a ruling point if more users are added.
2. **Medium · the DB CHECK refused a person's "none" (`'{}'`).** It would have aborted the nightly subject step. Fixed (`cardinality = 0 OR …`); test G-W7 now covers `'{}'`.
3. **Medium · overrides from a read-only session.** Now `write: true`.
4. **Low · out-of-scope best documents.** `v_requirement` now hides their kind / stage / status / date / reason too, not only the file id.
5. **Low · override note.** A note naming a partner of that entity is refused (use the code); UI copy says so. Test added.
6. **Low · offline directory credential.** The staff loader never refreshes (it needs a fresh short-lived token) and uses the staff-email regex.
7. **Low · directory consent link.** Accepted. `/api/subject/directory` also needs write scope.
8. **Low · Handling raise race.** The re-sync already re-reads each batch right before writing. Tests for restricted / unknown / secret tiers were added.
9. **Info.** The measure script now refuses main via `dbguard`.
10. **Info.** The subject route reads `source` after the guard.

**Coder** (5 defects, all fixed):
1. **Clear override did nothing until the rebuild.** The build now stores the machine result; overrides are applied only in `v_requirement`. G-W4b checks that Clear works **at once**.
2. **Audited FS skipped required funds with no Datum roster.** Entity-level rules now use catalog entities too (G-R10). On this branch the 9 Required = Yes entities all have rosters, so the mix is unchanged.
3. **Without the directory token, the nightly run cleared Subject (person).** The last value is now kept.
4. **A person emptying Subject code(s) became NULL**, and the machine codes came back. It is now stored as `'{}'` (G-T8).
5. **A person-only edit also sent codes.** Codes are sent only when changed, and the server refuses `[]` without `none`.

**Coder minors fixed:**
- Match subject ignores earlier Confirm / Wrong reviews.
- App decisions newer than the last read-back win, and `subject_person` events are carried too.
- Stale subject / personnel values are cleared when a document's kind changes.
- Requirement keys are de-duplicated (one company kind per entity); G-R11.
- The checklist total comes from the counts and the client clamps the page.
- The Subject form refreshes after a save.
- The Handling raise checks that the tier choice exists.
- Matching is deterministic (sorted entities).
- `DELETE` instead of `TRUNCATE` for `ops.requirement`.

**Noted, not changed:**
- A Link to a document someone marked Wrong is accepted: the app can't see Wrong per file today.
- Raising Handling on the label doesn't change `cat.file.handling` until the crawl reads it.

**Totals after the fixes:** pipeline **35/35**, WO-02 sync **31/31**, vitest **110/110**, `tsc` clean, DB guards **13/13**. The result mix and the lane (1,478) are unchanged.
