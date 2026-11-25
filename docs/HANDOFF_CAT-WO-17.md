# HANDOFF · CAT-WO-17 · Duplicates and zips (LIMITED - Finance + Confidential)

**Status:** RELEASED 2026-11-25 (~18:45 UTC) on Ryan's rulings in the thread (17:16 UTC: drop moves 1 and 2, keep 3; zips
"Yes to Both" 16:43 UTC). Worker version `fe602182-ee62-4f67-9fa2-ae29a42a5972` on `catalog.allegis.app`. Released after
CAT-WO-14 (e1a9e06) and CAT-WO-15 (98110c0).

Order: `C:\DriveCatalog\orders\CAT-WO-17_Duplicates_and_Zips.md`. Dry runs and the rehearsal: `docs/CAT-WO-17_DRYRUN.md`.
No label changes, no Drive writes. Rules R-060, R-061, R-062.

## What changed
- **R-060 v2 · which copy is primary** (migration `017_wo17.sql`, step 1 of `ops.build_documents`), only for duplicate groups
  wholly inside Finance + Confidential: Finance, non-Revver, **preferred folder** (`ops.dup_folder_pref`), **not misfiled**
  (year folder outside its range folder), **not archive-like**, **no copy name**, then CAT-WO-02's newest modified, file ID.
  Keys live in `ops.v_file_r060`. Preferred rows (Ryan): `02-Legal/Organized Entities - 2026-10-21`,
  `00-All Reports/2025/2025-Q4`. Undo one: `UPDATE ops.dup_folder_pref SET active = false WHERE …`, then a derive.
- **Why v2:** kinds, K-1 parties, status and the audited-FS year are read from the PRIMARY copy's folder / name
  (`apply_derive_wo02`). v1 ("oldest created wins") moved 6,906 primaries and re-kinded 329 files (135 K-1s lost their kind,
  K1-SET Met 257 → 249). v2 moves a primary only for a stated reason. **Never judge a primary-rule change from
  ops.build_documents alone; run the full derive** (`scripts/release_wo17.py derive` on a throwaway).
- **R-061 · Find hides copies** (`src/lib/find.ts` `HIDE_COPIES_SQL`, opt `hideCopies` set by /api/find and /api/export
  only; the Review queue is unchanged). A copy is hidden only when its document's primary is itself in Find. Shown again by
  the **Show copies** box (Filters › Primary copy), the Primary copy filter, or a File ID / Catalog ID filter. Chip
  `COPIES shown`.
- **R-062 · zip contents** (`pipeline/zips_wo17.py`, `cat.zip_listing`, `cat.zip_member`, `app.v_zip_member`, `app.v_zip_listing` (the app role has no USAGE on `cat`),
  `/api/zip`, `ZipContents.tsx`): side panel **Inside this zip** on a `.zip` row, each member "also on Drive" (same md5;
  linked when the user can open it) or "only in this zip". Read in memory, drive.readonly, net guard; nothing on disk.

## Main after release
- Derive on main (pages off) + checklists: primary flag flips 801 (613 become primary, 188 stop), kind 0, stage 0, fiscal
  year 51, status 7, entities 0. Every checklist count unchanged (K1-SET Met 257, PCAP-Q Met 377).
- Find: 48,889 rows; 40,804 shown with copies hidden.
- Zips: 1,688 listings / 51,198 members copied from `catwo17-throwaway` (same file, same md5), not downloaded twice.
  Finance 729 zips, 3,767 files only inside a zip; Confidential 959 zips, 26,582 only inside a zip (all Revver copy).
  80 password-protected (names only), 2 not zips.
- CIP-II TY25 investor K-1s: in `07-Taxes/2025/01_Partner Packages/Zipped Files/…TY25 Investor Package.zip` (117), all 117
  also loose in `…/01_Partner Packages/CIP-II` (kind k1). Question closed.
- Tonight's nightly will write labels for the 51 fiscal-year and 7 status changes (normal re-sync).

## Not done / follow-ups
- **Nightly does not list new zips.** Run `py pipeline\zips_wo17.py --db-url-file C:\DriveCatalog\catalog_db_url.txt --release --apply`
  by hand (it only reads zips that are new or whose md5 changed), or add it as a nightly step in a later order.
- Signed-in smoke test on production (needs Ryan's browser through Access): Show copies box, a zip's side panel.
- Ryan to confirm whether `Organized Entities - 2026-10-21` is a real clean-up or a bulk Revver export (uploaded in one day;
  1,606 of 1,611 documents also in the Revver copy). It is preferred as ruled.
- 26,582 Revver-copy files exist only inside zips (16.5k images): part of the Revver phase (CAT-WO-10), not this order.
- `ops.wo17_release_before` (snapshot of Find before the release) can be dropped with the restore point.

## Clean-up after two clean nightlies
Neon: `pre-catwo17` (br-sweet-frost-bdexoj7k), `catwo17-throwaway` (br-floral-leaf-bdscsctp), `catwo17-throwaway-r2`
(br-steep-snow-bdy0rfpu). Files: `C:\DriveCatalog\catwo17_branch_url.txt`, `catwo17r2_branch_url.txt`.

## Other branches
cat-wo-09 / 11 / 16 must rebase: `src/lib/find.ts`, `findstate.ts`, `FindClient.tsx`, `SidePanel.tsx`, migration 017.
Next free rule number is tracked in CAT-WO-09's notes (R-069 at the time of writing).
