"""
CAT-WO-04 · version linking: group documents into families, pick each family's current member, give the others a role.
Pure functions over in-memory rows: item 0's counts (scripts/measure_wo04_item0.py) and the derive step
(pipeline/families_wo04.py) run this same code, so the measured numbers are what the build sets.

File names are used in memory only; nothing here prints or stores them (stems are hashed before they leave).

Rulings: R-027 (L6 Version label: Family / Role / Supersedes / Amends), R-028 (an amendment is not a supersession;
an amended and restated document is), R-029 (Find's "Current versions only" off by default).
"""
import collections, hashlib, re

# ------------------------------------------------------------------ the token list (data: ops.version_token)
# (token_id, pattern, marker). marker = the role hint a hit gives a non-current member: 'redline', 'draft', 'executed'
# or None (a plain version token). The migration seeds ops.version_token with exactly this list (version 1);
# load_tokens() reads the active rows back, so the list is data, versioned like the decomposition rules.
LB, LE = r"(?<![a-z])", r"(?![a-z])"
DEFAULT_TOKENS = [
    ("VT-copy-of",   r"^\s*copy of\s+", None),
    ("VT-copy",      LB + r"copy" + LE + r"(\s*\(?\d{1,2}\)?)?", None),
    ("VT-paren-n",   r"\(\s*\d{1,2}\s*\)", None),
    ("VT-fully-exec", LB + r"fully[\s_-]*executed" + LE, "executed"),
    ("VT-executed",  LB + r"(executed|execution version)" + LE, "executed"),
    ("VT-signed",    LB + r"(signed|countersigned|counter-signed)" + LE, "executed"),
    ("VT-docusign",  LB + r"docu[\s_-]?sign(ed)?" + LE, "executed"),
    ("VT-redline",   LB + r"(red[\s_-]?lined?|black[\s_-]?lined?|compare|comparison|markup|marked[\s_-]?up|mark[\s_-]?up)" + LE, "redline"),
    ("VT-draft",     LB + r"drafts?" + LE, "draft"),
    ("VT-final",     LB + r"final" + LE, None),
    ("VT-clean",     LB + r"clean" + LE, None),
    ("VT-vN",        r"(?<![a-z0-9])v(er(sion)?)?[\s_.-]?\d{1,3}([._]\d{1,2})?(?![0-9])", None),
    ("VT-revN",      LB + r"rev(ision|ised)?(?![a-z])[\s_.-]?\d{0,3}", None),
    ("VT-initials",  r"[\[(]\s*[a-z]{2,4}(\s*[,/&]\s*[a-z]{2,4})*\s*(comments?|edits?)?\s*[\])]", None),
    ("VT-comments",  LB + r"(with |w[/ ])?(\w+ )?(comments?|edits?|changes)" + LE, "redline"),
    ("VT-corrected", LB + r"(corrected|amended)" + LE + r"(?!\s*(and|&)\s*restated)", None),   # K-1s: amended / corrected; never A&R
    ("VT-date-ymd",  r"(?<!\d)(19|20)\d{2}[\s._-]?(0?[1-9]|1[0-2])[\s._-]?(0?[1-9]|[12]\d|3[01])(?!\d)", None),
    ("VT-date-mdy",  r"(?<!\d)(0?[1-9]|1[0-2])[\s._/-](0?[1-9]|[12]\d|3[01])[\s._/-]((19|20)?\d{2})(?!\d)", None),
    ("VT-date-text", LB + r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}(st|nd|rd|th)?,?\s*((19|20)\d{2})?(?!\d)", None),
    ("VT-date-6",    r"(?<!\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([0-2]\d)(?!\d)", None),   # MMDDYY date stamps
]
EXT = re.compile(r"\.[a-z0-9]{2,5}$", re.I)

# ------------------------------------------------------------------ kinds
# Periodic singletons: a newer one is a new document, never a new version (order: "Kinds excluded").
EXCLUDED_KINDS = {"bank_stmt", "invoice", "receipt", "capital_call_notice", "distribution_notice", "wire_confirmation"}
K1_KIND = "k1"
K1_AMENDED = re.compile(LB + r"(amended|corrected)" + LE, re.I)
# R-028: amendment kinds and the base kind they amend
AMENDS_BASE = {"lpa_amendment": "lpa", "operating_agreement_amendment": "operating_agreement"}
AMENDMENT_NAME = re.compile(LB + r"(amendment|amending)" + LE, re.I)
AR_NAME = re.compile(LB + r"(amended\s*(and|&)\s*restated|a\s*&\s*r|a\s*and\s*r)" + LE, re.I)

ROLES = ["current", "superseded", "amends", "redline", "draft_of"]
ROLE_LABEL = {"current": "Current", "superseded": "Superseded", "amends": "Amends",
              "redline": "Redline / compare", "draft_of": "Draft of"}

# Picking the current member (order: "Picking the current member"); lower is better.
def rank(stage, status):
    if stage == "fully_executed": return 1
    if status == "issued": return 2
    if status == "final": return 3
    if stage == "partially_executed": return 4
    if stage == "final_unexecuted": return 5
    if status == "in_review": return 6
    if status == "draft" or stage == "draft": return 8
    return 7                     # nothing known: after In review, before Draft (a draft marker is evidence; silence is not)


def executed(m):
    return m["stage"] in ("fully_executed", "partially_executed")


# ------------------------------------------------------------------ stems
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def period_end(tid, txt):
    """A date in a name that is a MONTH END names the period the document covers (a monthly rec, a quarter's
    statement), not a version: it is kept in the stem as 'pYYYYMM', so two period ends never group. Any other date
    (a save / send date) is a version token and is dropped. Returns the kept text or None."""
    import calendar
    n = [int(x) for x in re.findall(r"\d+", txt)]
    try:
        if tid == "VT-date-ymd":
            y, mo, d = n[0], n[1], n[2]
            if len(n) == 1:  # 20230331
                t = str(n[0]); y, mo, d = int(t[:4]), int(t[4:6]), int(t[6:])
        elif tid == "VT-date-mdy":
            mo, d, y = n[0], n[1], n[2]
        elif tid == "VT-date-6":
            t = re.sub(r"\D", "", txt); mo, d, y = int(t[:2]), int(t[2:4]), int(t[4:])
        elif tid == "VT-date-text":
            mo = MONTHS[re.match(r"[a-z]{3}", txt.strip().lower()).group(0)]; d = n[0]; y = n[1] if len(n) > 1 else None
        else:
            return None
        if y is None: return None
        if y < 100: y += 2000
        if calendar.monthrange(y, mo)[1] == d:
            return f" p{y:04d}{mo:02d} "
    except (ValueError, IndexError, KeyError, AttributeError):
        return None
    return None


class Tokens:
    def __init__(self, rows=None):
        self.rows = [(tid, re.compile(p, re.I), mk) for tid, p, mk in (rows or DEFAULT_TOKENS)]

    def stem(self, name):
        """(stem, token ids hit, markers hit). The stem: lower-case, extension and version tokens dropped,
        punctuation to single spaces."""
        s = EXT.sub("", (name or "").strip()).lower()
        s = s.replace("_", " ")
        hits, marks = [], set()
        for tid, rx, mk in self.rows:
            if tid.startswith("VT-date"):
                s2 = rx.sub(lambda m, t=tid: period_end(t, m.group(0)) or " ", s)
            else:
                s2 = rx.sub(" ", s)
            if s2 != s:
                hits.append(tid)
                if mk: marks.add(mk)
                s = s2
        s = re.sub(r"[^a-z0-9&]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s, hits, marks


def loose(stem):
    """A looser stem for 'similar but not equal' (medium): digits and 1-2 letter words dropped, words sorted."""
    w = [t for t in stem.split() if not t.isdigit() and len(t) > 2]
    return " ".join(sorted(set(w)))


def h(s):
    return hashlib.sha1(s.encode()).hexdigest()[:10]


# ------------------------------------------------------------------ grouping
def doc_keys(m):
    """the identity keys a family shares (order: 'Candidates'), besides the stem"""
    return (m["kind"], tuple(sorted(m["entities"] or [])))


def subj(m):
    s = tuple(sorted(m["subject_codes"] or []))
    return (s, m["subject_person"]) if (s or m["subject_person"]) else None


def period(m):
    """(fy, period) or None when neither is known"""
    return (m["fy"], m["period"]) if (m["fy"] or m["period"]) else None


def eligible(m):
    k = m["kind"]
    if not k or k in EXCLUDED_KINDS: return False
    if k == K1_KIND: return True       # K-1s are considered, but only amended / corrected ones form a family (below)
    return True


def build(members, tokens=None):
    """
    members: dicts with document_id, name, kind, entities, subject_codes, subject_person, fy, period, effective_date,
             modified_time, stage, status, shared (primary copy on a shared drive), person (person-set membership:
             None or dict(family=<key or None>, role=..., current=bool)).
    Returns a list of families: dict(key, members=[doc ids], confidence 'high'|'medium', reason=[keys matched],
            hits=Counter(token ids)). Single-member groups are not families.
    """
    tokens = tokens or Tokens()
    by = {}
    for m in members:
        st, hits, marks = tokens.stem(m["name"])
        if m.get("content_amended") and m.get("kind") == K1_KIND and "VT-corrected" not in hits:
            hits = list(hits) + ["VT-corrected"]          # CAT-WO-06: the Amended K-1 box on page 1 is a version marker
        m["stem"], m["hits"], m["marks"] = st, hits, marks
        if not eligible(m) or not st:
            continue
        by.setdefault(doc_keys(m), []).append(m)
    fams = []
    for (kind, ents), ms in by.items():
        # 1. exact stem + subject + period = high
        grp = collections.defaultdict(list)
        for m in ms:
            grp[(m["stem"], subj(m), period(m))].append(m)
        singles = []
        for (st, sj, pe), g in grp.items():
            if kind == K1_KIND:
                g = k1_family(g)
            if len(g) > 1:
                if not any(m["hits"] for m in g):
                    # identical names, no version marker on any member: which is current would rest on dates alone
                    fams.append(dict(members=g, confidence="medium", reason=["same name", "kind", "entities", "subject", "period", "no version marker"]))
                    continue
                if all(t.startswith("VT-date") for m in g for t in m["hits"]) and not (pe and pe[1]):
                    # the names differ only by a date and no quarter / period is known: dates alone are weak evidence
                    # of versions (two reports sent on two dates), so a person decides
                    fams.append(dict(members=g, confidence="medium", reason=["stem", "kind", "entities", "subject", "period", "dates only"]))
                    continue
                fams.append(dict(members=g, confidence="high", reason=["stem", "kind", "entities", "subject", "period"]))
            else:
                singles.extend(g)
        # 2. one key missing (subject or period on one side only), same stem = medium
        idx = collections.defaultdict(list)
        for f in fams:
            if f["members"][0]["kind"] == kind and tuple(sorted(f["members"][0]["entities"] or [])) == ents and f["confidence"] == "high":
                idx[f["members"][0]["stem"]].append(f)
        left = []
        for m in singles:
            if kind == K1_KIND: continue
            cands = [f for f in idx.get(m["stem"], []) if compatible(m, f["members"][0])]
            if len(cands) == 1:
                f = cands[0]
                f.setdefault("medium_add", []).append(m)
            else:
                left.append(m)
        # singles that pair with each other on the same stem with one key missing
        bys = collections.defaultdict(list)
        for m in left:
            bys[m["stem"]].append(m)
        rest = []
        for st, g in bys.items():
            if len(g) > 1 and all(compatible(a, g[0]) for a in g[1:]):
                fams.append(dict(members=g, confidence="medium", reason=["stem", "kind", "entities", "one key missing"]))
            else:
                rest.extend(g)
        # 3. similar stem (loose equal, exact different), subject and period equal = medium
        byl = collections.defaultdict(list)
        for m in rest:
            if kind == K1_KIND: continue
            lk = loose(m["stem"])
            if lk and len(lk.split()) >= 2:
                byl[(lk, subj(m), period(m))].append(m)
        for k, g in byl.items():
            if len(g) > 1:
                fams.append(dict(members=g, confidence="medium", reason=["similar stem", "kind", "entities", "subject", "period"]))
    out = []
    for f in fams:
        if f.get("medium_add"):          # a high family that also takes members missing a key becomes medium
            f["members"] = f["members"] + f.pop("medium_add"); f["confidence"] = "medium"
            f["reason"] = f["reason"][:3] + ["one key missing"]
        f["hits"] = collections.Counter(t for m in f["members"] for t in m["hits"])
        out.append(f)
    return out


def compatible(a, b):
    """same subject and period where both have one; at most one of them missing on one side"""
    sa, sb, pa, pb = subj(a), subj(b), period(a), period(b)
    if sa and sb and sa != sb: return False
    if pa and pb and pa != pb: return False
    return True


def k1_family(g):
    """K-1s join a family only through an amended / corrected K-1 for the same partner and year (same subject and
    period are already in the key; the subject must be known)."""
    if len(g) < 2 or subj(g[0]) is None: return g[:1] if len(g) == 1 else []
    if not any(K1_AMENDED.search(m["name"] or "") or m.get("content_amended") for m in g): return []
    return g


# ------------------------------------------------------------------ roles
def tie_key(m):
    return (rank(m["stage"], m["status"]), -(m["effective_date"].toordinal() if m["effective_date"] else 0),
            -(m["modified_time"].timestamp() if m["modified_time"] else 0), not m["shared"], m["document_id"])


def pick(members):
    """(current member, {doc: (role, supersedes)}) for one family. A person's current wins. An executed member is
    never superseded by a member that is not executed (G1)."""
    pc = [m for m in members if (m.get("person") or {}).get("current")]
    if pc:
        cur = sorted(pc, key=tie_key)[0]
    else:
        cur = sorted(members, key=tie_key)[0]
    # G1: if the pick is not executed but an executed member exists, the executed one is current
    if not executed(cur) and any(executed(m) for m in members) and not pc:
        cur = sorted([m for m in members if executed(m)], key=tie_key)[0]
    roles = {}
    for m in members:
        if m is cur:
            roles[m["document_id"]] = ("current", None)
        elif executed(m) and not executed(cur):
            roles[m["document_id"]] = ("current", None)          # never superseded by an unsigned version (G1)
        elif "redline" in m.get("marks", ()):
            roles[m["document_id"]] = ("redline", cur["document_id"])
        elif "draft" in m.get("marks", ()) or m["status"] == "draft" or m["stage"] == "draft":
            roles[m["document_id"]] = ("draft_of", cur["document_id"])
        else:
            roles[m["document_id"]] = ("superseded", cur["document_id"])
    return cur, roles


def amendment_links(fams_current, members_by_doc):
    """
    R-028. fams_current: [(family index, current member)]. An amendment family's current member Amends the current
    base (same entities, base kind) in force at its effective date; an A&R base supersedes the base before it, and
    the amendments of a superseded base are superseded by the A&R that restated them.
    Returns (amends {amendment doc: base doc}, ar_supersedes {old base doc: A&R doc}, ambiguous [family indexes]).
    """
    bases = collections.defaultdict(list)                 # (base kind, ents) -> [(eff, is_ar, member)]
    for i, cur in fams_current:
        if cur["kind"] in AMENDS_BASE.values():
            bases[(cur["kind"], tuple(sorted(cur["entities"] or [])))].append((i, cur))
    amends, ar_sup, ambiguous = {}, {}, []
    # base chains: originals first, then A&Rs by effective date
    chain = {}
    for key, bs in bases.items():
        ar = [b for b in bs if AR_NAME.search(b[1]["name"] or "")]
        orig = [b for b in bs if b not in ar]
        if len(orig) > 1 or any(b[1]["effective_date"] is None for b in ar) and len(ar) > 1:
            ambiguous.extend(i for i, _ in bs); continue      # more than one original, or A&Rs that can't be ordered
        seq = orig + sorted(ar, key=lambda b: b[1]["effective_date"] or members_by_doc[b[1]["document_id"]]["modified_time"].date())
        for a, b in zip(seq, seq[1:]):
            ar_sup[a[1]["document_id"]] = b[1]["document_id"]
        chain[key] = seq
    for i, cur in fams_current:
        base_kind = AMENDS_BASE.get(cur["kind"])
        if not base_kind: continue
        seq = chain.get((base_kind, tuple(sorted(cur["entities"] or []))))
        if not seq:
            continue                                         # no base on file: the amendment stays current on its own
        eff = cur["effective_date"]
        pick_ = seq[0]
        for b in seq[1:]:
            if eff and b[1]["effective_date"] and b[1]["effective_date"] <= eff: pick_ = b
        if eff is None and len(seq) > 1:
            ambiguous.append(i); continue
        amends[cur["document_id"]] = pick_[1]["document_id"]
    return amends, ar_sup, ambiguous
