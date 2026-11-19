"""
CAT-WO-02 · derivation rules for R-021 (Parties on K-1s) and R-022 (Status), plus item 9 proposals.
Pure functions over in-memory rows: the same code produces item 0's counts and the branch derivation, so the
numbers reported are exactly what the rules set. Unknown stays blank (None), never guessed.

Paths and names are used in memory only; nothing here prints or stores them.
"""
import re

# A regex's \b treats "_" and digits as word characters, so it misses 'Statement_2023', 'Draft_v2', 'FINAL1'.
# In the patterns below '‹' / '›' mean the start / end of a WORD by letters: no letter before / after.
# (Not '<' / '>': those are regex syntax in '(?<!', '(?<=', '(?P<name>'.)
LB, LE = r"(?<![A-Za-z])", r"(?![A-Za-z])"


def W(rx, flags=re.I):
    """Compile a pattern written with '‹' (word start) and '›' (word end) as letter boundaries."""
    return re.compile(rx.replace("‹", LB).replace("›", LE), flags)


# ------------------------------------------------------------------ R-021 · K-1 parties
K1_CONTAINER = W(r"(‹k-?1'?s?›|‹1s›|‹tax returns?›|‹investor packages?›|‹k1s›)")
RECEIVED_MARK = W(r"(‹investments? in›|‹received›|‹investee|‹from (the )?fund)")
GP_MARK = W(r"(‹gp entities›|^gps?›|‹gps management|‹general partners?›)")
MGMT_MARK = W(r"(^mgmt co›|‹management compan)")
PBC_MARK = W(r"(‹pbc›|‹estimates?›)")

ISSUER_TYPES = {"fund", "spv"}


def gp_fund(gp_code, entity_codes):
    """'MTV-III (GP)' -> 'MTV-III' when that fund code exists; ambiguous GPs (e.g. MTV-IV (GP): A/B) -> None."""
    base = re.sub(r"\s*\(GP\)$", "", gp_code)
    return base if base != gp_code and base in entity_codes else None


K1R2_MAX = 3   # CAT-WO-03: more "received" K-1s than this for one GP and fiscal year = crowded -> unknown (apply_derive_wo02)


def k1_parties(segs, ents, ent_type, k1_in_folder, entity_codes):
    """
    segs: lower-cased folder path segments (drive name dropped); ents: entity codes on the file;
    ent_type: code -> entity_type; k1_in_folder: K-1 files in the same folder.
    Returns (issuing, receiving[list], rule_id) - any part may be None/[] (unknown).
    """
    path = [re.sub(r"^\d{1,3}[\s._-]+", "", s) for s in segs]
    j = " / ".join(path)
    types = {e: ent_type.get(e) for e in ents}
    funds = [e for e in ents if types[e] in ISSUER_TYPES]
    gps = [e for e in ents if types[e] == "gp"]
    mancos = [e for e in ents if types[e] == "manco"]

    # K1-R1: received by the management company ("Mgmt Co / ... Investments in ...")
    if any(MGMT_MARK.search(s) for s in path) and RECEIVED_MARK.search(j):
        recv = mancos[:1] if len(mancos) == 1 else []
        iss = funds[0] if len(funds) == 1 else None
        if recv or iss:
            return iss, recv, "K1-R1-mgmtco-received"
        return None, [], None
    # K1-R2: a GP's K-1 from its fund ("GP entities" / "GPs" folders, or a GP-only entity on the file)
    if (any(GP_MARK.search(s) for s in path) or (gps and not funds and k1_in_folder < 3)) and not PBC_MARK.search(j):
        if len(gps) == 1:
            iss = funds[0] if len(funds) == 1 else gp_fund(gps[0], entity_codes)
            return iss, gps, "K1-R2-gp-received"
        return None, [], None
    # K1-R3: issued by a fund/SPV to its LPs: a K-1 container folder holding several K-1s, one fund on the file
    if any(K1_CONTAINER.search(s) for s in path) and not RECEIVED_MARK.search(j) and not PBC_MARK.search(j):
        if len(funds) == 1 and not gps and k1_in_folder >= 3:
            return funds[0], ["LP"], "K1-R3-issued-to-lps"
    return None, [], None


# ------------------------------------------------------------------ R-022 · Status (publishing lifecycle)
STATUS_CODES = ["draft", "in_review", "final", "issued", "superseded"]
NAME_MARKERS = [  # (marker id, pattern on the file NAME, status)
    ("name:draft", W(r"‹draft›"), "draft"),
    ("name:redline", W(r"(‹red-?line(d)?›|‹blackline›)"), "in_review"),
    ("name:vN", W(r"((?<![-A-Za-z])v\d{1,2}(\.\d+)?(?![0-9.])|‹ver(sion)? ?\d{1,2}(?![0-9])|‹rev ?\d{1,2}(?![0-9]))"), "in_review"),
    ("name:final", W(r"‹final›"), "final"),
    ("name:issued", W(r"‹issued›"), "issued"),
    ("name:signed", W(r"(‹signed›|‹executed›)"), "final"),
]
FOLDER_MARKERS = [  # (marker id, pattern on a folder SEGMENT, status)
    ("folder:drafts", W(r"^\W*(\d+[\s._-]+)?drafts?›"), "draft"),
    ("folder:issued", W(r"^\W*(\d+[\s._-]+)?issued›"), "issued"),
    ("folder:final", W(r"^\W*(\d+[\s._-]+)?finals?›"), "final"),
]


def markers(name, segs):
    out = [m for m, rx, _ in NAME_MARKERS if rx.search(name or "")]
    out += [m for m, rx, _ in FOLDER_MARKERS if any(rx.search(s) for s in segs)]
    return out


def status_for(kind, executable, name, segs, stage=None):
    """
    Status for non-executable kinds (Stage stays the signing progress for executable kinds).
    A fully executed agreement implies Final (R-022). Conflicting markers ('draft' with 'final'/'issued') -> blank.
    Returns (status|None, rule_id|None).
    """
    if executable:
        return ("final", "ST-exec-fully-executed") if stage == "fully_executed" else (None, None)
    ms = markers(name, segs)
    if not ms:
        return None, None
    st = {s for m, rx, s in NAME_MARKERS + FOLDER_MARKERS if m in ms}
    if "draft" in st and (st & {"final", "issued"}):
        return None, "ST-conflict"
    if "issued" in st: return "issued", "ST-issued"
    if "final" in st: return "final", "ST-final"
    if "in_review" in st: return "in_review", "ST-in-review"
    if "draft" in st: return "draft", "ST-draft"
    return None, None


# ------------------------------------------------------------------ item 9 · no-kind rules (F-018), as Ryan ruled them
# Each rule: (id, kind it sets, folder-segment pattern or None, name pattern or None, plain-words description).
# A file matches when every given pattern matches (folder: any segment) and the per-rule limits below allow it.
# Only files with NO kind are touched. First match wins, in this order.
# Ruled out (Ryan): NK01 (replaced by K1N / K1F), NK09 'wire' (rejected), NK10 / NK11 (0 files; KND-003 / KND-004
# already cover them), the 'extension' half of NK04 and the PBC half of NK12.
_RK1_REPORT = r"(‹fin(ancial)? ?(report|rpt)s?›|‹qtr›|‹qtrly›)"
_RK1_QTR = r"(‹qtr›|‹qtrly›|‹quarter(ly)?›|‹q[1-4]›)"
NOKIND_RULES = [
    ("K1N", "k1", None, r"(‹k-?1(?![0-9])|‹k1s›|‹k-1s›|‹schedule k-?1(?![0-9]))",
     "the name says K-1 ('K-1', 'K1', 'K-1s', 'Schedule K-1'; not 'K-1065'-style numbers); not archives"),
    ("K1F", "k1", r"(‹k-?1'?s?›(?![0-9])|‹k1s›)", None,
     "a folder named for K-1s ('<FY> K-1s', 'K-1s from <auditor>', 'Final K-1s') and the file is a pdf / doc / image"),
    ("NK02", "invoice", None, r"(‹inv(oice)?s?›|‹inv ?#?\d)",
     "'invoice' / 'inv #' in the name; PDF and Word only"),
    ("NK03", "bank_stmt", r"‹statements?›", r"(‹statements?›|‹stmts?›)",
     "'statement' in the name, inside a '…Statements' folder, ONLY in a bank-statement folder ('bank', 'account "
     "statement', or a bank the catalog knows), never under Financial / Capital / Partner or Capital Account "
     "Statements or K-1 folders"),
    ("NK04", "tax_form", None, r"(1042|1099|8804|8805|‹w-?9|‹w-?8|7004|8868)",
     "a tax-form number in the name (1042, 1099, 8804 / 8805, W-9 / W-8, 7004, 8868); bare 'extension' dropped"),
    ("NK05", "tax_return", r"‹tax returns?›", r"(1065|1120|990|‹returns?›)",
     "'1065'/'1120'/'990'/'return' in the name, inside a '…Tax Returns…' folder; not archives"),
    ("NK06", "valuation_memo", None, r"(‹valuations?›|409a)",
     "'valuation' / '409A' in the name; PDF and Word only"),
    # RK1 (approved; runs before NK07): a fin / financial report or 'Qtr' name -> quarterly_report when it also names a
    # quarter, else financial_statements. Its loc_agreement half is the KND-049 v2 fix in 004 (those files lose the
    # wrong kind at derive and arrive here with no kind).
    ("RK1Q", "quarterly_report", None, rf"^(?=.*{_RK1_REPORT})(?=.*{_RK1_QTR})",
     "RK1: 'Fin Report' / 'Financial Report' / 'Fin Rpt' / 'Qtr' in the name AND a quarter (Qtr / quarter / Q1-Q4)"),
    ("RK1F", "financial_statements", None, _RK1_REPORT,
     "RK1: 'Fin Report' / 'Financial Report' / 'Fin Rpt' / 'Qtr' in the name, no quarter"),
    ("NK07", "quarterly_report", r"‹reports?›", r"‹reports?›",
     "'report' in the name, inside a '…Reports…' folder (after RK1)"),
    ("NK08", "receipt", None, r"‹receipts?›",
     "'receipt' in the name"),
    ("NK12", "workpaper", r"‹workpapers?›", None,
     "inside a '…Workpapers…' folder (PBC-only folders rejected)"),
]
# every rule above is approved; apply_derive_wo02.py applies these by default
NOKIND_RULED = frozenset(r[0] for r in NOKIND_RULES)
# per-rule file-type limits (cat.file.file_type_family)
NK_FAMILIES = {"K1F": frozenset({"pdf", "image", "doc"}), "NK02": frozenset({"pdf", "doc"}),
               "NK06": frozenset({"pdf", "doc"})}
NK_NOT_FAMILIES = {"K1N": frozenset({"archive"}), "NK05": frozenset({"archive"})}
# NK03 · bank-statement folders only (Ryan). A bank 'the catalog knows' = the bank-issuer rule's names (ISS-004P),
# loaded by the caller with set_bank_pattern(); without it only 'bank' / 'account statement' folders count.
NK03_BANK = W(r"(‹bank|‹account statements?›|‹schwab›)")   # Schwab: Ryan round 4 (in the bank list for NK03)
# Ryan round 5: issuer = bank from Schwab ONLY for PDFs under a Schwab folder (sheets / Word / other keep their issuer)
SCHWAB_FOLDER = W(r"‹schwab›")


def schwab_issuer(segs, family, issuer):
    """'bank' when a PDF sits under a Schwab folder and has no issuer yet; else None (nothing to change)."""
    if family == "pdf" and issuer is None and any(SCHWAB_FOLDER.search(s) for s in segs):
        return "bank"
    return None
NK03_EXCLUDE = W(r"(‹financial statements?›|‹capital statements?›|‹(partner|partners'?|capital) account statements?›|"
                 r"‹k-?1'?s?›(?![0-9])|‹k1s›)")
_bank_names = None


def set_bank_pattern(pg_pattern):
    r"""The ISS-004P pattern (Postgres ARE: (?i) and \y); \y -> \b like drive_crawl.derive."""
    global _bank_names
    _bank_names = re.compile(pg_pattern.replace("\\y", "\\b")) if pg_pattern else None


def nk03_folder(segs):
    """'bank' / 'account statement' / known-bank folder, and none of the excluded statement or K-1 folders."""
    if any(NK03_EXCLUDE.search(s) for s in segs): return False
    return any(NK03_BANK.search(s) or (_bank_names is not None and _bank_names.search(s)) for s in segs)


_NK = [(rid, kind, W(frx) if frx else None, W(nrx) if nrx else None, d) for rid, kind, frx, nrx, d in NOKIND_RULES]


def nokind_rule(name, segs, only=None, family=None):
    """(rule id, kind) of the first matching rule, optionally only among `only` (the ruled ids)."""
    n = name or ""
    for rid, kind, frx, nrx, _ in _NK:
        if only is not None and rid not in only: continue
        if rid in NK_FAMILIES and (family or "") not in NK_FAMILIES[rid]: continue
        if rid in NK_NOT_FAMILIES and (family or "") in NK_NOT_FAMILIES[rid]: continue
        if frx and not any(frx.search(s) for s in segs): continue
        if nrx and not nrx.search(n): continue
        if rid == "NK03" and not nk03_folder(segs): continue
        return rid, kind
    return None, None


# ------------------------------------------------------------------ item 9 · re-kind rules RK2-RK4 (Ryan approved)
# These CHANGE an existing machine kind (never a person's kind_confirmed). apply_derive_wo02.py runs them over the
# whole catalog after every derive, before the no-kind rules.
RK2_OA = W(r"‹operating agreements?›")
RK2_AMEND = W(r"(‹amend|‹restat)")
RK3_BOOKLET = W(r"‹subscription (booklet|book|package|docs?)›")
RK3_BLANK = W(r"(‹blank›|‹form›|‹template›)")
RK4_FORMATION = W(r"(‹certificate of amendment›|‹name change›|‹de amendment›|‹delaware amendment›|"
                  r"‹amendment to (the )?certificate›)")


# ------------------------------------------------------------------ CAT-WO-03.1 · audited financial statements (Ryan 2026-11-19)
# A fund's "Annual Report" is its audited financial statements. Kind audited_financial_statements, FY = the report year,
# period = the fiscal year (never a quarter: the "2025-Q4" folder it sits in is where it was filed, not its period).
#   AFS-A  "<firm> <YYYY> Annual Report - <entity legal name>"                       (Ryan)
#   AFS-B  a "_Final Reports" folder and "Annual Report" in the file name             (Ryan)
#   AFS-C  "Annual Report" + exactly ONE Datum legal name + one year (name, else a year folder)   (default taken, Ryan
#          approved "add shape C": the FY2024 reports are named "<legal name> ... 2024 Annual Report")
# Never: drafts / redlines / versions, cover letters, decks, presentations, summaries. Machine kinds only, and only
# over the report kinds the measurement found them under. Entity comes from the legal-name entity rules (ENT-0xx).
AFS_KIND = "audited_financial_statements"
AFS_FROM_KINDS = {None, "quarterly_report", "audit_report", "financial_statements", AFS_KIND}   # audit_report: until 006b renames it (then harmless)
_AFS_A = re.compile(r"^(?P<firm>.+?)\s+(?P<fy>(?:19|20)\d{2})\s+annual\s+report\s*[-–—]\s*(?P<legal>.+?)(\.[a-z0-9]{2,5})?$", re.I)
_AFS_ANNUAL = re.compile(r"\bannual\s+report\b", re.I)
_AFS_FINAL_SEG = re.compile(r"^_?final\s+reports?$", re.I)
_AFS_NOT = re.compile(r"\b(draft|redline[sd]?|blackline|v\d{1,2}|version|letter|cover|deck|presentation|slides|summary|highlights)\b", re.I)
_AFS_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_AFS_CIP1_EXCLUDE = re.compile(r"(\bII\b|\bIII\b|(?<![0-9])2(?![0-9]))")
_LEGAL_SUFFIX = {"lp", "llc", "inc", "ltd", "l", "p", "c"}


def legal_key(s):
    """a legal name as lower-case words, punctuation dropped, trailing entity form (L.P., LLC ...) removed"""
    t = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()
    while t and t[-1] in _LEGAL_SUFFIX:
        t.pop()
    return " ".join(t)


def legal_entities(name, legal):
    """entities whose Datum legal name appears in the name (whole words; the longest wins). CIP-I only when the name
    has no "II", "III" or "2" (Ryan: CIP-I legal-name rule turned on with that exclusion)."""
    n = " " + re.sub(r"[^a-z0-9]+", " ", (name or "").lower()) + " "
    found = [lg for lg in legal if lg and f" {lg} " in n]
    # a match nested in a longer one ("cyber innovation partners" in "... partners ii") is the longer one's; two
    # DIFFERENT funds named in one file stay ambiguous (both returned)
    kept = [lg for lg in found if not any(lg != o and f" {lg} " in f" {o} " for o in found)]
    hits = set().union(*[legal[lg] for lg in kept]) if kept else set()
    if "CIP-I" in hits and _AFS_CIP1_EXCLUDE.search(name or ""):
        hits.discard("CIP-I")
    return hits


def afs_rule(name, segs, kind, legal):
    """-> (rule_id, fiscal_year or None, entity or None) for an audited-FS report, else None.
    segs: folder segments (drive dropped); legal: {legal_key(Datum company name): {entity codes}}."""
    name = name or ""
    if kind not in AFS_FROM_KINDS or not _AFS_ANNUAL.search(name) or _AFS_NOT.search(name):
        return None
    ents = legal_entities(name, legal)
    ent = next(iter(ents)) if len(ents) == 1 else None
    yrs = set(_AFS_YEAR.findall(name))
    if len(yrs) != 1:
        yrs = {s.strip() for s in (segs or []) if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", s or "")}
    fy = int(next(iter(yrs))) if len(yrs) == 1 else None
    m = _AFS_A.match(name)
    if m:
        return "AFS-A", int(m.group("fy")), ent
    if any(_AFS_FINAL_SEG.match((s or "").strip()) for s in (segs or [])):
        return "AFS-B", fy, ent
    if ent and fy:
        return "AFS-C", fy, ent
    return None


_AUDITED_WORD = re.compile(r"\baudited\b", re.I)
_AUDIT_KINDS = {"audit_report", AFS_KIND}


def audit_kind_rule(name, family, kind):
    """CAT-WO-03.1 rulings (Ryan 2026-11-19) on the audited-FS kinds, by file type. Machine kinds only.
    -> (rule_id, kind) or (None, None).
      P2  an EMAIL in an audit kind, or a financial-statements email named "audited" -> correspondence (the rules
          skip email files: mail ABOUT the statements is not the statements)
      P3  a SPREADSHEET in an audit kind -> financial_statements (workbooks stay financial statements)
      P5  a financial_statements PDF named "audited" -> audited_financial_statements
    P4 (Word drafts stay audited FS, Status = Draft) is afs_status()."""
    if family == "email" and (kind in _AUDIT_KINDS or (kind == "financial_statements" and _AUDITED_WORD.search(name or ""))):
        return "AK-P2-email", "correspondence"
    if family == "sheet" and kind in _AUDIT_KINDS:
        return "AK-P3-sheet", "financial_statements"
    if family == "pdf" and kind == "financial_statements" and _AUDITED_WORD.search(name or ""):
        return "AK-P5-audited-pdf", AFS_KIND
    return None, None


def afs_status(kind, family):
    """P4: a Word document of the audited statements is a draft (Status = Draft, so it never satisfies AUD-01)."""
    return ("draft", "AK-P4-word-draft") if kind == AFS_KIND and family == "doc" else (None, None)


def rekind_rule(name, kind, stage=None, issuer=None):
    """(rule id, new kind) when RK2 / RK3 / RK4 changes this file's kind, else (None, None)."""
    n = name or ""
    if RK2_OA.search(n) and kind != "correspondence":                       # RK2: the 11 cover emails stay
        k = "operating_agreement_amendment" if RK2_AMEND.search(n) else "operating_agreement"
        return ("RK2", k) if k != kind else (None, None)
    if (RK3_BOOKLET.search(n) or (issuer == "counsel" and RK3_BLANK.search(n) and kind in ("subscription_agreement", None))) \
            and stage != "fully_executed" and kind != "template":
        return "RK3", "template"
    if RK4_FORMATION.search(n) and kind not in ("tax_return", "tax_form", "formation_filing", "correspondence"):   # cover emails stay, as in RK2
        return "RK4", "formation_filing"
    return None, None


# ------------------------------------------------------------------ item 9 · re-kind rules RK1-RK4 (Ryan, live Review queue) - APPROVED; plain-words record
# Implemented above: RK1 = KND-049 v2 (004) + RK1Q / RK1F in NOKIND_RULES; RK2-RK4 = rekind_rule().
RECLASS_PROPOSALS = [
    ("RK1", "fix KND-049 '(?i)pledge (agreement|fin)' -> '(?i)pledge agreement'; then name 'fin report'/'financial report'/"
            "'qtr' on no-kind or loc_agreement files -> quarterly_report (Qtr / quarter / Qn) else financial_statements"),
    ("RK2", "name 'operating agreement' -> operating_agreement (NEW kind, Datum FORM-04); amendments / restated: ruling needed"),
    ("RK3", "name 'subscription booklet/book/package/docs', or counsel 'blank'/'form'/'template' -> kind template "
            "(not when fully executed). R-022 Status has no 'template' choice, so this is a KIND, not a Status"),
    ("RK4", "name 'certificate of amendment'/'name change'/'DE amendment' -> formation_filing (not tax returns / forms)"),
]


# ------------------------------------------------------------------ item 9 · PROPOSED K-1 kind rules (FY2023 gap, CAT-WO-03 prep)
# APPROVED by Ryan (they are K1N / K1F in NOKIND_RULES above, replacing NOKIND NK01); kept as the plain-words record.
K1_KIND_PROPOSALS = [
    ("K1N", "name says K-1 ('K-1', 'K1', 'K-1s', 'Schedule K-1'; not 'K-1065'-style numbers) on a no-kind file -> k1"),
    ("K1F", "a folder named for K-1s ('2023 K-1s', 'K-1s from PwC', 'Final K-1s') AND the file is document-like "
            "(pdf / doc / image; not sheets, archives, email) on a no-kind file -> k1. Supersedes NK01 if both are ruled."),
]
