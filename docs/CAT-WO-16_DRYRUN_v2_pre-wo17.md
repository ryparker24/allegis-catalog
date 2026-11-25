# CAT-WO-16 · BANK-L4 v2 (R-068 widenings) next to v1 · dry run (throwaway)

Run 2026-11-25 12:31 local on throwaway `catwo16-throwaway`; main untouched. No Drive or label writes: Drive was only READ (page 1). Codes and counts only: no names, paths or account digits. v2 is stored INACTIVE (BANK-L4 v2) until Ryan rules; the nightly would keep using v1.

v2 = v1 plus (a) a mapped 4-digit token set off by - _ . or spaces in the file name, skipped inside a date-shaped run (MMDD-YYYY, YYYY-MMDD, MMDD-YY, MM-DD-YY pieces) and ambiguous when a name holds two different mapped accounts, and (b) on page 1 the last 4 of a longer account number after Account / Acct / Account Number / A/C.

## Per version (documents in scope: bank_stmt, wire_confirmation, no-kind under 03-Cash)

| | v1 | v2 |
|---|---:|---:|
| Newly given an entity | 173 | 2,870 |
| Confirmations (entity already there) | 146 | 773 |
| Conflicts (-> Content disagrees, not written) | 0 | 293 |
| Ambiguous (2 mapped accounts) | 52 | 113 |
| Person-set (skipped) | 0 | 0 |
| No match | 6,263 | 2,585 |
| Bank statements / wire confirmations in the Content disagrees lane | 0 | 110 |
| Labelled bank statements with no entity (3,817 before) | 3,686 | 1,084 |
| Labelled wire confirmations with no entity (10 before) | 9 | 9 |
| Label writes (labelled files whose Entity would change) | 132 | 2,793 |

Where the last 4 was found: v1 name 266, page1 105 · v2 name 2,760, page1 1,289 documents.

Page 1 (re-read, 6,368 documents): v1 pattern multi 52, no_match 5,850, ok 53, open_error 1, skipped_format 412 · v2 pattern multi 177, no_match 2,878, ok 2,900.

## Matches by entity (documents given or confirmed)

| Entity | v1 | v2 |
|---|---:|---:|
| ACCSO | 0 | 65 |
| ACLLC | 150 | 377 |
| ACMC | 37 | 147 |
| ASOF | 0 | 216 |
| ASOF (GP) | 7 | 170 |
| CIP-I | 1 | 216 |
| CIP-I (GP) | 11 | 172 |
| CIP-II | 5 | 160 |
| CIP-II (GP) | 0 | 149 |
| CIP-III | 14 | 155 |
| CIP2A | 5 | 198 |
| CSOP | 1 | 205 |
| MCAS | 0 | 16 |
| MTAV | 86 | 309 |
| MTV-III (PF) | 0 | 47 |
| MTV-III (PF) (GP) | 0 | 36 |
| MTV-IV (A) | 0 | 74 |
| MTV-IV (Annex) | 0 | 61 |
| MTV-IV (Annex) (GP) | 0 | 51 |
| MTV-IV (B) | 0 | 63 |
| MTV-IV (GP) | 0 | 52 |
| MTV-V (A) | 0 | 54 |
| MTV-V (B) | 0 | 53 |
| MTV-V (GP) | 0 | 51 |
| MTV-V (MTEF) | 0 | 58 |
| MTV-VI | 0 | 50 |
| NL-I | 0 | 115 |
| NL-I (GP) | 0 | 119 |
| NL-II | 0 | 45 |
| NL-II (GP) | 0 | 57 |
| X | 2 | 57 |
| X (GP) | 0 | 45 |

## Spot check: 50 random documents matched ONLY by v2's file-name form, against page 1

Documents only v2's file-name form matches: 2,494.

| Page 1 | Documents |
|---|---:|
| agree | 27 |
| disagree (another mapped account) | 1 |
| page 1 shows no account number | 22 |

**Agreement where page 1 shows an account number: 27 of 28 (96%).**

## Date-risk numbers (the brief's list of mapped numbers that read like dates)

v2 file-name matches on a date-risk number (after the date guard): 564 tokens (ASOF 108, ASOF (GP) 116, CIP-III 141, MTV-IV (Annex) 51, MTV-IV (Annex) (GP) 51, MTV-IV (GP) 52, X 45). Tokens the date guard skipped (all mapped numbers): 0.

## Timings

pages 4482s, v1 289s, v2 729s

## Log

```
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
BANK PAGES: read 6,368 · 4479s · multi 52 · no_match 5,850 · ok 53 · open_error 1 · skipped_format 412 · v2:multi 177 · v2:no_match 2,878 · v2:ok 2,900
CONTENT CHECK APPLIED: fiscal year filled 0 · quarter filled 0 · disagreements 49 (entity 33, fiscal_year 16)
BANK-L4 APPLIED: documents 6,634 · signals 367 on 319 documents · conflicts 0 · by source name 266, page1 105
CONTENT CHECK APPLIED: fiscal year filled 0 · quarter filled 0 · disagreements 342 (entity 326, fiscal_year 16)
BANK-L4 APPLIED: documents 6,634 · signals 4,360 on 3,643 documents · conflicts 293 · by source name 2,760, page1 1,289
```
