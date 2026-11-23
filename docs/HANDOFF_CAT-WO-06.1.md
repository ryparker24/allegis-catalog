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
1. 2026-11-22 22:00 nightly (code 9ec3c6c) **OK**: crawl new 409 / changed 2,398 / removed 19 · portals exported directly (451 / 1,160 / 51) · **pages sub-step: read 500 in 560 s** (ok 189, no anchor 255, encrypted 56; backlog 13,771) · derive ok · read-back ok · re-sync 716 written, 0 errors, modifiedTime 0 of 43 · checklists unchanged (K1-SET 48 · PCAP-Q 176 · LP-SUB 70) · exit 0 · no banner. **Clean nightly 2 of 2 for CAT-WO-05; 1 of 2 for CAT-WO-06.**
2. The crawl picked up the **119 CIP-II 2025 Q4 PCAPs**: 119 documents (all primary), kind capital_statement, entity CIP-II, FY2025 Q4, partner high from the file name on 79, low on 26. **Not labelled** (the nightly labels no new files: 614 readable files in LIMITED - Finance carry no Allegis Document label, 408 of them new on 2026-11-22), so their Status stays blank (status rules run on labelled documents) and Find / Checklists don't see them.
3. Task disabled. Restore point **`pre-catwo061`** = `br-curly-forest-bdgvcx3y` (main LSN 8/408B1BC0).
4. `cat-wo-06-1` fast-forwarded into main **locally** (e94c442; not pushed).
5. On main (owner): `010_wo061.sql` (7 GP code aliases, 2 folder aliases, rule ENT-GP-P provisional).
6. `nightly.py --only derive,checklists` (pages off): NIGHTLY OK.
7. The 119 CIP-II PCAPs read on main: 122 s, ok 119; candidates high 91 · medium 3 · MULTIPLE 48 rows · NOT_IN_FUND 2 · no roster name 5. With the file-name matches: **102 documents high (99 CIP-II roster partners: content 91, name 11)**, 16 low only, 1 none.
8. `nightly.py --only derive,checklists`: NIGHTLY OK. Re-sync dry run: read 46,259 · **would re-sync 263 files** (Entity 209 · Subject code(s) 66 · Version family / role 24 · Supersedes 8 · Status 10) · person-owned skipped 1 · errors 0.
9. **STOP for Ryan's apply.**

## Dry run (main)
- **By rule:** ENT-GP-P adds the GP entity on the GP partner-package documents (Entity written on 209 files); the version families of 24 files re-form because their entity set changed; 66 files get Subject codes (GP members matched under their GP's roster, plus content).
- **Checklists before -> after (main):** **K1-SET Met 48 -> 123**, Missing 345 -> 269, On file 20 -> 21 (ASOF (GP) +11, CIP-II (GP) +12, MTV-III (PF) (GP) +11, MTV-IV (Annex) (GP) +12, MTV-IV (GP) +18, MTV-V (GP) +12; MTV-IV (Annex) fund -1, see "Throwaway results") · PCAP-Q 176 -> 176 · LP-SUB 70 -> 70.
- **PCAP-Q for the CIP-II 2025 Q4 PCAPs moves only once they are labelled.** Then: Status Final (ST5-FIN-REPORTPDF) and about **99 Met of 119** (99 roster partners high), ~16 On file (partner unconfirmed), ~4 Missing. Labelling new files is outside this order (the bulk labeller); proposed as a separate step for Ryan.
