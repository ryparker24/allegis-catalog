# CAT-WO-13 · PCAP cadence per fund (R-058) · handoff

**Status:** RELEASED 2026-11-25 (≈01:40 UTC) on Ryan's "CAT-WO-13 - please apply" (2026-11-25 01:26 UTC).

## What it does
- `db/migrations/013_wo13.sql`: `ops.requirement_cadence` (quarterly / annual / none, `first_period` yyyyq), R-058 seed for
  PCAP-Q (11 quarterly, 4 annual, from 2025 Q4; ruled_by `Ryan R-058`), PCAP-Q v2 = v1 + `entity_filter.cadence` (v1 kept),
  `app.v_requirement` + `cadence` (no row = annual).
- `pipeline/requirements_wo03.py`: quarterly = quarters >= first_period; annual = Q4 only from the first year; none = no rows;
  an entity with no row = annual from the rule's first FY (14 entities on main, incl. the no-roster rows).
- Checklists: cadence beside the entity (rows, scope list, Gaps) and a Cadence filter.
- Tests: `pipeline/test_wo13.py` 10/10, `test/wo13.test.ts` 4/4; app suite 163/163 after the rebase on CAT-WO-12.

## Dry run (throwaway `catwo13-throwaway` = `br-blue-butterfly-bdd5z840`)
See `docs/CAT-WO-13_DRYRUN.md`: PCAP-Q rows 2,103 -> 588, Missing 1,674 -> 201, Met + On file 380 -> 380.

## Release steps (2026-11-25 UTC)
1. No other release in flight (CAT-WO-12 released and closed; CAT-WO-11 waiting for the 22:00 nightly).
2. Restore point **`pre-catwo13` = `br-sparkling-glade-bdxic70x`** (main, no compute).
3. Task "Allegis Catalog nightly" disabled.
4. `cat-wo-13` rebased on main `27e2aac` -> `d14c172`; `git push origin cat-wo-13:main` (fast-forward `27e2aac..d14c172`).
5. Migration 013 on main (`scripts/run_sql_wo03.py --release`), 0.2 s; no open sessions on main beforehand
   (the `app.v_requirement` replacement waits on open readers).
6. Checklists rebuilt on main (`requirements_wo03.py --release --apply`), 1,641 rows:
   - PCAP-Q **588** rows (was 2,103): Met 358, On file 22 (Met + On file **380**), Missing **201** (was 1,674), No roster 7 (was 49).
     By cadence: quarterly 383, annual 205.
   - Unchanged: AUDITED-FS 34, GP-COMMIT 21, K1-SET 428, LP-SIDE 285, LP-SUB 285 (same results as before the build).
7. Worker deployed (`npm run deploy` from `d14c172`): version **`54e308bb-9b75-4134-a17c-6827d64341b7`**; unauthenticated `/` and
   `/api/checklists` -> 302 to Cloudflare Access.
8. `app-main` moved to `d14c172` (detached).
9. Nightly re-enabled: next run 2026-11-24 22:00 (MT).

**CATWO13 RELEASED d14c172** (2026-11-25): main + `app-main` on this commit, Worker version `54e308bb-9b75-4134-a17c-6827d64341b7`,
restore point `pre-catwo13` (`br-sparkling-glade-bdxic70x`), nightly enabled. This line was added in a docs-only commit after
the release commit.

## Open
- Delete `pre-catwo13` and `catwo13-throwaway` after two clean nightlies.
- Signed-in smoke test of the Checklists cadence column / filter (Access sign-in; not done here).
