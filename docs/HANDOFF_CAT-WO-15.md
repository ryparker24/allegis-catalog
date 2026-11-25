# CAT-WO-15 · Review queue split · handoff

**Status:** RELEASED 2026-11-25 (~17:55 UTC) on Ryan's "please release CAT-WO-15" (2026-11-25 05:06 UTC), after CAT-WO-14.

## What it does
- `app.v_review_counts` + `review_total` (the queue without no_kind / status_unknown); open_total unchanged.
- Review: headline "To review" and the sidebar badge use review_total; No kind / Status unknown sit in "Backlog (rule rounds)"
  with "All lanes"; the default list shows the four review lanes.
- `POST /api/review/subject-bulk`: bulk Confirm of single-candidate Match subject rows, ≤ 500 per action (R-023), through the
  single-save Parties path. **Not clicked** in the release: that is Ryan's.

## Release steps
1. Restore point **`pre-catwo15` = `br-patient-waterfall-bdl7il6e`** (nightly still disabled from CAT-WO-14).
2. `cat-wo-15` rebased on main `e1a9e06` -> **`98110c0`**, tests 171/171, type check clean; pushed to main.
3. Migration 015 on main (0.1 s).
4. Worker deployed: version **`ef951557-48b2-4e18-adbb-d49725cda650`**; unauthenticated `/` and `/review` -> 302 (Access).
5. `app-main` moved to `98110c0`; nightly re-enabled (next run 22:00 MT).

## Counts on main after the release (with CAT-WO-14's labelled portal files)
To review **2,341** (stage unknown 328, executed low confidence 327, match subject 1,670, content disagrees 16); backlog: no kind
12,502, status unknown 9,079; all lanes 23,922.

**CATWO15 RELEASED 98110c0** (2026-11-25): main + `app-main`, Worker `ef951557`, restore point `pre-catwo15`, nightly enabled.

## Open
- Signed-in smoke test of the Review screen and the bulk Confirm (Ryan).
- Delete `pre-catwo15` and `catwo15-throwaway` after two clean nightlies (Ryan to confirm).
