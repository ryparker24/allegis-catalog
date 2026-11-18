# CAT-WO-03 prep: items 0–2, for Ryan's rulings

*2026-11-17. Prep only. Every write in this document went to the throwaway Neon branch `wo03-prep-throwaway` (`br-gentle-silence-bd3vdeaf`, endpoint `ep-spring-tooth-bdjsjhwi`). Nothing was written to main, Drive or labels, and no screens were built; those wait for CAT-WO-02 Part 2. This document uses codes and counts only and names no LP.*

## Rulings received (Ryan, 2026-11-17) and what was done

All of this is on the throwaway branch only. Nothing was applied to main.

| ruling | decision | where | branch state |
|---|---|---|---|
| (a) entities | 5 aliases and 11 new entities **approved**. **CIP-II (GP) is a new GP entity, not CIP2A** (CIP2A is the CIP-II Admin manco). | `db/wo03_prep/004_entities_aliases.sql` | the 11 entities are no longer provisional; 10 Datum-code aliases; the roster maps **414 / 414** (22 exact, 10 alias) |
| (a) untyped entities | types **proposed, not applied**: X, NL-I, NL-II, XI, CYBER-II → `fund`; TM → `spv` | the commented block in `004` | awaiting ruling; confirm CYBER-II is the fund and not an SPV |
| (b) subtype → kind | **approved as proposed** (27 mappings, satisfying or candidate). PCAP stays catalog-only (`capital_statement`). | `005_subtype_kind.sql` → `ref.doc_subtype_kind` | loaded |
| (c) applicability | workbook for Ryan to fill in | `C:\DriveCatalog\orders\CAT-WO-03_Applicability.xlsx` | 60 rows: AUD-01 30 (including 8 catalog-only funds), OFF-05 22, OFF-04 8; Required is a Yes / No / Unknown dropdown |
| (d) rules | six rules **approved**, with three amendments | `proposed_rules.sql` (now the ruled version) | all 6 `active = true`, version 1 |

**The three amendments in (d):**
1. **K1-SET:** a K-1 counts only when matched to a partner on that entity's roster.
2. **LP-SIDE:** a row with no candidate reads "none found (not tracked in Datum)".
3. **PCAP-Q:** checked per partner per quarter (`entity_partner_quarter`), FY2025 forward.

**Loader change:** when a subtype disappears from an export, it is now marked inactive instead of deleted, because rules and mappings reference it.

### FY2022 K-1 gap: diagnosis and fix

**The fiscal-year rules are not what empties FY2022.** In the full catalog (all files with derived kind `k1`, not only the labelled ones), K-1s by fiscal year are:

| FY | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| K-1s | 558 | 859 | 1,870 | 1,978 | 863 | 327 | 1,336 | 1,376 |

Checks:
- Every K-1 under a 2022 folder has FY2022 (0 disagree).
- File-name years agree with the folder year on 5,316 K-1s and disagree on 70.
- Only 275 K-1s have no fiscal year at all.

What this means for each year:
- **FY2022:** Drive simply holds fewer K-1-looking files for 2022: 904, of which 863 are classified as `k1`.
- **FY2023:** the real hole is the **kind**, not the year. Of 1,064 K-1-looking FY2023 files (a K-1 in the name or under a K-1 folder), **733 have no kind**. That is a kind-rule gap to fix in `derive` separately; I haven't touched it here.

**The fiscal-year defect found and fixed on the branch** (`006_fy_folder_rules.sql`):
- **Defect:** `PER-001`, `PER-003` and `PER-008` read a folder's year only when the year is the whole name or starts it. Folders like "<fund> 2012 K-1s", "<x> 2006 Taxes" or "Tax 2014" gave no year.
- **Fix:** two path rules, `PER-009` (year before Tax/Taxes/Audit/K-1) and `PER-010` (year after them). Both are priority 10 and capture only the year.
- **Method:** baseline `ops.apply_rules()`, snapshot, add the rules, rerun.
- **Result:** fiscal-year winners for **about 775 files** change, 212 of them K-1s. The figure is ±2 between runs; see the tie-break defect below.

**Changes by year** (before → after, counts):

| change | files | of which K-1 |
|---|---:|---:|
| no year → a year | 586 | 172 |
| reassigned year | ~189 | 40 |

| new year | 2002 | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2023 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| files | 7 | 2 | 22 | 24 | 155 | 25 | 53 | 43 | 55 | 30 | 124 | 85 | 61 | 51 | 25 | 11 | 1 | 1 | 1 |

- **No file moves into or out of FY2022** (0 in every run).
- The largest reassignments are 2014→2013 (58), 2014→2015 (34), 2009→2008 (27), 2026→2014 (17) and 2008→2009 (17). Each is a nearer folder's year replacing a farther one; the 2026 values were wrong.
- **Second defect (found while counting):** `cat.v_file_best` is `DISTINCT ON (file_id, field) … ORDER BY priority, distance, (source = 'name') DESC` with no final tie-breaker.
  - When two signals tie, the winner can change between executions. The same diff gave 774, 775 and 776.
  - **Proposed fix:** add `s.rule_id, s.value` to the ORDER BY. Not applied; it is a view change on main's schema and needs its own ruling.
- `cat.document.fiscal_year_auto` on the branch isn't rebuilt yet (that is `ops.build_documents()`). The counts above come from the signal winners (`cat.v_file_best`), which that step rolls up.
- **Gotcha:** the rule value must be the two characters `\1`. A shell-escaped `\\1` collapsed to the byte `0x01` in the first attempt. The SQL file uses dollar quoting.

---

*The prep write-up as it stood before the rulings follows.*

**Rulings needed, in order:** (a) entity additions and aliases, (b) the subtype → kind mapping, (c) the applicability table, (d) the requirement rules. Each section ends with a "Rule:" line.

## What was run

- **Export pair:** `datum_partner_roster_2026-11-17.csv` (414 rows, 14 columns) and `datum_doc_subtype_2026-11-17.csv` (39 rows, 12 columns).
  - Both have exactly the expected columns.
  - Neither has a TIN, address, bank, amount, phone or email column.
- **Branch DDL:** `db/wo03_prep/003_roster_tables.sql` adds:
  - `ref.party`, `ref.doc_subtype`, `ref.datum_export` (file name, sha256, row count);
  - `ops.requirement_rule` and `ops.requirement_applicability`.
  - Grants: none to `catalog_app` (REVOKE ALL FROM PUBLIC).
- **Loader:** `db/wo03_prep/roster_load.py` (crawl step `roster`). It:
  - checks columns and refuses forbidden ones;
  - maps Datum company codes by exact `ref.entity` code, then `ref.entity_alias` on the code or the company's legal name;
  - stores unmapped companies with `entity_code` NULL, never guessed;
  - refuses the main endpoint.
  - **Load as-is:** 414 rows, 264 mapped, 150 unmapped (16 of 32 companies).
  - **Load with the proposals in (a)** (branch only, entities `provisional`): 414 / 414 mapped; 22 companies by exact code, 10 by alias.
- **Measurement:** `db/wo03_prep/measure.py` (read-only). The universe is `app.v_find`: the 46,259 labelled files, with the secret tier already excluded.
  - Entity codes on unlabelled files are too sparse to use (236 derived entity values across 202,507 files).
- **Proposed rules:** `db/wo03_prep/proposed_rules.sql`, loaded on the branch, all `active = false`.

## Item 0: measurements

### Roster per Datum company

The table shows rows, the subscriptions an LP is expected to have, the company's own GP row, and carried-interest rows.

| Datum company | kind | rows | LP subs expected | GP row | carry | catalog entity |
|---|---|---:|---:|---:|---:|---|
| ASOF | fund | 2 | 1 | 1 | 0 | ASOF |
| Allegis X | fund | 7 | 5 | 2 | 1 | X *(alias, proposed)* |
| CIP-I | fund | 6 | 5 | 1 | 0 | CIP-I |
| CIP-II | fund | 119 | 118 | 1 | 0 | CIP-II |
| CSOP | fund | 2 | 1 | 1 | 0 | CSOP |
| MTV-III (PF) | fund | 14 | 13 | 1 | 0 | **new** |
| MTV-IV (A) | fund | 16 | 15 | 1 | 0 | MTV-IV (A) |
| MTV-IV (Annex) | fund | 16 | 15 | 1 | 0 | MTV-IV (Annex) |
| MTV-IV (B) | fund | 4 | 3 | 1 | 0 | MTV-IV (B) |
| MTV-V (A) | fund | 9 | 8 | 1 | 0 | MTV-V (A) |
| MTV-V (B) | fund | 9 | 8 | 1 | 0 | MTV-V (B) |
| MTV-V (MTEF) | fund | 20 | 19 | 1 | 0 | MTV-V (MTEF) |
| NL-I | fund | 2 | 1 | 1 | 0 | NL-I |
| NL-II | fund | 2 | 1 | 1 | 0 | NL-II |
| ASOF (GP) | gp | 11 | – | – | 0 | **new** |
| Allegis X (GP) | gp | 13 | – | – | 0 | **new** |
| CIP-I (GP) | gp | 13 | – | – | 0 | CIP-I (GP) |
| CIP-II (GP) | gp | 13 | – | – | 0 | **new** (see question 2) |
| MTV-III (PF) (GP) | gp | 12 | – | – | 0 | **new** |
| MTV-IV (Annex) (GP) | gp | 13 | – | – | 0 | MTV-IV (Annex) (GP) |
| MTV-IV (GP) | gp | 19 | – | – | 0 | MTV-IV (GP) |
| MTV-V (GP) | gp | 12 | – | – | 0 | MTV-V (GP) |
| NL-I (GP) | gp | 9 | – | – | 0 | **new** |
| NL-II (GP) | gp | 5 | – | – | 0 | **new** |
| Allegis IVY (SPV) | spv | 13 | 13 | 0 | 0 | IVY *(alias, proposed)* |
| Allegis TM (SPV) | spv | 6 | 6 | 0 | 0 | TM *(alias, proposed)* |
| Attotude (SPV) | spv | 1 | 1 | 0 | 0 | **new** |
| Dragos (SPV) | spv | 14 | 13 | 0 | 1 | ACCSO *(alias, proposed)* |
| Fundam (SPV) | spv | 25 | 25 | 0 | 0 | **new** |
| Lightship I (SPV) | spv | 1 | 1 | 0 | 0 | **new** |
| Lightship II (SPV) | spv | 1 | 1 | 0 | 0 | **new** |
| Shape MTV-VI (SPV) | spv | 5 | 5 | 0 | 0 | MTV-VI *(alias needed; today it matches only `ref.entity.name`)* |

- **Partner codes:**
  - `LP-` on 331 rows;
  - `GPM-` on 52 rows (GP members);
  - `GM-` on 28 GP rows plus 2 SPV rows.
- **Repeats:**
  - 57 partner codes sit in more than one company (at most 11);
  - 59 relationships span companies.
- **The fund's own GP row:** found where the partner's legal **or** display name equals a Datum GP company's name or code (matched in memory).
  - 15 fund rows match, covering all 14 funds.
  - **CSOP**'s GP row is **CIP-I (GP)**.
  - **NL-I**'s GP row matches only on display name.
  - `Allegis X` has 2 GP rows: its GP holds a capital interest and a carried interest (`LP-0001` and `LP-0001-CI`).
- **Blank dates:**
  - `commitment_date` is blank on 2 rows (`Allegis X` LP-0001-CI, `Dragos (SPV)` LP-0008).
  - `active_from` is blank on 1 row.
  - `active_to` is never set.

**Reverse gap:** these catalog entities have no Datum roster: CIP-III, CYBER-II, MTV-I, MTV-I (GP), MTV-II, MTV-II (GP), MTV-II (MTEF), MTV-III, MTV-III (GP), MTV-III (MTEF), XI. Their partner checklists show "no roster in Datum".

### Subscription agreements and side letters per entity

Counts show all copies | primary copies. The last column is the number of LP subscriptions the roster expects.

| entity | subscription | side letter | roster LP subs |
|---|---|---|---:|
| ACCSO | 27 \| 14 | 9 \| 3 | 13 |
| ASOF | 0 \| 0 | 4 \| 3 | 1 |
| CIP-I | 11 \| 1 | 1 \| 0 | 5 |
| CIP-I (GP) | 54 \| 30 | 4 \| 2 | (gp) |
| CIP-II | 115 \| 114 | 6 \| 6 | 118 |
| CIP-III | 16 \| 14 | 0 | no roster |
| CSOP | 45 \| 20 | 5 \| 2 | 1 |
| IVY | 6 \| 6 | 0 | 13 |
| MTV-III | 13 \| 8 | 0 | no roster |
| MTV-IV (A) | 51 \| 21 | 0 | 15 |
| MTV-IV (Annex) | 26 \| 14 | 0 | 15 |
| MTV-IV (B) | 10 \| 5 | 0 | 3 |
| MTV-V (A) | 52 \| 28 | 11 \| 6 | 8 |
| MTV-V (B) | 5 \| 3 | 0 | 8 |
| MTV-V (MTEF) | 0 | 0 | 19 |
| MTV-VI | 4 \| 2 | 0 | 5 |
| NL-I | 0 | 1 \| 0 | 1 |
| NL-II | 0 | 0 | 1 |
| TM | 0 | 1 \| 1 | 6 |
| X | 18 \| 12 | 26 \| 23 | 5 |

- **No entity:** 8 subscription agreements and 6 side letters carry no entity.
- **Stage mix:**
  - Subscriptions: fully executed 191, unknown 110, draft 48, n/a 20, final unexecuted 5.
  - Side letters: fully executed 28, draft 19, final unexecuted 14, unknown 7, partly executed 1, n/a 1.
- **CSOP** (45 subscriptions against 1 expected) and **CIP-I (GP)** (54) suggest many of these files belong to another entity or are portfolio-side subscriptions. Partner matching (item 3) will separate them.

### Auto-match to partners (folder, then file name)

The matcher normalises names in memory (punctuation and legal suffixes removed). The universe is the roster partners of the document's entities.

- **High:** exactly one partner matched, by a whole folder segment or by the full name inside the file name.
- **Low:** several partners matched, or only a distinctive word (5+ letters) matched.

| kind | n | high (folder) | high (name) | low | none | no roster |
|---|---:|---:|---:|---:|---:|---:|
| subscription_agreement | 374 | 0 | 149 (40%) | 155 (41%) | 43 (11%) | 27 (7%) |
| side_letter | 70 | 0 | 18 (26%) | 46 (66%) | 0 | 6 (9%) |
| k1 | 7,216 | 77 (1%) | 1,176 (16%) | 1,085 (15%) | 434 (6%) | 4,444 (62%) |

- **Folder rules:** they find almost nothing as written. Per-LP folders are not named after the partner's full legal or display name. Item 3 needs a few folder rules learned from the low-confidence lane.
- **K-1 "no roster" (62%):** these are mostly K-1s for entities with no Datum roster (mancos, the MTV-I/II/III family) and K-1s received from portfolio companies (see finding 1).

### K-1s per entity × FY

Counts are primary copies, shown against the roster size.

| entity | roster | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|
| CIP-II | 119 | 309 | 6 | 11 | 4 | 26 |
| MTV-IV (A) | 16 | 76 | 0 | 8 | 0 | 48 |
| MTV-V (A) | 9 | 34 | 0 | 6 | 0 | 25 |
| MTV-V (MTEF) | 20 | 38 | 0 | 2 | 0 | 0 |
| X | 7 | 0 | 0 | 2 | 7 | 19 |
| ACCSO | 14 | 0 | 0 | 0 | 14 | 18 |
| IVY | 13 | 6 | 0 | 4 | 7 | 16 |
| CIP-I (GP) | 13 | 23 | 2 | 2 | 13 | 18 |
| MTV-IV (GP) | 19 | 15 | 2 | 5 | 0 | 0 |

The full grid is in `measure.py` output section 5. **FY2022 is near zero for every entity, while FY2021 is high.** That is a fiscal-year derivation artefact: the folder year or tax year is probably being read as the FY. Fix it before K-1 results mean anything.

### PCAP (`capital_statement`) per entity × quarter

| entity | 2024 Q2 | 2025 Q2 | 2025 Q3 | 2025 Q4 |
|---|---:|---:|---:|---:|
| CIP-II | 117 | 2 | 1 | 0 |
| IVY / TM | 6 / 6 | 0 | 0 | 0 |
| MTV-III, MTV-IV (A), (Annex), (B), MTV-V (A), (B), (MTEF) | 0 | 0 | 0 | 13 / 33 / 14 / 4 / 15 / 6 / 20 |
| MTV-I | 0 | 0 | 0 | 1 |

All other entity-quarters in FY2024–FY2025 are 0. Capital statements are stored **per partner** (CIP-II's 117 in 2024 Q2 ≈ its 119 partners). A "PCAP package per fund per quarter" therefore needs a rule on what counts as the package: one per partner, or a single combined file. This is question 4.

### Audited financial statements per entity × FY

Counts are primary copies, shown as financial_statements / audit_report.

- Most funds have financial statements every year from 2022 to 2025. For example, MTV-IV (A) has 9 / 19 / 21 / 31 and CSOP has 3 / 7 / 7 / 8.
- **Thin or empty:**
  - NL-I: 1 file in 2024, none in the other years;
  - ACCSO: 1 file in 2023, none in the other years;
  - CIP-II: 0 in 2024;
  - the MTV-I / MTV-II families: 0 in every year.

## (a) Entity master: proposed additions and aliases

These already exist on the branch as `provisional`, which demonstrates the mapping. They are not on main.

**Aliases** (`ref.entity_alias`, Datum code → existing entity):

| Datum code | → entity |
|---|---|
| Allegis X | X |
| Dragos (SPV) | ACCSO |
| Shape MTV-VI (SPV) | MTV-VI |
| Allegis IVY (SPV) | IVY |
| Allegis TM (SPV) | TM |

**New entities** (codes are proposals; each also needs label choices via `labels_setup.py --sync-choices`):

| proposed code | type | family | Datum code |
|---|---|---|---|
| MTV-III (PF) | fund | MTV | MTV-III (PF) |
| MTV-III (PF) (GP) | gp | MTV | MTV-III (PF) (GP) |
| ASOF (GP) | gp | ASOF | ASOF (GP) |
| X (GP) | gp | X | Allegis X (GP) |
| CIP-II (GP) | gp | CIP | CIP-II (GP) |
| NL-I (GP) | gp | NL | NL-I (GP) |
| NL-II (GP) | gp | NL | NL-II (GP) |
| FUNDAM | spv | – | Fundam (SPV) |
| LS-I | spv | – | Lightship I (SPV) |
| LS-II | spv | – | Lightship II (SPV) |
| ATTOTUDE | spv | – | Attotude (SPV) |

**Also on main:**
- `entity_type` is NULL for CYBER-II, NL-I, NL-II, TM, X and XI.
- NL-I and NL-II, which Datum calls `fund`, need `fund`.
- TM, which Datum calls `spv`, needs `spv`.
- X needs `fund`.

The rules filter on Datum's company kind, so this does not block anything, but the catalog should agree.

> **Rule:** accept, rename or reject each alias and each new code; set the missing `entity_type`s.

## (b) Datum subtype → catalog kind mapping

**Checklist subtypes** (these are needed for (d)):

| Datum subtype | name | → catalog kind(s) | note |
|---|---|---|---|
| OFF-03 | Subscription agreements, GP-accepted (all LPs) | subscription_agreement | |
| OFF-05 | Side letters (all) | side_letter | |
| OFF-04 | GP commitment / GP subscription | subscription_agreement, matched to the fund's GP partner | no separate catalog kind; add `gp_subscription` only if you want one |
| AUD-01 | Audited financial statements (signed opinion) | financial_statements | `audit_report` (the opinion alone) is a candidate, not satisfying |
| AUD-03 | K-1 set (issued) | k1, issued direction only | see finding 1 |
| *(none)* | PCAP | capital_statement | ask Datum for a subtype, e.g. `AUD-05` |

**Other subtypes** (a suggested mapping so both sides agree; low priority):

| Datum subtype | → catalog kind |
|---|---|
| AUD-02 | tax_return |
| AUD-04 | quarterly_report (annual LP letter) |
| FORM-01, FORM-06, FORM-07 | formation_filing |
| FORM-02 | lpa |
| FORM-03 | lpa_amendment |
| FORM-04, FORM-05 | lpa / legal_agreement (no operating-agreement kind) |
| OFF-01 | ppm |
| OFF-02, POL-04 | regulatory_filing |
| OFF-07 | w9_w8 |
| FIN-01 | loc_agreement |
| GOV-02 | minutes, board_consent |
| POL-01, POL-02, POL-03 | policy |

The other subtypes (ADV-*, FIN-02/03, GOV-01/03–06, OFF-06/08/09/10) have no clear catalog kind yet.

> **Rule:** the mapping above, then the same mapping is ruled on the Datum side (WO-203).

## (c) Conditional applicability: the table to fill in

Datum marks these subtypes `conditional` for the entity's company kind. Each needs a yes or no per entity. Unanswered cells show "applicability not set", never Missing. The evidence column comes from item 0.

**AUD-01 audited FS** (conditional for every fund and SPV):

| entity | evidence: FS primary 2024 / 2025 | required? |
|---|---|---|
| ASOF | 6 / 8 | |
| CIP-I | 8 / 8 | |
| CIP-II | 0 / 4 | |
| CSOP | 7 / 8 | |
| MTV-III (PF) | (new entity) | |
| MTV-IV (A) | 21 / 31 | |
| MTV-IV (Annex) | 7 / 8 | |
| MTV-IV (B) | 7 / 7 | |
| MTV-V (A) | 18 / 27 | |
| MTV-V (B) | 7 / 7 | |
| MTV-V (MTEF) | 7 / 7 | |
| NL-I | 1 / 0 | |
| NL-II | 4 / 4 | |
| X | 9 / 10 | |
| ACCSO | 0 / 0 | |
| ATTOTUDE | (new) | |
| FUNDAM | (new) | |
| IVY | 12 / 8 | |
| LS-I | (new) | |
| LS-II | (new) | |
| MTV-VI | 7 / 10 | |
| TM | 12 / 8 | |
| *catalog-only funds:* CIP-III, MTV-I, MTV-II, MTV-II (MTEF), MTV-III, MTV-III (MTEF), XI, CYBER-II | MTV-III 7 / 10; the others 0 | |

**OFF-05 side letters:** the same 22 entities. Evidence is side letters on file (all copies):
- ACCSO 9, ASOF 4, CIP-I 1, CIP-II 6, CSOP 5, MTV-V (A) 11, NL-I 1, TM 1, X 26;
- every other entity 0.

**OFF-04 GP commitment for SPVs** (conditional for spv): ACCSO, ATTOTUDE, FUNDAM, IVY, LS-I, LS-II, MTV-VI, TM. No SPV has a GP row in the roster; 2 SPVs have a `GM-` row.

> **Rule:** fill in yes / no (and a note) for each cell. It is stored as `ops.requirement_applicability`, with columns entity, subtype, required, note, ruled_by and ruled_at.

## (d) Proposed requirement rules

These are on the branch in `ops.requirement_rule`, all inactive.

| rule | checklist | subtype | kinds | subject | who / which | from | satisfied when |
|---|---|---|---|---|---|---|---|
| LP-SUB v1 | LP subscriptions | OFF-03 | subscription_agreement | entity × partner | fund + spv; `capital`, not the company's GP | – | Stage = Fully executed |
| LP-SIDE v1 | LP subscriptions | OFF-05 | side_letter | entity × partner | entities ruled *required* in (c); `capital`, not GP | – | Stage = Fully executed. A partner with no candidate shows **"none on file"**, not Missing |
| GP-COMMIT v1 | LP subscriptions | OFF-04 | subscription_agreement | entity × partner | funds (+ SPVs ruled required); the fund's own GP row | – | Stage = Fully executed |
| AUDITED-FS v1 | fund-level | AUD-01 | financial_statements | entity × FY | fund + spv ruled required in (c) | FY2022 | Status ∈ Final, Issued |
| K1-SET v1 | fund-level | AUD-03 | k1 | entity × partner × FY | fund, spv, gp; capital + carried interest | **FY2025** | Status = Issued |
| PCAP-Q v1 | fund-level | *none* (`no_datum_subtype`) | capital_statement | entity × quarter | fund + spv | FY2025 | Status ∈ Final, Issued |

**How the rules behave:**
- **Until CAT-WO-02 Part 2:** K-1s, financial statements and capital statements all carry stage `n_a` today, so "Status" can't be evaluated. The interim rule is "a primary copy exists and is not marked Wrong". Those rows show as 🟠 rather than 🟢 until Status is set.
- **Carried interest:** `carried_interest` rows expect no subscription. They are excluded from LP-SUB and LP-SIDE and included in K1-SET.
- **Mancos:** AUD-03 is required for mancos in Datum, but mancos have no roster. They show "no roster in Datum".

> **Rule:** accept or amend each rule (kinds, subject, start year, satisfied-when). On acceptance the rule is set `active = true` as version 1.

## Findings and questions

1. **K-1 direction:** the catalog `k1` kind mixes K-1s the fund **issued** to its partners with K-1s it **received** from portfolio companies. The issuer is blank on 6,520 of 7,216.
   - **Proposal:** a K-1 counts toward AUD-03 only when it is matched to a roster partner of that entity. A received K-1 never matches a roster partner.
   - **Alternatively:** add a direction (issued / received) to the label in CAT-WO-02.
2. **Is Datum's `CIP-II (GP)` the catalog's `CIP2A`** (the CIP-II Admin manco)? If so, it should be an alias rather than a new entity. Also, which GP entity is CSOP's GP? The roster says CIP-I (GP).
3. **The FY2022 K-1 gap** (finding in item 0) is a fiscal-year derivation problem and should be fixed in `derive` before checklists ship.
4. **The PCAP package:** is it per partner (one capital statement per LP per quarter) or one combined file per fund per quarter? The data shows per-partner files (CIP-II 2024 Q2: 117 against 119 partners). This decides `entity_quarter` against `entity_partner_quarter`.
5. **Side letters:** Datum's "Side letters (all)" can't say which LPs *have* one. As proposed, LP-SIDE never reports Missing, only Met / On file / none on file. A true Missing needs a per-partner "has side letter" flag from Datum.
6. **Dates are fund-level** (as the order notes). K-1s are checked from FY2025 only; there is a note to the Datum thread for admission and exit dates.

## Branch

`wo03-prep-throwaway` holds the loaded roster, the provisional entities and aliases, and the inactive proposed rules. Keep it until the rulings are in, then delete it. The build phase starts from a fresh branch after CAT-WO-02 Part 2.
