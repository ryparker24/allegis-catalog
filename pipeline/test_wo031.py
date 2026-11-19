"""CAT-WO-03.1 · audited financial statements rule + the annual check. Offline (no DB, no Drive). Invented names only."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_wo02 as dw
import requirements_wo03 as rq

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

legal = {dw.legal_key(n): {e} for n, e in [("Cyber Innovation Partners, L.P.", "CIP-I"), ("Cyber Innovation Partners II, LP", "CIP-II"),
                                            ("Allegis Capital X, LP", "X"), ("Allegis NL Capital, LP", "NL-I")]}
A = dw.afs_rule
check("G-F1 shape A: '<firm> <YYYY> Annual Report - <legal name>' -> AFS, FY, entity (CIP-I legal name)",
      A("AllegisCyber 2025 Annual Report - Cyber Innovation Partners, LP.pdf", ["00-All Reports", "2025", "2025-Q4", "_Final Reports"], "quarterly_report", legal) == ("AFS-A", 2025, "CIP-I"))
check("G-F2 CIP-I never with II / III / 2 (that is CIP-II)",
      A("AllegisCyber 2025 Annual Report - Cyber Innovation Partners II, LP.pdf", [], "quarterly_report", legal) == ("AFS-A", 2025, "CIP-II")
      and "CIP-I" not in dw.legal_entities("Cyber Innovation Partners III Annual Report 2024", legal)
      and "CIP-I" not in dw.legal_entities("Cyber Innovation Partners 2 Annual Report", legal))
check("G-F3 shape B: a '_Final Reports' folder + 'Annual Report'; FY from the year folder when the name has none",
      A("Annual Report.pdf", ["00-All Reports", "2024", "2024-Q4", "_Final Reports"], "audited_financial_statements", legal) == ("AFS-B", 2024, None))
check("G-F4 shape C: 'Annual Report' + one legal name + one year (the FY2024 naming)",
      A("Allegis Capital X 2024 Annual Report.pdf", ["Reports"], "quarterly_report", legal) == ("AFS-C", 2024, "X"))
check("G-F5 never drafts / redlines / versions / letters / decks",
      all(A(n, ["_Final Reports"], "quarterly_report", legal) is None for n in
          ["Allegis Capital X 2024 Annual Report DRAFT.pdf", "Annual Report v2.pdf", "Annual Report cover letter.pdf",
           "Annual Report presentation.pptx", "Annual Report redline.docx"]))
check("G-F6 shape C needs exactly one entity and a year; otherwise nothing",
      A("Annual Report.pdf", ["Reports"], "quarterly_report", legal) is None
      and A("Allegis Capital X and Allegis NL Capital 2024 Annual Report.pdf", ["Reports"], "quarterly_report", legal) is None)
check("G-F7 only report kinds are re-kinded (a K-1 / subscription agreement named 'Annual Report' is left alone)",
      A("Allegis Capital X 2024 Annual Report.pdf", [], "k1", legal) is None
      and A("Allegis Capital X 2024 Annual Report.pdf", [], "subscription_agreement", legal) is None)
sw = {"status": ["final", "issued"], "annual": True}
q4 = {"kind": "audited_financial_statements", "status": "issued", "period": "q4"}
fy = {"kind": "audited_financial_statements", "status": "issued", "period": "fy"}
none = {"kind": "audited_financial_statements", "status": "final", "period": None}
check("G-F8 AUD-01 v2: an annual period (fy or none) qualifies; a quarter never does (sub-status not_annual)",
      rq.satisfies(fy, sw) and rq.satisfies(none, sw) and not rq.satisfies(q4, sw) and rq.sub_status(q4, sw, True) == "not_annual")
import datetime
RULE = {"rule_id": "AUDITED-FS", "subtype_code": "AUD-01", "subject_type": "entity_fy", "period_from": 2022,
        "entity_filter": {"company_kind": ["fund"]}, "partner_filter": None}
subs = rq.subjects(RULE, {}, [{"entity": "FUND-A", "partner": "LP-0001", "ckind": "fund", "interest": "capital", "is_gp": False}],
                   {"FUND-A": "fund", "FUND-B": "fund"}, datetime.date(2026, 11, 19), {"FUND-A": 2023})
fa = sorted(x[2] for x in subs if x[0] == "FUND-A"); fb = sorted(x[2] for x in subs if x[0] == "FUND-B")
check("G-F9 requirement years start at the entity's first year (earliest roster commitment), never before; no roster date = the rule's start",
      fa == [2023, 2024, 2025] and fb == [2022, 2023, 2024, 2025], f"{fa} {fb}")
K = dw.audit_kind_rule
check("G-F10 P2: emails in an audit kind (or FS emails named 'audited') -> correspondence; the audited-FS rule never sees them",
      K("RE: audited financial statements", "email", "audit_report") == ("AK-P2-email", "correspondence")
      and K("FW: Audited FS 2024", "email", "financial_statements") == ("AK-P2-email", "correspondence")
      and K("FW: monthly financials", "email", "financial_statements") == (None, None))
check("G-F11 P3: spreadsheets in an audit kind -> financial_statements; P5: FS PDFs named 'audited' -> audited FS",
      K("Audited FS workbook.xlsx", "sheet", "audited_financial_statements") == ("AK-P3-sheet", "financial_statements")
      and K("Audited Financial Statements 2023.pdf", "pdf", "financial_statements") == ("AK-P5-audited-pdf", "audited_financial_statements")
      and K("Financial Statements Q2.pdf", "pdf", "financial_statements") == (None, None))
check("G-F12 P4: a Word file of the audited statements is Status = Draft; a PDF is not",
      dw.afs_status("audited_financial_statements", "doc") == ("draft", "AK-P4-word-draft")
      and dw.afs_status("audited_financial_statements", "pdf") == (None, None))
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
