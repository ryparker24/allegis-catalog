# CAT-WO-04 handoff · Version linking

*2026-11-19 / 20. Codes, IDs and counts only: no LP, individual, file or folder names. Order: `orders/CAT-WO-04_Version_Linking.md`. Rulings R-027, R-028 and R-029 approved as written (Ryan).*

**Status (kept current):** built on git branch `cat-wo-04` and tested on the throwaway Neon branch `catwo04-throwaway` (`br-orange-sunset-bd95ohjb`, from main after CAT-WO-03.1). Release steps are in "Release log".

## Item 0 · measure (main, read-only, the final rules; labelled documents 39,190)
- **Multi-member families: 1,912, holding 4,580 documents.**
  - **High: 737** (applied automatically): 1,647 documents.
  - **Medium: 1,175** (Review › Link versions; nothing applied): 2,933 documents.
  - Another 89 single-document families only carry amendment / A&R links.
- **By kind** (documents, high / medium): financial statements 941 (508 / 433) · tax returns 828 (523 / 305) · workpapers 605 (33 / 572) · tax forms 444 (84 / 360) · quarterly reports 392 (16 / 376) · correspondence 364 (193 / 171) · fund analysis 228 (42 / 186) · PBC requests 162 (58 / 104) · valuation memos 160 (135 / 25) · legal agreements 115 (53 / 62) · audited FS 48 (6 / 42) · journal imports 47 (27 / 20) · operating agreements 40 (0 / 40) · LPAs 27 (2 / 25) · LPA amendments 24 (7 / 17) · 17 other kinds ≤ 26 each.
- **Family size:**
  - high: 2 → 613 · 3 → 83 · 4 → 18 · 5 → 9 · 6 → 5 · 7+ → 9;
  - medium: 2 → 942 · 3 → 124 · 4 → 41 · 5 → 37 · 6+ → 31.
- **Why medium:**
  - similar but not equal names: 566;
  - identical names with no version mark (current would rest on dates alone): 518;
  - names that differ only by a date, with no quarter known: 62;
  - one key (subject or period) missing on a member: 19;
  - an amendment whose base is unclear: 10.
- **Token hits** (members of multi-member families): dates m/d/y 536, final 502, dates y-m-d 497, draft 292, vN 221, (n) 123, rev 113, initials in brackets 84, signed 82, executed 26, dates in words 17, redline / compare 16, MMDDYY 12, copy 10, fully executed 6, clean 4, corrected / amended 3, comments 2, copy of 1.
- **Roles in high families:**
  - current 740, superseded 732, draft of 257, redline 4, amends 3;
  - 93 lpa / operating-agreement families went to medium because the base was unclear.
- **Picks that disagree with today's Stage / Status (high families):**
  - not current but Status Final: 122;
  - not current but Stage fully executed: 25 (another executed member is current);
  - current with Status Draft 18, In review 18, Stage draft 5, final unsigned 1;
  - current with no Status / Stage: 349.
- **Expected label writes:**
  - **L6 Version on 2,106 files** (1,736 documents);
  - **Status → Superseded on 1,150 files** (993 documents; blank or machine Status only).

## Defaults taken (for Ryan's review)
1. **Scope = labelled documents** (Find's 39,190), the same scope as parties and status. Unlabelled documents get no family.
2. **Identical names with no version mark → medium.** The order's "same stem" would make them high. They are often a PDF and its workbook, or copies edited apart, so the current one would be picked on dates alone. **518 families wait in Review.**
3. **A month-end date in a name is the period, not a version.** It stays in the stem, so "Rec 01.31" and "Rec 02.28" never group. Any other date is a version token, as ordered.
4. **Names that differ only by a date, with no quarter known → medium** (62 families).
5. **"No Status / Stage" ranks after In review and before Draft.** The order's list doesn't place it, and a draft mark is evidence while silence is not.
6. **K-1 "amended / corrected"** is a version token (never "amended and restated"). K-1s otherwise form no families (0 today).
7. **Executed counterparts:**
   - G1 holds: an executed document is never superseded by an unsigned one; with a person's draft current, the executed member stays Current too.
   - Two executed members: the later one is current (25 cases).
8. **A&R** supersedes the base before it. Amendments of a restated base become Superseded by the A&R and keep Amends → old base. More than one original base, or A&Rs without dates → medium.
9. **Version actions change the catalog at once** (person-set, through an `app.review_event` trigger, as in CAT-WO-03.1). The **L6 label follows in that night's re-sync**; the browser does not write it. A person's edit to L6 in Drive is never overwritten, and it is not read back into families (use the side-panel actions).
10. **The family build runs inside derive** (the end of `apply_derive_wo02`), with **last night's Subject**. Its Superseded status is therefore in place before the same night's re-sync; otherwise the status reset would flip-flop on Drive. The Subject step runs later, so a Subject change reaches families one night later.
11. **Machine status churn:** each derive resets status, then the family step sets Superseded again (~1,000 documents get a new `updated_at` each night; Drive is unaffected).
12. **Family IDs are stable** across runs: a rebuilt family reuses the ID most of its members had.
13. **The Link versions lane** is a counter card on the Review page that opens a family list (families, not files). Accept needs every member to open for you.
14. **Move to another family** is "the family of catalog ID …" (a member's number).
15. **Checklists:** no requirement rule uses LPAs today, so "base plus amendments" is built but unused. The checklist mix was unchanged on the branch: no best document is a superseded member today.

## Tests
- pipeline `test_wo04` **13/13** (G-S1/2 stems; **G-V1** executed never superseded by a draft; **G-V2** an amendment is never a supersession, A&R; **G-V3** a person-set current survives two nightly runs, removal sticks; **G-V4** no mixed entities / subjects, excluded kinds, K-1s; **G-V5** no file name in logs or L6; G-C1 checklists current-first)
- DB `test_wo04_guards` **11/11** on the branch (catalog_app privileges; security_barrier views; **G-D4** no family mixes entities / subjects / kinds across the whole catalog; **G-D5** no name in family rows or L6 values; **G-D2** person current survives two real family builds; remove / merge / amends / split / unknown action)
- **G-V6** (label writes leave modifiedTime unchanged, one pilot file, restored): `scripts/pilot_wo04_mtime.py`, run at release (it writes to Drive).
- unchanged suites: `test_label_sync_wo02` 33/33 · `test_wo03` 36/36 · `test_wo031` 12/12 · DB `test_wo031_guards` 8/8 · `test_wo03_guards` 13/13 · vitest 127/127 · `tsc` clean

## Release log
1. L6 **Version** created as a DRAFT (`labels_setup_wo04.py --create-drafts --release`), Ryan-only permissions. **STOP: Ryan publishes in Label manager.**
