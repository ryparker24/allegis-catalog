"""
CAT-WO-02 · derivation rules for R-021 (Parties on K-1s) and R-022 (Status), plus item 9 proposals.
Pure functions over in-memory rows: the same code produces item 0's counts and the branch derivation, so the
numbers reported are exactly what the rules set. Unknown stays blank (None), never guessed.

Paths and names are used in memory only; nothing here prints or stores them.
"""
import re

# A regex's \b treats "_" and digits as word characters, so it misses 'Statement_2023', 'Draft_v2', 'FINAL1'.
# In the patterns below '<' / '>' mean the start / end of a WORD by letters: no letter before / after.
LB, LE = r"(?<![A-Za-z])", r"(?![A-Za-z])"


def W(rx, flags=re.I):
    """Compile a pattern written with '<' (word start) and '>' (word end) as letter boundaries."""
    return re.compile(rx.replace("<", LB).replace(">", LE), flags)


# ------------------------------------------------------------------ R-021 · K-1 parties
K1_CONTAINER = W(r"(<k-?1'?s?>|<1s>|<tax returns?>|<investor packages?>|<k1s>)")
RECEIVED_MARK = W(r"(<investments? in>|<received>|<investee|<from (the )?fund)")
GP_MARK = W(r"(<gp entities>|^gps?>|<gps management|<general partners?>)")
MGMT_MARK = W(r"(^mgmt co>|<management compan)")
PBC_MARK = W(r"(<pbc>|<estimates?>)")

ISSUER_TYPES = {"fund", "spv"}


def gp_fund(gp_code, entity_codes):
    """'MTV-III (GP)' -> 'MTV-III' when that fund code exists; ambiguous GPs (e.g. MTV-IV (GP): A/B) -> None."""
    base = re.sub(r"\s*\(GP\)$", "", gp_code)
    return base if base != gp_code and base in entity_codes else None


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
    if (any(GP_MARK.search(s) for s in path) or (gps and not funds)) and not PBC_MARK.search(j):
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
    ("name:draft", W(r"<draft>"), "draft"),
    ("name:redline", W(r"(<red-?line(d)?>|<blackline>)"), "in_review"),
    ("name:vN", W(r"(<v ?\d{1,2}(\.\d+)?(?![0-9])|<rev ?\d+(?![0-9]))"), "in_review"),
    ("name:final", W(r"<final>"), "final"),
    ("name:issued", W(r"<issued>"), "issued"),
    ("name:signed", W(r"(<signed>|<executed>)"), "final"),
]
FOLDER_MARKERS = [  # (marker id, pattern on a folder SEGMENT, status)
    ("folder:drafts", W(r"^\W*(\d+[\s._-]+)?drafts?>"), "draft"),
    ("folder:issued", W(r"^\W*(\d+[\s._-]+)?issued>"), "issued"),
    ("folder:final", W(r"^\W*(\d+[\s._-]+)?finals?>"), "final"),
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


# ------------------------------------------------------------------ item 9 · PROPOSED no-kind rules (F-018)
# Proposals only: nothing applies these until Ryan rules on each one (NOKIND_RULED stays empty until then).
# Each rule: (id, kind it would set, folder-segment pattern or None, name pattern or None, plain-words description).
# A file matches when every given pattern matches (folder: any segment). First match wins, in this order.
NOKIND_RULES = [
    ("NK01", "k1", r"(<k-?1'?s?>|<1s>)", None,
     "a folder named for K-1s (e.g. '…/<FY> K-1s from PwC/…', '…/Final K-1s/…')"),
    ("NK02", "invoice", None, r"(<inv(oice)?s?>|<inv ?#?\d)",
     "'invoice' / 'inv #' in the name"),
    ("NK03", "bank_stmt", r"<statements?>", r"(<statements?>|<stmts?>)",
     "'statement' in the name, inside a '…Statements' folder (e.g. '…/Mgmt Co/…/<x> Statements/<FY>/')"),
    ("NK04", "tax_form", None, r"(1042|1099|8804|8805|<w-?9|<w-?8|<extension>|7004|8868)",
     "a tax-form number or 'extension' in the name"),
    ("NK05", "tax_return", r"<tax returns?>", r"(1065|1120|990|<returns?>)",
     "'1065'/'1120'/'990'/'return' in the name, inside a '…Tax Returns…' folder"),
    ("NK06", "valuation_memo", None, r"(<valuations?>|409a)",
     "'valuation' in the name"),
    ("NK07", "quarterly_report", r"<reports?>", r"<reports?>",
     "'report' in the name, inside a '…Reports…' folder"),
    ("NK08", "receipt", None, r"<receipts?>",
     "'receipt' in the name"),
    ("NK09", "wire_confirmation", None, r"<wires?>",
     "'wire' in the name (e.g. '* - Wire *')"),
    ("NK10", "capital_call_notice", None, r"(<capital call>|<call notice>)",
     "'capital call' in the name"),
    ("NK11", "distribution_notice", None, r"<dist(ribution)? notice>",
     "'distribution notice' in the name"),
    ("NK12", "workpaper", r"(<workpapers?>|<pbc>)", None,
     "inside a '…Workpapers…' or '…PBC…' folder"),
]
NOKIND_RULED = {}   # rule id -> True once Ryan approves (CAT-WO-02 item 9); derivation applies only these
_NK = [(rid, kind, W(frx) if frx else None, W(nrx) if nrx else None, d) for rid, kind, frx, nrx, d in NOKIND_RULES]


def nokind_rule(name, segs, only=None):
    """(rule id, kind) of the first matching rule, optionally only among `only` (the ruled ids)."""
    n = name or ""
    for rid, kind, frx, nrx, _ in _NK:
        if only is not None and rid not in only: continue
        if frx and not any(frx.search(s) for s in segs): continue
        if nrx and not nrx.search(n): continue
        return rid, kind
    return None, None
