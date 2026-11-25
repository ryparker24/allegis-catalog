# CAT-WO-17 · Duplicates and zips · dry run (throwaway)

Run 2026-11-25 on `catwo17-throwaway` (br-floral-leaf-bdscsctp); main untouched. Codes, counts and folder names only.
Before = ops.build_documents with CAT-WO-02's winner rule; after = migration `017_wo17.sql` (R-060), same data, same run.

## Duplicates (R-060)

| | Count |
|---|---:|
| Duplicate groups (same md5, 2+ live copies, all drives) | 43,551 |
| Extra copies | 61,248 |
| Groups whose winner changes | 12,265 (Finance winner 4,184 · Confidential winner 8,081) |
| Groups touching another drive (old rule kept) | 159 |
| Document titles that change (title = the winner's name) | 1,695 |
| Document kind that changes | 0 |
| Document fiscal year that changes (path-derived tie-break follows the winner) | 224 |
| Execution stage that changes | 0 |

Finance still always beats Confidential (it already did: shared drive first).

### Why the winner changed

| Reason | Old winner folder | New winner folder | Groups |
|---|---|---|---:|
| older | Confidential › Entire Revver Contents 11-12-2026 | same | 6,887 |
| older | Finance › 07-Taxes | same | 2,145 |
| older | Finance › 00-All Reports | same | 784 |
| archive | Confidential › Entire Revver Contents 11-12-2026 | same | 712 |
| older | Finance › 02-Legal | same | 450 |
| archive | Confidential › GP Portal (Published Docs) | Confidential › Partner Portal | 418 |
| older | Finance › 12-Valuation | same | 102 |
| older | Finance › 06-Vendors | same | 100 |
| older | Finance › 07-Taxes | Finance › 00-All Reports | 92 |
| older | Finance › 03-Cash | same | 87 |
| older | Finance › 14-Systems and GL | Finance › 06-Vendors | 52 |
| copyname | Confidential › Entire Revver Contents 11-12-2026 | same | 39 |

### Finance moves Ryan should look at (veto candidates)

| Old winner | New winner | Groups | Why |
|---|---|---:|---|
| 00-All Reports/1996 - 2010/2010 | 00-All Reports/2011 - 2020/2010 | 582 | the 2011-2020 copy was uploaded earlier (2025-05-13 vs 2026-05-31) |
| 07-Taxes/2011 - 2020/<year> (same year folder) | same year folder, other subfolder | ~1,700 | same upload day; earliest second wins |
| 02-Legal/Organized Entities - 2026-10-21/CIP, CSOP & Allegis CIP Mgmt (GP) | 02-Legal/CIP, CSOP & Allegis CIP Mgmt (GP)/LPA, Allegis Mgmt VI, Org & Syndication Costs | 141 | the 2026-10-21 folder is a later copy set |
| 07-Taxes/2025/03_KPMG Workpapers | 00-All Reports/2025/2025-Q4 | 59 | the report was filed first |
| 14-Systems and GL/Quickbooks/QB Desktop Enterprise | 06-Vendors/Quickbooks/Quickbooks Desktop Backups - May 2025 | 50 | the backup folder is older |
| 12-Valuation/2025/Valuation Support - Q3 2025 | Valuation Support - Q2 2025 | 33 | first quarter it was filed in |

## Ryan's vetoes (2026-11-25 17:16 UTC) · re-run

1. **Dropped:** a year folder outside its range folder (`2011 - 2020/2010`) is misfiled and loses (key `r060_misfiled`; 650 files,
   all in 00-All Reports). Moves from `1996 - 2010/2010` to the misfiled folder: 582 → **0**.
2. **Dropped:** `02-Legal/Organized Entities - 2026-10-21` is a preferred folder (`ops.dup_folder_pref`, key `r060_preferred`) and
   wins inside Finance. Groups leaving that folder: 387 → **0** (33 change winner inside it).
   Note for Ryan: every file in that folder was uploaded on one day (2026-10-22) and 1,606 of its 1,611 documents are also
   in the Revver copy, so it reads as a bulk export, not a hand clean-up. Where it overlaps the working folders it now wins
   over them: Subscription Docs 95, LPAs 56, Entity Formation Docs 18, GP Agreements 17. Set the row `active = false` to undo.
3. **Kept:** 59 KPMG workpaper copies give way to `00-All Reports/2025/2025-Q4`.

Key order now: Finance, non-Revver, preferred folder, not misfiled, not archive, no copy name, oldest created, shallower, file ID.

| After the vetoes | Count |
|---|---:|
| Groups whose winner changes | 11,319 (Finance 3,238 · Confidential 8,081) |
| Titles that change | 1,630 |
| Kind / execution stage that change | 0 / 0 |
| Fiscal year that changes | 224 |
| Find, Finance rows shown with copies hidden | 39,666 of 46,952 (unchanged) |

(The tables above this section are the first run, before the vetoes.)
## Release rehearsal (2026-11-25, `catwo17-throwaway-r2` = main after CAT-WO-14 / CAT-WO-15) · R-060 v2

The first dry run compared ops.build_documents only. A **full derive** (the nightly's, pages off, + checklists) on a fresh
copy of main showed more: kinds, K-1 parties, status and the audited-FS year are read from the **primary copy's folder and
name** (apply_derive_wo02), so the first rule ("oldest created wins") re-kinded files when it moved primaries wholesale.

| Full derive vs main today | v1 (oldest created) | **v2 (released rule)** |
|---|---:|---:|
| Find rows whose primary flag flips | 6,906 | **801** |
| Kind changes | 329 (135 K-1s lose their kind) | **0** |
| Fiscal year changes | 321 | **51** |
| Status changes | 705 | **7** |
| K1-SET Met | 257 → 249 | **257 → 257** |
| Every other checklist count | | **same as main** |

**R-060 v2:** Finance, non-Revver, preferred folder, not misfiled, not archive, no copy name, then CAT-WO-02's own
"newest modified", file ID. A primary moves only for a stated reason; "oldest created" and "shallower" are gone.
Ruling 3 (KPMG workpapers → 00-All Reports/2025/2025-Q4) is a second preferred-folder row.

v2 moves: 613 files become primary, 188 stop being primary. To Organized Entities 21 · to 00-All Reports/2025/2025-Q4 71 ·
to Partner Portal (from GP Portal `Archive (unused)`) 425 · out of archive-like folders 92 · to the misfiled 2010 folder 0.

**R-061 fix:** 187 documents in Find have their primary on a drive outside Find (164 in LIMITED - Investment Team). Hiding
every non-primary row would have removed them from Find, so a copy is hidden only when its document's primary is itself in
Find. Find after release: 48,889 rows, **40,804 shown** with copies hidden (8,085 hidden).
## Find (R-061)

Finance files in Find: 46,952 → **39,666** shown with copies hidden (7,286 copies hidden). Confidential files are not in
Find yet (CAT-WO-14 adds the portal folders). Review queue unchanged (it does not hide copies).

## Zips (R-062)

Ryan's OK 2026-11-25 16:43 UTC ("Yes to Both": Finance and Confidential). Listed in memory with drive.readonly, net guard on,
nothing on disk or Drive; 4 workers, 21 min, 9.1 GB. Written to `cat.zip_listing` / `cat.zip_member` on the throwaway only.

| | Finance | Confidential |
|---|---:|---:|
| Zips | 729 | 959 |
| Files inside (incl. one nested level) | 13,442 | 35,476 |
| Also on Drive (same md5 as a catalog file) | 9,537 | 8,478 |
| **Only inside a zip** | **3,767** | **26,582** |
| Not hashed (password-protected or too big) | 138 | 416 |

All zips: 1,596 listed, 80 password-protected (names only), 2 not real zips, 0 failed, 0 over the cap.

Only inside a zip, by folder:

| Folder | Files | Zips | PDF | Excel/CSV | Word | Images |
|---|---:|---:|---:|---:|---:|---:|
| Conf › Entire Revver Contents 11-12-2026 | 26,582 | 403 | 2,590 | 747 | 184 | 16,533 |
| Finance › 07-Taxes | 1,943 | 145 | 1,287 | 635 | 0 | 0 |
| Finance › 14-Systems and GL | 1,649 | 117 | 0 | 30 | 0 | 0 |
| Finance › 06-Vendors | 97 | 5 | 91 | 4 | 0 | 0 |
| Finance › 02-Legal | 55 | 10 | 55 | 0 | 0 | 0 |
| Finance › 04-Mgmt Co | 18 | 4 | 8 | 1 | 0 | 0 |
| Finance › other | 5 | 4 | | | | |

(14-Systems and GL: 1,575 of 1,649 are .xml / .rels export parts, plus 44 .md and 30 .csv; not documents.)

### CIP-II 2025 investor K-1s

Yes, they are in a zip: `07-Taxes/2025/01_Partner Packages/Zipped Files/Cyber Innovation Partners II, LP_TY25 Investor
Package.zip`, 117 files, all K-1-named. **All 117 are also on Drive as loose files** in `07-Taxes/2025/01_Partner Packages/CIP-II`,
where the catalog already has them as kind k1 (main). Nothing about them is only inside the zip. Same folder also holds
CIP II Administrative TY25 (4, all loose too) and the CIP-II 1042-S packages (17 + 2 files only inside zips: the amended
1042-S and one final 1042-S set).