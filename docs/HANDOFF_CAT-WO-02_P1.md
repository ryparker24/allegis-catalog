# CAT-WO-02 Part 1 · released (Datum look, Datum lists, Labels panel, saved-view folders)

*2026-11-17 (MST). Codes, IDs and counts only: no LP, individual or file names. Part 2 (items 0, 5–9) is built and
reviewed on branch `cat-wo-02-p2` against a throwaway Neon branch; it is not released (see its handoff on that branch).*

## Released

| Step | Result |
|---|---|
| Hotfix first | CAT-WO-01.1 `56158ad` (deployed by the hotfix tab as Worker `b3400283…`). Part 1 was rebased onto it, and the Review screen was rebuilt on its `ReviewView` (its page-level load-error banner and its render tests kept). |
| Ancestry | `git merge-base --is-ancestor 56158ad28b790e93fe80e68f34b4c0a638cffb5e HEAD` → **exit 0** (the hotfix commit is an ancestor of the released head). |
| Restore point | Neon branch **`pre-catwo02-p1` = `br-blue-recipe-bda3c0cs`**, taken from main (`br-misty-silence-bd0rx01g`) before any write. To roll back, restore main from it. |
| DB on main | `db/migrations/003_wo02_part1.sql` was run as the owner (direct endpoint), exit 0. |
| G1/G2 on main (read-only) | `py db/tests/check_main_readonly.py` → **25/25 passed** (privilege matrix including `view_folder` and `user_pref`; secret tier never returned; no SECURITY DEFINER). |
| Push | `origin/main` fast-forwarded to the Part 1 head (`56158ad..997abe0`, then the two fixes below). |
| Deploy | Worker `allegis-catalog` on `catalog.allegis.app`. Final version **`2dec1196-f5d1-4fc9-9daa-ec1f5f05b45a`** (earlier the same day: `5f9b96b4…`, `9be79fb6…`). Unauthenticated request → 302 to Cloudflare Access. All six secrets present. No secret or setting changed. |

**Main after 003:**
- Saved views: Ryan's 4 seed views are filed in **Tax (1) · Agreements (2) · Close (1)**; 0 unfiled.
- `catalog_app` has I/U/D on `app.view_folder` and `app.user_pref`, and nothing on `cat`.
- `app.v_entity` now shows names for 28 entities.

## What Part 1 delivers
- **Datum look:** dark rail and top bar, serif page titles, green primary buttons, Labels button. On Find and the Review queue (in the screens below).
- **Item 2 · Datum lists (Find):**
  - columns can be resized, reordered and sorted (server-side);
  - each header has a filter suited to the column type;
  - pages of 10 / 25 / 100;
  - layout is saved with a view, and the last state is kept per user.
- **Item 2 · Datum lists (Review queue):**
  - columns can be resized and sorted (server-side);
  - header filters: lane, kind, stage, entity, fiscal-year range;
  - pages of 10 / 25 / 100, with the pager above and below the list;
  - the last state is kept per user.
  - The queue's default order is unchanged. The default page size is now 25 (was 50); the API still returns 50 when no size is asked for.
- **Item 3:** the Labels panel (read-only).
- **Item 4:** saved-view folders with PINNED, nested two levels at most (enforced in the DB), drag-drop / Move to…, and the seed folders.

## Reviews (designer + coder), all rounds
- **Shell / Find / Labels / folders:** designer 4 must-fix + 9 should-fix; coder 2 defects + 11 minors. Fixed; see commit `a060170`.
- **Review screen:**
  - **Designer:** 3 must-fix + 6 should-fix + 5 nits.
    - Must-fix: a CSS rule turned the card numbers grey and the explanations upper-case; the error banner had too little contrast; six cards squeezed onto one row.
    - Also: Find's full pager, empty states, focus styles and the shorter Confirm button.
  - **Coder:** 2 defects, both fixed.
    - A column drag reloaded the queue and wiped the form.
    - Overlapping loads could show stale rows.
    - Also fixed: the saved sort and widths are now validated; Previous works after a forward walk; the "Why" sort now reverses; prefs aren't rewritten on every visit.
  - See commit `997abe0`.
- **Not done (noted for a follow-up):**
  - the Review queue has no column order or visibility controls (Find has both);
  - the top-bar search is not applied to the queue;
  - Confidence has no header filter;
  - the resize separator has no arrow-key control (same on Find).
- **Tests:** `npx vitest run` → **73 passed (73)** (includes the hotfix's 3 render tests); `tsc` clean.

## Found after the first deploy (fixed and redeployed)
1. **Dangling CSS selector.** Removing a duplicate rule left a bare `.grid`, which turned the next rule into `.grid .ctr.kpi .k-exp`, so the one-line card explanations didn't apply. Fixed in `a82c659`. A scan of `globals.css` finds no other dangling selector, and the braces balance.
2. **Screenshot mode didn't hide document content.** `?mask=1` masked file names only, but the Review page opens the first row's Drive preview, which shows the document itself.
   - One proof screenshot showed document content: an LP name and a person's contact details. That screenshot was deleted at once and is not in this handoff.
   - `0a0b84b` makes screenshot mode replace the preview with a placeholder (display-only; normal use unchanged).
   - Before each later screenshot, a check confirmed 0 iframes on the page and every visible name masked.

## Proof (live deployment, names masked, preview hidden; screenshots kept outside the repo)
- **Review queue:** counters 19,089 open · 342 stage unknown · 330 executed at low confidence · 18,417 no kind; 25 rows; "Page 1 of 764 · 1–25 of 19,089 files"; no load error.
- **Find:** saved view "ACCSO · subscription docs" (filed under Agreements): 14 files, 3 filter chips, Datum pager and toolbar.
- **Labels panel:** Allegis Document fields with "Editable after Part 2" / "Machine-set" tags.
- The screenshot visits set Ryan's own "last view" preference on main (`app.user_pref`, Find = the ACCSO view). That is ordinary app behaviour and the only app-side write.

## Ryan
- Keep `pre-catwo02-p1` until satisfied, then delete it (Neon console → Branches).
- The throwaway branch `catwo02-test-throwaway` (`br-red-band-bd2d79yz`) holds Part 2's work; keep it until Part 2 is released.
