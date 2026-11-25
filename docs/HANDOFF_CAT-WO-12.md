# HANDOFF · CAT-WO-12 · Find: text search as a filter, in-window search field, edited saved views

**Status:** RELEASED 2026-11-25 (01:20 UTC). `CATWO12 RELEASED 2ff3776`. Worker version `59cc706a-a4bb-4df4-848d-112c5e907cb8` on `catalog.allegis.app`. main fast-forwarded `d919695..2ff3776`; `app-main` moved to `2ff3776` before the 22:00 nightly (app-only change; the nightly pipeline is untouched).

Order: `C:\DriveCatalog\orders\CAT-WO-12_Find_Text_Search_Filter.md`. App-only: no Drive writes, no label changes, no rules, **no migration** (`app.saved_view.spec` is jsonb and holds `search` as is).

## What changed
- **Text is a filter.** One term (`search` in the spec; `?q=` only as the hand-off from the header box on another page) shows as the chip `TEXT <term> ×`, first in the chip row, counted in "N filters". Chip ×, **Clear all** and More › Clear filters remove it. It goes to `/api/find` and `/api/export` like every other filter; changing it resets to page 1. The `Search: "…" clear` line under the title is gone.
- **In-window search field** in the list card, start of the chip row (below the Filters / Columns toolbar, above the column headers). Combines with every filter in force. Commits 300 ms after typing stops or on Enter; Esc clears; × when non-empty. `/` still focuses the header box. **Filters** panel has a **Text** entry that takes you to the field.
- **Header search starts fresh.** Clears every filter, column filter, sort and grouping and leaves the open saved view (sidebar highlight goes); page size and columns are kept. The header box empties after submit. From another page it navigates to `/?q=…`, which Find treats the same way and then removes from the address bar.
- **Saved views.** Title = the view's name; any change to filters, text, columns or sort → `<name> · edited` (replaces "Saved view · changed") with **Update view**, **Revert**, **Save as new view**. Title is `Search results` when the text term is the only filter, else `Find`.
- **Storage rule changed (Ryan, 2026-11-24/25):** saved views now **store their text term** (reverses CAT-WO-02's "search text is never stored" for saved views only). The last-state pref (`app.user_pref`, key `find`) still never stores it; the tab's own term lives in `sessionStorage` (`catalog.find.q`), else Find takes the open view's term.

## Files
- `src/lib/findstate.ts` (new): the list-state rules as plain functions (wire, fingerprint, headerSearch, setText, setFilter, clearAll, revert, restoredText, chipsOf, titleOf).
- `src/components/FindClient.tsx`: uses findstate; `TextSearchField`; header / start-up flow; Update / Revert / Save as new.
- `src/components/AppShell.tsx`: header box empties after submit, no longer refills from `?q=`; `PageHeader` title takes a node.
- `src/lib/views.ts`: `storedSpec` keeps `search`.
- `src/app/globals.css`: in-window field, TEXT chip, "· edited".
- Tests: `test/wo12.test.ts` (new, 17 tests); `test/wo02_part1.test.ts` #5 updated to the new storage rule. **159/159 pass**; typecheck clean.

## Preview (Stop 1)
Local Worker (`wrangler.local.jsonc`) + `scripts/dev_proxy.ts` against throwaway Neon branch **`catwo12-throwaway` (`br-red-lake-bd8e5417`, endpoint `ep-lucky-breeze-bdphmtqu`)**, created 2026-11-25 00:48 UTC on Ryan's "throwaway ok". `?mask=1`. Screenshots in `C:\DriveCatalog\proofs\catwo12\` (outside the repo):
1. saved view opened: `2025 K-1s`, 4 chips, 218 files;
2. header search `w-9` from that view: `Search results`, only `TEXT w-9`, 214 files, rail highlight gone;
3. `2025 K-1s · edited`: in-window `MTV-IV` + the view's filters, 5 filters, 45 files; Update / Revert / Save as new; Revert → 218, not edited;
4. Kind W-9 / W-8 + in-window `CIP`: 2 filters, 211 → 66; restored after reload.
Afterwards the Worker and proxy were stopped, ports 8787/8788 confirmed free, `.dev.vars` and the dev secret deleted.

## Release (Stop 2, Ryan said "apply" 2026-11-25 01:12 UTC)
- Tests green; branch already on current origin/main (`d919695`); CAT-WO-11 not mid-release (its release waits for the 2026-11-24 22:00 nightly gate). No restore point: no migration, no main DB writes.
- `npm run deploy` → version `59cc706a-a4bb-4df4-848d-112c5e907cb8`. Unauthenticated `/`, `/api/find`, `/api/views` → 302 to Cloudflare Access.
- `git push origin cat-wo-12:main` (fast-forward); `app-main` detached at `2ff3776`.
- **Not done:** signed-in smoke test on production (needs Ryan's browser through Access).
- **CAT-WO-11 note:** `cat-wo-11` must rebase on `2ff3776`. Overlap is `src/components/FindClient.tsx` only if it touched Find.

## Clean-up
- Throwaway `catwo12-throwaway` (`br-red-lake-bd8e5417`): delete when Ryan has finished with it (not deleted; needs his say-so).
