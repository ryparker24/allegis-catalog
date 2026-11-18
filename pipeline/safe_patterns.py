"""
CAT-WO-02 · codes-only generalisation of folder paths and file names (item 0 / item 9).
A path segment or name token is printed ONLY if it is a year, an Allegis entity / portco (shown as its CODE),
or a word on the GENERIC allow-list below. LP and person names become <LP> / <PERSON>; anything else <other>.
So nothing that could be an LP, an individual or a file name ever reaches the terminal or a report.
"""
import re

GENERIC = {w.lower() for w in """
finance limited shared drive drives fund funds tax taxes k1 k-1 k1s k-1s k-1's schedule schedules workpaper workpapers
return returns federal state states investor investors partner partners lp lps gp gps issued received final finals
draft drafts archive archived admin administration accounting reporting report reports statement statements quarterly
annual audit audits investment investments portfolio portfolios form forms distribution distributions capital call calls
legal docs documents signed executed old misc other others shared copy copies scans scanned working wp pbc closing
close year-end yearend ye q1 q2 q3 q4 fy cy ty bank banking banks wire wires wires invoices invoice ap ar vendor vendors
payroll hr benefits mgmt management co company companies llc lp. l.p. inc corp holdings entity entities general
financial financials gl journal journals entries je budget budgets valuation valuations 409a cap table tables board
minutes consents consent agreements agreement subscription subscriptions side letters letter lpa ppm ddq nda
compliance regulatory sec adv form-pf filings filing formation k-1 composite composites estimates estimate extensions
extension 1065 1120 990 8804 8805 1042 1099 w-9 w-8 w9 w8 notices notice cpa preparer prepared support supporting
backup backups new current prior templates template revver export entire contents systems system pdf xlsx
received_k1s issued_k1s investee investees portfolio_companies spv spvs side_letters sub docs_signed
ii iii iv v vi vii annex allegis files to package packages pledge ups write 1s pf media parts sent cutups updated
mediatech technology for by ventures nl pwc and update ca cover covers from amendment amendments of the in
""".split()}
# Words that sit inside LP names but are generic on their own (never mask a segment because of these alone)
SAFE_EVEN_IF_LP = {"trust", "family", "llc", "lp", "foundation", "fund", "capital", "partners", "investments", "holdings",
                   "inc", "group", "the", "of", "and", "ii", "iii", "iv", "management", "ventures", "company", "co"}

YEAR = re.compile(r"^(19|20)\d\d$")
FYLIKE = re.compile(r"^(fy|ty|cy)?\s?'?(19|20)?\d\d$", re.I)
NUMPREFIX = re.compile(r"^\d{1,3}[\s._-]+")

def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())

class Masker:
    def __init__(self, cur):
        cur.execute("SELECT entity_code, name, aliases, legacy_names FROM ref.entity")
        self.ent = {}
        for code, name, al, leg in cur.fetchall():
            for x in [code, name, *(al or []), *(leg or [])]:
                if x: self.ent[norm(x)] = code
        cur.execute("SELECT alias, entity_code FROM ref.entity_alias WHERE NOT coalesce(generic,false)")
        for a, c in cur.fetchall():
            if a: self.ent.setdefault(norm(a), c)
        cur.execute("SELECT portco_code, name, street_name, legal_name, aliases FROM ref.portco")
        self.pco = {}
        for code, n, sn, ln, al in cur.fetchall():
            for x in [code, n, sn, ln, *(al or [])]:
                if x and len(x) > 2: self.pco[norm(x)] = code
        cur.execute("SELECT folder_name, portco_code FROM ref.portco_folder_alias")
        for a, c in cur.fetchall():
            if a: self.pco.setdefault(norm(a), c)
        cur.execute("SELECT name, aliases FROM ref.lp")
        self.lp = set()
        for n, al in cur.fetchall():
            for x in [n, *(al or [])]:
                if x and len(x) > 2: self.lp.add(norm(x))
        cur.execute("SELECT name FROM ref.person")
        self.person = {norm(n) for (n,) in cur.fetchall() if n and len(n) > 2}
        # single words of LP / person names: a segment containing one is masked whole as <name>
        self.name_words = set()
        for x in self.lp | self.person:
            for w in re.split(r"[^a-z0-9]+", x):
                if len(w) > 1 and w not in SAFE_EVEN_IF_LP and w not in GENERIC: self.name_words.add(w)

    def segment(self, seg):
        """one folder-path segment -> a safe token"""
        s = norm(NUMPREFIX.sub("", seg))
        if not s: return "<other>"
        if s in self.lp: return "<LP>"
        if s in self.person: return "<PERSON>"
        if YEAR.match(s) or FYLIKE.match(s) and re.search(r"\d\d", s): return "<FY>"
        if s in self.ent: return f"<ENT:{self.ent[s]}>"
        if s in self.pco: return f"<PCO:{self.pco[s]}>"
        words = re.split(r"[\s/_-]+", s)
        out = []
        for w in words:
            w2 = w.strip("()[].,'&")
            if not w2: continue
            if w2 in self.name_words: return "<name>"
            if YEAR.match(w2): out.append("<FY>")
            elif w2 in self.ent: out.append(f"<ENT:{self.ent[w2]}>")
            elif w2 in GENERIC: out.append(w2)
            elif not out or out[-1] != "*": out.append("*")
        t = " ".join(out)
        return t if t and t != "*" else "*"

    def path(self, segments, skip_root=True):
        segs = list(segments or [])
        return "/".join(self.segment(x) for x in segs)

NAME_TOKEN = re.compile(r"[A-Za-z0-9'&.]+|[^A-Za-z0-9'&.\s]")

def name_pattern(name, masker):
    """a file name -> its shape: generic words, years, codes; everything else collapsed to '*'."""
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name or "")
    toks = NAME_TOKEN.findall(base)
    out = []
    for t in toks:
        tl = t.lower().strip(".")
        if not tl: continue
        if YEAR.match(tl): out.append("<FY>")
        elif tl in masker.ent and len(tl) > 1: out.append(f"<ENT:{masker.ent[tl]}>")
        elif tl in masker.name_words: return "<name>"
        elif tl in GENERIC: out.append(tl)
        elif t in "-_()&,": out.append(t)
        else: out.append("*")
    s = " ".join(out)
    s = re.sub(r"(\* ?)+", "* ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s or "*"
