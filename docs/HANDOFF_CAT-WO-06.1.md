# CAT-WO-06.1 handoff · GP folder entities + read new documents first

*2026-11-22. Codes and counts only; folder names that are not entity codes are given as S-numbers (S-10, S-12 as in the CAT-WO-06 diagnosis). Decision: Ryan, "GP folder rules + read new first" (decision card).*

**Status (kept current):** built on git branch `cat-wo-06-1` from main `192c61a`; tested on the throwaway `catwo06-throwaway` **as-is** (not reset from main: resetting a branch needs Ryan's own request, so the throwaway still carries the CAT-WO-06 test reads; its K-1 baseline matched main: K1-SET Met 48). Main waits for the 2026-11-22 22:00 nightly and the coordinator's go.

## What changes
| Piece | Where | Notes |
|---|---|---|
| Generic GP folder rule | `db/migrations/010_wo061.sql` → `ops.decomposition_rule` **ENT-GP-P** (path_segment, `(?i)^(.+ \(GP\))$` → the whole folder name as entity), provisional | resolved through `ref.entity_alias`, like every path entity |
| GP code aliases | same migration: upper-cased code of every GP entity (7 new rows; the rest existed) | `cat.v_file_entity` joins on `upper(value)` |
| Two folder aliases | same migration: S-10 → MTV-III (PF) (GP), S-12 → MTV-IV (Annex) (GP), looked up from `cat.folder` at run time (no folder name in the repo or reports) | 2 rows |
| Read new first | `pages_wo06.to_read` / `fresh_key` | person-picked lane documents, then documents created / modified in the last 14 days or changed since their read (newest first), then the never-read backlog (oldest first) |

## Throwaway results (derive + checklists, pages step off)
- **K1-SET Met 48 → 123 (+75)**; Missing 345 → 269; On file 20 → 21.
- By GP entity, FY2025 (Met): ASOF (GP) 0 → 11 · CIP-II (GP) 0 → 12 (1 On file) · MTV-III (PF) (GP) 0 → 11 · MTV-IV (Annex) (GP) 0 → 12 · MTV-IV (GP) 0 → 18 · MTV-V (GP) 0 → 12 · CIP-I (GP) 13 unchanged · NL-I (GP) / NL-II (GP) / X (GP) unchanged (folders named after the fund; no rule, as ruled).
- **One fund row leaves Met:** MTV-IV (Annex) K1-SET 2025, 1 → 0. Its document is a GP K-1 in folder S-12, posted in the GP portal to a different partner; with the GP entity on the document the old file-name match is no longer the only high match, so only the portal's partner stays. The earlier Met was most likely a false positive.
- PCAP-Q and LP-SUB unchanged (176 / 70).
- Entity labels: the GP entity is added next to the fund code on these files (as CIP-I (GP) already had); all GP choices exist on the published Entity label (no Label manager change).

## Tests
- pipeline `test_wo06` 51/51 (+ the read-new-first order) · wo03 36/36 · wo04 13/13 · wo05 23/23 · label sync 34/34
- DB guards `test_wo06_guards` 15/15 on the throwaway

## Defaults taken (for Ryan's review)
1. **One generic rule instead of six per-folder rules:** any folder named "<entity> (GP)" gives the GP entity once its upper-cased name is an alias. The NL-I / NL-II / X folders are picked up automatically if renamed "… (GP)".
2. **The fund code in the same folder name still counts** (CIP-II (GP) folder → CIP-II and CIP-II (GP)), mirroring CIP-I (GP). The fund's rows don't gain anything from it (the partners are GP members).
3. **"New" = created or modified in the last 14 days, or changed since the read.**
4. The rule applies to every folder with such a name (other years' partner-package folders too: 5–8 folders per name).

## Release log
*Waiting for the 2026-11-22 22:00 nightly (and its pickup of the 119 new CIP-II PCAPs) and the coordinator's go.*
