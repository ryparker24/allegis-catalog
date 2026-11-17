# Allegis Catalog app (v1)

CAT-WO-01. Find and Review queue over the Allegis Drive Catalog (Neon `curly-sunset-06555843`, db `catalog`).
Users: Ryan only. Rows: files carrying the **Allegis Document** label (Decision 1 default), secret tier never.

Next.js 16 on Cloudflare Workers via `@opennextjs/cloudflare`. Hostname `catalog.allegis.app`, behind
Cloudflare Access **and** Google sign-in (both must pass).

## Layout

| Path | What |
|---|---|
| `db/migrations/001_app_schema.sql` | schema `app`: `labelled_file`, `saved_view`, `review_event` (append-only), views `v_find`, `v_review_queue`, `v_review_counts`, `v_portco`, `v_entity`; secret tier excluded **in the view** |
| `db/migrations/002_catalog_app_role.sql` (+ `_grants.sql`) | role `catalog_app`: SELECT on views, I/U/D on `saved_view`, INSERT on `review_event`, nothing on `cat`/`ref`/`ops` |
| `db/load_labelled.py` | loads labelled file IDs (from the labelling run's resume list) into `app.labelled_file` |
| `db/tests/test_guards.py` | G1 + G2 DB guard tests (throwaway branch only; refuses the main endpoint) |
| `src/lib/*` | session (sealed cookie, access token only), access (Cloudflare Access JWT), authz (domain + allowlist), google (OAuth online, Drive batch), live (per-page access check), find (SQL builder), labels, review |
| `src/app/api/*` | `auth/{login,callback,logout}`, `me`, `facets`, `find`, `export`, `views`, `review`, `review/confirm` |
| `test/*.test.ts` | vitest unit tests (G3, G5, G6 and the rest) |
| `scripts/measure_item0.py` | item 0 measurement (read-only) |
| `scripts/mtime_check.ts` | G4 live modifiedTime check (one pilot-folder file) |
| `scripts/access_sweep.py` | G3 manual-check helper (read-only) |
| `scripts/worker_smoke.ts` | end-to-end smoke test against `wrangler dev -c wrangler.local.jsonc` (branch DB) |

## Run

```
npm ci
npm test                      # unit tests
npx tsc --noEmit
cp .dev.vars.example .dev.vars   # fill in; CATALOG_APP_DB_URL must be a THROWAWAY BRANCH for local work
npx opennextjs-cloudflare build && npx wrangler dev -c wrangler.local.jsonc --port 8787
npm run deploy                # only after R2 + R3 and the Worker secrets are set
```

Worker secrets (`npx wrangler secret put <NAME>`): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`,
`CATALOG_APP_DB_URL`, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`. No KV, R2, D1 or Durable Object bindings.

## Privacy rules (enforced in code)

- No file name column exists in any `app` view; names come only from the live Drive call, as the user, and go to the browser only.
- Worker logs pass through `src/lib/log.ts`: allow-listed keys (IDs, codes, counts), anything else dropped.
- No refresh token is requested (`access_type=online`), parsed, or stored. The session cookie expires with the access token.
