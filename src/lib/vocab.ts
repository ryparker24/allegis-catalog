// Generated from labels_setup.py constants (choice code -> display name). Codes only; no names of people or LPs.
export const VOCAB = {
  "kind": {
    "409a": "409A Valuation",
    "audit_report": "Audit Report",
    "bank_stmt": "Bank Statement",
    "board_consent": "Board Consent",
    "board_materials": "Board Materials",
    "cap_table": "Cap Table",
    "capital_call_notice": "Capital Call Notice",
    "capital_statement": "Capital Statement (PCAP)",
    "closing_statement": "Closing Statement",
    "correspondence": "Correspondence",
    "ddq": "DDQ",
    "distribution_notice": "Distribution Notice",
    "escrow_notice": "Escrow Notice",
    "financial_statements": "Financial Statements",
    "fund_analysis": "Fund Analysis",
    "funds_flow": "Funds Flow",
    "gp_note": "GP Note",
    "investment_memo": "Investment Memo",
    "invoice": "Invoice",
    "journal_import": "Journal Import",
    "k1": "K-1",
    "legal_agreement": "Legal Agreement (other)",
    "loc_agreement": "Line of Credit Agreement",
    "lpa": "LPA",
    "lpa_amendment": "LPA Amendment",
    "merger_agreement": "Merger Agreement",
    "minutes": "Minutes",
    "nda": "NDA",
    "pbc_request": "PBC Request",
    "policy": "Policy",
    "ppm": "PPM",
    "purchase_agreement": "Purchase Agreement",
    "quarterly_report": "Quarterly Report",
    "receipt": "Receipt",
    "safe_or_note": "SAFE / Convertible Note",
    "side_letter": "Side Letter",
    "stock_certificate": "Stock Certificate",
    "subscription_agreement": "Subscription Agreement",
    "tax_form": "Tax Form",
    "tax_return": "Tax Return",
    "template": "Template",
    "valuation_memo": "Valuation Memo",
    "vendor_contract": "Vendor Contract",
    "w9_w8": "W-9 / W-8",
    "wire_confirmation": "Wire Confirmation",
    "workpaper": "Workpaper",
    "formation_filing": "Formation / State Filing",
    "regulatory_filing": "Regulatory Filing (SEC/State)",
    "other": "Other"
  },
  "period": {
    "fy": "FY",
    "q1": "Q1",
    "q2": "Q2",
    "q3": "Q3",
    "q4": "Q4",
    "month": "Month",
    "as_of": "As-of date",
    "n_a": "N/A"
  },
  "stage": {
    "draft": "Draft",
    "final_unexecuted": "Final - not yet signed",
    "partially_executed": "Partially executed",
    "fully_executed": "Fully executed",
    "n_a": "Not applicable",
    "unknown": "Unknown"
  },
  "evidence": {
    "docusign": "DocuSign / certificate",
    "e_sign_other": "Other e-signature",
    "digital_sig": "Digital signature",
    "conformed": "Conformed (/s/)",
    "wet_ink_scan": "Wet-ink scan",
    "manual": "Confirmed by reviewer"
  },
  "tier": {
    "normal": "Normal",
    "restricted": "Restricted",
    "secret": "Secret"
  },
  "contains": {
    "lp_pii": "LP personal info",
    "bank_details": "Bank / wire details",
    "tax_id": "Tax ID",
    "credentials": "Credentials"
  },
  "review": {
    "needs_review": "Needs review",
    "confirmed": "Confirmed",
    "wrong": "Wrong - see note"
  },
  "workstream": {
    "accounting": "Accounting",
    "admin": "Admin",
    "audit": "Audit",
    "cash_banking": "Cash Banking",
    "fund_metrics": "Fund Metrics",
    "gp": "GP",
    "hr_benefits": "HR Benefits",
    "investor_relations": "Investor Relations",
    "legal": "Legal",
    "mgmt_co": "Mgmt Co",
    "mgmt_fees": "Mgmt Fees",
    "opex_interco": "Opex Interco",
    "other": "Other",
    "policies_marketing": "Policies Marketing",
    "portfolio": "Portfolio",
    "regulatory": "Regulatory",
    "reporting": "Reporting",
    "systems": "Systems",
    "tax": "Tax",
    "valuation": "Valuation",
    "vendors_ap": "Vendors AP"
  },
  "status": {
    "draft": "Draft",
    "in_review": "In review",
    "final": "Final",
    "issued": "Issued",
    "superseded": "Superseded"
  },
  "party_extra": {
    "LP": "An outside limited partner (no LP names; LP codes only from a list Ryan approves)",
    "EXTERNAL": "Any other third party"
  },
  "issuer": {
    "administrator": "Administrator",
    "allegis": "Allegis",
    "auditor": "Auditor",
    "bank": "Bank",
    "counsel": "Counsel",
    "datum": "Datum",
    "lp": "Lp",
    "other": "Other",
    "portco": "Portco",
    "unknown": "Unknown"
  }
} as const;

export type VocabList = keyof typeof VOCAB;
export function display(list: VocabList, code: string | null | undefined): string {
  if (code == null) return "";
  return (VOCAB[list] as Record<string, string>)[code] ?? code;
}
