r"""
CAT-WO-06 · first-page reading: tie K-1s, PCAPs, subscription agreements and side letters to Datum partner codes from
what is printed on the page (R-033 .. R-038).

  py pipeline\pages_wo06.py --db-url-file <url file> [--release] (--backfill | --incremental) [--limit N] [--apply]
  py pipeline\pages_wo06.py --db-url-file <url file> --seed-rules            (CNT-* rules -> ops.decomposition_rule)
  py pipeline\pages_wo06.py --db-url-file <url file> --apply-content         (content FY / period fill + disagreements)

R-033  Pages are read on this machine, IN MEMORY, with the crawler's drive.readonly login. Only codes, page numbers,
       method, confidence and reason codes are stored. Page text, names, addresses, TINs, amounts and percentages are
       never stored, logged or sent anywhere (no cloud OCR, no LLM). OCR is local Tesseract, fed through a pipe.
R-034  A content match replaces a folder / name machine match; a person's Subject always wins; a content match that
       disagrees with a person's value or a portal-derived code goes to Review (subject_wo03.merge_content).
R-035  A PCAP package / K-1 bundle gets one row per partner found, with its page range.
R-036  A code is applied only when that partner is on the Datum roster of the document's entity (else NOT_IN_FUND).
R-037  Handling Contains gets Tax ID when page 1 carries a TIN pattern, LP PII when a roster partner is matched
       (presence only; never the value; tier unchanged; a person's removal sticks - catalog_labels.handling_raise).
R-038  Anchors and patterns are data: ops.decomposition_rule applies_to='content' (CNT-K1-*, CNT-PCAP-*, CNT-SUB-*,
       CNT-SL-*). A rule whose pattern JSON says "mode": "review_only" feeds the lane and is never auto-applied.

Prints counts and codes only.
"""
import argparse, collections, datetime, io, json, os, re, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXTRACTOR_VERSION = "cnt-3"
KINDS = ("k1", "capital_statement", "subscription_agreement", "side_letter")
PDF = "application/pdf"
GDOC = "application/vnd.google-apps.document"
WORD_EXCEL = re.compile(r"(msword|wordprocessingml|ms-excel|spreadsheetml|vnd\.google-apps\.spreadsheet|opendocument\.(text|spreadsheet))")
MAX_BYTES = 60_000_000          # larger files are counted 'too_large' and not downloaded
EXPORT_MAX = 10_000_000         # Drive's export limit for a Google Doc -> PDF
TEXT_MIN = 40                   # characters on a page below which the page counts as having no text layer
OCR_DPI = 200
OCR_TOP_DPI = 150
OCR_PAGE_CAP = 60               # at most this many pages OCR'd per document (the rest -> outcome ocr_partial)
SIG_PAGES = 4                   # subscription agreements: the signature pages among the last 4 (as sig_scan.py)
SIG_MAX = 3
BATCH = 200
NIGHTLY_CAP = 500
TEMP_DIR = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")), "catwo06")
CODE_RE = re.compile(r"^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$")
OUTCOMES = ("ok", "no_anchor", "ocr_needed", "ocr_partial", "too_large", "encrypted", "download_error", "open_error",
            "skipped_format", "no_file")
REASONS = ("NO_ROSTER_MATCH", "NOT_IN_FUND", "MULTIPLE", "CONFLICT_PERSON", "CONFLICT_PORTAL")
ANCHOR_RE = re.compile(r"^[A-Z0-9]{1,6}(-[A-Z0-9]{1,8}){0,3}$")

# ------------------------------------------------------------------ R-038 rules (seeded as data; vetoable one by one)
# (rule_id, field, anchor code, spec, note). spec keys: start / end / label / title / rx (Python regexes), region (fraction
# of the page height from the top), certain (the anchor is a certain partner position), mode (apply | review_only).
TIN_RX = r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)|(?<!\d)\d{2}-\d{7}(?!\d)|XXX-XX-\d{4}|\*{3}-\*{2}-\d{4}"
CNT_RULES = [
    ("CNT-K1-HDR", "statement_start", "K1-HDR",
     {"rx": r"Schedule\s*K-?1\s*\(?\s*Form\s*1065\s*\)?", "with": r"Part\s*II|Information\s+About\s+the\s+Partner", "region": 0.30},
     "a page that starts one partner's K-1 (form header + Part II on the page)"),
    ("CNT-K1-PI", "entity", "K1-PI-B",
     {"start": r"Partnership'?s\s+name,\s*address", "end": r"IRS\s+[Cc]enter|publicly\s+traded|Part\s*II|^\s*C\b", "max_dy": 70},
     "Part I item B: the partnership's name -> entity code"),
    ("CNT-K1-PII", "partner", "K1-PII-F",
     {"start": r"(?<![A-Za-z'’]s )Name,\s*address,\s*city|Partner'?s\s+name,\s*address,\s*city",
      "end": r"General\s+partner\s+or\s+LLC|Limited\s+partner\s+or\s+other|^\s*[GH]\s+|What\s+type\s+of\s+entity", "max_dy": 70,
      "certain": True, "gp_rows": True},
     "Part II item F (older forms: E): the partner's name block -> partner code"),
    ("CNT-K1-YEAR", "tax_year", "K1-YEAR",
     {"rx": r"(?:For\s+calendar\s+year|calendar\s+year)\s*(20\d{2})|Schedule\s*K-?1\s*\(?\s*Form\s*1065\s*\)?\s*(20\d{2})|\b(20\d{2})\s*Schedule\s*K-?1", "region": 0.25},
     "the K-1's tax year (calendar-year funds)"),
    ("CNT-K1-AMENDED", "amended", "K1-AMD",
     {"rx": r"[Xx✓✔☒■]\s*Amended\s+K-?1|Amended\s+K-?1\s*[Xx✓✔☒■](?![A-Za-z])", "region": 0.25},
     "the Amended K-1 box is marked (joins the original's family, CAT-WO-04 rule)"),
    ("CNT-K1-FINAL", "final", "K1-FIN",
     {"rx": r"[Xx✓✔☒■]\s*Final\s+K-?1|Final\s+K-?1\s*[Xx✓✔☒■](?![A-Za-z])", "region": 0.25},
     "the Final K-1 box is marked (recorded, not used)"),
    ("CNT-PCAP-TITLE", "statement_start", "PCAP-HDR",
     {"rx": r"(?i)(partner'?s'?\s+capital\s+(account\s+)?statement|statement\s+of\s+(the\s+)?partner'?s'?\s+capital|"
            r"capital\s+account\s+statement|statement\s+of\s+changes\s+in\s+partner'?s'?\s+capital|investor\s+capital\s+statement)",
      "region": 0.30},
     "a page whose top region starts one partner's capital statement"),
    ("CNT-PCAP-PARTNER", "partner", "PCAP-HDR-LBL",
     {"label": r"(?i)\b(limited\s+partner|partner\s+name|investor\s+name|partner|investor|member|prepared\s+for|account\s+name)\s*[:\-]",
      "region": 0.35, "certain": True},
     "PCAP header: a 'Partner:' / 'Investor:' label -> partner code"),
    ("CNT-PCAP-TOP", "partner", "PCAP-HDR-TOP",
     {"region": 0.30, "certain": False},
     "PCAP header without a label: a roster name in the top region (never certain -> lane)"),
    ("CNT-PCAP-PERIOD", "period_end", "PCAP-PER",
     {"rx": r"(?i)(?:period|quarter|year|months?)\s+end(?:ed|ing)\s*:?\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})|"
            r"(?:as\s+of|through)\s+([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})",
      "region": 0.35},
     "PCAP period end -> fiscal year and quarter (calendar fiscal year)"),
    ("CNT-PCAP-FUND", "entity", "PCAP-FUND", {"region": 0.30}, "PCAP header: the fund's name -> entity code"),
    ("CNT-SUB-LBL", "partner", "SUB-LBL",
     {"label": r"(?i)(name\s+of\s+(investor|subscriber|purchaser|limited\s+partner)|(investor|subscriber)'?s?\s+name|"
               r"print(?:ed)?\s+name(\s+of\s+(investor|subscriber))?|exact\s+name|\bsubscriber\s*:|\binvestor\s*:)",
      "certain": True},
     "subscription agreement cover / signature page: the investor-name label -> partner code"),
    ("CNT-SUB-TOP", "partner", "SUB-TOP", {"certain": False},
     "subscription agreement: a roster name elsewhere on the cover / signature pages (never certain -> lane)"),
    ("CNT-SUB-SIG", "sig_page", "SUB-SIG",
     {"rx": r"(?i)IN\s+WITNESS\s+WHEREOF|\bBy:\s|\bSignature:|\bSigned:|Authorized\s+Signatory|SIGNATURE\s+PAGE"},
     "which of the last pages are signature pages (as sig_scan.py)"),
    ("CNT-SUB-FUND", "entity", "SUB-FUND", {"region": 0.5}, "subscription agreement cover: the fund's name -> entity code"),
    ("CNT-SL-DEAR", "partner", "SL-DEAR", {"rx": r"(?im)^\s*Dear\s+(.{2,120}?)\s*[:,]\s*$", "certain": True},
     "side letter: the 'Dear ...' line -> partner code"),
    ("CNT-SL-ADDR", "partner", "SL-ADDR", {"region": 0.45, "certain": False},
     "side letter: a roster name in the address block (lane unless the Dear line agrees)"),
    ("CNT-SL-FUND", "entity", "SL-FUND", {"region": 0.6}, "side letter page 1: the fund's name -> entity code"),
    ("CNT-ALL-TIN", "tin_presence", "TIN", {"rx": TIN_RX}, "R-037: a TIN pattern on page 1 -> Handling Contains Tax ID (presence only)"),
]
RULE_IDS = [r[0] for r in CNT_RULES]


def seed_rules(con, log=print):
    """Upsert CNT-* rules (provisional rows only; a ruled or vetoed row is never touched again, as the R-032 seed)."""
    cur = con.cursor()
    n = 0
    for rid, field, anchor, spec, note in CNT_RULES:
        for k, v in spec.items():
            if isinstance(v, str) and k in ("rx", "start", "end", "label", "with"):
                re.compile(v)
        spec = dict(spec); spec.setdefault("mode", "apply")
        cur.execute("""INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, provisional)
                       VALUES (%s, 1, %s, 'content', %s, %s, 50, true, %s, true)
                       ON CONFLICT (rule_id, version) DO UPDATE SET field=EXCLUDED.field, pattern=EXCLUDED.pattern, value=EXCLUDED.value,
                         notes=EXCLUDED.notes WHERE ops.decomposition_rule.provisional""", (rid, field, json.dumps(spec), anchor, note))
        n += cur.rowcount
    cur.execute("DELETE FROM ops.decomposition_rule WHERE applies_to='content' AND provisional AND NOT (rule_id = ANY(%s))", (RULE_IDS,))
    con.commit()
    log(f"content rules seeded: {n} upserted (provisional only), {cur.rowcount} stale provisional removed; {len(RULE_IDS)} in the seed")


def load_rules(cur):
    """{rule_id: dict(field, anchor, spec, active, mode)} from the newest version of each CNT rule; seed defaults for rules
    not yet in the table (offline / tests). A vetoed rule (active = false) is returned with active False and never used."""
    out = {rid: dict(field=f, anchor=a, spec=dict(s, mode=s.get("mode", "apply")), active=True) for rid, f, a, s, _ in CNT_RULES}
    if cur is not None:
        cur.execute("""SELECT DISTINCT ON (rule_id) rule_id, field, value, pattern, active FROM ops.decomposition_rule
                       WHERE applies_to = 'content' ORDER BY rule_id, version DESC""")
        for rid, field, anchor, pattern, active in cur.fetchall():
            try:
                spec = json.loads(pattern)
            except (TypeError, ValueError):
                continue
            out[rid] = dict(field=field, anchor=anchor, spec=dict(spec, mode=spec.get("mode", "apply")), active=bool(active))
    for r in out.values():
        r["mode"] = r["spec"]["mode"]
    return out


def set_review_only(con, rule_ids, log=print):
    """R-038 (< 97% precision on the sample): a new version of each rule with mode review_only (it feeds the lane only)."""
    cur = con.cursor()
    for rid in rule_ids:
        cur.execute("""INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, provisional)
                       SELECT rule_id, version + 1, field, applies_to, (pattern::jsonb || '{"mode": "review_only"}')::text, value, priority,
                              active, notes || ' [review-only: under 97%% precision on the sample]', provisional
                       FROM ops.decomposition_rule WHERE rule_id = %s AND applies_to = 'content'
                       ORDER BY version DESC LIMIT 1
                       ON CONFLICT DO NOTHING""", (rid,))
    con.commit()
    log(f"review-only: {', '.join(rule_ids) or 'none'}")


# ------------------------------------------------------------------ text model (pure)
class Line:
    __slots__ = ("text", "x0", "y0", "x1", "y1")

    def __init__(self, text, x0, y0, x1, y1):
        self.text, self.x0, self.y0, self.x1, self.y1 = text, x0, y0, x1, y1

    def __repr__(self):            # never the text (R-033): a Line in a traceback shows its box only
        return f"Line(box={self.x0:.0f},{self.y0:.0f},{self.x1:.0f},{self.y1:.0f})"


class Page:
    """A page's lines with boxes in points, its height, and whether the text came from OCR. Held in memory only."""
    __slots__ = ("lines", "width", "height", "ocr", "chars")

    def __init__(self, lines, width, height, ocr=False):
        self.lines = sorted(lines, key=lambda l: (round(l.y0, 0), l.x0))
        self.width, self.height, self.ocr = width, height, ocr
        self.chars = sum(len(l.text) for l in lines)

    def __repr__(self):
        return f"Page(lines={len(self.lines)}, ocr={self.ocr})"

    def region(self, frac):
        return [l for l in self.lines if l.y1 <= self.height * frac + 1]

    def text(self, frac=None):
        return "\n".join(l.text for l in (self.region(frac) if frac else self.lines))


def norm(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# "the", trust suffixes, "dtd ...", legal forms: dropped for a NORMALISED (medium) match
NORM_DROP = set("""the llc l c lp p llp inc incorporated ltd limited corp corporation co company trust trustee trustees ttee tr dtd
dated ua u a fbo revocable irrevocable living as of""".split())
DATE_TAIL = re.compile(r"\b(dtd|dated|u a|ua)\b.*$")


def norm_loose(s):
    s = norm(s)
    s = DATE_TAIL.sub("", s)
    return " ".join(t for t in s.split() if t not in NORM_DROP and not t.isdigit())


def window_after(page, start_rx, end_rx=None, max_dy=70, col_tol=30):
    """Lines in the box under the anchor line (same column), up to the end anchor. -> (anchor Line|None, [Line])."""
    srx = re.compile(start_rx)
    erx = re.compile(end_rx, re.M) if end_rx else None
    anchor = next((l for l in page.lines if srx.search(l.text)), None)
    if anchor is None:
        # a form label split over two or three text lines (PDF form fields often are): join neighbours on the page
        L = page.lines
        for i in range(len(L)):
            for j in (i + 1, i + 2):
                if j < len(L) and abs(L[j].y0 - L[i].y0) < 24 and srx.search(" ".join(l.text for l in L[i:j + 1])):
                    seg = L[i:j + 1]
                    anchor = Line(" ".join(l.text for l in seg), min(l.x0 for l in seg), min(l.y0 for l in seg),
                                  max(l.x1 for l in seg), max(l.y1 for l in seg))
                    break
            if anchor is not None:
                break
        if anchor is None:
            return None, []
    col_w = max(anchor.x1 - anchor.x0, page.width * 0.35)
    out = []
    for l in page.lines:
        if l is anchor or l.y0 < anchor.y1 - 2 or l.y0 > anchor.y1 + max_dy:
            continue
        if l.x0 < anchor.x0 - col_tol or l.x0 > anchor.x0 + col_w:
            continue
        if erx and erx.search(l.text):
            break
        out.append(l)
    tail = srx.split(anchor.text, maxsplit=1)[-1] if srx.groups == 0 else ""
    if tail and len(norm(tail)) > 3 and not re.search(r"(?i)see\s+instructions|entered\s+in", tail):
        out.insert(0, Line(tail, anchor.x0, anchor.y0, anchor.x1, anchor.y1))
    return anchor, out


def label_values(page, label_rx, region=None):
    """For each line holding the label: the text after it on the line, lines to its right at the same height, and the next
    line under it. -> [[Line]] (one window per label hit)."""
    rx = re.compile(label_rx)
    lines = page.region(region) if region else page.lines
    out = []
    for l in lines:
        m = rx.search(l.text)
        if not m:
            continue
        win = []
        tail = l.text[m.end():].strip(" :-_\t")
        if len(norm(tail)) >= 3:
            win.append(Line(tail, l.x0, l.y0, l.x1, l.y1))
        mid = (l.y0 + l.y1) / 2
        win += [o for o in lines if o is not l and o.x0 >= l.x0 and abs((o.y0 + o.y1) / 2 - mid) < 4 and o.x0 > l.x0 + 5]
        below = [o for o in lines if o.y0 > l.y1 - 1 and o.y0 < l.y1 + 22 and o.x1 > l.x0 - 10 and o.x0 < l.x1 + 150]
        if below:
            win.append(min(below, key=lambda o: o.y0))
        out.append(win)
    return out


def find_rx(text, rx):
    m = re.search(rx, text)
    return m


# ------------------------------------------------------------------ name index (pure; names in memory only)
class NameIndex:
    """Partner aliases (ref.party_alias) as token sequences. EXACT = the alias's normalised words, contiguous, inside the
    window; NORMALISED = after dropping 'the', legal forms, trust suffixes and 'dtd ...'. Only specific aliases are kept
    (2+ words, or 1 word of 7+ letters)."""

    def __init__(self, alias_rows, party_rows):
        # alias_rows: (partner_code, alias); party_rows: (entity_code, partner_code, is_company_gp)
        self.roster = collections.defaultdict(set)
        self.gp_rows = set()
        for e, p, g in party_rows:
            if e:
                self.roster[e].add(p)
                if g:
                    self.gp_rows.add((e, p))
        self.exact = collections.defaultdict(list)     # first token -> [(tokens, partner)]
        self.loose = collections.defaultdict(list)
        for p, a in alias_rows:
            for idx, toks in ((self.exact, norm(a).split()), (self.loose, norm_loose(a).split())):
                if len(toks) >= 2 or (len(toks) == 1 and len(toks[0]) >= 7):
                    idx[toks[0]].append((tuple(toks), p))

    @staticmethod
    def _scan(idx, toks):
        hits = set()
        for i, t in enumerate(toks):
            for seq, p in idx.get(t, ()):
                if tuple(toks[i:i + len(seq)]) == seq:
                    hits.add(p)
        return hits

    def match(self, text):
        """-> (exact partners, normalised partners) found in the text."""
        return self._scan(self.exact, norm(text).split()), self._scan(self.loose, norm_loose(text).split())


class EntityIndex:
    """Fund / GP / SPV names (ref.entity name + aliases, ref.entity_alias non-generic, Datum company names) -> entity code.
    The LONGEST name found wins; two different entities at that length -> none."""

    def __init__(self, rows):
        self.idx = collections.defaultdict(list)
        for name, code in rows:
            toks = norm(name).split()
            if code and (len(toks) >= 2 or (len(toks) == 1 and len(toks[0]) >= 4)):
                self.idx[toks[0]].append((tuple(toks), code))

    def match(self, text):
        toks = norm(text).split()
        best, codes = 0, set()
        for i, t in enumerate(toks):
            for seq, c in self.idx.get(t, ()):
                if tuple(toks[i:i + len(seq)]) == seq:
                    if len(seq) > best:
                        best, codes = len(seq), {c}
                    elif len(seq) == best:
                        codes.add(c)
        return next(iter(codes)) if len(codes) == 1 else None


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def parse_date(s):
    s = (s or "").strip().replace(",", " ")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2})\s+(\d{4})$", " ".join(s.split()))
        if not m or m.group(1)[:3].lower() not in MONTHS:
            return None
        mo, d, y = MONTHS[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def period_of(d):
    """calendar fiscal year: period end -> (fy, quarter) for quarter-end dates, else (fy, None)."""
    if d is None:
        return None, None
    q = {3: 1, 6: 2, 9: 3, 12: 4}.get(d.month) if d.day >= 28 else None
    return d.year, q


# ------------------------------------------------------------------ extraction per kind (pure)
class Stmt:
    """One partner statement found in a document: page range, anchor, rule, partner candidates, content fields.
    name_line (the anchor's name text) stays in memory for alias learning; it is never stored except as a person-confirmed
    alias (ref.party_alias, DB only)."""

    def __init__(self, page_from, page_to=None):
        self.page_from, self.page_to = page_from, page_to or page_from
        self.anchor = self.rule = None
        self.certain = False
        self.exact, self.loose = set(), set()
        self.gp_ok = False
        self.entity = self.fy = self.quarter = self.period_end = None
        self.amended = self.final = False
        self.name_line = None
        self.received_by = None        # a K-1 whose partner block names a catalog entity: received BY that entity

    def __repr__(self):
        return f"Stmt(p{self.page_from}-{self.page_to}, {self.anchor}, {sorted(self.exact)}, {sorted(self.loose)})"


def _use(rules, rid):
    r = rules.get(rid)
    return r if r and r["active"] else None


def _partner_from(stmt, win_lines, names, rule_id, rules, certain=None):
    r = _use(rules, rule_id)
    if not r or not win_lines:
        return False
    text = "\n".join(l.text for l in win_lines)
    ex, lo = names.match(text)
    if not ex and not lo:
        if stmt.name_line is None:
            stmt.name_line = win_lines[0].text
        if stmt.anchor is None and any(k in r["spec"] for k in ("start", "label", "rx")):
            stmt.anchor, stmt.rule = r["anchor"], rule_id     # the anchor was found; no roster name in it
        return False
    stmt.exact, stmt.loose = ex, lo
    stmt.anchor, stmt.rule = r["anchor"], rule_id
    stmt.certain = r["spec"].get("certain", False) if certain is None else certain
    stmt.gp_ok = bool(r["spec"].get("gp_rows"))
    stmt.name_line = win_lines[0].text
    return True


def k1_starts(pages, rules):
    r = _use(rules, "CNT-K1-HDR")
    if not r:
        return [1] if pages else []
    rx, wx, reg = re.compile(r["spec"]["rx"]), re.compile(r["spec"]["with"]), r["spec"].get("region", 0.3)
    out = [i + 1 for i, p in enumerate(pages) if p is not None and rx.search(p.text(reg)) and wx.search(p.text())]
    return out or ([1] if pages and pages[0] is not None else [])


def extract_k1(pages, names, ents, rules):
    starts = k1_starts(pages, rules)
    out = []
    for n, s in enumerate(starts):
        p = pages[s - 1]
        st = Stmt(s, (starts[n + 1] - 1) if n + 1 < len(starts) else len(pages))
        r = _use(rules, "CNT-K1-PII")
        if r:
            _, win = window_after(p, r["spec"]["start"], r["spec"].get("end"), r["spec"].get("max_dy", 70))
            if not _partner_from(st, win, names, "CNT-K1-PII", rules) and win:
                st.received_by = ents.match("\n".join(l.text for l in win))   # e.g. a portfolio K-1 issued TO an Allegis fund
        r = _use(rules, "CNT-K1-PI")
        if r:
            _, win = window_after(p, r["spec"]["start"], r["spec"].get("end"), r["spec"].get("max_dy", 70))
            st.entity = ents.match("\n".join(l.text for l in win)) if win else None
        r = _use(rules, "CNT-K1-YEAR")
        if r:
            m = re.search(r["spec"]["rx"], p.text(r["spec"].get("region")))
            if m:
                y = next(g for g in m.groups() if g)
                st.fy = int(y)
        for rid, attr in (("CNT-K1-AMENDED", "amended"), ("CNT-K1-FINAL", "final")):
            r = _use(rules, rid)
            if r and re.search(r["spec"]["rx"], p.text(r["spec"].get("region"))):
                setattr(st, attr, True)
        out.append(st)
    return out


def pcap_starts(pages, rules):
    r = _use(rules, "CNT-PCAP-TITLE")
    if not r:
        return [1] if pages else []
    rx, reg = re.compile(r["spec"]["rx"]), r["spec"].get("region", 0.3)
    out = [i + 1 for i, p in enumerate(pages) if p is not None and rx.search(p.text(reg))]
    return out or ([1] if pages and pages[0] is not None else [])


def extract_pcap(pages, names, ents, rules):
    starts = pcap_starts(pages, rules)
    out = []
    for n, s in enumerate(starts):
        p = pages[s - 1]
        st = Stmt(s, (starts[n + 1] - 1) if n + 1 < len(starts) else len(pages))
        r = _use(rules, "CNT-PCAP-PARTNER")
        found = False
        if r:
            for win in label_values(p, r["spec"]["label"], r["spec"].get("region")):
                if _partner_from(st, win, names, "CNT-PCAP-PARTNER", rules):
                    found = True; break
        r = _use(rules, "CNT-PCAP-TOP")
        if not found and r:
            _partner_from(st, p.region(r["spec"].get("region", 0.3)), names, "CNT-PCAP-TOP", rules)
        r = _use(rules, "CNT-PCAP-PERIOD")
        if r:
            m = re.search(r["spec"]["rx"], p.text(r["spec"].get("region")))
            if m:
                st.period_end = parse_date(next((g for g in m.groups() if g), None))
                st.fy, st.quarter = period_of(st.period_end)
        r = _use(rules, "CNT-PCAP-FUND")
        if r:
            st.entity = ents.match(p.text(r["spec"].get("region", 0.3)))
        out.append(st)
    return out


def sig_pages(pages, rules):
    r = _use(rules, "CNT-SUB-SIG")
    if not r:
        return []
    rx = re.compile(r["spec"]["rx"])
    n = len(pages)
    cands = [i + 1 for i in range(max(1, n - SIG_PAGES), n) if i > 0 and pages[i] is not None and rx.search(pages[i].text())]
    return cands[-SIG_MAX:]


def extract_sub(pages, names, ents, rules):
    st = Stmt(1, len(pages))
    look = [1] + sig_pages(pages, rules)
    r = _use(rules, "CNT-SUB-LBL")
    found = False
    if r:
        for pn in look:
            p = pages[pn - 1]
            if p is None:
                continue
            for win in label_values(p, r["spec"]["label"]):
                if _partner_from(st, win, names, "CNT-SUB-LBL", rules):
                    found = True; break
            if found:
                st.page_from = st.page_to = pn
                break
    r = _use(rules, "CNT-SUB-TOP")
    if not found and r:
        for pn in look:
            p = pages[pn - 1]
            if p is not None and _partner_from(st, p.lines, names, "CNT-SUB-TOP", rules):
                st.page_from = st.page_to = pn
                break
    r = _use(rules, "CNT-SUB-FUND")
    if r and pages and pages[0] is not None:
        st.entity = ents.match(pages[0].text(r["spec"].get("region", 0.5)))
    return [st]


def extract_sl(pages, names, ents, rules):
    st = Stmt(1, len(pages))
    p = pages[0] if pages else None
    if p is None:
        return [st]
    r = _use(rules, "CNT-SL-DEAR")
    found = False
    if r:
        m = re.search(r["spec"]["rx"], p.text())
        if m:
            found = _partner_from(st, [Line(m.group(1), 0, 0, 0, 0)], names, "CNT-SL-DEAR", rules)
    r = _use(rules, "CNT-SL-ADDR")
    if not found and r:
        _partner_from(st, p.region(r["spec"].get("region", 0.45)), names, "CNT-SL-ADDR", rules)
    r = _use(rules, "CNT-SL-FUND")
    if r:
        st.entity = ents.match(p.text(r["spec"].get("region", 0.6)))
    return [st]


EXTRACT = {"k1": extract_k1, "capital_statement": extract_pcap, "subscription_agreement": extract_sub, "side_letter": extract_sl}


def tin_present(page, rules):
    r = _use(rules, "CNT-ALL-TIN")
    return bool(r and page is not None and re.search(r["spec"]["rx"], page.text()))


# ------------------------------------------------------------------ R-036 classification (pure)
def classify(st, roster_entities, names, rules):
    """-> [(partner|None, roster entity|None, confidence, reason)] for one statement.
    high   : one EXACT roster partner inside a certain anchor of an apply-mode rule
    medium : a normalised match, an uncertain anchor, or a review-only rule  -> Match subject lane
    low    : NOT_IN_FUND (a partner of another fund's roster) / MULTIPLE / NO_ROSTER_MATCH"""
    roster = {}
    for e in sorted(roster_entities):
        for p in names.roster.get(e, ()):
            if (e, p) in names.gp_rows and not st.gp_ok:
                continue                                    # the fund's own GP row: only from a K-1's partner block
            roster.setdefault(p, e)
    if not st.exact and not st.loose:
        if st.received_by:
            return [(None, None, "none", None)]               # received by a catalog entity: not a roster document, not in the lane
        return [(None, None, "none", "NO_ROSTER_MATCH")]
    review_only = (rules.get(st.rule) or {}).get("mode") == "review_only"
    ex_in = sorted(p for p in st.exact if p in roster)
    lo_in = sorted(p for p in st.loose if p in roster and p not in ex_in)
    out_fund = sorted((st.exact | st.loose) - set(roster))
    if len(ex_in) == 1 and not lo_in:
        conf = "high" if (st.certain and not review_only) else "medium"
        return [(ex_in[0], roster[ex_in[0]], conf, None)]
    if len(ex_in) + len(lo_in) > 1:
        return [(p, roster[p], "low", "MULTIPLE") for p in (ex_in + lo_in)[:6]]
    if len(ex_in) + len(lo_in) == 1:
        p = (ex_in + lo_in)[0]
        return [(p, roster[p], "medium", None)]
    if not roster:
        return [(p, None, "low", "NO_ROSTER_MATCH") for p in out_fund[:6]]
    return [(p, None, "low", "NOT_IN_FUND") for p in out_fund[:6]]


# ------------------------------------------------------------------ reading (download to memory, PyMuPDF, local OCR)
def tesseract_exe():
    for c in (shutil.which("tesseract"), r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if c and os.path.exists(c):
            return c
    return None


def ocr_lines(png, exe, scale):
    """Tesseract through a pipe (stdin -> TSV on stdout): no file is written. scale: points per pixel. -> [Line]"""
    p = subprocess.run([exe, "stdin", "stdout", "-l", "eng", "--psm", "3", "tsv"], input=png, capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError("ocr failed")
    words = collections.defaultdict(list)
    for row in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5" or not c[11].strip():
            continue
        try:
            key = (int(c[2]), int(c[3]), int(c[4]))
            words[key].append((int(c[6]), int(c[7]), int(c[8]), int(c[9]), c[11]))
        except ValueError:
            continue
    out = []
    for ws in words.values():
        ws.sort()
        x0 = min(w[0] for w in ws); y0 = min(w[1] for w in ws)
        x1 = max(w[0] + w[2] for w in ws); y1 = max(w[1] + w[3] for w in ws)
        out.append(Line(" ".join(w[4] for w in ws), x0 * scale, y0 * scale, x1 * scale, y1 * scale))
    del p
    return out


def text_page(fpage):
    lines = collections.defaultdict(list)
    for x0, y0, x1, y1, w, b, ln, wn in fpage.get_text("words"):
        lines[(b, ln)].append((x0, y0, x1, y1, w))
    out = []
    for ws in lines.values():
        out.append(Line(" ".join(w[4] for w in ws), min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws)))
    return Page(out, fpage.rect.width, fpage.rect.height)


class Reader:
    """Opens one PDF from bytes and hands out pages (text layer first, OCR when the page has none). Counts OCR use."""

    def __init__(self, data, ocr_exe):
        import pymupdf as fitz
        self.doc = fitz.open(stream=data, filetype="pdf")
        self.exe = ocr_exe
        self.ocr_used = self.ocr_missing = False
        self.ocr_pages = 0
        self.text_layer = None
        self.cache = {}

    @property
    def n(self):
        return self.doc.page_count

    def page(self, i, top=None):
        """i: 1-based. top: fraction of the page to OCR when OCR is needed (cheaper for header scans). None when unreadable."""
        key = (i, top)
        if key in self.cache:
            return self.cache[key]
        if (i, None) in self.cache:
            return self.cache[(i, None)]
        fp = self.doc.load_page(i - 1)
        pg = text_page(fp)
        if i == 1:
            self.text_layer = pg.chars >= TEXT_MIN
        if pg.chars < TEXT_MIN:
            if not self.exe:
                self.ocr_missing = True; pg = None
            elif self.ocr_pages >= OCR_PAGE_CAP:
                self.ocr_missing = True; pg = None
            else:
                import pymupdf as fitz
                dpi = OCR_TOP_DPI if top else OCR_DPI
                clip = fitz.Rect(0, 0, fp.rect.width, fp.rect.height * top) if top else None
                pix = fp.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY)
                png = pix.tobytes("png"); del pix
                try:
                    pg = Page(ocr_lines(png, self.exe, 72.0 / dpi), fp.rect.width, fp.rect.height, ocr=True)
                    self.ocr_used = True; self.ocr_pages += 1
                except Exception:
                    pg = None; self.ocr_missing = True
                del png
        self.cache[key] = pg
        return pg

    def close(self):
        self.cache.clear()
        self.doc.close()


def pages_for(reader, kind):
    """The pages each kind needs (order 'What is read, per kind'); others are None."""
    n = reader.n
    pages = [None] * n
    if n == 0:
        return pages
    if kind in ("k1", "capital_statement") and n > 1:
        # bundles / packages: the top region of every page to find statement starts, then that page in full
        for i in range(1, n + 1):
            pages[i - 1] = reader.page(i, top=0.35)
        starts = (k1_starts if kind == "k1" else pcap_starts)(pages, RULES_FOR_PAGES[0])
        for s in starts:
            if pages[s - 1] is not None and pages[s - 1].ocr:
                pages[s - 1] = reader.page(s)                      # the full page for the partner / Part I anchors
            elif kind == "k1" and pages[s - 1] is not None:
                pages[s - 1] = reader.page(s)
    else:
        pages[0] = reader.page(1)
        if kind == "subscription_agreement":
            for i in range(max(2, n - SIG_PAGES + 1), n + 1):
                pages[i - 1] = reader.page(i)
    return pages


RULES_FOR_PAGES = [None]        # the run's rules, for pages_for (set by read_document)


def read_document(data, kind, names, ents, rules, roster_entities, ocr_exe):
    """-> dict(outcome, page_count, pages_read, text_layer, ocr_used, statements=[(Stmt, [classified])], tin, lp_pii)."""
    RULES_FOR_PAGES[0] = rules
    try:
        rd = Reader(data, ocr_exe)
    except Exception:
        return dict(outcome="open_error")
    try:
        if rd.doc.needs_pass:
            return dict(outcome="encrypted", page_count=None)
        pages = pages_for(rd, kind)
        stmts = EXTRACT[kind](pages, names, ents, rules) if any(p is not None for p in pages) else []
        res = []
        lp_pii = False
        for st in stmts:
            ents_for = set(roster_entities) or ({st.entity} if st.entity else set())
            cl = classify(st, ents_for, names, rules)
            lp_pii = lp_pii or any(p and e for p, e, c, r in cl)
            res.append((st, cl))
        pages_read = sum(1 for p in pages if p is not None)
        if not stmts or all(p is None for p in pages):
            outcome = "ocr_needed" if rd.ocr_missing else "no_anchor"
        elif all(st.anchor is None for st in stmts):
            outcome = "ocr_partial" if rd.ocr_missing else "no_anchor"
        else:
            outcome = "ocr_partial" if rd.ocr_missing else "ok"
        return dict(outcome=outcome, page_count=rd.n, pages_read=pages_read, text_layer=bool(rd.text_layer),
                    ocr_used=rd.ocr_used, statements=res, tin=tin_present(pages[0] if pages else None, rules), lp_pii=lp_pii)
    finally:
        rd.close()


# ------------------------------------------------------------------ Drive (read-only) and the network guard
ALLOWED_HOSTS = re.compile(r"(^|\.)(googleapis\.com|neon\.tech|google\.com)$")


def net_guard():
    """Audit hook: any socket connect / name lookup to a host other than the Google APIs (Drive + its token endpoint) or
    Neon raises. Installed by the CLI and the measure (guard test G-N1); it cannot be removed for the process."""
    def hook(event, args):
        if event == "socket.getaddrinfo":
            host = args[0]
            if isinstance(host, bytes): host = host.decode("ascii", "replace")
            if host and not re.match(r"^[\d.:]+$", str(host)) and not ALLOWED_HOSTS.search(str(host).rstrip(".")):
                raise PermissionError(f"CAT-WO-06 net guard: connection to a host outside Google APIs / Neon refused")
    sys.addaudithook(hook)


def download(svc, file_id, mime, size):
    """Bytes in memory. Google Docs are exported to PDF. No file is written."""
    from googleapiclient.http import MediaIoBaseDownload
    if mime == GDOC:
        req = svc.files().export_media(fileId=file_id, mimeType=PDF)
    else:
        if size and size > MAX_BYTES:
            return None
        req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req, chunksize=8 * 2**20)
    done = False
    while not done:
        _, done = dl.next_chunk(num_retries=5)
        if buf.tell() > MAX_BYTES:
            return None
    return buf.getvalue()


def clean_temp():
    """%TEMP%\\catwo06 is emptied before and after every run (the reader writes nothing there; the guard checks it)."""
    if os.path.isdir(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            try:
                p = os.path.join(TEMP_DIR, f)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass
    else:
        os.makedirs(TEMP_DIR, exist_ok=True)


# ------------------------------------------------------------------ DB
SCOPE_SQL = """
WITH d AS (
  SELECT d.document_id, coalesce(d.kind_confirmed, d.kind_auto) AS kind
  FROM cat.document d WHERE coalesce(d.kind_confirmed, d.kind_auto) = ANY(%(kinds)s)
), f AS (
  SELECT DISTINCT ON (fd.document_id) fd.document_id, f.file_id, f.mime_type, f.size_bytes,
         coalesce(f.md5, 'rev:' || coalesce(f.head_revision_id, f.modified_time::text)) AS version_key, f.drive_name,
         greatest(f.modified_time, f.created_time) AS fresh,
         (fd.file_role = 'primary') AS is_primary
  FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
  WHERE fd.document_id IN (SELECT document_id FROM d) AND f.removed_run IS NULL AND f.trashed IS NOT TRUE
    AND f.is_shortcut IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret' AND f.noise_flag IS NOT TRUE
  ORDER BY fd.document_id, (fd.file_role = 'primary') DESC, (f.mime_type = 'application/pdf') DESC, f.file_id
)
SELECT d.document_id, d.kind, f.file_id, f.mime_type, f.size_bytes, f.version_key, f.drive_name, f.is_primary, f.fresh
FROM d LEFT JOIN f USING (document_id)
"""


def scope(cur):
    cur.execute(SCOPE_SQL, {"kinds": list(KINDS)})
    return [dict(zip(["document_id", "kind", "file_id", "mime", "size", "version_key", "drive", "is_primary", "fresh"], r)) for r in cur.fetchall()]


def fmt_of(mime):
    if mime == PDF: return "pdf"
    if mime == GDOC: return "gdoc"
    if mime and WORD_EXCEL.search(mime): return "word_excel"
    if mime and mime.startswith("image/"): return "image"
    return "other" if mime else "no_file"


def to_read(cur, docs, incremental):
    """documents whose (version_key, extractor_version) is not read yet, plus person-picked lane documents (alias learning)."""
    cur.execute("SELECT document_id, md5, extractor_version, read_at FROM cat.doc_page_read")
    done = {d: (m, v, at) for d, m, v, at in cur.fetchall()}
    cur.execute("""SELECT DISTINCT e.document_id FROM app.review_event e JOIN cat.doc_page_read r ON r.document_id = e.document_id
                   WHERE e.source = 'match_subject' AND e.edits ? 'subject_codes' AND e.created_at > r.read_at
                     AND EXISTS (SELECT 1 FROM cat.doc_content_match m WHERE m.document_id = e.document_id AND m.confidence <> 'high')""")
    learn = {r[0] for r in cur.fetchall()}
    out = []
    for d in docs:
        if fmt_of(d["mime"]) not in ("pdf", "gdoc"):
            continue
        prev = done.get(d["document_id"])
        if prev and prev[0] == d["version_key"] and prev[1] == EXTRACTOR_VERSION and d["document_id"] not in learn:
            continue
        out.append(dict(d, learn=d["document_id"] in learn))
    # CAT-WO-06.1: person-picked lane documents first, then NEW or CHANGED documents (newest first), then the backlog
    # (never read, older first). A document read before whose md5 changed counts as changed.
    for d in out:
        prev = done.get(d["document_id"])
        d["changed"] = bool(prev) and prev[0] != d["version_key"]
    out.sort(key=fresh_key)
    return out, learn


def fresh_key(d, now=None):
    """sort key: lane learning first; then documents created / modified in the last 14 days or changed since their read,
    newest first; then the never-read backlog, oldest document first (stable over nights)."""
    import datetime as _dt
    now = now or _dt.datetime.now(_dt.timezone.utc)
    f = d.get("fresh")
    recent = bool(d.get("changed")) or (f is not None and (now - f).days < 14)
    return (not d.get("learn"), not recent, -(f.timestamp() if (recent and f) else 0), d["document_id"])


def roster_entities(cur, ids):
    """document -> entities (person-set entities, else file entities) plus the issuing entity."""
    out = collections.defaultdict(set)
    cur.execute("""SELECT d.document_id, unnest(coalesce(d.entities_confirmed, '{}')) FROM cat.document d WHERE d.document_id = ANY(%s)
                   UNION SELECT d.document_id, coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto) FROM cat.document d
                   WHERE d.document_id = ANY(%s) AND coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto) IS NOT NULL""", (ids, ids))
    for d, e in cur.fetchall():
        if e: out[d].add(e)
    cur.execute("SELECT document_id FROM cat.document WHERE document_id = ANY(%s) AND entities_confirmed IS NOT NULL", (ids,))
    conf = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT fd.document_id, e.entity_code FROM cat.file_document fd JOIN cat.v_file_entity e ON e.file_id = fd.file_id
                   WHERE fd.document_id = ANY(%s) AND NOT coalesce(e.from_generic_only, false)""", (ids,))
    for d, e in cur.fetchall():
        if d not in conf and e: out[d].add(e)
    return out


def load_indexes(cur):
    cur.execute("SELECT DISTINCT entity_code, partner_code, is_company_gp FROM ref.party WHERE entity_code IS NOT NULL")
    party = cur.fetchall()
    cur.execute("SELECT partner_code, alias FROM ref.party_alias")
    names = NameIndex(cur.fetchall(), party)
    cur.execute("""SELECT alias, entity_code FROM ref.entity_alias WHERE NOT coalesce(generic, false)
                   UNION SELECT name, entity_code FROM ref.entity WHERE active IS NOT FALSE
                   UNION SELECT datum_company_name, entity_code FROM ref.party WHERE entity_code IS NOT NULL""")
    ents = EntityIndex(cur.fetchall())
    return names, ents


def write_batch(con, results):
    """results: [(doc row, read dict)] -> cat.doc_page_read, cat.doc_content_match, cat.doc_content_check (codes only)."""
    cur = con.cursor()
    for d, r in results:
        did = d["document_id"]
        stmts = r.get("statements") or []
        cur.execute("""INSERT INTO cat.doc_page_read (document_id, md5, page_count, pages_read, text_layer, ocr_used, extractor_version,
                                                      outcome, statements, tin_present, lp_pii, read_ms, read_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                       ON CONFLICT (document_id) DO UPDATE SET md5=EXCLUDED.md5, page_count=EXCLUDED.page_count, pages_read=EXCLUDED.pages_read,
                         text_layer=EXCLUDED.text_layer, ocr_used=EXCLUDED.ocr_used, extractor_version=EXCLUDED.extractor_version,
                         outcome=EXCLUDED.outcome, statements=EXCLUDED.statements, tin_present=EXCLUDED.tin_present, lp_pii=EXCLUDED.lp_pii,
                         read_ms=EXCLUDED.read_ms, read_at=now()""",
                    (did, d["version_key"], r.get("page_count"), r.get("pages_read"), r.get("text_layer"), bool(r.get("ocr_used")),
                     EXTRACTOR_VERSION, r["outcome"], len(stmts), bool(r.get("tin")), bool(r.get("lp_pii")), r.get("ms")))
        cur.execute("DELETE FROM cat.doc_content_match WHERE document_id = %s", (did,))
        rows, seq = [], 0
        for st, cl in stmts:
            seq += 1
            for cand, (p, e, conf, reason) in enumerate(cl, 1):
                rows.append((did, seq, cand, st.page_from, st.page_to, st.anchor if st.anchor and ANCHOR_RE.match(st.anchor) else None,
                             st.rule, p if p and CODE_RE.match(p) else None, e, st.entity, conf, reason))
        if rows:
            cur.executemany("""INSERT INTO cat.doc_content_match (document_id, seq, cand, page_from, page_to, anchor, rule_id, partner_code,
                                   roster_entity, content_entity, confidence, reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
        # content-derived fields: the first statement's FY / quarter / period end / entity (a package carries one period)
        fy = next((st.fy for st, _ in stmts if st.fy), None)
        q = next((st.quarter for st, _ in stmts if st.quarter), None)
        pe = next((st.period_end for st, _ in stmts if st.period_end), None)
        ents = sorted({st.entity for st, _ in stmts if st.entity})
        amended = any(st.amended for st, _ in stmts)
        if stmts or r["outcome"] in ("ok", "no_anchor", "ocr_partial"):
            cur.execute("""INSERT INTO cat.doc_content_check (document_id, file_id, checked_at, content_fiscal_year, content_quarter,
                                  content_period_end, content_entity, content_amended, content_read_at)
                           VALUES (%s, %s, now(), %s, %s, %s, %s, %s, now())
                           ON CONFLICT (document_id) DO UPDATE SET content_fiscal_year=EXCLUDED.content_fiscal_year,
                             content_quarter=EXCLUDED.content_quarter, content_period_end=EXCLUDED.content_period_end,
                             content_entity=EXCLUDED.content_entity, content_amended=EXCLUDED.content_amended, content_read_at=now()""",
                        (did, d["file_id"], fy, q, pe, ents[0] if len(ents) == 1 else None, amended))
    con.commit()


def learn_aliases(con, learned):
    """'Corrections stick': for a document a person matched in the lane, the anchor's name text becomes an alias of the code
    the person picked (ref.party_alias, source 'lane'; DB only, never logged). learned: [(document_id, [name lines])]."""
    if not learned:
        return 0
    cur = con.cursor()
    cur.execute("""SELECT DISTINCT ON (document_id) document_id, edits -> 'subject_codes' FROM app.review_event
                   WHERE source = 'match_subject' AND document_id = ANY(%s) AND edits ? 'subject_codes' ORDER BY document_id, event_id DESC""",
                ([d for d, _ in learned],))
    picked = {d: [c for c in (v or []) if isinstance(c, str) and CODE_RE.match(c)] for d, v in cur.fetchall()}
    n = 0
    for did, lines in learned:
        codes = picked.get(did) or []
        if len(codes) != 1:
            continue                                      # a multi-code pick can't say which name belongs to which code
        for ln in lines:
            ln = " ".join((ln or "").split())[:120]
            if len(norm(ln).split()) < 2:
                continue
            cur.execute("INSERT INTO ref.party_alias (partner_code, alias, source) VALUES (%s, %s, 'lane') ON CONFLICT DO NOTHING", (codes[0], ln))
            n += cur.rowcount
    con.commit()
    return n


def mem_mb():
    try:
        import ctypes, ctypes.wintypes as w
        class PMC(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                        ("d", ctypes.c_size_t), ("e", ctypes.c_size_t), ("f", ctypes.c_size_t)]
        c = PMC(); c.cb = ctypes.sizeof(PMC)
        k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = w.HANDLE
        ps = ctypes.windll.psapi; ps.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]
        ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return round(c.WorkingSetSize / 2**20), round(c.PeakWorkingSetSize / 2**20)
    except Exception:
        return 0, 0


def run(con, svc, incremental=True, limit=None, apply=True, log=print, only_ids=None, connect=None):
    """Read in-scope documents not read yet (or changed), in batches of BATCH; write codes only. Returns counters."""
    clean_temp()
    t0 = time.time()
    cur = con.cursor()
    rules = load_rules(cur)
    docs = scope(cur)
    todo, learn = to_read(cur, docs, incremental)
    if only_ids is not None:
        todo = [d for d in todo if d["document_id"] in set(only_ids)]
    backlog = 0
    if limit is not None and len(todo) > limit:
        backlog = len(todo) - limit
        todo = todo[:limit]
    names, ents = load_indexes(cur)
    exe = tesseract_exe()
    con.commit()
    c = collections.Counter()
    by_kind = collections.defaultdict(collections.Counter)
    learned_total = 0
    last_ping = time.time()
    try:
        for b0 in range(0, len(todo), BATCH):
            batch = todo[b0:b0 + BATCH]
            rents = roster_entities(cur, [d["document_id"] for d in batch])
            con.commit()
            results, learned = [], []
            for d in batch:
                t1 = time.time()
                if t1 - last_ping > 60:            # keep the session (and a Neon compute) alive through a long read
                    try:
                        con.execute("SELECT 1"); con.commit()
                    except Exception:
                        if connect is None: raise
                        con = connect(); cur = con.cursor()
                    last_ping = t1
                if not d["file_id"]:
                    r = dict(outcome="no_file")
                else:
                    try:
                        data = download(svc, d["file_id"], d["mime"], d["size"])
                    except Exception:
                        data = False
                    if data is None:
                        r = dict(outcome="too_large")
                    elif data is False:
                        r = dict(outcome="download_error")
                    else:
                        r = read_document(data, d["kind"], names, ents, rules, rents.get(d["document_id"], set()), exe)
                    del data
                r["ms"] = round((time.time() - t1) * 1000)
                c[r["outcome"]] += 1
                by_kind[d["kind"]][r["outcome"]] += 1
                for st, cl in r.get("statements") or []:
                    for p, e, conf, reason in cl:
                        by_kind[d["kind"]][f"cand:{conf}"] += 1
                        if reason: by_kind[d["kind"]][f"reason:{reason}"] += 1
                if d.get("learn"):
                    learned.append((d["document_id"], [st.name_line for st, _ in (r.get("statements") or []) if st.name_line]))
                for st, _ in r.get("statements") or []:
                    st.name_line = None if not d.get("learn") else st.name_line
                results.append((d, r))
            if apply:
                try:
                    write_batch(con, results)
                except Exception:
                    if connect is None: raise
                    try: con.close()
                    except Exception: pass
                    con = connect(); cur = con.cursor()     # the session was dropped during the read: write on a new one
                    write_batch(con, results)
                learned_total += learn_aliases(con, learned)
            for _, r in results:
                for st, _ in r.get("statements") or []:
                    st.name_line = None
            del results, learned
            log(f"  pages batch {b0 // BATCH + 1}: {min(b0 + BATCH, len(todo)):,}/{len(todo):,} read · memory peak {mem_mb()[1]} MB")
    finally:
        clean_temp()
    secs = time.time() - t0
    c["read"] = len(todo); c["backlog"] = backlog; c["learned_aliases"] = learned_total
    log(f"PAGES {'APPLIED' if apply else 'DRY RUN (nothing written)'}: in scope {len(docs):,} · read {len(todo):,} · backlog {backlog:,} · "
        f"OCR {'available' if exe else 'NOT installed'} · {secs:.0f}s · " + " · ".join(f"{k} {v:,}" for k, v in sorted(c.items()) if k in OUTCOMES))
    for k in sorted(by_kind):
        log(f"    {k:24} " + "  ".join(f"{o}={n:,}" for o, n in sorted(by_kind[k].items())))
    return c, by_kind, secs


# ------------------------------------------------------------------ content check (fill blanks; disagreements -> lane)
def apply_content(con, apply=True, log=print):
    """Content FY / quarter fill BLANK machine fields (never a person's); a disagreement with the document's current value
    is recorded in cat.doc_content_check.content_disagrees (the Content disagrees lane) and never overwritten. Entity is
    checked, not filled (entities come from file signals). Runs inside every derive (cheap SQL)."""
    cur = con.cursor()
    cur.execute("SELECT to_regclass('cat.doc_page_read') IS NOT NULL")
    if not cur.fetchone()[0]:
        return {}
    cur.execute("""
      WITH x AS (
        SELECT c.document_id, c.content_fiscal_year cfy, c.content_quarter cq, c.content_entity ce,
               coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) fy, coalesce(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto) fq,
               coalesce(d.fye_flag_confirmed, d.fye_flag_auto) fye, d.fiscal_year_confirmed, d.fiscal_quarter_confirmed,
               coalesce(d.kind_confirmed, d.kind_auto) kind,
               coalesce(d.entities_confirmed, (SELECT array_agg(DISTINCT e.entity_code) FROM cat.file_document fd
                         JOIN cat.v_file_entity e ON e.file_id = fd.file_id WHERE fd.document_id = d.document_id)) ents,
               coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto) issuing
        FROM cat.doc_content_check c JOIN cat.document d ON d.document_id = c.document_id
        WHERE c.content_read_at IS NOT NULL)
      SELECT document_id, cfy, cq, ce, fy, fq, fye, fiscal_year_confirmed, fiscal_quarter_confirmed, kind, ents, issuing FROM x""")
    fills_fy, fills_q, dis = [], [], {}
    for did, cfy, cq, ce, fy, fq, fye, fyc, fqc, kind, ents, issuing in cur.fetchall():
        d = []
        if cfy is not None:
            if fy is None:
                fills_fy.append((cfy, did))
            elif fy != cfy:
                d.append("fiscal_year")
        if cq is not None and kind == "capital_statement":
            cur_q = fq if fq is not None else (4 if fye else None)
            if cur_q is None and fqc is None:
                fills_q.append((cq, did))
            elif cur_q is not None and cur_q != cq:
                d.append("period")
        if ce is not None:
            have = set(ents or []) | ({issuing} if issuing else set())
            if have and ce not in have:
                d.append("entity")
        dis[did] = d or None
    if apply:
        cur.executemany("""UPDATE cat.document SET fiscal_year_auto=%s, updated_at=now() WHERE document_id=%s AND fiscal_year_confirmed IS NULL
                           AND fiscal_year_auto IS NULL""", fills_fy)
        cur.executemany("""UPDATE cat.document SET fiscal_quarter_auto=%s, updated_at=now() WHERE document_id=%s AND fiscal_quarter_confirmed IS NULL
                           AND fiscal_quarter_auto IS NULL AND fye_flag_confirmed IS NULL""", fills_q)
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _cd (document_id bigint, d text[]) ON COMMIT DROP"); cur.execute("TRUNCATE _cd")
        with cur.copy("COPY _cd FROM STDIN") as cp:
            cp.set_types(["int8", "text[]"])
            for k, v in dis.items():
                cp.write_row((k, v))
        cur.execute("""UPDATE cat.doc_content_check c SET content_disagrees = _cd.d FROM _cd
                       WHERE _cd.document_id = c.document_id AND c.content_disagrees IS DISTINCT FROM _cd.d""")
        # R-037 presence flags (codes only): Tax ID when page 1 carries a TIN pattern; LP PII when a roster partner matched
        cur.execute("""UPDATE cat.document d SET content_flags = f.flags, updated_at = now()
                       FROM (SELECT document_id, nullif(array_remove(ARRAY[CASE WHEN tin_present THEN 'tax_id' END,
                                                                           CASE WHEN lp_pii THEN 'lp_pii' END], NULL), '{}') AS flags
                             FROM cat.doc_page_read) f
                       WHERE f.document_id = d.document_id AND d.content_flags IS DISTINCT FROM f.flags""")
        con.commit()
    else:
        con.rollback()
    n_dis = collections.Counter(f for v in dis.values() if v for f in v)
    log(f"CONTENT CHECK {'APPLIED' if apply else 'DRY RUN'}: fiscal year filled {len(fills_fy):,} · quarter filled {len(fills_q):,} · "
        f"disagreements {sum(1 for v in dis.values() if v):,} ({', '.join(f'{k} {v:,}' for k, v in sorted(n_dis.items())) or 'none'})")
    return dict(fy=len(fills_fy), q=len(fills_q), disagree=dict(n_dis))


def nightly_step(con, log=print, cap=NIGHTLY_CAP):
    """CAT-WO-06 item 2: the `pages` sub-step inside derive (after kinds, before families / subject / requirements).
    Incremental only, capped per night (the rest stays as backlog). A Drive or OCR failure never stops the nightly: the
    step is reported 'NOT run' and the content already read stays in use."""
    cur = con.cursor()
    cur.execute("SELECT to_regclass('cat.doc_page_read') IS NOT NULL")
    if not cur.fetchone()[0]:
        return
    con.commit()
    if os.environ.get("CATWO06_PAGES", "1") == "0":
        log("   pages skipped (CATWO06_PAGES=0)")
    else:
        try:
            home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
            if home not in sys.path: sys.path.insert(0, home)
            import drive_crawl as dc
            from googleapiclient.discovery import build
            svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
            run(con, svc, incremental=True, limit=cap, apply=True, log=log)
        except (Exception, SystemExit) as e:
            con.rollback()
            log(f"   pages NOT run ({type(e).__name__}); content already read stays in use")
    apply_content(con, apply=True, log=log)


class _NoBrowser:
    """a token that can't be refreshed silently is a failure, never a browser window"""
    @staticmethod
    def from_client_secrets_file(*a, **k):
        raise RuntimeError("sign-in needed: the drive.readonly token could not be refreshed without a browser")


def main():
    import psycopg
    import dbguard_wo03 as dbg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--backfill", action="store_true", help="all in-scope documents not yet read")
    g.add_argument("--incremental", action="store_true", help="new or changed md5s (the nightly's mode)")
    g.add_argument("--seed-rules", action="store_true")
    g.add_argument("--apply-content", action="store_true")
    g.add_argument("--review-only", help="comma-separated CNT rule ids to set review-only (new rule version)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true", help="write the results (else a dry run: read, count, write nothing)")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    net_guard()
    with psycopg.connect(url) as con:
        if a.seed_rules:
            seed_rules(con); return
        if a.review_only:
            set_review_only(con, [x.strip() for x in a.review_only.split(",") if x.strip()]); return
        if a.apply_content:
            apply_content(con, apply=a.apply); return
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        if home not in sys.path: sys.path.insert(0, home)
        os.chdir(home)                                   # the crawler's token file lives there
        import drive_crawl as dc
        dc.InstalledAppFlow = _NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        run(con, svc, incremental=a.incremental, limit=a.limit if a.limit else (None if a.backfill else NIGHTLY_CAP), apply=a.apply,
            connect=lambda: psycopg.connect(url))
        print(f"memory: process peak {mem_mb()[1]} MB")


if __name__ == "__main__":
    main()
