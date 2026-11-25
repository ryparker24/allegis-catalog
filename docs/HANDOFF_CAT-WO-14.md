# CAT-WO-14 · Partner Portal + LP Portal folders (Confidential) · handoff

**Status:** RELEASED 2026-11-25 (16:44–17:50 UTC) on Ryan's "Run the nightly now; if it's clean, release CAT-WO-14 with the portal
labels, then CAT-WO-15" (2026-11-25 05:20 UTC). R-059 = option A (Ryan): portal copies are Issued and count toward checklists.

## Before the release
- The 2026-11-24 22:00 nightly failed at `crawl` (KeyError 'fileId': a shared-drive change has no file). Fix in
  `C:\DriveCatalog\drive_crawl.py` (outside the repo; backup `drive_crawl.py.pre-nightlyfix.bak`): skip changes with no fileId.
  The manual rerun `nightly_20261124_2220` finished ok at 06:36 UTC.
- No other release in flight (CAT-WO-09, -11, -17 on their branches; nightly enabled by no one else).

## Release steps
1. Restore point **`pre-catwo14` = `br-royal-glade-bdekxn6s`**; nightly disabled.
2. `cat-wo-14` rebased on main `9945b15`, pushed (`9ac29df`, then the script fix `e1a9e06`); `app-main` moved.
3. Migration 014 on main (label scope, folder rules, R-059 = A, aliases).
4. `scripts/release_wo14.py derive`: folder ancestors, server rules, documents, content checks, apply_derive, page 1 of the
   portal PCAP / K-1 / capital-call documents (1,017 read, all ok), content check, subject, checklists.
5. Labels: 1,937 portal files labelled (Catalog Review = Needs review), **0 errors**. A first run through the release script
   used the crawler's read-only login and got 403 on every file (nothing written); the label login (labels_sync.creds, as the
   nightly) was used for the run that wrote. The script is fixed (`e1a9e06`).
6. Derive + checklists again with the labelled copies.

## Results on main (match the dry run, option A)
| Rule | Met | On file | Missing |
|---|---:|---:|---:|
| PCAP-Q | 358 -> **377** | 22 -> 23 | 201 -> **181** |
| K1-SET | 208 -> **257** | 41 -> 48 | 164 -> **108** |

Also (entities from any copy): AUDITED-FS Met 31 -> 32; LP-SUB Met 70 -> 72, Missing 146 -> 142; LP-SIDE none found 260 -> 259.
Option A set Issued on 249 documents with a portal copy. Portal files labelled: 1,937.

**CATWO14 RELEASED e1a9e06** (2026-11-25): main + `app-main` (then moved on with CAT-WO-15), restore point `pre-catwo14`
(`br-royal-glade-bdekxn6s`). The Worker was deployed with CAT-WO-15 (no app change in CAT-WO-14).

## Open
- Delete after two clean nightlies: `pre-catwo14`, `catwo14-throwaway`, `-r2`, `-r3`, `-r4` (Ryan to confirm the deletes).
- LP Portal 2026-Q3 folders "LS-III" / "FP-2026" have no catalog entity (Ryan).
