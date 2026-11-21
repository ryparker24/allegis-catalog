r"""
CAT-WO-05 · portal postings -> Issued + Published To (R-030 / R-031), and the R-032 status rules.

  py pipeline\portals_wo05.py --db-url-file <url file> [--dir C:\DriveCatalog\portal_exports] [--apply] [--release]

Steps (all codes only; a partner NAME never enters the catalog DB, a log or a label):
  load()          nightly step `portals`: the newest dated exports (lp_postings_<date>.csv, gp_postings_<date>.csv,
                  gp_member_xwalk_<date>.csv) -> ref.portal_posting. The portals are READ-ONLY sources: this module has
                  no connection to either portal; it reads the dated export files only.
  apply_issued()  inside every derive, after version families: cat.doc_posting (file ID, then md5 copies), Status = Issued
                  (machine; a person's Status still wins in every view), Issued date, Published To, Portal kind conflicts.
  doc_partners()  the Subject step adds the posted-to partner (method 'portal', high) where it maps to the Datum roster.
  status_rules()  the R-032 proposals (ops.decomposition_rule applies_to = 'status'), used by apply_derive_wo02.

Partner mapping:
  LP portal  the portal's partner code is the Datum LP-#### code: exact when it is on the roster, else unmapped.
  GP portal  the export carries the member number and two md5 hashes of the member's normalized name (exact and
             token-sorted); the roster's display / legal names are hashed the same way IN MEMORY and compared. A hash
             that matches one roster code = crosswalk; several = ambiguous (no code); none = unmapped. No name is read
             from the portal and none is stored.
Dates are handled and written as YYYY-MM-DD strings / dates; nothing here writes to Drive.
"""
import argparse, collections, csv, datetime, glob, hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbguard_wo03 as dbg

DEFAULT_DIR = r"C:\DriveCatalog\portal_exports"
BATCH = 2000

LP_COLS = ["posting_id", "drive_file_id", "partner_ref", "fund_ref", "doc_type", "period", "posted_date", "published"]
GP_COLS = ["posting_id", "drive_file_id", "member_ref", "fund_ref", "doc_type", "doc_year", "period", "posted_date"]
XW_COLS = ["member_ref", "key_md5", "key_sorted_md5"]
# a column that could carry a name / contact / free text is refused outright (the export must be codes only)
FORBID = {"name", "names", "title", "display", "legal", "investor", "member_name", "email", "mail", "phone", "address",
          "contact", "first", "last", "note", "notes", "description", "doc_title"}

# the posting's document type -> the catalog kind it should be (None = no kind check)
EXPECTED_KIND = {("lp", "QR"): "quarterly_report", ("lp", "CRR"): "capital_statement", ("lp", "TAX"): "k1",
                 ("gp", "CC"): "capital_call_notice", ("gp", "K1"): "k1", ("gp", "QR"): "quarterly_report",
                 ("gp", "ST"): "capital_statement", ("gp", "CIA"): "legal_agreement", ("gp", "GPL"): "legal_agreement",
                 ("gp", "W2"): "tax_form", ("gp", "OTH"): None}
CHANNEL = {"lp": "lp_portal", "gp": "gp_portal"}
# Issued date = the first posted date only when the posting was timely: posted no later than this many days after the
# period end (a quarter or the tax / fiscal year). Bulk back-loads (e.g. 2019 notices loaded in 2026) keep Status =
# Issued and their Published To date, but no Issued date (default taken).
TIMELY_DAYS = 270
CODE_RE = re.compile(r"^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$")
FILE_RE = re.compile(r"^[A-Za-z0-9_-]{10,80}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------ pure parts (unit-tested)
def norm_name(s):
    """the portal export's normalization: lower case, non-alphanumerics -> one space, trimmed"""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def name_hashes(s):
    n = norm_name(s)
    if not n:
        return set()
    return {hashlib.md5(n.encode()).hexdigest(), hashlib.md5(" ".join(sorted(n.split(" "))).encode()).hexdigest()}


def forbidden_columns(cols):
    return [c for c in cols if set(re.split(r"[_\s]+", c.lower())) & FORBID or c.lower() in FORBID]


def parse_period(period, year=None):
    """'2026-Q2' -> (2026, 2); '2025' / '2025-FY' -> (2025, None); year fallback ('2024' / 'Unknown')."""
    m = re.match(r"^(\d{4})(?:-Q([1-4]))?(?:-FY)?$", (period or "").strip())
    if m:
        return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
    if year and re.match(r"^\d{4}$", str(year).strip()):
        return int(str(year).strip()), None
    return None, None


def period_end(fy, q):
    if fy is None:
        return None
    if q is None:
        return datetime.date(fy, 12, 31)
    return datetime.date(fy, 3 * q, 30 if q in (2, 3) else 31)


def timely(posted, fy, q, days=TIMELY_DAYS):
    """True when a posting's date can stand as the document's Issued date (not a bulk back-load)."""
    pe = period_end(fy, q)
    return bool(posted and pe and posted <= pe + datetime.timedelta(days=days))


def map_partner(portal, partner_ref, entity, roster_codes, hash_index=None, xw=None, party_entities=None, gp_codes=None):
    """-> (portal_partner, partner_code|None, partner_map, candidates|None). partner_ref '' = a fund-level posting.
    GP portal: a member's name hash may hit several roster codes (Datum keeps one code per relationship). GP-roster codes
    are preferred; then the posting's own GP entity decides; otherwise the candidates are kept for the per-document step."""
    if not partner_ref:
        return None, None, "fund_level", None
    if portal == "lp":
        ok = partner_ref in roster_codes
        return partner_ref, (partner_ref if ok else None), ("exact" if ok else "unmapped"), None
    pp = f"M{int(partner_ref)}"
    codes = set()
    for h in (xw or {}).get(partner_ref) or set():
        codes |= (hash_index or {}).get(h, set())
    if not codes:
        return pp, None, "unmapped", None
    if gp_codes is not None and len(codes) > 1 and codes & gp_codes:
        codes = codes & gp_codes
    if len(codes) > 1 and entity and party_entities:
        at = {c for c in codes if entity in party_entities.get(c, ())}
        if len(at) == 1:
            codes = at
    if len(codes) == 1:
        return pp, next(iter(codes)), "crosswalk", None
    return pp, None, "ambiguous", sorted(codes)


def resolve_for_document(candidates, doc_entities, party_entities):
    """an ambiguous posting -> the one candidate whose roster entity is on the document, else None (never a guess)"""
    hit = {c for c in candidates or () if set(party_entities.get(c, ())) & set(doc_entities or ())}
    return next(iter(hit)) if len(hit) == 1 else None


# the portals file annual reports (audited statements) under "Quarterly Reports": those kinds agree with that type
COMPATIBLE = {"quarterly_report": {"financial_statements", "audited_financial_statements"}}


def kind_conflict(doc_kind, expected):
    """a posting disagrees with the catalog when both kinds are known and differ (a blank kind is not a conflict)."""
    return bool(doc_kind and expected and doc_kind != expected and doc_kind not in COMPATIBLE.get(expected, ()))


def issued_values(postings):
    """postings: [{posting_id, portal, posted_date, fiscal_year, fiscal_quarter}] for one document ->
    (channels, first posted date, posting IDs (<= 20), Issued date | None)."""
    chans = sorted({CHANNEL[p["portal"]] for p in postings})
    dates = sorted(p["posted_date"] for p in postings if p["posted_date"])
    ids = sorted({p["posting_id"] for p in postings}, key=lambda s: (s[:3], int(s[4:])))[:20]
    good = sorted(p["posted_date"] for p in postings if timely(p["posted_date"], p["fiscal_year"], p["fiscal_quarter"]))
    return chans, (dates[0] if dates else None), ids, (good[0] if good else None)


# ------------------------------------------------------------------ exports
def newest(dirpath, stem):
    files = sorted(glob.glob(os.path.join(dirpath, f"{stem}_*.csv")))
    if not files:
        raise SystemExit(f"no {stem}_<date>.csv in the portal export folder")
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", files[-1])
    if not m:
        raise SystemExit(f"undated export file name for {stem}")
    return files[-1], m.group(1)


def read_checked(path, expected):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        bad = forbidden_columns(cols)
        if bad:
            raise SystemExit(f"REFUSED {os.path.basename(path)}: column(s) that could carry names {bad}")
        if cols != expected:
            raise SystemExit(f"REFUSED {os.path.basename(path)}: columns differ from expected")
        rows = list(rd)
    return rows, hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_exports(dirpath=DEFAULT_DIR):
    lf, ld = newest(dirpath, "lp_postings")
    gf, gd = newest(dirpath, "gp_postings")
    xf, xd = newest(dirpath, "gp_member_xwalk")
    lp, lsha = read_checked(lf, LP_COLS)
    gp, gsha = read_checked(gf, GP_COLS)
    xw_rows, xsha = read_checked(xf, XW_COLS)
    for r in lp + gp:
        if not FILE_RE.match(r["drive_file_id"]) or (r["posted_date"] and not DATE_RE.match(r["posted_date"])):
            raise SystemExit("REFUSED: a row with a malformed file ID or date")
    xw = {r["member_ref"]: {r["key_md5"], r["key_sorted_md5"]} for r in xw_rows}
    files = [("lp", "postings", lf, ld, lsha, len(lp)), ("gp", "postings", gf, gd, gsha, len(gp)), ("gp", "member_xwalk", xf, xd, xsha, len(xw_rows))]
    return lp, ld, gp, gd, xw, files


# ------------------------------------------------------------------ export (only with Ryan's read-only logins)
# When C:\DriveCatalog\lp_portal_url.txt and gp_portal_url.txt exist (a login that can SELECT only the columns below; see
# the handoff for the exact grants), the nightly writes today's dated exports first, inside READ ONLY transactions.
# Without the files the newest exports on disk are used (the fallback). The URLs are never printed.
LP_URL_FILE = os.path.join(os.path.dirname(DEFAULT_DIR), "lp_portal_url.txt")
GP_URL_FILE = os.path.join(os.path.dirname(DEFAULT_DIR), "gp_portal_url.txt")
LP_EXPORT_SQL = """SELECT document_id, storage_ref, coalesce(lp_id, ''), fund_id,
       CASE doc_type WHEN 'Quarterly Reports' THEN 'QR' WHEN 'Capital Reconciliation Reports' THEN 'CRR' ELSE 'TAX' END,
       period, to_char(loaded_at, 'YYYY-MM-DD'), CASE WHEN published THEN 1 ELSE 0 END
FROM lp_portal.document WHERE storage_provider = 'drive' ORDER BY document_id"""
GP_EXPORT_SQL = """SELECT d.id, d.drive_file_id, coalesce(d.member_id::text, ''), coalesce(d.fund_id::text, ''),
       CASE d.doc_type WHEN 'Capital Calls' THEN 'CC' WHEN 'Carried Interest Agreement' THEN 'CIA' WHEN 'GP Legal Docs' THEN 'GPL'
         WHEN 'K-1s' THEN 'K1' WHEN 'Quarterly Reports' THEN 'QR' WHEN 'Statements' THEN 'ST' WHEN 'W-2' THEN 'W2' ELSE 'OTH' END,
       d.doc_year, coalesce(d.period, ''), coalesce(to_char(d.modified_at, 'YYYY-MM-DD'), '')
FROM portal.document d WHERE d.published AND d.drive_file_id IS NOT NULL ORDER BY d.id"""
# the GP member key view Ryan creates (portal.v_catalog_member_key): member id + two md5 hashes of the normalized name;
# the login can read the view only, never portal.member
GP_XW_SQL = "SELECT member_ref, key_md5, key_sorted_md5 FROM portal.v_catalog_member_key ORDER BY member_ref::bigint"


def export_from_portals(dirpath=DEFAULT_DIR, today=None, log=print):
    """-> True when today's exports were written from the portals, False when the URL files are absent (fallback)."""
    if not (os.path.exists(LP_URL_FILE) and os.path.exists(GP_URL_FILE)):
        log("portal logins not set up (no lp_portal_url.txt / gp_portal_url.txt): using the newest dated exports on disk")
        return False
    import psycopg
    day = (today or datetime.date.today()).isoformat()
    for url_file, jobs in ((LP_URL_FILE, [("lp_postings", LP_COLS, LP_EXPORT_SQL)]),
                           (GP_URL_FILE, [("gp_postings", GP_COLS, GP_EXPORT_SQL), ("gp_member_xwalk", XW_COLS, GP_XW_SQL)])):
        url = dbg.read_url(url_file)
        with psycopg.connect(url) as con:
            con.read_only = True                              # SELECT only, enforced by the session as well as the grants
            for stem, cols, sql in jobs:
                rows = con.execute(sql).fetchall()
                tmp = os.path.join(dirpath, f".{stem}_{day}.tmp")
                with open(tmp, "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh, lineterminator="\n")
                    w.writerow(cols)
                    w.writerows(rows)
                os.replace(tmp, os.path.join(dirpath, f"{stem}_{day}.csv"))
                log(f"  exported {stem}_{day}.csv rows={len(rows)}")
    return True


# ------------------------------------------------------------------ load (nightly step `portals`)
def build_rows(cur, lp, ld, gp, gd, xw):
    cur.execute("SELECT portal, fund_ref, entity_code FROM ref.portal_fund_map")
    fmap = {(p, f): e for p, f, e in cur.fetchall()}
    cur.execute("SELECT partner_code, entity_code, datum_company_kind FROM ref.party")
    roster, pent, gpc = set(), collections.defaultdict(set), set()
    for c, e, k in cur.fetchall():
        roster.add(c)
        if e: pent[c].add(e)
        if k == "gp": gpc.add(c)
    # roster names hashed in memory (never stored, never printed); then the names are dropped
    hidx = collections.defaultdict(set)
    cur.execute("SELECT partner_code, display_name, legal_name FROM ref.party")
    for c, dn, ln in cur.fetchall():
        for h in name_hashes(dn) | name_hashes(ln):
            hidx[h].add(c)
    cur.execute("SELECT partner_code, alias FROM ref.party_alias")
    for c, al in cur.fetchall():
        for h in name_hashes(al):
            hidx[h].add(c)
    rows = []
    for r in lp:
        if r["published"] != "1":
            continue
        ent = fmap.get(("lp", r["fund_ref"]))
        fy, q = parse_period(r["period"])
        pp, code, how, cand = map_partner("lp", r["partner_ref"], ent, roster)
        rows.append((f"LPD-{int(r['posting_id'])}", "lp", r["drive_file_id"], pp, code, how, cand, r["fund_ref"], ent, r["doc_type"],
                     EXPECTED_KIND.get(("lp", r["doc_type"])), fy, q, r["posted_date"] or None, ld))
    for r in gp:
        ent = fmap.get(("gp", r["fund_ref"])) if r["fund_ref"] else None
        fy, q = parse_period(r["period"], r["doc_year"])
        pp, code, how, cand = map_partner("gp", r["member_ref"], ent, roster, hidx, xw, pent, gpc)
        if ent is None and code and len(pent.get(code, ())) == 1:
            ent = next(iter(pent[code]))                     # a member posting without a fund: the partner's only GP
        rows.append((f"GPD-{int(r['posting_id'])}", "gp", r["drive_file_id"], pp, code, how, cand, r["fund_ref"] or None, ent, r["doc_type"],
                     EXPECTED_KIND.get(("gp", r["doc_type"])), fy, q, r["posted_date"] or None, gd))
    hidx.clear()
    return rows


def load(con, dirpath=DEFAULT_DIR, apply=False, log=print):
    """Replace ref.portal_posting from the newest exports. Commits only when apply. Counts and codes only."""
    import psycopg
    lp, ld, gp, gd, xw, files = read_exports(dirpath)
    log(f"checked: lp_postings {ld} rows={len(lp)} · gp_postings {gd} rows={len(gp)} · gp_member_xwalk rows={len(xw)} (columns OK, codes only)")
    with con.transaction() as tx:
        cur = con.cursor()
        rows = build_rows(cur, lp, ld, gp, gd, xw)
        cur.execute("DELETE FROM ref.portal_posting")
        cur.executemany("""INSERT INTO ref.portal_posting (posting_id, portal, file_id, portal_partner, partner_code, partner_map,
                             partner_candidates, fund_ref, entity_code, doc_type, expected_kind, fiscal_year, fiscal_quarter, posted_date, export_date)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
        for portal, kind, f, dt, sha, n in files:
            cur.execute("""INSERT INTO ref.portal_export (portal, file_kind, export_date, file_name, sha256, row_count) VALUES (%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (portal, file_kind, export_date) DO UPDATE SET sha256=EXCLUDED.sha256, row_count=EXCLUDED.row_count, loaded_at=now()""",
                        (portal, kind, dt, os.path.basename(f), sha, n))
        c = collections.Counter((r[1], r[5]) for r in rows)
        pp = {(r[1], r[3]) for r in rows if r[3]}
        pmap = collections.Counter()
        seen = set()
        for r in rows:
            if r[3] and (r[1], r[3]) not in seen:
                seen.add((r[1], r[3])); pmap[(r[1], r[5])] += 1
        log(f"{'loaded' if apply else 'DRY RUN (rolled back)'}: ref.portal_posting rows={len(rows)} · postings by partner map "
            + ", ".join(f"{p}:{m}={n}" for (p, m), n in sorted(c.items())))
        log(f"  portal partners {len(pp)}: " + ", ".join(f"{p}:{m}={n}" for (p, m), n in sorted(pmap.items())))
        if not apply:
            raise psycopg.Rollback(tx)
    return rows


# ------------------------------------------------------------------ derive: Issued + Published To
LIVE = """f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'"""


def doc_postings(cur):
    """{document_id: [(posting_id, match)]}: by file ID, then by md5 (copies of a posted file, e.g. the Finance original)."""
    out = collections.defaultdict(dict)
    cur.execute(f"""SELECT fd.document_id, p.posting_id FROM ref.portal_posting p JOIN cat.file f ON f.file_id = p.file_id
                    JOIN cat.file_document fd ON fd.file_id = f.file_id WHERE {LIVE}""")
    for d, pid in cur.fetchall():
        out[d][pid] = "file_id"
    cur.execute(f"""SELECT DISTINCT fd.document_id, p.posting_id
                    FROM ref.portal_posting p JOIN cat.file pf ON pf.file_id = p.file_id
                    JOIN cat.file f ON f.md5 = pf.md5 AND f.file_id <> pf.file_id
                    JOIN cat.file_document fd ON fd.file_id = f.file_id
                    WHERE pf.md5 IS NOT NULL AND coalesce(pf.size_bytes, 0) > 0 AND {LIVE}""")
    for d, pid in cur.fetchall():
        out[d].setdefault(pid, "md5")
    return {d: sorted(v.items()) for d, v in out.items()}


def portal_status(cur):
    """{document_id: 'PORTAL-LP' | 'PORTAL-GP' | 'PORTAL-GP+LP'} for every posted document (derive's status loop)."""
    dp = doc_postings(cur)
    cur.execute("SELECT posting_id, portal FROM ref.portal_posting")
    portal = dict(cur.fetchall())
    return {d: "PORTAL-" + "+".join(sorted({portal[p].upper() for p, _ in pl})) for d, pl in dp.items()}


def apply_issued(conn, apply=True, log=print):
    """R-031 inside derive (after families, so a posted document stays Issued). Writes only machine columns, only what
    changed (idempotent); a person's Status / Issued date always wins in the views and the re-sync never overwrites it."""
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('ref.portal_posting') IS NOT NULL")
    if not cur.fetchone()[0]:
        return collections.Counter()
    dp = doc_postings(cur)
    cur.execute("SELECT posting_id, portal, posted_date, fiscal_year, fiscal_quarter, expected_kind FROM ref.portal_posting")
    post = {r[0]: dict(zip(["posting_id", "portal", "posted_date", "fiscal_year", "fiscal_quarter", "expected_kind"], r)) for r in cur.fetchall()}
    c = collections.Counter()
    ids = sorted(dp)
    doc = {}
    for i in range(0, len(ids), BATCH):                      # streamed in batches (memory guard G-M1)
        cur.execute("""SELECT document_id, coalesce(kind_confirmed, kind_auto), status_auto, status_rule, issued_date_auto,
                              published_channels_auto, published_date_auto, published_ids_auto, status_confirmed
                       FROM cat.document WHERE document_id = ANY(%s)""", (ids[i:i + BATCH],))
        for r in cur.fetchall():
            doc[r[0]] = r
    upd, links, conflicts = [], [], []
    for d, plist in dp.items():
        if d not in doc:
            continue
        _, kind, st, srule, idate, ch_old, pd_old, ids_old, st_person = doc[d]
        ps = [post[p] for p, _ in plist]
        chans, first, pids, issued = issued_values(ps)
        rule = "PORTAL-" + "+".join(sorted({p["portal"].upper() for p in ps}))
        new_idate = issued                                   # only this step writes issued_date_auto (None for a back-load)
        row = ("issued", rule, new_idate, chans, first, pids)
        if (st, srule, idate, ch_old or [], pd_old, ids_old or []) != ("issued", rule, new_idate, chans, first, pids):
            upd.append(row + (d,))
        for p, m in plist:
            links.append((d, p, m))
            c[f"match:{m}"] += 1
            if kind_conflict(kind, post[p]["expected_kind"]):
                conflicts.append((d, p, kind, post[p]["expected_kind"]))
        c["documents"] += 1
        c[f"kind:{kind or '(none)'}"] += 1
        c["person_status_kept" if st_person and st_person != "issued" else "status_issued"] += 1
        c["issued_date_set" if new_idate else "issued_date_blank_backload"] += 1
    c["conflict_rows"] = len(conflicts)
    c["conflict_documents"] = len({x[0] for x in conflicts})
    c["documents_changed"] = len(upd)
    if apply:
        # a document no longer posted loses its machine portal values (its next derive status comes from the rules)
        cur.execute("""UPDATE cat.document SET published_channels_auto=NULL, published_date_auto=NULL, published_ids_auto=NULL,
                              issued_date_auto=NULL,
                              status_auto=CASE WHEN status_rule LIKE 'PORTAL-%%' THEN NULL ELSE status_auto END,
                              status_rule=CASE WHEN status_rule LIKE 'PORTAL-%%' THEN NULL ELSE status_rule END,
                              updated_at=now()
                       WHERE (published_ids_auto IS NOT NULL OR issued_date_auto IS NOT NULL OR status_rule LIKE 'PORTAL-%%') AND NOT (document_id = ANY(%s))""", (ids,))
        c["documents_cleared"] = cur.rowcount
        for i in range(0, len(upd), BATCH):
            cur.executemany("""UPDATE cat.document SET status_auto=%s, status_rule=%s, issued_date_auto=%s, published_channels_auto=%s,
                                      published_date_auto=%s, published_ids_auto=%s, updated_at=now() WHERE document_id=%s""", upd[i:i + BATCH])
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _dp (document_id bigint, posting_id text, match text) ON COMMIT DROP")
        cur.execute("TRUNCATE _dp")
        with cur.copy("COPY _dp FROM STDIN") as cp:
            for x in links: cp.write_row(x)
        cur.execute("DELETE FROM cat.doc_posting t WHERE NOT EXISTS (SELECT 1 FROM _dp s WHERE s.document_id=t.document_id AND s.posting_id=t.posting_id AND s.match=t.match)")
        cur.execute("INSERT INTO cat.doc_posting SELECT document_id, posting_id, match FROM _dp ON CONFLICT DO NOTHING")
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _kc (document_id bigint, posting_id text, doc_kind text, posted_kind text) ON COMMIT DROP")
        cur.execute("TRUNCATE _kc")
        with cur.copy("COPY _kc FROM STDIN") as cp:
            for x in conflicts: cp.write_row(x)
        cur.execute("""DELETE FROM ops.portal_kind_conflict t WHERE NOT EXISTS (SELECT 1 FROM _kc s WHERE s.document_id=t.document_id
                         AND s.posting_id=t.posting_id AND s.doc_kind=t.doc_kind AND s.posted_kind=t.posted_kind)""")
        cur.execute("""INSERT INTO ops.portal_kind_conflict (document_id, posting_id, doc_kind, posted_kind)
                       SELECT document_id, posting_id, doc_kind, posted_kind FROM _kc ON CONFLICT DO NOTHING""")
        conn.commit()
    else:
        conn.rollback()
    log(f"PORTALS {'APPLIED' if apply else 'DRY RUN'}: posted documents {c['documents']:,} (by file ID {c['match:file_id']:,} links, "
        f"md5 copies {c['match:md5']:,}) · changed {c['documents_changed']:,} · cleared {c.get('documents_cleared', 0):,} · "
        f"Issued date set {c['issued_date_set']:,} / back-load (no date) {c['issued_date_blank_backload']:,} · "
        f"person Status kept {c['person_status_kept']:,} · Portal kind conflicts {c['conflict_documents']:,} documents")
    return c


def doc_partners(cur, dp=None):
    """{document_id: {(partner_code, entity_code, how)}}: postings whose partner maps to the Datum roster, plus ambiguous
    GP postings resolved by the document's own entities (entities + Parties issuing). Codes only.
    dp: the {document_id: [(posting_id, match)]} links in memory (measurement); default = cat.doc_posting."""
    cur.execute("SELECT to_regclass('ref.portal_posting') IS NOT NULL")
    if not cur.fetchone()[0]:
        return {}
    cur.execute("SELECT partner_code, entity_code FROM ref.party WHERE entity_code IS NOT NULL")
    pent = collections.defaultdict(set)
    for c, e in cur.fetchall():
        pent[c].add(e)
    if dp is None:
        cur.execute("SELECT document_id, posting_id FROM cat.doc_posting")
        links = cur.fetchall()
    else:
        links = [(d, p) for d, v in dp.items() for p, _ in v]
    cur.execute("SELECT posting_id, partner_code, entity_code, partner_candidates FROM ref.portal_posting WHERE partner_code IS NOT NULL OR partner_candidates IS NOT NULL")
    pinfo = {r[0]: r[1:] for r in cur.fetchall()}
    links = [(d, p) for d, p in links if p in pinfo]
    docs = sorted({d for d, _ in links})
    dinfo = {}
    for i in range(0, len(docs), BATCH):
        cur.execute("""SELECT document_id, entities_confirmed, coalesce(issuing_entity_confirmed, issuing_entity_auto)
                       FROM cat.document WHERE document_id = ANY(%s)""", (docs[i:i + BATCH],))
        for d, ec, iss in cur.fetchall():
            dinfo[d] = (ec, iss)
    rows = [(d,) + tuple(pinfo[p]) + dinfo.get(d, (None, None)) for d, p in links]
    need = sorted({r[0] for r in rows if r[4] is None})
    auto_ents = collections.defaultdict(set)
    for i in range(0, len(need), BATCH):
        cur.execute("SELECT document_id, entities FROM app.v_find WHERE document_id = ANY(%s)", (need[i:i + BATCH],))
        for d, es in cur.fetchall():
            auto_ents[d] |= set(es or ())
    out = collections.defaultdict(set)
    for d, code, ent, cand, ents_conf, issuing in rows:
        if code:
            out[d].add((code, ent or (next(iter(pent[code])) if len(pent.get(code, ())) == 1 else None), "posting"))
            continue
        doc_ents = (set(ents_conf) if ents_conf is not None else auto_ents.get(d, set())) | ({issuing} if issuing else set())
        r = resolve_for_document(cand, doc_ents, pent)
        if r:
            hit = pent[r] & doc_ents
            out[d].add((r, next(iter(hit)) if len(hit) == 1 else None, "document_entity"))
    return out


# ------------------------------------------------------------------ R-032 status rules (proposals, as data)
# The seed (ops.decomposition_rule, applies_to = 'status'). pattern = JSON conditions, Python regex, case-insensitive:
#   family [file type families] · kinds / not_kinds · folder (any folder segment) · not_folder · name · not_name · special
# value = the Status it proposes ('working' = measured only, stays blank). First matching rule wins (priority order), and
# only on a non-executable document still blank after the released rules (R-022 markers, P4) and the portal postings.
_NOT_DRAFT_NAME = r"\b(draft|redline|mark-?up|unsigned|not[\s_-]*final|for[\s_-]*review|comments?)\b"
_NOT_DRAFT_FOLDER = r"\b(drafts?|working|wip|work[\s_-]*in[\s_-]*progress|for[\s_-]*review)\b"
STATUS_RULES = [
    ("ST5-ISS-FOLDER", "issued", 10, {"family": ["pdf"], "folder": r"^\W*(\d+[\s._-]+)?(final[\s_-]*reports?|issued|sent|distributed|as[\s_-]*filed|filed)\b",
                                      "not_name": _NOT_DRAFT_NAME},
     "PDFs in folders named final reports / issued / sent / distributed / as filed / filed"),
    ("ST5-ISS-TAXFILED", "issued", 11, {"kinds": ["tax_return"], "folder": r"(as[\s_-]*filed|e-?file|filed[\s_-]*returns?|\baccepted\b)",
                                        "not_name": _NOT_DRAFT_NAME},
     "tax returns in as-filed or e-file confirmation folders"),
    ("ST5-ISS-K1PORTAL", "issued", 12, {"family": ["pdf"], "kinds": ["k1"], "folder": r"\bk-?1'?s?\b", "special": "k1_portal_year",
                                        "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "K-1 PDFs in K-1 folders where the same tax year has portal postings for that fund"),
    ("ST5-FIN-NAME", "final", 20, {"family": ["pdf"], "name": r"\b(final|executed|signed|conformed)\b", "not_name": _NOT_DRAFT_NAME},
     "PDFs whose name says final, executed, signed or conformed (not already Issued)"),
    ("ST5-FIN-FOLDER", "final", 21, {"family": ["pdf"], "folder": r"\bfinals?\b", "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "PDFs in a folder whose name has 'final' anywhere (the released rule needs it at the start)"),
    ("ST5-FIN-K1PDF", "final", 22, {"family": ["pdf"], "kinds": ["k1"], "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "K-1 PDFs (the final form; Issued only from a posting or an issued folder)"),
    ("ST5-FIN-BANKPDF", "final", 23, {"family": ["pdf"], "kinds": ["bank_stmt"], "not_name": _NOT_DRAFT_NAME},
     "bank statement PDFs (issued by the bank)"),
    ("ST5-FIN-THIRDPARTY", "final", 24, {"family": ["pdf"], "kinds": ["invoice", "tax_form", "w9_w8", "wire_confirmation", "receipt"],
                                         "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "third-party PDFs received: invoices, tax forms, W-9 / W-8, wire confirmations, receipts"),
    ("ST5-FIN-REPORTPDF", "final", 25, {"family": ["pdf"], "kinds": ["quarterly_report", "capital_statement", "audited_financial_statements",
                                                                     "capital_call_notice", "distribution_notice"],
                                        "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "investor report / notice PDFs (quarterly reports, capital statements, audited FS, call and distribution notices)"),
    ("ST5-FIN-TAXRETPDF", "final", 26, {"family": ["pdf"], "kinds": ["tax_return"], "not_name": _NOT_DRAFT_NAME, "not_folder": _NOT_DRAFT_FOLDER},
     "tax return PDFs (not drafts / for review)"),
    ("ST5-DRF-NAME", "draft", 30, {"name": r"(\bdraft\b|\bred-?line[ds]?\b|\bmark-?up\b|\bcomments?\b|\bfor[\s_-]*review\b|(?<![A-Za-z])v\d{1,2}(?![0-9]))",
                                   "not_name": r"\bfinal\b"},
     "names with draft, vN without final, redline, markup, comments, for review"),
    ("ST5-DRF-FOLDER", "draft", 31, {"family": ["doc", "sheet"], "folder": r"^\W*(\d+[\s._-]+)?(drafts?|working|wip|work[\s_-]*in[\s_-]*progress)\b"},
     "Word and Excel files in folders named drafts or working"),
    ("ST5-DRF-WORDREPORT", "draft", 32, {"family": ["doc"], "kinds": ["quarterly_report", "capital_statement", "financial_statements",
                                                                     "audited_financial_statements"]},
     "Word files of reports and statements (the issued version is the PDF), as P4 does for audited FS"),
    ("ST5-WORKING", "working", 40, {"family": ["sheet"], "folder": r"(work[\s_-]*papers?|\brecs?\b|reconciliations?|\bsupport\b|\bpbc\b)"},
     "spreadsheets in workpaper / rec / support / PBC folders: stay blank (a 'Working' Status would need Label manager)"),
    ("ST5-WORKING-KIND", "working", 41, {"family": ["sheet"], "kinds": ["workpaper", "pbc_request", "journal_import", "fund_analysis", "valuation_memo"]},
     "working spreadsheets by kind (workpapers, PBC lists, journal imports, analyses, valuation models): stay blank"),
]


def seed_status_rules(con, log=print):
    """Upsert the seed. Only PROVISIONAL rows are replaced; once Ryan has ruled (provisional = false) a row is never touched,
    and a vetoed rule (active = false) stays vetoed."""
    cur = con.cursor()
    n = 0
    for rid, val, pri, spec, note in STATUS_RULES:
        for v in spec.values():
            if isinstance(v, str): re.compile(v)
        cur.execute("""INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, provisional)
                       VALUES (%s, 1, 'status', 'status', %s, %s, %s, true, %s, true)
                       ON CONFLICT (rule_id, version) DO UPDATE SET pattern=EXCLUDED.pattern, value=EXCLUDED.value, priority=EXCLUDED.priority,
                         notes=EXCLUDED.notes WHERE ops.decomposition_rule.provisional""", (rid, json.dumps(spec), val, pri, note))
        n += cur.rowcount
    ids = [r[0] for r in STATUS_RULES]
    cur.execute("DELETE FROM ops.decomposition_rule WHERE applies_to='status' AND provisional AND NOT (rule_id = ANY(%s))", (ids,))
    con.commit()
    log(f"status rules seeded: {n} upserted (provisional only), {cur.rowcount} stale provisional removed; {len(ids)} in the seed")


def load_status_rules(cur, include_vetoed=False):
    cur.execute("""SELECT DISTINCT ON (rule_id) rule_id, pattern, value, priority, active, notes FROM ops.decomposition_rule
                   WHERE applies_to = 'status' ORDER BY rule_id, version DESC""")
    out = []
    for rid, pat, val, pri, active, note in cur.fetchall():
        if not active and not include_vetoed:
            continue
        spec = json.loads(pat)
        comp = {k: re.compile(v, re.I) for k, v in spec.items() if k in ("folder", "not_folder", "name", "not_name")}
        out.append(dict(rule_id=rid, value=val, priority=pri, active=active, spec=spec, rx=comp, note=note))
    return sorted(out, key=lambda r: (r["priority"], r["rule_id"]))


def k1_portal_years(cur):
    """{(entity, tax year)} with K-1 / tax postings in either portal (the ST5-ISS-K1PORTAL condition)."""
    cur.execute("SELECT to_regclass('ref.portal_posting') IS NOT NULL")
    if not cur.fetchone()[0]:
        return set()
    cur.execute("SELECT DISTINCT entity_code, fiscal_year FROM ref.portal_posting WHERE expected_kind = 'k1' AND entity_code IS NOT NULL AND fiscal_year IS NOT NULL")
    return set(cur.fetchall())


def rule_matches(rule, name, segs, family, kind, entities=(), fy=None, k1_years=frozenset()):
    s = rule["spec"]
    if s.get("family") and family not in s["family"]:
        return False
    if s.get("kinds") and kind not in s["kinds"]:
        return False
    if s.get("not_kinds") and kind in s["not_kinds"]:
        return False
    rx = rule["rx"]
    if "folder" in rx and not any(rx["folder"].search(x or "") for x in segs):
        return False
    if "not_folder" in rx and any(rx["not_folder"].search(x or "") for x in segs):
        return False
    if "name" in rx and not rx["name"].search(name or ""):
        return False
    if "not_name" in rx and rx["not_name"].search(name or ""):
        return False
    if s.get("special") == "k1_portal_year":
        if fy is None or not any((e, fy) in k1_years for e in (entities or ())):
            return False
    return True


def first_rule(rules, name, segs, family, kind, entities=(), fy=None, k1_years=frozenset()):
    """the first matching rule (priority order) -> (status|None, rule_id). 'working' proposes no Status (blank)."""
    for r in rules:
        if rule_matches(r, name, segs, family, kind, entities, fy, k1_years):
            return (None if r["value"] == "working" else r["value"]), r["rule_id"]
    return None, None


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--issued", action="store_true", help="also run apply_issued (normally inside derive)")
    ap.add_argument("--seed-rules", action="store_true", help="upsert the R-032 status rule seed (provisional rows only), then stop")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    with psycopg.connect(url) as con:
        if a.seed_rules:
            seed_status_rules(con); return
        load(con, a.dir, apply=a.apply)
        if a.issued:
            apply_issued(con, apply=a.apply)


if __name__ == "__main__":
    main()
