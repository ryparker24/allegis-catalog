# CAT-WO-06.2 handoff · K-1 Parties flip-flop fix

*2026-11-24. Codes and counts only.*

**Status:** built on git branch `cat-wo-06-2` (`6ffb49e`, from main `35ae559`), merged into main **locally** (not pushed). Restore point `pre-catwo062` = `br-fancy-credit-bdpg4p9u` (main LSN A/826B8CF0). The nightly stays enabled on `app-main` `63e1547`. **STOP for Ryan's apply.**

## Why
The 2026-11-23 22:00 nightly re-wrote Parties on ~1,580 K-1 files. `apply_derive_wo02` counted K-1s per folder (`k1_folder`, used by K1-R3 "issued by a fund to its LPs", which needs 3+ K-1s in the folder) from the kinds **before** the run's own re-kinds (K1F / K1N make ~3,214 documents K-1s every night). A single derive pass undercounted and left K1-R3 unfired; the label step's second pass (CAT-WO-06.1) counted correctly and fired it. On a night without new files only the first pass would run and the re-sync would flip those files back.

## Fix
- `pipeline/apply_derive_wo02.py`: `k1_folder` counts each document's **final** kind (this run's re-kinds included). One pass now gives the same Parties as two.
- `pipeline/pages_wo06.py` / `subject_wo03.py`: their temp tables (`_cd`, `_lane`) are created if missing and truncated, so two passes in one transaction work (needed by the guard; no effect on the nightly, which commits between passes).
- `db/tests/test_wo062_guards.py`: in ONE rolled-back transaction on main, a full derive (rules, build_documents, the WO-02 pass) and then a second WO-02 pass. **2/2 on main:** full derive vs the stored state: kind 0 · Parties 0 · Status 0 changes; second pass vs first: 0 · 0 · 0 (129,204 documents).
- Suites: test_wo06 51/51 · test_wo061 11/11 · wo03 36/36 · wo04 13/13 · wo05 23/23 · label sync 34/34.

## Dry run on main
- `nightly.py --only derive,checklists` (code 6ffb49e, pages off): NIGHTLY OK. Parties: K1-R3 4,537 · K1-R2 gp-received 51 · K1-R2 crowded -> unknown 841 · unknown 4,161 (the values on Drive since 2026-11-23). Checklists unchanged: K1-SET Met 200 · PCAP-Q 358 · LP-SUB 70.
- Re-sync dry run: read 46,949 · **would re-sync 49 files, all Subject code(s)** (last night's Subject step, written by the next re-sync as usual) · **Parties writes 0** · person-owned skipped 1 · errors 0.

## Apply plan
Push main · deploy the Worker (no app change; keeps main and the Worker on one commit) · move `app-main` to the release commit (the nightly then runs the fix) · CATWO062 RELEASED. No Drive write is part of this release (the 49 Subject writes happen in the next nightly).
