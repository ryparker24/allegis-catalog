# CAT-WO-16 · Bank statement entity from the account's last 4 · dry run (throwaway)

Run 2026-11-24 23:26 local on throwaway `catwo16-throwaway` (from main; main untouched). No Drive or label writes: Drive was only READ (page 1 of statements no name / path matched). Codes and counts only: no names, paths or account digits (ref.bank_account is loaded from the map file outside the repo).

## Summary and findings (for Ryan's ruling R-068)

- As briefed (account cues x1234, ****1234, #1234, "ending 1234", acct...1234), BANK-L4 gives an entity to **173 documents** and
  confirms the existing entity on 146; **0 conflicts**, 52 ambiguous (two mapped accounts on page 1). Labelled bank statements
  with no entity: **3,817 -> 3,686**. Label writes: 132 labelled files' Entity (mostly ACLLC 121).
- The map: 40 rows loaded for 32 entities; `ACCSO (GP)` and `CIP-III (GP)` are not catalog entities (skipped, not invented). The
  three rows marked assumed were confirmed by Ryan on 2026-11-25 (ACLLC x2, ASOF (GP)).
- **Most file names carry the last 4 without a cue**, set off by a dash or underscore after letters (shapes `aaa-1234-.a`,
  `aaa_1234_99`): about 2,300 of the 3,817 no-entity statements. They are NOT matched as briefed. A BANK-L4 v2 that also accepts a
  delimited token after a bank word would cover them; the risk is a mapped number that reads like a date (e.g. 1121 = Nov 21).
- **Page 1 rarely matches** (53 of 5,850 read): statements likely print the full account number, where the last 4 is not a whole
  token. A v2 could accept the last 4 of a longer number after "Account". Both options are Ryan's call (R-068).
- Page 1 reading is slow (~70 min for 6,368 documents); the nightly step reads at most 300 new / changed documents a night.
- CAT-WO-09 will later add about 401 bank_stmt documents (no-kind round 3); BANK-L4 will see them the night they get the kind.

## Map

Rows loaded: 40; entities: 32; last-4s mapped to more than one entity: 0.

Codes in the map that are not in ref.entity (skipped, not invented): `ACCSO (GP)` (1 row), `CIP-III (GP)` (1 row).

| Entity | Accounts mapped |
|---|---:|
| ACCSO | 1 |
| ACLLC | 2 |
| ACMC | 2 |
| ASOF | 1 |
| ASOF (GP) | 1 |
| CIP-I | 1 |
| CIP-I (GP) | 1 |
| CIP-II | 2 |
| CIP-II (GP) | 2 |
| CIP-III | 1 |
| CIP2A | 2 |
| CSOP | 1 |
| MCAS | 1 |
| MTAV | 2 |
| MTV-III (PF) | 1 |
| MTV-III (PF) (GP) | 1 |
| MTV-IV (A) | 1 |
| MTV-IV (Annex) | 1 |
| MTV-IV (Annex) (GP) | 1 |
| MTV-IV (B) | 1 |
| MTV-IV (GP) | 1 |
| MTV-V (A) | 1 |
| MTV-V (B) | 1 |
| MTV-V (GP) | 1 |
| MTV-V (MTEF) | 1 |
| MTV-VI | 1 |
| NL-I | 1 |
| NL-I (GP) | 1 |
| NL-II | 1 |
| NL-II (GP) | 1 |
| X | 2 |
| X (GP) | 2 |

## Bank statements with no entity (labelled files)

| Kind | Files | No entity before | No entity after |
|---|---:|---:|---:|
| (no kind) | 54 | 51 | 51 |
| bank_stmt | 5,045 | 3,817 | 3,686 |
| wire_confirmation | 26 | 10 | 9 |

## Outcomes per document (scope: bank_stmt, wire_confirmation, no-kind under 03-Cash; all copies)

| Kind | Entity set | Agrees with an existing entity | Conflict (-> Content disagrees) | Ambiguous (2 entities) | Person-set (skipped) | No match |
|---|---:|---:|---:|---:|---:|---:|
| (no kind) | 0 | 0 | 0 | 0 | 0 | 33 |
| bank_stmt | 172 | 146 | 0 | 52 | 0 | 5,879 |
| wire_confirmation | 1 | 0 | 0 | 0 | 0 | 351 |

Where the last 4 was found: name 266, page1 105 documents.

Page 1 reads (documents no name / path matched): multi 52, no_match 5,850, ok 53, open_error 1, skipped_format 412.

## Matches by entity (documents given or confirmed by BANK-L4)

| Entity | Documents |
|---|---:|
| ACLLC | 150 |
| ACMC | 37 |
| ASOF (GP) | 7 |
| CIP-I | 1 |
| CIP-I (GP) | 11 |
| CIP-II | 5 |
| CIP-III | 14 |
| CIP2A | 5 |
| CSOP | 1 |
| MTAV | 86 |
| X | 2 |

## Conflicts

Content disagrees lane: 31 -> 31 (bank statements / wire confirmations in the lane now: 0). A conflict is never written as an entity; the lane shows it for a person.

## Label writes it would make (nightly re-sync of labelled files; not written)

Labelled files whose Entity label would change: 132 (bank_stmt 131, wire_confirmation 1). Entities added: ACLLC 121, ACMC 1, ASOF (GP) 7, CIP-I 1, CIP-III 1, CSOP 1.

## Timings

pages 4141s, rule 286s

## Log

```
BANK MAP: 40 rows loaded · 32 entities · not in ref.entity (skipped): ACCSO (GP) (1), CIP-III (GP) (1) · last-4s mapped to 2+ entities: 0
  bank page 1: 100/6,368 read
  bank page 1: 200/6,368 read
  bank page 1: 300/6,368 read
  bank page 1: 400/6,368 read
  bank page 1: 500/6,368 read
  bank page 1: 600/6,368 read
  bank page 1: 700/6,368 read
  bank page 1: 800/6,368 read
  bank page 1: 900/6,368 read
  bank page 1: 1,000/6,368 read
  bank page 1: 1,100/6,368 read
  bank page 1: 1,200/6,368 read
  bank page 1: 1,300/6,368 read
  bank page 1: 1,400/6,368 read
  bank page 1: 1,502/6,368 read
  bank page 1: 1,602/6,368 read
  bank page 1: 1,702/6,368 read
  bank page 1: 1,803/6,368 read
  bank page 1: 1,903/6,368 read
  bank page 1: 2,003/6,368 read
  bank page 1: 2,103/6,368 read
  bank page 1: 2,203/6,368 read
  bank page 1: 2,303/6,368 read
  bank page 1: 2,403/6,368 read
  bank page 1: 2,503/6,368 read
  bank page 1: 2,603/6,368 read
  bank page 1: 2,703/6,368 read
  bank page 1: 2,803/6,368 read
  bank page 1: 2,903/6,368 read
  bank page 1: 3,003/6,368 read
  bank page 1: 3,103/6,368 read
  bank page 1: 3,203/6,368 read
  bank page 1: 3,303/6,368 read
  bank page 1: 3,403/6,368 read
  bank page 1: 3,508/6,368 read
  bank page 1: 3,608/6,368 read
  bank page 1: 3,708/6,368 read
  bank page 1: 3,808/6,368 read
  bank page 1: 3,908/6,368 read
  bank page 1: 4,008/6,368 read
  bank page 1: 4,108/6,368 read
  bank page 1: 4,208/6,368 read
  bank page 1: 4,308/6,368 read
  bank page 1: 4,408/6,368 read
  bank page 1: 4,508/6,368 read
  bank page 1: 4,608/6,368 read
  bank page 1: 4,708/6,368 read
  bank page 1: 4,808/6,368 read
  bank page 1: 4,908/6,368 read
  bank page 1: 5,009/6,368 read
  bank page 1: 5,109/6,368 read
  bank page 1: 5,210/6,368 read
  bank page 1: 5,310/6,368 read
  bank page 1: 5,410/6,368 read
  bank page 1: 5,510/6,368 read
  bank page 1: 5,610/6,368 read
  bank page 1: 5,710/6,368 read
  bank page 1: 5,811/6,368 read
  bank page 1: 5,911/6,368 read
  bank page 1: 6,011/6,368 read
  bank page 1: 6,111/6,368 read
  bank page 1: 6,211/6,368 read
  bank page 1: 6,311/6,368 read
BANK PAGES: read 6,368 · 4139s · multi 52 · no_match 5,850 · ok 53 · open_error 1 · skipped_format 412
CONTENT CHECK APPLIED: fiscal year filled 0 · quarter filled 0 · disagreements 49 (entity 33, fiscal_year 16)
BANK-L4 APPLIED: documents 6,634 · signals 367 on 319 documents · conflicts 0 · by source name 266, page1 105
```
