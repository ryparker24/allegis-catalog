# CAT-WO-14 · Partner Portal + LP Portal folders · dry run (throwaway)

Run 2026-11-24 20:20 local on throwaway `catwo14-throwaway-r4` (main untouched). No Drive or label writes: Drive was only READ (first-page reading). Codes and counts only.

Branch base: `cat-wo-14` sits on `cat-wo-13`, and migration 013 is on this throwaway, so every checklist figure below has the CAT-WO-13 PCAP cadence applied.

R-059 = **option A** (Ryan, 2026-11-25): portal copies are Issued and count toward checklists. Option B is shown only for comparison.

## Summary and findings

- **Scope:** 1,937 files join the label scope (Partner Portal 1,661, LP Portal 276); 1 file under "0_Empty Partner Folders" is left
  out. GP Portal, Secrets and Tokens, ID and Revver are outside both prefixes. The crawl already lists all of My Drive (R-001), so
  only the label scope changed (`ops.label_scope`, read by the label and read-back steps).
- **Checklists, option A (Ryan's ruling):** PCAP-Q Met 358 -> **377**, Missing 201 -> **181**; K1-SET Met 208 -> **257**,
  Missing 164 -> **108**. Option B (comparison): PCAP-Q unchanged; K1-SET Met 243 / Missing 124.
- **Finance copies:** 1,090 portal files are exact copies of Finance files and all already sit in the Finance file's document
  (948 documents; the Finance copy stays primary). 0 needed re-joining; no new document is made for an exact copy.
- **Partner match:** capital calls 729 of 729 matched (673 high: page reading confirmed 562, all agreeing with the existing code);
  PCAPs 375 of 431 high (87%); K-1s 353 of 451 high (78%). The page reading found no roster name on 168 portal K-1s (no change).
- **Status (option A):** 249 documents newly set Issued (the rest were already Issued by the portal postings, or are a person's
  status, superseded, or an executable kind). Handling: every in-scope file is Restricted (HND-003); 1,773 carry Contains LP PII.
- **Labels it would write:** 1,937 files, 25,216 field writes (nothing written; Drive was only read).

Found and fixed during the dry runs (both are in this commit):
1. The Capital Calls notices are the GP's calls to its members (page 1 names the fund's GP as issuer in all four folders). With the
   fund code alone, every addressee read as "not in fund" and 758 documents went to the Content disagrees lane. The capital-call
   folder rules now also give the GP entity (X (GP), CIP-II (GP), NL-I (GP), NL-II (GP)); disagreements end at 33 (32 before the page reading).
2. A checklist candidate took its entities from its primary copy only; the Finance primary of a portal PCAP / K-1 often has no
   entity, so the fund folder's entity was lost. The build now takes a document's entities from **any** of its in-scope copies
   (option B: not from portal copies). This also moves other rules slightly (both options): AUDITED-FS Met 31 -> 32, LP-SUB
   Met 70 -> 72 / Missing 146 -> 142, LP-SIDE none found 260 -> 259.

Not handled (for Ryan): the LP Portal 2026-Q3 Final PCAPs include two fund folders with no catalog entity (an "LS-III" and an
"FP-2026" folder, 1 file each); they get the kind and period but no entity. The checklist figures use cadence (CAT-WO-13, now on
main), so 2026 Q3 PCAPs count only for the quarterly entities.

Throwaways: the figures are from `catwo14-throwaway-r4` (br-crimson-darkness-bd9cp38w). Earlier attempts `catwo14-throwaway`,
`-r2`, `-r3` are superseded and can be deleted.

## Files in scope by folder

| Folder | Files in label scope |
|---|---:|
| LP Portal / (top) | 16 |
| LP Portal / Final Full Reports | 25 |
| LP Portal / Final PCAPs | 233 |
| LP Portal / K-1s | 2 |
| Partner Docs / (top) | 2 |
| Partner Docs / Capital Calls / Allegis X | 108 |
| Partner Docs / Capital Calls / CIP-II | 319 |
| Partner Docs / Capital Calls / NL-I | 196 |
| Partner Docs / Capital Calls / NL-II | 106 |
| Partner Docs / Distribution Notices | 19 |
| Partner Docs / K1s / 2024 | 148 |
| Partner Docs / K1s / 2025 | 302 |
| Partner Docs / Legal Agreements / (GP / fund agreements) | 18 |
| Partner Docs / Legal Agreements / Transfer Agreements | 29 |
| Partner Docs / Other Docs | 41 |
| Partner Docs / PCAPs / 2025 | 85 |
| Partner Docs / PCAPs / 2026 Q1 | 113 |
| Partner Docs / PCAPs / 2026 Q2 | 107 |
| Partner Portal / (top) | 8 |
| Partner Portal / Fund Documents | 60 |
| **Total** | **1,937** |

Left out under the two subtrees: 1 file(s) ("0_Empty Partner Folders": 1; secret / noise / shortcut: the rest). Already labelled before: 0.

## Kinds assigned (files, before -> after)

| Folder | Kind | Before | After |
|---|---|---:|---:|
| LP Portal / (top) | (none) | 16 | 16 |
| LP Portal / Final Full Reports | financial_statements | 4 | 4 |
| LP Portal / Final Full Reports | quarterly_report | 21 | 21 |
| LP Portal / Final PCAPs | (none) | 58 | 0 |
| LP Portal / Final PCAPs | capital_statement | 161 | 233 |
| LP Portal / Final PCAPs | workpaper | 14 | 0 |
| LP Portal / K-1s | k1 | 2 | 2 |
| Partner Docs / (top) | k1 | 2 | 2 |
| Partner Docs / Capital Calls / Allegis X | capital_call_notice | 108 | 108 |
| Partner Docs / Capital Calls / CIP-II | capital_call_notice | 319 | 319 |
| Partner Docs / Capital Calls / NL-I | capital_call_notice | 196 | 196 |
| Partner Docs / Capital Calls / NL-II | capital_call_notice | 106 | 106 |
| Partner Docs / Distribution Notices | (none) | 1 | 1 |
| Partner Docs / Distribution Notices | distribution_notice | 18 | 18 |
| Partner Docs / K1s / 2024 | k1 | 149 | 149 |
| Partner Docs / K1s / 2025 | k1 | 302 | 302 |
| Partner Docs / Legal Agreements / (GP / fund agreements) | legal_agreement | 10 | 10 |
| Partner Docs / Legal Agreements / (GP / fund agreements) | lpa | 1 | 1 |
| Partner Docs / Legal Agreements / (GP / fund agreements) | operating_agreement | 7 | 7 |
| Partner Docs / Legal Agreements / Transfer Agreements | (none) | 29 | 0 |
| Partner Docs / Legal Agreements / Transfer Agreements | legal_agreement | 0 | 29 |
| Partner Docs / Other Docs | (none) | 15 | 15 |
| Partner Docs / Other Docs | financial_statements | 4 | 4 |
| Partner Docs / Other Docs | k1 | 3 | 3 |
| Partner Docs / Other Docs | tax_form | 1 | 1 |
| Partner Docs / Other Docs | tax_return | 15 | 15 |
| Partner Docs / Other Docs | w9_w8 | 1 | 1 |
| Partner Docs / Other Docs | wire_confirmation | 1 | 1 |
| Partner Docs / Other Docs | workpaper | 1 | 1 |
| Partner Docs / PCAPs / 2025 | capital_statement | 85 | 85 |
| Partner Docs / PCAPs / 2026 Q1 | (none) | 27 | 0 |
| Partner Docs / PCAPs / 2026 Q1 | capital_statement | 79 | 113 |
| Partner Docs / PCAPs / 2026 Q1 | workpaper | 7 | 0 |
| Partner Docs / PCAPs / 2026 Q2 | (none) | 28 | 0 |
| Partner Docs / PCAPs / 2026 Q2 | capital_statement | 79 | 107 |
| Partner Portal / (top) | (none) | 8 | 8 |
| Partner Portal / Fund Documents | audited_financial_statements | 17 | 17 |
| Partner Portal / Fund Documents | financial_statements | 10 | 10 |
| Partner Portal / Fund Documents | quarterly_report | 33 | 33 |

Documents under the two subtrees whose machine fields changed: kind 121 (of 1,795 documents).

## Entity from the folder (per-partner folders, files)

| Folder | Entity codes | Files |
|---|---|---:|
| LP Portal / Final PCAPs | ATTOTUDE, FUNDAM, LS-I, LS-II, MTV-III, MTV-III (PF), MTV-IV (A), MTV-IV (Annex), MTV-IV (B), MTV-V (A), MTV-V (B), MTV-V (MTEF) | 233 |
| LP Portal / K-1s | MTV-V (MTEF) | 2 |
| Partner Docs / Capital Calls / Allegis X | X, X (GP) | 108 |
| Partner Docs / Capital Calls / CIP-II | CIP-II, CIP-II (GP) | 319 |
| Partner Docs / Capital Calls / NL-I | NL-I, NL-I (GP) | 196 |
| Partner Docs / Capital Calls / NL-II | NL-II, NL-II (GP) | 106 |
| Partner Docs / K1s / 2024 | ACLLC, CIP-I, CIP-I (GP), CIP-II, CIP2A, MTV-VI, X | 148 |
| Partner Docs / K1s / 2025 | ACLLC, CIP-I, CIP-I (GP), CIP-II, CIP2A, IVY, MTV-III, MTV-III (PF), MTV-IV (A), MTV-IV (Annex), MTV-IV (B), MTV-V (A), MTV-V (B), MTV-V (MTEF), MTV-VI, TM, X | 302 |
| Partner Docs / PCAPs / 2025 | MTV-III, MTV-III (PF), MTV-IV (A), MTV-IV (Annex), MTV-IV (B), MTV-V (A), MTV-V (B), MTV-V (MTEF), MTV-VI | 85 |
| Partner Docs / PCAPs / 2026 Q1 | FUNDAM, LS-I, LS-II, MTV-III, MTV-III (PF), MTV-IV (A), MTV-IV (Annex), MTV-IV (B), MTV-V (A), MTV-V (B), MTV-V (MTEF) | 113 |
| Partner Docs / PCAPs / 2026 Q2 | ATTOTUDE, FUNDAM, LS-I, LS-II, MTV-III, MTV-III (PF), MTV-IV (A), MTV-IV (Annex), MTV-IV (B), MTV-V (A), MTV-V (B), MTV-V (MTEF) | 107 |

## Partner match (per-partner documents: PCAPs, K-1s, capital calls)

| Kind | Documents | High / confirmed before | High / confirmed after | Rate after | Any match after | From page reading |
|---|---:|---:|---:|---:|---:|---:|
| capital_call_notice | 729 | 673 | 673 | 92% | 729 | 0 |
| capital_statement | 431 | 286 | 375 | 87% | 387 | 17 |
| k1 | 451 | 351 | 353 | 78% | 365 | 0 |

First-page reading of the portal documents: ok 1,017, read 1,017.

## Joined existing Finance documents (exact copies)

Files under the two subtrees: 1,938. In a dup group with a Finance file: 1,090; of those, already in the Finance file's document: 1,090; in a different document: 0. Documents: 1,795, of which 948 are Finance documents the portal copy joins (the Finance copy stays primary: shared-drive copies rank first). No new document is made for an exact copy (ops.build_documents groups by md5).

## Status and handling (portal files, option A)

| Status | Documents |
|---|---:|
| issued | 1,765 |
| final | 16 |
| (none) | 9 |
| superseded | 4 |

Option A set Issued on 249 of 1,794 documents with a portal copy (never a person's status, a superseded version or an executable kind).

| Handling tier | Contains LP PII | Files |
|---|---|---:|
| restricted | no | 164 |
| restricted | yes | 1,773 |

## Checklists: PCAP-Q and K1-SET (before -> option A; option B for comparison)

| Rule | Result | Before | Option A | Option B |
|---|---|---:|---:|---:|
| PCAP-Q | met | 358 | 377 | 358 |
| PCAP-Q | on_file | 22 | 23 | 22 |
| PCAP-Q | missing | 201 | 181 | 201 |
| PCAP-Q | no_roster | 7 | 7 | 7 |
| PCAP-Q | **rows** | 588 | 588 | 588 |
| K1-SET | met | 208 | 257 | 243 |
| K1-SET | on_file | 41 | 48 | 46 |
| K1-SET | missing | 164 | 108 | 124 |
| K1-SET | no_roster | 15 | 15 | 15 |
| K1-SET | **rows** | 428 | 428 | 428 |

### Per entity (Met / Missing): before -> option A (option B)

| Rule | Entity | Met | Missing |
|---|---|---|---|
| PCAP-Q | ATTOTUDE | 0 -> 2 (0) | 3 -> 1 (3) |
| PCAP-Q | LS-I | 0 -> 3 (0) | 4 -> 1 (4) |
| PCAP-Q | LS-II | 0 -> 3 (0) | 4 -> 1 (4) |
| PCAP-Q | MTV-III (PF) | 0 -> 11 (0) | 14 -> 2 (14) |
| K1-SET | CIP-I | 0 -> 1 (1) | 1 -> 1 (1) |
| K1-SET | CSOP | 0 -> 1 (1) | 2 -> 1 (1) |
| K1-SET | MTV-III (PF) | 0 -> 11 (0) | 14 -> 1 (14) |
| K1-SET | MTV-IV (Annex) | 0 -> 6 (6) | 16 -> 7 (7) |
| K1-SET | MTV-IV (B) | 0 -> 2 (2) | 4 -> 1 (1) |
| K1-SET | MTV-V (A) | 0 -> 7 (7) | 8 -> 0 (0) |
| K1-SET | MTV-V (B) | 0 -> 3 (0) | 9 -> 6 (9) |
| K1-SET | MTV-V (MTEF) | 0 -> 18 (18) | 20 -> 1 (1) |

Entities not listed: no change.

## Label writes it would make (nightly `label` step; not written)

Files to label: 1,937 · field writes: 25,216 · Handling field writes: 3,710. Every file also gets Catalog ID and Catalog Review = Needs review.

| Field | Files |
|---|---:|
| status | 1,927 |
| kind | 1,897 |
| fiscal_year | 1,889 |
| workstream | 1,880 |
| published_channels | 1,632 |
| published_ids | 1,632 |
| published_date | 1,623 |
| entities | 1,541 |
| subject_codes | 1,510 |
| issued_date | 1,076 |
| period | 733 |
| issuing_entity | 91 |
| receiving_entities | 78 |
| issuer | 48 |
| stage | 34 |
| effective_date | 29 |
| version_family | 4 |
| version_role | 4 |
| version_supersedes | 4 |

| Kind (labelled) | Files |
|---|---:|
| capital_call_notice | 729 |
| capital_statement | 538 |
| k1 | 457 |
| quarterly_report | 54 |
| (no kind) | 40 |
| legal_agreement | 39 |
| financial_statements | 18 |
| distribution_notice | 18 |
| audited_financial_statements | 17 |
| tax_return | 15 |
| operating_agreement | 7 |
| wire_confirmation | 1 |
| lpa | 1 |
| w9_w8 | 1 |
| workpaper | 1 |
| tax_form | 1 |

## Timings

build before 9s, server derive 225s, apply_derive 268s, pages 932s, subject 24s

## Log

```
REQUIREMENTS APPLIED: 1,641 rows · run req_20261124_194858 · 9s
  AUDITED-FS n=   34  on_file:not_satisfying_kind=3  met=31
  GP-COMMIT  n=   21  missing=14  no_roster=7
  K1-SET     n=  428  missing=167  on_file:unknown=6  on_file:partner_unconfirmed=40  met=200  no_roster=15
  LP-SIDE    n=  285  on_file:unknown=1  on_file:partner_unconfirmed=10  on_file:final_unexecuted=2  none_found=260  met=5  no_roster=7
  LP-SUB     n=  285  missing=146  on_file:unknown=23  on_file:partner_unconfirmed=37  on_file:final_unexecuted=2  met=70  no_roster=7
  PCAP-Q     n=  588  missing=201  on_file:draft=1  on_file:partner_unconfirmed=21  met=358  no_roster=7
  ops.rebuild_folder_ancestors(): done
  ops.apply_rules(): folder_signal 68200, file_signal path 1241422, file_signal drive 68805, handling updated 0
  ops.build_documents(): files grouped 189996, documents upserted 128748, file links 189996, documents derived 127075, executable documents staged 5558
  ops.apply_content_checks(): draft -, unknown none, fully_executed -, fully_executed low, fully_executed high, final_unexecuted -, final_unexecuted medium, partially_executed -, unknown -, draft medium, fully_executed medium
labelled documents considered (parties / status): 40,668; catalog documents whose machine kind changes: 6,919
  afs:AFS-A:(none)                               9
  afs:AFS-B:(none)                              44
  afs:AFS-B:audited_financial_statements         8
  afs:AFS-C:(none)                              69
  afs:AFS-C:audited_financial_statements         8
  afs:AFS-C:financial_statements                 2
  execution:cleared_by_rekind                   26
  issuer:schwab-pdf->bank                    1,321
  kind:AK-P2-email:audited_financial_statements->correspondence     105
  kind:AK-P2-email:financial_statements->correspondence       2
  kind:AK-P3-sheet:audited_financial_statements->financial_statements       8
  kind:AK-P5-audited-pdf:financial_statements->audited_financial_statements       7
  kind:K1F:(none)->k1                        2,850
  kind:K1N:(none)->k1                          364
  kind:NK02:(none)->invoice                    264
  kind:NK03:(none)->bank_stmt                  716
  kind:NK04:(none)->tax_form                   441
  kind:NK05:(none)->tax_return                 218
  kind:NK06:(none)->valuation_memo             205
  kind:NK07:(none)->quarterly_report           349
  kind:NK08:(none)->receipt                     52
  kind:NK12:(none)->workpaper                  252
  kind:RK1F:(none)->financial_statements       357
  kind:RK1Q:(none)->quarterly_report           423
  kind:RK2:lpa->operating_agreement             90
  kind:RK2:lpa_amendment->operating_agreement_amendment      46
  kind:RK3:(none)->template                      2
  kind:RK3:correspondence->template              9
  kind:RK3:subscription_agreement->template      23
  kind:RK4:(none)->formation_filing              9
  kind:RK4:legal_agreement->formation_filing       3
  parties:K1-R2-crowded->unknown               841
  parties:K1-R2-gp-received                     51
  parties:K1-R3-issued-to-lps                4,552
  parties:unknown                            4,180
  status:-                                  17,369
  status:draft                               1,748
  status:final                              19,537
  status:in_review                             348
  status:issued                              1,666
  status_rule:PORTAL-GP                      1,116
  status_rule:PORTAL-GP+LP                      29
  status_rule:PORTAL-LP                        420
  status_rule:ST5-DRF-FOLDER                     2
  status_rule:ST5-DRF-NAME                     304
  status_rule:ST5-DRF-WORDREPORT               366
  status_rule:ST5-FIN-BANKPDF                4,760
  status_rule:ST5-FIN-FOLDER                 2,444
  status_rule:ST5-FIN-K1PDF                  4,380
  status_rule:ST5-FIN-REPORTPDF              1,318
  status_rule:ST5-FIN-TAXRETPDF                235
  status_rule:ST5-FIN-THIRDPARTY             1,817
  status_rule:ST5-ISS-FOLDER                    97
  status_rule:ST5-ISS-K1PORTAL                   3
  status_rule:ST5-WORKING                    1,165
  status_rule:ST5-WORKING-KIND               1,033
   pages skipped (CATWO06_PAGES=0)
CONTENT CHECK APPLIED: fiscal year filled 5 · quarter filled 0 · disagreements 32 (entity 16, fiscal_year 16)
documents considered 40,668; families 2,005 (high 743, medium 1,262); members 4,692
  amendment_base_ambiguous              87
  amends                                 3
  ar_supersedes                          1
PORTALS APPLIED: posted documents 1,572 (by file ID 1,610 links, md5 copies 0) · changed 0 · cleared 0 · Issued date set 1,014 / back-load (no date) 558 · person Status kept 0 · Portal kind conflicts 3 documents
PORTAL (CAT-WO-14, R-059 option B) APPLIED: documents with a portal copy 1,794 · set Issued 0
APPLIED: audited FS 455, kinds 6,919, execution cleared 26, issuers 1,321, parties 40,668 documents, status 40,668
  pages batch 1: 200/1,017 read · memory peak 343 MB
  pages batch 2: 400/1,017 read · memory peak 343 MB
  pages batch 3: 600/1,017 read · memory peak 343 MB
  pages batch 4: 800/1,017 read · memory peak 343 MB
  pages batch 5: 1,000/1,017 read · memory peak 343 MB
  pages batch 6: 1,017/1,017 read · memory peak 343 MB
PAGES APPLIED: in scope 21,227 · read 1,017 · backlog 0 · OCR available · 932s · ok 1,017
    capital_call_notice      cand:high=562  cand:low=242  ok=729  reason:NOT_IN_FUND=242
    capital_statement        cand:high=16  cand:low=14  cand:medium=92  cand:none=2  ok=120  reason:NOT_IN_FUND=10  reason:NO_ROSTER_MATCH=6
    k1                       cand:low=10  cand:medium=1  cand:none=162  ok=168  reason:NOT_IN_FUND=4  reason:NO_ROSTER_MATCH=168
CONTENT CHECK APPLIED: fiscal year filled 0 · quarter filled 0 · disagreements 33 (entity 16, fiscal_year 17)
SUBJECT APPLIED: documents 24,007 · doc_party rows 12,792 · documents changed 2,942 · K1-R2 parties matches sent to Match subject (crowded fund/GP/year) 0 · staff directory not available (skipped) · 24s
  content (CAT-WO-06): documents read with candidates 2,936 · content high documents 245 · code lists too long for the label (written as none) 0 · lane rows by reason: MEDIUM 38, MULTIPLE 67, NOT_IN_FUND 236, NO_ROSTER_MATCH 352
  labelled documents by kind: outcome (high / low / none / no_roster / confirmed)
    k1                             n= 9,624  high=1,986  low=935  none=1,574  no_roster=5,125  confirmed=4
    capital_call_notice            n= 1,003  high=731  low=112  none=114  no_roster=46
    capital_statement              n=   926  high=653  low=77  none=89  no_roster=107
    subscription_agreement         n=   242  high=99  low=55  none=72  no_roster=16
    legal_agreement                n=    58  high=17  low=11  none=23  no_roster=5  not_a_roster_kind=2
    side_letter                    n=    50  high=12  low=33  none=4  no_roster=1
    operating_agreement            n=    11  high=6  low=1  none=4
    operating_agreement_amendment  n=     9  high=3  low=1  none=5
    financial_statements           n=     3  high=3
    audited_financial_statements   n=     3  high=3
    (none)                         n=     2  high=2
    quarterly_report               n=     1  high=1
    correspondence                 n=     1  not_a_roster_kind=1
  subject coverage by kind (labelled): code / person / both / none
    k1                             code=1,990 person=0 both=0 none=7,634
    capital_call_notice            code=731 person=0 both=0 none=272
    capital_statement              code=653 person=0 both=0 none=273
    subscription_agreement         code=99 person=0 both=0 none=143
    legal_agreement                code=17 person=0 both=0 none=41
    side_letter                    code=12 person=0 both=0 none=38
    operating_agreement            code=6 person=0 both=0 none=5
    operating_agreement_amendment  code=3 person=0 both=0 none=6
    financial_statements           code=3 person=0 both=0 none=0
    audited_financial_statements   code=3 person=0 both=0 none=0
    (none)                         code=2 person=0 both=0 none=0
    quarterly_report               code=1 person=0 both=0 none=0
    correspondence                 code=0 person=0 both=0 none=1
PORTAL (CAT-WO-14, R-059 option B) APPLIED: documents with a portal copy 1,794 · set Issued 0
REQUIREMENTS APPLIED: 1,641 rows · run req_20261124_201941 · 5s
  AUDITED-FS n=   34  on_file:not_satisfying_kind=2  met=32
  GP-COMMIT  n=   21  missing=14  no_roster=7
  K1-SET     n=  428  missing=127  on_file:unknown=5  on_file:partner_unconfirmed=46  met=235  no_roster=15
  LP-SIDE    n=  285  on_file:unknown=1  on_file:partner_unconfirmed=11  on_file:final_unexecuted=2  none_found=259  met=5  no_roster=7
  LP-SUB     n=  285  missing=142  on_file:unknown=20  on_file:partner_unconfirmed=42  on_file:final_unexecuted=2  met=72  no_roster=7
  PCAP-Q     n=  588  missing=201  on_file:draft=1  on_file:partner_unconfirmed=21  met=358  no_roster=7
PORTAL (CAT-WO-14, R-059 option A) APPLIED: documents with a portal copy 1,794 · set Issued 249
REQUIREMENTS APPLIED: 1,641 rows · run req_20261124_201948 · 4s
  AUDITED-FS n=   34  on_file:not_satisfying_kind=2  met=32
  GP-COMMIT  n=   21  missing=14  no_roster=7
  K1-SET     n=  428  missing=111  on_file:unknown=5  on_file:partner_unconfirmed=48  met=249  no_roster=15
  LP-SIDE    n=  285  on_file:unknown=1  on_file:partner_unconfirmed=11  on_file:final_unexecuted=2  none_found=259  met=5  no_roster=7
  LP-SUB     n=  285  missing=142  on_file:unknown=20  on_file:partner_unconfirmed=42  on_file:final_unexecuted=2  met=72  no_roster=7
  PCAP-Q     n=  588  missing=181  on_file:draft=1  on_file:partner_unconfirmed=22  met=377  no_roster=7
```
