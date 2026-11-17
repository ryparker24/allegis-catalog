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
- **Seed views:** the four seeds are my stand-ins ("K-1s, latest year first", "Signed agreements (primary copies)", "Bank statements by entity", "No kind yet"), because designs v0.1 are not in this workspace. Edit `SEED_VIEWS` in `src/lib/find.ts` to match the design. Seeds are inserted per user on first visit.
- **"Fully executed at low confidence"** = the document's stage is `fully_executed` and the content check's confidence is `low` (330). Counting by the scan's suggested stage instead gives 285.
- **Export** reads the DB only (codes plus links, no names, up to 50k rows) and is not live-checked per row. A link opens only if Google allows it.
- **Stack:** "same as Datum" could not be checked, because I did not open the Datum repo, as instructed. I used OpenNext (`@opennextjs/cloudflare`); swap if Datum uses vinext.
- **Item 4 live check:** a second write (the restore) went to the same single file, so Drive was left as found.
- **Review lane:** items 2, 4 and 5 (roles, Drive write path, access) still need the coder + CISO review named in the order. I have not run it.
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
