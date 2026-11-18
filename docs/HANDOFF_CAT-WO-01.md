# CAT-WO-01 handoff · Allegis Catalog app v1 (Find + Review queue)

*2026-11-17. Codes, IDs and counts only: no LP, individual or file names.*

## Item 0 · measurements (read-only; `scripts/measure_item0.py`)

1. **Labelled files by drive × kind × tier.** 46,259 labelled files, all in drive `LIMITED - Finance` (pilot folder included), **all tier `normal`**. Top kinds: `(none)` 18,417 · `k1` 7,216 · `bank_stmt` 4,396 · `financial_statements` 2,499 · `tax_form` 1,758 · `tax_return` 1,483 · `correspondence` 1,479 · `invoice` 1,354 · … (46 kinds in total; full table in the script output). **Secret tier: 34 files in the catalog; 0 in the labelled set (DB), and 0 of the 34 carry any catalog label live in Drive (34 checked, 0 errors).**
2. **Review queue sizes:** stage unknown **342** · fully executed at low confidence **330** · no kind **18,417** · union (distinct files) **19,089**.
3. **Label drift, 200 random labelled files:** 200/200 compared, 0 Drive errors, **0 files with any mismatch** (0 on every field: kind, entity, portco, fiscal_year, period, workstream, issuer, catalog_id, exec.stage, handling.tier/contains, review.status). Drift is zero today because nobody edits labels yet. The live-values approach stays, because the same Drive call is needed for the access check anyway, so it costs nothing extra.
4. **Drive API cost:** one batch `files.get` ×50 with `includeLabels`: 1.44 s (cold), 0.46, 0.46, 0.52 s; mean 0.72 s. **Page size set to 50.** In the Worker, a full Find request (SQL plus Drive batch) took 1.5–3.6 s.

## What was built

- `C:\DriveCatalog\app`: its own git repo (branch `main`, no remote yet: R1). `.gitignore` covers `client_secret*.json`, `token_*.json`, `catalog_db_url.txt`, `*db_url*.txt`, `listing_cache.json.gz`, `labels_done.txt`, the label logs/CSVs, `.dev.vars`, `.env*`. `git status` was clean after the commit; `git ls-files` shows no local-only file; a secret-pattern scan of the tree returned no matches.
- **DB** (`db/migrations`): schema `app` with `labelled_file`, `saved_view`, `review_event` (append-only by grant **and** trigger), and views `v_find`, `v_review_queue`, `v_review_counts`, `v_portco`, `v_entity`. Secret tier is excluded in `v_find` itself (`coalesce(handling,'secret') <> 'secret'`), and every other view reads through it. No file-name column exists in any `app` view. Role `catalog_app` has exactly the grants in the order.
- **App** (Next.js 16.4.6 on Workers via `@opennextjs/cloudflare` 1.20.17): Cloudflare Access JWT check plus Google sign-in, both required on every page and API request (allowlist and domain re-checked per request; the Access email must equal the Google email). OAuth uses `access_type=online` with PKCE; scopes `openid email drive.metadata.readonly`; `drive.metadata` is requested only when the first Review write needs it (409, then incremental consent). The session is an AES-GCM sealed, HttpOnly, Secure cookie holding the access token, with Max-Age equal to the token's life. No KV/R2/D1/DO bindings.
- **Find:** filters (kind, entity, portco, fiscal year, signing stage, tier, primary copy only), sort, column chooser, group-by (counts over the whole match set), CSV export (codes and Drive links only), server paging, and the total matched count. Each page gets one Drive batch `files.get` as the user (`id,name,webViewLink,labelInfo`). Unopenable rows are dropped, and the header reads "N not shown (no access)"; transient Drive errors are counted separately and also not shown. A row whose live tier is secret is never shown. Cells display live label values, with a "changed in Drive" marker where they differ from the DB. Row click opens a side panel with Drive's preview iframe and "Open in Drive". Saved views: four seeds inserted on first use.
- **Review queue:** stage unknown first, then lowest confidence, then no kind. The "why" column comes from scan signal codes and confidence. Counters: open, per bucket, reviewed today, skipped. **Confirm and next** calls `files.modifyLabels` as the user on **Execution** (stage, executed date) and **Catalog Review** (status, reviewed by, note) only, then inserts one `app.review_event` row; the file leaves the queue. **Skip** writes nothing. Gaps shows as a disabled tab, "not built (R-006)".

## Guards (each with its test and quoted output)

**G1 · secret tier never returned by any `app` view** · `db/tests/test_guards.py` (fixture rows, throwaway branch)
```
PASS  G1 app.v_find as catalog_app: secret-tier fixture returned = 0
PASS  G1 app.v_review_queue as catalog_app: secret-tier fixture returned = 0
PASS  G1 app.v_find as catalog_app: rows with tier outside (normal, restricted) = 0
PASS  G1 control: normal-tier fixture IS returned by app.v_find = 1
PASS  G1 control (Decision 2): restricted-tier fixture IS returned, badged by tier = 1
PASS  G1 app.v_find: control fixture after flip to secret returned = 0
PASS  G1 app.v_review_queue: control fixture after flip to secret returned = 0
```
**G2 · `catalog_app` refused INSERT on `cat` and UPDATE on `app.review_event`** · same file, throwaway branch
```
PASS  G2 catalog_app refused INSERT on cat.file  -- permission denied for schema cat
PASS  G2 catalog_app refused UPDATE on app.review_event  -- permission denied for table review_event
PASS  G2 catalog_app refused DELETE on app.review_event  -- permission denied for table review_event
PASS  G2 catalog_app refused SELECT on app.review_event (insert-only)  -- permission denied for table review_event
PASS  G2 catalog_app refused SELECT on ref.lp  -- permission denied for schema ref
PASS  G2 catalog_app refused SELECT on ops.run  -- permission denied for schema ops
PASS  G2 append-only trigger refuses UPDATE even for the owner  -- app.review_event is append-only (UPDATE refused)
27/27 passed
```
**G3 · a file the user can't open is dropped and counted** · `test/live.test.ts` (stubbed Drive batch, 404 for one id)
```
✓ G3 test_no_access_file_is_dropped_and_counted > stubbed Drive batch: 404 for one id -> that row is dropped, counted as 'not shown (no access)', others shown
   (asserts shown=[id1,id3], notShown={noAccess:1,checkFailed:0,total:1}, one batch of 3 files.get with labelInfo)
```
Manual check on a real file Ryan doesn't have: **none exists in scope.** `scripts/access_sweep.py` checked all 46,259 labelled IDs as Ryan: `DONE 46,259 checked: {200: 46259, 'unresolved': 0}; no-access ids: 0`. Live substitute (`scripts/live_404_check.ts`, real Drive, one real id plus one non-existent id):
```
PASS  G3 live: the unopenable id is dropped and counted (noAccess=1); the real file is shown
```
**G4 · a review write does not change `modifiedTime`** · `scripts/mtime_check.ts`. This is a live write on one ACCSO pilot-folder file through the app's own `reviewWrite()`, with the review_event going to the throwaway branch DB:
```
BEFORE  {"file_id":"180DfKiZCFvBptMVPfYEzyQsETkbBkmtw","modifiedTime":"2023-08-14T23:01:09.192Z","stage":"fully_executed","executed_date":null,"review_status":"needs_review","reviewed_by":"unset","note":"unset"}
WRITE   {"http":200,"ok":true,"labels":["exec","review"]}
AFTER   {"file_id":"180DfKiZCFvBptMVPfYEzyQsETkbBkmtw","modifiedTime":"2023-08-14T23:01:09.192Z","stage":"fully_executed","executed_date":null,"review_status":"wrong","reviewed_by":"set","note":"set"}
RESTORE {"http":200}
FINAL   {"file_id":"180DfKiZCFvBptMVPfYEzyQsETkbBkmtw","modifiedTime":"2023-08-14T23:01:09.192Z","stage":"fully_executed","executed_date":null,"review_status":"needs_review","reviewed_by":"unset","note":"unset"}
PASS  G4 modifiedTime unchanged by the review write (and by the restore): 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z -> 2023-08-14T23:01:09.192Z
```
The write re-asserted the stage already on the label and set Catalog Review to "Wrong" with a test note (a test write, not a human confirmation). The file's original Catalog Review values were then restored, so Drive is back exactly as it was. No other file was written.

**G5 · no refresh token anywhere** · `test/session.test.ts` plus greps
```
✓ G5 test_no_refresh_token_persisted (6 tests: online-only auth URL; exchangeCode drops refresh_token; sealSession whitelists fields;
   end-to-end callback cookie decrypts to no refresh token and Max-Age <= 3599; expired/tampered session refused)
$ git grep -c -i "refresh_token" HEAD -- src          -> (no matches, exit 1)
$ grep kv_namespaces|r2_buckets|d1_databases|durable_objects wrangler.jsonc  -> (none, exit 1)
branch DB: columns in schema app named like %refresh%/%token%: 0
branch DB: app.saved_view / app.review_event rows containing 'refresh_token': 0
```
Repo-wide, `refresh_token` appears only in `test/` (fake Google responses, asserting the value is dropped) and in three local scripts (`scripts/mtime_check.ts`, `live_404_check.ts`, `worker_smoke.ts`). Those scripts read Ryan's existing local `token_labels_apply.json` to mint one access token in memory, and they are not part of the Worker.

**G6 · non-`allegiscapital.com` and non-allowlisted accounts get 403** · `test/authz.test.ts`
```
✓ decideIdentity: personal gmail account -> 403
✓ decideIdentity: other Workspace domain -> 403
✓ decideIdentity: allegiscapital.com address without hd claim -> 403
✓ decideIdentity: allegiscapital.com but NOT allowlisted -> 403
✓ callback route: gmail account -> 403 and no session cookie
✓ callback route: allegiscapital.com non-allowlisted -> 403 and no session cookie
✓ every API request: a still-valid session for an account REMOVED from the allowlist -> 403
✓ Cloudflare Access: no config and not localhost -> 403; JWT missing -> 403; valid JWT for non-allowlisted email -> 403
Test Files 4 passed (4) · Tests 33 passed (33)
```
End-to-end in the real Worker runtime (`wrangler dev -c wrangler.local.jsonc`, branch DB, live Drive; `scripts/worker_smoke.ts`):
```
POST /api/find, no session                                 401
POST /api/find as non-allowlisted allegiscapital.com       403
GET /api/facets                                            200 kinds=46 entities=35 portcos=1 tiers=[{"value":"normal","n":46259}]
POST /api/find all labelled files, page 1                  200 total=46259 pageRows=50 shown=50 notShown={"noAccess":0,"checkFailed":0,"total":0}
POST /api/find with injection attempt                      400 {"error":"bad_spec","reason":"kind: bad value"}
POST /api/export kind=k1                                   200 rows=7216 header=file_id,document_id,kind,entities,portcos,fiscal_year,period,stage,signed_date,tier,is_primary,web_view_link
GET /api/views (seeds on first use)                        200 views=4 seeds=4
GET /api/review                                            200 counts={"stage_unknown":"342","low_confidence_executed":"329",...} first_reason=stage_unknown
POST /api/review/confirm with read-only session (no write) 409 {"error":"consent_required",...}
POST /api/review/confirm for a file not in the queue       404 {"error":"not_in_queue"}
```
(Counters were returned as strings in that run; the view now casts to int, re-applied and re-tested on the branch.) Under the production route config, `wrangler dev` rewrote every request to `catalog.allegis.app`, and every page and API was refused with `access_not_configured`. That confirms the Worker fails closed until R3's Access team domain and AUD are set.

## Deviations, stops, decisions

- **Decision 1:** default applied (labelled files only). **Decision 2:** default applied (restricted shown, badged, still subject to the live check; none exist in scope today).
- **Deviation: a third app table, `app.labelled_file`.** The order lists two tables, but the catalog DB has no record of which files carry the label: `cat.file.drive_labels` is empty on all 202,507 rows until CAT-WO-02's read-back. The labelled set exists only in the local resume list `labels_done.txt`. `db/load_labelled.py` loads those IDs (IDs only). `catalog_app` has no grant on the table; it is read only through the views. CAT-WO-02 should replace it with the read-back.
- **Seed views:** *(superseded: replaced with the designs v0.1 views, see "Follow-up" below)* the four seeds were my stand-ins ("K-1s, latest year first", "Signed agreements (primary copies)", "Bank statements by entity", "No kind yet"), because designs v0.1 are not in this workspace. Edit `SEED_VIEWS` in `src/lib/find.ts` to match the design. Seeds are inserted per user on first visit.
- **"Fully executed at low confidence"** = the document's stage is `fully_executed` and the content check's confidence is `low` (330). Counting by the scan's suggested stage instead gives 285.
- **Export** reads the DB only (codes plus links, no names, up to 50k rows) and is not live-checked per row. A link opens only if Google allows it.
- **Stack:** "same as Datum" could not be checked, because I did not open the Datum repo, as instructed. I used OpenNext (`@opennextjs/cloudflare`); swap if Datum uses vinext.
- **Item 4 live check:** a second write (the restore) went to the same single file, so Drive was left as found.
- **Review lane:** *(superseded: run, see "Follow-up" below)* items 2, 4 and 5 (roles, Drive write path, access) still need the coder + CISO review named in the order. I have not run it.
- **Dependency note:** `app.v_find` depends on `cat.v_file_entity`, `cat.v_file_portco`, `cat.file`, `cat.document`, `cat.file_document` and `cat.doc_content_check`. A future `cat` migration that DROPs one of these must re-run `001_app_schema.sql` and `002_catalog_app_grants.sql`. No local script does this today.

## Waiting on Ryan

| Item | Blocks | Built and tested meanwhile |
|---|---|---|
| **R1** GitHub repo `ryparker24/allegis-catalog` | push only | local repo committed; then `git remote add origin https://github.com/ryparker24/allegis-catalog.git && git push -u origin main` |
| **R2** OAuth Web client (redirects `https://catalog.allegis.app/api/auth/callback`, `http://localhost:3000/api/auth/callback`; for local Worker runs also `http://localhost:8787/api/auth/callback`) | real Google sign-in; the screenshots | full flow is coded and unit-tested with stubbed Google; `/api/auth/login` returns 503 "OAuth client not configured (R2)" until then |
| **R3** DNS + Access app for `catalog.allegis.app` | first deploy | route is in `wrangler.jsonc`; Worker refuses everything without `CF_ACCESS_TEAM_DOMAIN` + `CF_ACCESS_AUD` |
| **R4** migration on main | release | rehearsed end to end with psql on the throwaway branch (block below) |
| **Screenshots** (Find filtered with the "not shown" count, side-panel preview, Review queue before/after one confirm) | need R2 sign-in | not taken. They show file names, so Ryan should take them after R2 rather than put them in a handoff |

### R4 paste block (PowerShell, on Ryan's machine; prints nothing secret)
```powershell
cd C:\DriveCatalog\app\db\migrations
$owner = ((Get-Content C:\DriveCatalog\catalog_db_url.txt | Where-Object { $_ -match 'UNPOOLED' }) -replace '^[^=]+=','').Trim().Trim('"',"'")
psql $owner -v ON_ERROR_STOP=1 -f 001_app_schema.sql
$pw = python -c "import secrets;print(secrets.token_urlsafe(24))"
psql $owner -v ON_ERROR_STOP=1 -v pw="$pw" -f 002_catalog_app_role.sql
python ..\load_labelled.py --url-file C:\DriveCatalog\catalog_db_url.txt
# expect: app.labelled_file: 46,259 IDs loaded; not in cat.file: 0; secret tier: 0
cd C:\DriveCatalog\app
$appUrl = $owner -replace '^(postgres(?:ql)?://)[^@]+@', ('${1}catalog_app:' + $pw + '@')
$appUrl | npx wrangler secret put CATALOG_APP_DB_URL
Remove-Variable pw, appUrl
```
Then the other Worker secrets: `npx wrangler secret put GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (R2), `SESSION_SECRET` (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` (R3). Then `npm run deploy`.

### Throwaway branch
Neon branch `catwo01-test-throwaway` (`br-spring-frost-bdrt8htx`) on `curly-sunset-06555843` holds the rehearsed `app` schema, `catalog_app` and one test `review_event`. Delete it when done (I did not, because branch deletion is destructive). Main was only read (item 0); it was never written.

---

## Follow-up (after Ryan accepted `app.labelled_file`, OpenNext and the Decision 1/2 defaults)

Commits: `0237ae4` (seed views), `04a57a4` (review fixes), then this handoff update.

### 1 · Seed views from designs v0.1

`SEED_VIEWS` in `src/lib/find.ts`. All four have "primary copy only" on.

| View | Filters | Rows on the branch DB |
|---|---|---|
| ACCSO · subscription docs | kind = `subscription_agreement`, entity = `ACCSO` | **14** |
| MTV-II · FY2025 close | entity = `MTV-II`, fiscal year = 2025 | **2** |
| Unsigned side letters | kind = `side_letter`, stage in (`draft`, `final_unexecuted`, `partially_executed`) | **25** |
| K-1s · tax year 2025 | kind = `k1`, fiscal year = 2025 | **615** |

- **Workstream left off "MTV-II · FY2025 close".** `ref.vocab` (list `workstream`, 21 codes) has no single close or financial-reporting code. The candidates are `reporting` ("Reporting (All Reports)"), `regulatory` ("Regulatory reporting") and `accounting` ("Accounting (legacy)"). None is clearly the close workstream, so per the order the filter is left off. Add it to the seed once a code is chosen.
- **How the counts were made.** `npx tsx scripts/seed_view_counts.ts --url-file <catalog_app branch URL>` runs the app's own WHERE builder as `catalog_app`, so the grants and the secret-tier exclusion both apply. The real Worker gave the same totals when it ran each seed (smoke output below).
- **Fiscal year stored as strings.** The years are stored as `"2025"` so the facet checkbox matches the stored value (review finding C3).
- **Seeding.** Seeds are inserted per user on first visit, so on main they appear the first time Ryan opens the app.

### 2 · Coder + CISO review

Two reviewer subagents ran read-only (tsc, unit tests, grep; no DB, network or file edits).

**CISO.** Items 1–6 all **PASS**:
1. The Access JWT check verifies signature, iss, aud and exp, and fails closed.
2. Google sign-in requires `email_verified`, `hd`, the email domain and the allowlist. State and PKCE are bound to the browser, there is no open redirect, and `access_type=online`.
3. The session is AES-256-GCM with an HKDF key and random IV, and fails closed on tamper. The cookie is `__Host-`, HttpOnly, Secure and SameSite=Lax, and expires with the token on both sides. Logout is POST-only.
4. `catalog_app` grants are as specified. `review_event` is append-only by grant and by trigger, and the views are `security_barrier`. There is no SECURITY DEFINER function or default-privilege widening, and saved views are owner-scoped.
5. The review write touches only the Execution and Catalog Review labels, requires the file to be in the queue, and is made as the user.
6. No `console.*` call outside `log.ts`. Drive error bodies are never logged or returned.

**Coder.** Find SQL, the schema-to-code column match, grants against the statements the app runs, saved views, the live check, the review write, the auth flow and the 409 consent flow all work.

| # | Finding (reviewer) | Real defect? | What was done |
|---|---|---|---|
| S1 | No Origin/CSRF check on POST/DELETE. SameSite=Lax doesn't stop a page on a sibling `*.allegis.app` host from submitting a `text/plain` form (CISO, Low) | yes | **Fixed.** `guard.checkSameOrigin`: every non-GET request needs `Origin == APP_ORIGIN`, and a POST body must be `application/json`. |
| S2 | The log sanitizer's `CODE_SHAPED` pattern matches typical file names, so a name under an allowed key would pass. No call site does this today (CISO, Info) | latent | **Fixed.** Per-key shapes: ID keys accept only `[A-Za-z0-9_-]`, with no dots or spaces; every other string key accepts only lowercase snake_case codes. |
| C1 | The Review queue can stall. Rows the live check drops never leave the queue, the client always reloaded page 0, and there was no next-page control (Coder, defect) | yes | **Fixed.** The route walks forward up to 4 pages per request until something is shown and returns `nextPage`. The client keeps its page and shows a "Next page" button when a page shows nothing. |
| C2 | The skip list grows without limit in the query string. The server reads 500, so the URL risks a 414 (Coder, minor) | yes | **Fixed.** The client keeps the last 400 skips. |
| C3 | Seed fiscal year stored as a number while facet values are strings, so the checkbox state is wrong (Coder, minor) | yes | **Fixed.** Stored as strings. |
| C4 | Saving a view drops the `executed_date` and `review_status` columns (Coder, minor) | yes | **Fixed.** Both are allowed as display-only columns. |
| C5 | A batch-level Drive failure (400, or a 403 scope error) and per-item `dailyLimitExceeded` were counted as "no access" (Coder, minor) | yes | **Fixed.** A batch-level non-401 failure now counts as check failed, and `*LimitExceeded` counts as transient. |
| C6 | CSV export is not live-checked per row (Coder, flagged for CISO) | no, as designed | **Not changed.** This was already recorded under Deviations: codes and links only, no names, and a link opens only if Google allows it. If Ryan wants export to drop files he can't open, it costs one Drive batch per 50 rows. |
| C7 | Export used a raw `fetch`, so an expired session showed "export failed (401)" (Coder, minor) | yes | **Fixed.** A 401 now goes to sign-in. |

**Tests after the fixes:**
- `npx tsc --noEmit` is clean.
- `npm test` passes **45/45**: the original 33 plus 12 in `test/review_fixes.test.ts`. Those cover the CSRF cases, the sanitizer shapes, batch-level failures, the `*LimitExceeded` reasons, and the seed-view shape.

**Real Worker smoke test.** `wrangler dev -c wrangler.local.jsonc` against the throwaway branch and live Drive, output from `scripts/worker_smoke.ts`:
```
POST /api/find, no session                                 401
GET /api/auth/login (no OAuth client yet, R2)              503 OAuth client not configured (R2)
GET / localhost, no session                                200 (sign-in page)
POST /api/find as non-allowlisted allegiscapital.com       403
POST /api/review/confirm, no Origin                        403 {"error":"forbidden","reason":"bad_origin"}
POST /api/review/confirm, Origin=https://evil.allegis.app  403 {"error":"forbidden","reason":"bad_origin"}
POST /api/review/confirm, text/plain body                  403 {"error":"forbidden","reason":"bad_content_type"}
GET / signed in                                            200 (Find shell; Gaps tab disabled: not built (R-006))
GET /api/facets                                            200 kinds=46 entities=35 portcos=1 tiers=[{"value":"normal","n":46259}]
POST /api/find all labelled files, page 1                  200 total=46259 pageRows=50 shown=50 notShown={"noAccess":0,"checkFailed":0,"total":0} changedInDrive=0 groups=0 3956ms
POST /api/find kind=k1, entity filter, group by fiscal year 200 total=32 pageRows=32 shown=32 notShown={"noAccess":0,"checkFailed":0,"total":0} changedInDrive=0 groups=2 3856ms
POST /api/find fully executed + primary only, page 2       200 total=499 pageRows=50 shown=50 notShown={"noAccess":0,"checkFailed":0,"total":0} changedInDrive=0 groups=0 1487ms
POST /api/find with injection attempt                      400 {"error":"bad_spec","reason":"kind: bad value"}
POST /api/export kind=k1                                   200 rows=7216 header=file_id,document_id,kind,entities,portcos,fiscal_year,period,stage,signed_date,tier,is_primary,web_view_link
GET /api/views (seeds on first use)                        200 views=4 seeds=4
  seed "ACCSO · subscription docs"                         200 total=14 shown=14 notShown={"noAccess":0,"checkFailed":0,"total":0}
  seed "MTV-II · FY2025 close"                             200 total=2 shown=2 notShown={"noAccess":0,"checkFailed":0,"total":0}
  seed "Unsigned side letters"                             200 total=25 shown=25 notShown={"noAccess":0,"checkFailed":0,"total":0}
  seed "K-1s · tax year 2025"                              200 total=615 shown=50 notShown={"noAccess":0,"checkFailed":0,"total":0}
GET /api/review                                            200 counts={"stage_unknown":342,"low_confidence_executed":329,"no_kind":18417,"open_total":19088,"reviewed_today":1,"reviewed_total":1} shown=50 notShown={"noAccess":0,"checkFailed":0,"total":0} first_reason=stage_unknown page=0 nextPage=1 canWrite=true
POST /api/review/confirm with read-only session (no write) 409 {"error":"consent_required","login":"/api/auth/login?scope=write&next=/review"}
POST /api/review/confirm for a file not in the queue       404 {"error":"not_in_queue"}
```
- **Counts differ by one from item 0.** On the branch, `low_confidence_executed` is 329 and the open total is 19,088, against 330 and 19,089 in item 0. The difference is the single G4 test `review_event` on the branch. Main has none.
- **Seed rows deleted on the branch.** Before this run I deleted Ryan's old stand-in seed rows from the branch's `app.saved_view`, so the new seeds would insert.

**Not changed (listed only):**
- **C6:** export isn't live-checked per row (above).
- **CISO note:** CSRF protection now depends on the Origin header, which browsers always send on POST and DELETE. The check doesn't apply to `/api/auth/logout`: it is POST-only, and the worst a forged request can do is sign Ryan out.

### 3 · Ryan's steps after R1–R3 (PowerShell, in this order)

Run everything in one PowerShell window, because step 3 reuses `$owner`, `$pw` and `$appUrl` from step 2. Nothing below prints a secret. `npx wrangler secret put` either prompts for the value (hidden) or reads it from the pipe.

**Step 1 · R1: push to GitHub** (repo `ryparker24/allegis-catalog`, created empty)
```powershell
cd C:\DriveCatalog\app
git remote add origin https://github.com/ryparker24/allegis-catalog.git
git push -u origin main
```

**Step 2 · R4: migration and labelled-file load on MAIN**
```powershell
cd C:\DriveCatalog\app\db\migrations
$owner = ((Get-Content C:\DriveCatalog\catalog_db_url.txt | Where-Object { $_ -match 'UNPOOLED' }) -replace '^[^=]+=','').Trim().Trim('"',"'")
psql $owner -v ON_ERROR_STOP=1 -f 001_app_schema.sql
$pw = python -c "import secrets;print(secrets.token_urlsafe(24))"
psql $owner -v ON_ERROR_STOP=1 -v pw="$pw" -f 002_catalog_app_role.sql
python ..\load_labelled.py --url-file C:\DriveCatalog\catalog_db_url.txt
# expect: app.labelled_file: 46,259 IDs loaded; not in cat.file: 0; secret tier: 0
$appUrl = $owner -replace '^(postgres(?:ql)?://)[^@]+@', ('${1}catalog_app:' + $pw + '@')
```

**Step 3 · Deploy, then set the Worker secrets.** Deploying first is safe: until `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` are set, the Worker refuses every request with 403. Deploying first also means `secret put` doesn't stop to ask whether to create the Worker.
```powershell
cd C:\DriveCatalog\app
npx wrangler login                     # once per machine, as the Cloudflare account that owns allegis.app
npm ci
npm run deploy                         # opennextjs-cloudflare build + deploy; custom domain catalog.allegis.app

# CATALOG_APP_DB_URL  <- step 2 ($appUrl: the catalog_app role on MAIN, unpooled endpoint, db "catalog")
$appUrl | npx wrangler secret put CATALOG_APP_DB_URL

# SESSION_SECRET      <- generated here, 48 random bytes; never stored anywhere else
python -c "import secrets;print(secrets.token_urlsafe(48))" | npx wrangler secret put SESSION_SECRET

# GOOGLE_CLIENT_ID    <- R2: Google Cloud console, project "GP Member Portal" > APIs & Services > Credentials >
#                        the new OAuth 2.0 Web client > "Client ID"   (paste at the prompt)
npx wrangler secret put GOOGLE_CLIENT_ID
# GOOGLE_CLIENT_SECRET <- R2: same client > "Client secret"            (paste at the prompt)
npx wrangler secret put GOOGLE_CLIENT_SECRET

# CF_ACCESS_TEAM_DOMAIN <- R3: Cloudflare Zero Trust > Settings > Custom pages > "Team domain",
#                          e.g. <team>.cloudflareaccess.com            (paste at the prompt)
npx wrangler secret put CF_ACCESS_TEAM_DOMAIN
# CF_ACCESS_AUD       <- R3: Zero Trust > Access > Applications > the catalog.allegis.app app > Overview >
#                        "Application Audience (AUD) Tag"             (paste at the prompt)
npx wrangler secret put CF_ACCESS_AUD

npx wrangler secret list               # expect the six names above (values are never shown)
Remove-Variable owner, pw, appUrl
```
- **No redeploy needed.** Each `secret put` makes a new Worker version live at once.
- **Do not set `ACCESS_MODE`** on the deployed Worker. It exists for localhost only, and the check ignores it whenever the Access secrets are set.

**Step 4 · Check it is live (in a browser)**
1. Open `https://catalog.allegis.app`. Cloudflare Access should ask you to sign in first, then "Sign in with Google" appears. Sign in as `ryan@allegiscapital.com`.
2. **Find** should show 46,259 labelled files and the four seed views in the sidebar: ACCSO · subscription docs, MTV-II · FY2025 close, Unsigned side letters, K-1s · tax year 2025.
3. **Review** asks for label-write access the first time you confirm a row (the 409, then Google's consent screen).
4. Take the screenshots the order asks for here. They show file names, so keep them out of the repo.

**Step 5 · Clean up.** Delete the throwaway Neon branch `catwo01-test-throwaway` (`br-spring-frost-bdrt8htx`) on project `curly-sunset-06555843`: Neon console > Branches > the branch > Delete.

---

## Released (2026-11-17)

Released from commit `31c958996432da7b80d0a21a992a3c29171e8e68`, after Ryan finished R1–R3 and authorized the writes to main and the branch deletion for this release.

| Step | Result |
|---|---|
| 1 · Push | `origin` = `https://github.com/ryparker24/allegis-catalog.git` (private). The remote `main` head was `31c958996432da7b80d0a21a992a3c29171e8e68` at release. |
| 2 · Restore point | Neon branch **`pre-catwo01` = `br-shy-forest-bdmeb2id`**, taken from main (`br-misty-silence-bd0rx01g`) before any write. To roll back, restore main from this branch. |
| 3 · R4 on main | `001_app_schema.sql` and `002_catalog_app_role.sql` ran with the direct (unpooled) owner connection, then `load_labelled.py`. See the counts below. |
| 4 · Deploy | `npm run deploy` deployed Worker `allegis-catalog`, version `b07c8075-741c-485d-a965-af8f89c4bcb0`, on custom domain `catalog.allegis.app`. Plain settings: `APP_ORIGIN`, `ALLOWED_HD=allegiscapital.com`, `ALLOWLIST=ryan@allegiscapital.com`. `ACCESS_MODE` is not set. |
| 5 · Secrets | Six names set; sources in the table below. Values were never printed, logged or committed. Each upload used a temp JSON outside the repo, deleted afterwards and confirmed gone. |
| 6 · Verify | All six required secrets are present. The DB URL uses `catalog_app` on the pooled endpoint. An unauthenticated request gets a 302 to Cloudflare Access. The throwaway branch `br-spring-frost-bdrt8htx` is deleted. |

**Step 3 counts (main):**
- **Load:** `app.labelled_file` holds **46,259** rows, with 0 not found in `cat.file` and 0 secret tier.
- **Views present:** `v_entity`, `v_find`, `v_portco`, `v_review_counts`, `v_review_queue`, all `security_barrier`.
- **`app.v_find`** returns 46,259 rows as `catalog_app`.
- **`app.v_review_counts`:** stage_unknown 342, low_confidence_executed 330, no_kind 18,417, open_total 19,089, reviewed_total 0. This matches item 0.
- **Saved views:** `app.saved_view` has 0 rows. The seeds insert on Ryan's first visit.
- **G1/G2 on main, read-only: 26/26 passed.** Run with `py db/tests/check_main_readonly.py --owner-url-file ... --app-url-file ... --reference-url-file <throwaway branch>`.
  - Every session is `default_transaction_read_only`, so nothing was written.
  - G1 checked all 34 real secret-tier files against every view: 0 returned.
  - G1 also confirmed main's view definitions are identical to the throwaway branch, where the fixture tests passed 27/27.
  - G2 covers the full `catalog_app` privilege matrix across 48 relations, no CREATE on any schema, and the role's attributes and memberships. It also checks refused reads on cat/ref/ops, `review_event` and `labelled_file`, the append-only triggers, and that there are no SECURITY DEFINER functions.

**Step 5 secrets, by name:**

| Secret | Source |
|---|---|
| `CATALOG_APP_DB_URL` | Ryan's file, `C:\DriveCatalog\catalog_app.env`. Checked before upload: it logs in as `catalog_app` on main and sees 46,259 rows. |
| `CF_ACCESS_TEAM_DOMAIN` | Ryan's file. It matches `allegis.cloudflareaccess.com`, the team in Cloudflare's own login redirect, whose certs endpoint serves 2 keys. |
| `SESSION_SECRET` | Ryan's file, a fresh random value of at least 32 characters, different from `GOOGLE_CLIENT_SECRET`. It overwrote the value set earlier in the release. |
| `GOOGLE_CLIENT_ID` | Ryan's file (R2 client "Allegis Catalog", project GP Member Portal). |
| `GOOGLE_CLIENT_SECRET` | Ryan's file (same client). |
| `CF_ACCESS_AUD` | Ryan's file (R3 Access application AUD tag). |

- **Generated by me and kept:** none. Ryan's file supplied every secret.
- **Allowlist:** `ryan@allegiscapital.com` is a plain Worker setting in `wrangler.jsonc`, not a secret.
- **Interim values, all since replaced from the file:** I set `SESSION_SECRET` (generated, never printed), `CATALOG_APP_DB_URL` and `CF_ACCESS_TEAM_DOMAIN` once during the release.

**Step 6 checks:**
```
== required by code
present  GOOGLE_CLIENT_ID
present  GOOGLE_CLIENT_SECRET
present  SESSION_SECRET
present  CATALOG_APP_DB_URL
present  CF_ACCESS_TEAM_DOMAIN
present  CF_ACCESS_AUD
== DB URL role (from the file)
user: catalog_app | host contains -pooler: True
== unauthenticated request
302 https://allegis.cloudflareaccess.com/cdn-cgi/access/login/catalog.allegis.app?…
```
The 302 comes from Cloudflare Access, not the Worker, so Access sits in front of the app.

**Still open:**
1. Ryan's first sign-in at `https://catalog.allegis.app` (Access, then Google) is the live end-to-end check.
2. The screenshots from the order can be taken then.
3. Keep `pre-catwo01` until Ryan is satisfied, then delete it.
4. The local scratch files that held branch and main credentials during the release are deleted.

## CAT-WO-01.1 hotfix: Review page "shows no files"

**Diagnosis (counts and codes only):**
- (c) The queue view on main, read as `catalog_app`, has 19,089 open rows (342 / 330 / 18,417). The first page is all normal tier.
- `wrangler tail` captured two of Ryan's reloads:
  - `GET /api/review` page=0, skip=0 ids, 200, with log `review_page` count=50, dropped_no_access=0, dropped_check_failed=0.
  - This rules out (a) the 409 consent path, (b) the live check dropping every row, and (d) paging/skip state.
- A browser check (element counts only) showed counters 19,089 / 342 / 330 / 18,417, 50 rows, and the side panel open.
- The captured window has no failed requests. The earlier empty loads were not captured, so the original failure is **not reproduced**.

**Defect fixed:**
- **Before:** a failed Review load set an error that was rendered only inside the side panel. The panel is closed when no row is selected, which is always the case after a failed first load. The page therefore looked like an empty queue with every counter at 0.
- **After:**
  - Load failures (first load, Next page, the reload after Skip, the reload after a save) set a page-level `role="alert"` banner above the table: "Could not load the review queue: <error code> (<reason>), HTTP <status>".
  - A save that succeeded but was followed by a failed reload is no longer reported as "Not saved".
  - The page body was extracted into the presentational `ReviewView` so it can be rendered in tests.
- **Tests:**
  - `test/review_load_error.test.ts` failed first against the unfixed view (2 of 3 failed: no alert rendered) and passes after the fix.
  - The suite passes 48/48 and tsc is clean.
- **Deploy:** Worker version `b3400283-c8a6-4f80-9491-f738a0760ec4`.
