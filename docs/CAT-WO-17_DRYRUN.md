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

## Find (R-061)

Finance files in Find: 46,952 → **39,666** shown with copies hidden (7,286 copies hidden). Confidential files are not in
Find yet (CAT-WO-14 adds the portal folders). Review queue unchanged (it does not hide copies).

## Zips (R-062)

Pending Ryan's OK to download (asked 2026-11-25). In scope: Finance 729 zips, Confidential 959 (non-empty, not Secret);
none over the 1.5 GB cap (largest 904 MB).
