r"""
CAT-WO-03 item 3 (R-026) · a document's Subject: which roster partner (LP- / GM- / GPM-) or which staff member it is about.

  py pipeline\subject_wo03.py --db-url-file <branch url file> [--apply] [--release] [--directory-token <token json>]

Roster subjects (subscription agreements, side letters, K-1s, PCAPs; GP agreements incl. carry grants and member
admission documents of GP entities) are matched against the rosters of the document's entities:
  1. a person's decision first: the Subject code(s) label read back (subject_codes_confirmed), else the latest app
     decision (review_event edits.subject_codes, e.g. the Match subject lane)          -> confidence 'confirmed'
  2. FOLDER: a folder name holding a partner's full name (normalised)                  -> 'folder'
  3. NAME: the file name holding a partner's full name                                 -> 'name'
  4. TOKEN: only a distinctive word of a partner's name                                -> always low
  K-1s / PCAPs: when CAT-WO-02 Parties knows the issuing entity, only THAT entity's roster is used (the K-1 was
  issued to one of its partners); a K-1 received by the fund's own GP entity (Parties receiving = that GP) is the
  fund's GP row ('parties'). The fund's GP row is otherwise matched only by its full name in the FILE name.
  High = exactly ONE partner by file name (or, with no file-name match, exactly one by folder). Several full matches,
  or a token match only, are LOW: they go to the Review lane "Match subject". High matches become subject_codes_auto
  (written to the Subject code(s) label by the re-sync); low ones are written nowhere until a person picks.
Staff subjects (personnel documents): matched by name against the Workspace directory, only with --directory-token
(a token with directory.readonly; names are read into memory only). Without it the step is skipped and reported.
Personnel documents (employment / offer / compensation ... in the file name) get personnel_auto = true: the re-sync
then raises Handling to Restricted + Personnel info (never lowers it).

Names (LP aliases, file and folder names, staff names) are used ONLY in memory: never printed, logged or stored.
Prints counts and codes only.
"""
import argparse, collections, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbguard_wo03 as dbg

PARTIES_MAX = 3
STAFF_EMAIL = re.compile(r"^[a-z0-9._%+-]{1,64}@allegiscapital\.com$")
CODE_RE = re.compile(r"^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$")
ROSTER_KINDS = ("subscription_agreement", "side_letter", "k1", "capital_statement")
GP_AGREEMENT_KINDS = ("legal_agreement", "operating_agreement", "operating_agreement_amendment")   # GOV-04 / GOV-05, GP entities only
PERSONNEL_NAME = re.compile(
    r"(?i)\b(offer letter|employment (agreement|contract|letter)|compensation (letter|agreement|plan)|comp letter|bonus letter|"
    r"severance|separation agreement|retention (letter|agreement|bonus)|performance review)\b")

# legal / generic words dropped before matching (a partner's name must still have something distinctive left)
GENERIC = set("""llc l l c lp l p llp inc incorporated ltd limited corp corporation co company the and of trust trustee trustees
ttee tr dtd dated ua u a fbo revocable irrevocable living family foundation fund funds partners partner partnership holdings holding
investments investment investors investor capital ventures venture group management associates enterprises international global
gp lp i ii iii iv v vi vii viii ix x xi ira roth account acct as for""".split())
# words that are common in Allegis file names and never distinctive of a partner
FILE_WORDS = set("""allegis cyber innovation special opportunities opportunity mtv annex mtef pledge schedule final draft signed executed
subscription agreement side letter statement statements capital k1 k tax return returns copy scan scanned report quarterly annual
investor amended amendment admission""".split())


def norm(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def name_tokens(s, keep_fund_words=False):
    """partner-name words left after dropping legal / generic words; for a partner's FULL pattern also drop common
    Allegis file words (a manager row named "Allegis Capital, LLC" must not match every Allegis folder)."""
    tk = [t for t in norm(s).split() if t not in GENERIC]
    return tk if keep_fund_words else [t for t in tk if t not in FILE_WORDS]


LEGAL = set("llc l c lp p llp inc incorporated ltd limited corp corporation co the".split())


def gp_tokens(s):
    """the fund's own GP row: its name WITH 'gp' and fund words, only legal suffixes dropped ('mtv iv gp')."""
    return [t for t in norm(s).split() if t not in LEGAL]


def contains_seq(hay_tokens, needle_tokens):
    """needle as a contiguous word sequence inside hay (both token lists)."""
    n = len(needle_tokens)
    if not n or n > len(hay_tokens):
        return False
    first = needle_tokens[0]
    for i, t in enumerate(hay_tokens[: len(hay_tokens) - n + 1]):
        if t == first and hay_tokens[i:i + n] == needle_tokens:
            return True
    return False


class RosterIndex:
    """Per entity: partner -> name patterns. A 'full' pattern is the alias without generic words, kept only when it is
    specific enough (2+ words, or 1 word of 7+ letters); distinctive tokens (5+ letters, used by at most 2 partners in
    the whole roster, not a common file word) give LOW matches only."""

    def __init__(self, party_rows, alias_rows):
        # party_rows: (entity_code, partner_code[, is_company_gp]); alias_rows: (partner_code, alias)
        self.by_entity = collections.defaultdict(set)
        self.gp_rows = set()                          # (entity, partner): the fund's own GP row
        for row in party_rows:
            e, p = row[0], row[1]
            if e:
                self.by_entity[e].add(p)
                if len(row) > 2 and row[2]:
                    self.gp_rows.add((e, p))
        self.full = collections.defaultdict(set)     # partner -> {tuple(tokens)}
        self.gpfull = collections.defaultdict(set)   # partner -> {tuple(tokens)} for GP rows (name with 'gp')
        self.tok = collections.defaultdict(set)      # partner -> {token}
        df = collections.Counter()
        per = collections.defaultdict(set)
        gp_partners = {p for _, p in self.gp_rows}
        for p, a in alias_rows:
            if p in gp_partners:
                g = gp_tokens(a)
                if len(g) >= 2 and "gp" in g:
                    self.gpfull[p].add(tuple(g))
            tk = name_tokens(a)
            if (len(tk) >= 2) or (len(tk) == 1 and len(tk[0]) >= 7):
                self.full[p].add(tuple(tk))
            per[p] |= {t for t in tk if len(t) >= 5 and not t.isdigit()}
        for p, ts in per.items():
            df.update(ts)
        for p, ts in per.items():
            self.tok[p] = {t for t in ts if df[t] <= 2 and t not in FILE_WORDS}

    def partners(self, entities):
        out = {}
        for e in sorted(entities):          # deterministic: a partner on two rosters gets the same entity every run
            for p in self.by_entity.get(e, ()):
                out.setdefault(p, e)
        return out


def match_doc(idx, entities, file_names, folder_segments):
    """-> ('none'|'no_roster'|'high'|'low', [(partner, entity, method)]). Pure; names stay in memory."""
    cands = idx.partners(entities)
    if not cands:
        return "no_roster", []
    name_tk = [norm(n).split() for n in file_names]
    seg_tk = [norm(s).split() for s in folder_segments]
    by_name, by_folder, by_tok = set(), set(), set()
    for p in cands:
        if (cands[p], p) in idx.gp_rows:             # the fund's own GP: full GP name in the FILE name only
            if any(contains_seq(h, list(pt)) for pt in idx.gpfull.get(p, ()) for h in name_tk):
                by_name.add(p)
            continue
        pats = idx.full.get(p, ())
        if any(contains_seq(h, list(pt)) for pt in pats for h in name_tk):
            by_name.add(p); continue
        if any(contains_seq(h, list(pt)) for pt in pats for h in seg_tk):
            by_folder.add(p); continue
        toks = idx.tok.get(p, ())
        if toks and any(t in set(h) for t in toks for h in name_tk + seg_tk):
            by_tok.add(p)
    if len(by_name) == 1:
        p = next(iter(by_name)); return "high", [(p, cands[p], "name")]
    if not by_name and len(by_folder) == 1:
        p = next(iter(by_folder)); return "high", [(p, cands[p], "folder")]
    low = sorted(by_name | by_folder) or sorted(by_tok)
    if not low or len(low) > 6:                     # too many to be a useful pick list
        return "none", []
    return "low", [(p, cands[p], "name" if p in by_name else "folder" if p in by_folder else "name") for p in low]


def personnel(file_names):
    return any(PERSONNEL_NAME.search(n or "") for n in file_names)


def staff_match(staff, file_names):
    """staff: [(email, [name variants])] -> the one email whose full name is in a file name, else None."""
    name_tk = [norm(n).split() for n in file_names]
    hits = {em for em, names in staff for nm in names
            if len(norm(nm).split()) >= 2 and any(contains_seq(h, norm(nm).split()) for h in name_tk)}
    return next(iter(hits)) if len(hits) == 1 else None


# ------------------------------------------------------------------ DB
DOCS_SQL = """
SELECT d.document_id, coalesce(d.kind_confirmed, d.kind_auto) AS kind, coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fy,
       d.entities_confirmed, coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto) AS issuing,
       coalesce(d.receiving_entities_confirmed, d.receiving_entities_auto) AS receiving,
       d.subject_codes_confirmed, d.subject_codes_auto, d.subject_person_auto, d.subject_rule, d.personnel_auto,
       EXISTS (SELECT 1 FROM cat.file_document fl JOIN app.labelled_file l ON l.file_id = fl.file_id WHERE fl.document_id = d.document_id) AS labelled
FROM cat.document d
WHERE coalesce(d.kind_confirmed, d.kind_auto) = ANY(%s) OR d.document_id = ANY(%s)
   OR d.subject_codes_auto IS NOT NULL OR d.subject_person_auto IS NOT NULL OR d.personnel_auto   -- stale values get cleared (coder review)
"""
FILES_SQL = """
SELECT fd.document_id, f.file_id, f.name, f.path_segments
FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
WHERE fd.document_id = ANY(%s) AND f.removed_run IS NULL AND f.trashed IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'
"""
ENT_SQL = "SELECT fd.document_id, e.entity_code FROM cat.file_document fd JOIN cat.v_file_entity e ON e.file_id = fd.file_id WHERE fd.document_id = ANY(%s)"
# the latest app decision per document and field (Match subject lane / Find side panel), with its time
EVENTS_SQL = """
SELECT DISTINCT ON (document_id) document_id, edits -> %s AS v, created_at
FROM app.review_event WHERE document_id IS NOT NULL AND edits ? %s ORDER BY document_id, event_id DESC
"""
LAST_READBACK_SQL = "SELECT max(finished_at) FROM ops.label_sync_run WHERE mode = 'readback' AND applied AND finished_at IS NOT NULL"


def fund_gp_entities(cur):
    """fund entity -> (its GP's entity, the fund's GP-row partner code). The GP row's legal / display name equals a
    Datum GP company's name; names are compared in memory only."""
    cur.execute("SELECT DISTINCT lower(btrim(datum_company_name)), entity_code FROM ref.party WHERE datum_company_kind = 'gp' AND entity_code IS NOT NULL")
    gp_by_name = dict(cur.fetchall())
    cur.execute("SELECT entity_code, partner_code, lower(btrim(legal_name)), lower(btrim(display_name)) FROM ref.party WHERE is_company_gp AND entity_code IS NOT NULL AND interest_kind = 'capital'")
    out = {}
    for e, p, ln, dn in cur.fetchall():
        g = gp_by_name.get(ln) or gp_by_name.get(dn)
        if g and e not in out:
            out[e] = (g, p)
    return out


def run(conn, apply=False, staff=None, log=print):
    t0 = time.time()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT entity_code, partner_code, is_company_gp FROM ref.party WHERE entity_code IS NOT NULL")
    party = cur.fetchall()
    gp_of_fund = fund_gp_entities(cur)            # fund entity -> (GP entity, GP-row partner code)
    cur.execute("SELECT partner_code, alias FROM ref.party_alias")
    idx = RosterIndex(party, cur.fetchall())
    gp_entities = {r[0] for r in cur.execute("SELECT entity_code FROM ref.entity WHERE entity_type = 'gp'")}
    # an app decision newer than the last read-back wins over the label read back (coder review: a second app
    # correction, or one made while the Subject fields are unpublished, must not be lost); older ones the label owns
    last_rb = cur.execute(LAST_READBACK_SQL).fetchone()[0]
    newer = lambda at: last_rb is None or at > last_rb
    ev_codes = {d: [c for c in (v or []) if isinstance(c, str) and CODE_RE.match(c)] for d, v, at in cur.execute(EVENTS_SQL, ("subject_codes", "subject_codes")) if newer(at) and isinstance(v, list)}
    ev_person = {d: (v if isinstance(v, str) and STAFF_EMAIL.match(v) else None) for d, v, at in cur.execute(EVENTS_SQL, ("subject_person", "subject_person")) if newer(at)}
    events = ev_codes
    # CAT-WO-05 R-031: the partner a document was POSTED to in the LP / GP portal (codes only; mapped to the Datum roster)
    import portals_wo05
    portal = portals_wo05.doc_partners(cur)
    cur.execute(DOCS_SQL, (list(ROSTER_KINDS + GP_AGREEMENT_KINDS), list(set(ev_codes) | set(ev_person) | set(portal))))
    docs = {r[0]: r for r in cur.fetchall()}
    ids = list(docs)
    files = collections.defaultdict(list)
    ents = collections.defaultdict(set)
    for i in range(0, len(ids), 5000):
        cur.execute(FILES_SQL, (ids[i:i + 5000],))
        for did, fid, name, segs in cur.fetchall():
            files[did].append((name or "", segs or []))
        cur.execute(ENT_SQL, (ids[i:i + 5000],))
        for did, e in cur.fetchall():
            ents[did].add(e)
    # personnel candidates: any document whose files' names carry a personnel marker (any kind, or none)
    cur.execute("""SELECT DISTINCT fd.document_id FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
                   WHERE f.removed_run IS NULL AND coalesce(f.handling, 'secret') <> 'secret' AND f.name ~* %s""",
                (PERSONNEL_NAME.pattern.replace("(?i)", "").replace(r"\b", r"\y"),))
    pers_ids = {r[0] for r in cur.fetchall()} - set(docs)
    if pers_ids:
        cur.execute(DOCS_SQL.replace("coalesce(d.kind_confirmed, d.kind_auto) = ANY(%s) OR ", ""), (list(pers_ids),))
        for r in cur.fetchall():
            docs[r[0]] = r
        cur.execute(FILES_SQL, (list(pers_ids),))
        for did, fid, name, segs in cur.fetchall():
            files[did].append((name or "", segs or []))

    rows_party, upd = [], []
    rep = collections.defaultdict(collections.Counter)        # kind -> outcome counts (labelled documents)
    cover = collections.defaultdict(collections.Counter)      # kind -> code / person / both / none (labelled)
    results = {}
    for did, r in docs.items():
        _, kind, fy, ent_conf, issuing, receiving, conf, auto_old, person_old, rule_old, pers_old, labelled = r
        fl = files.get(did, [])
        names = [n for n, _ in fl]
        segs = sorted({s for _, ss in fl for s in ss})
        entities = set(ent_conf) if ent_conf is not None else set(ents.get(did, ()))
        if issuing: entities.add(issuing)
        is_pers = personnel(names)
        roster_doc = kind in ROSTER_KINDS or (kind in GP_AGREEMENT_KINDS and entities & gp_entities)
        outcome, matches, rule = "not_a_roster_kind", [], None
        person_codes = events[did] if did in events else conf
        if person_codes is not None:
            outcome = "confirmed" if person_codes else "confirmed_none"
            matches = [(p, None, "person" if did in events else "label") for p in person_codes]
            rule = "SUBJ-PERSON"
        elif roster_doc and kind in ("k1", "capital_statement") and issuing in gp_of_fund and gp_of_fund[issuing][0] in (receiving or ()):
            outcome, matches, rule = "high", [(gp_of_fund[issuing][1], issuing, "parties")], "SUBJ-PARTIES"
        elif roster_doc:
            # issued documents: the issuer's roster only (a K-1 is issued to one of the ISSUER's partners)
            roster_ents = {issuing} if (kind in ("k1", "capital_statement") and issuing) else entities
            outcome, matches = match_doc(idx, roster_ents, names, segs)
            rule = {"high": "SUBJ-HIGH", "low": "SUBJ-LOW"}.get(outcome)
        if person_codes is None and did in portal:
            # a posting is the strongest evidence: the posted-to partner(s) are high; a high name/folder match is kept
            pm = [(p, e, "portal") for p, e, _h in sorted(portal[did], key=lambda x: x[0])]
            have = {p for p, _, _ in pm}
            matches = pm + ([m for m in matches if m[0] not in have] if outcome == "high" else [])
            outcome, rule = "high", ("SUBJ-PORTAL" if rule != "SUBJ-HIGH" else "SUBJ-PORTAL+HIGH")
            roster_doc = True
        results[did] = (r, outcome, matches, rule, person_codes, roster_doc, is_pers, names)
    # Part 2's K1-R2 marks a GP as the RECEIVER; a GP gets one or a few K-1s a year from its fund. More than
    # PARTIES_MAX documents for one fund / GP / year are probably K-1s the GP issued to its members: low (Match subject).
    crowd = collections.Counter((m[0][1], m[0][0], r[2]) for r, o, m, ru, *_ in results.values() if ru == "SUBJ-PARTIES")
    downgraded = 0
    for did, (r, outcome, matches, rule, person_codes, roster_doc, is_pers, names) in list(results.items()):
        if rule == "SUBJ-PARTIES" and crowd[(matches[0][1], matches[0][0], r[2])] > PARTIES_MAX:
            results[did] = (r, "low", matches, "SUBJ-PARTIES-CROWDED", person_codes, roster_doc, is_pers, names)
            downgraded += 1
    for did, (r, outcome, matches, rule, person_codes, roster_doc, is_pers, names) in results.items():
        _, kind, fy, ent_conf, issuing, receiving, conf, auto_old, person_old, rule_old, pers_old, labelled = r
        auto = sorted(p for p, _, m in matches) if outcome == "high" else None
        for p, e, m in matches:
            rows_party.append((did, p, e, m, "confirmed" if outcome.startswith("confirmed") else outcome))
        # without the directory (no --directory-token) the last machine value is KEPT, never cleared (coder review)
        sp = (staff_match(staff, names) if is_pers else None) if staff is not None else person_old
        if (auto or None) != (auto_old or None) or sp != person_old or rule != rule_old or bool(is_pers) != bool(pers_old):
            upd.append((auto, sp, rule, is_pers or None, did))
        if labelled and (roster_doc or is_pers or person_codes is not None):
            k = kind or "(none)"
            rep[k][outcome] += 1
            has_code = bool(person_codes) or bool(auto)
            has_person = bool(sp)
            cover[k]["both" if has_code and has_person else "code" if has_code else "person" if has_person else "none"] += 1
    if apply:
        cur.execute("TRUNCATE cat.doc_party")
        cur.executemany("INSERT INTO cat.doc_party (document_id, partner_code, entity_code, method, confidence) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", rows_party)
        cur.executemany("UPDATE cat.document SET subject_codes_auto=%s, subject_person_auto=%s, subject_rule=%s, personnel_auto=%s, updated_at=now() WHERE document_id=%s", upd)
        # app decisions newer than the last read-back become the person's values ('{}' = "none"; a cleared person = NULL)
        cur.executemany("UPDATE cat.document SET subject_codes_confirmed=%s::text[], updated_at=now() WHERE document_id=%s", [(v, d) for d, v in ev_codes.items()])
        cur.executemany("UPDATE cat.document SET subject_person_confirmed=%s, updated_at=now() WHERE document_id=%s", [(v, d) for d, v in ev_person.items()])
        conn.commit()
    else:
        conn.rollback()
    log(f"SUBJECT {'APPLIED' if apply else 'DRY RUN (nothing written)'}: documents {len(docs):,} · doc_party rows {len(rows_party):,} · "
        f"documents changed {len(upd):,} · K1-R2 parties matches sent to Match subject (crowded fund/GP/year) {downgraded:,} · staff directory {'used' if staff else 'not available (skipped)'} · {time.time() - t0:.0f}s")
    log("  labelled documents by kind: outcome (high / low / none / no_roster / confirmed)")
    for k in sorted(rep, key=lambda k: -sum(rep[k].values())):
        v = rep[k]
        log(f"    {k:30} n={sum(v.values()):6,}  " + "  ".join(f"{o}={v[o]:,}" for o in ("high", "low", "none", "no_roster", "confirmed", "confirmed_none", "not_a_roster_kind") if v[o]))
    log("  subject coverage by kind (labelled): code / person / both / none")
    for k in sorted(cover, key=lambda k: -sum(cover[k].values())):
        v = cover[k]
        log(f"    {k:30} code={v['code']:,} person={v['person']:,} both={v['both']:,} none={v['none']:,}")
    return rep, cover


def load_staff(token_file):
    """[(email, [display name variants])] from the Workspace directory (People API, directory.readonly). In memory only."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    c = Credentials.from_authorized_user_file(token_file, ["https://www.googleapis.com/auth/directory.readonly"])
    if not c.valid:
        # CISO review: never refreshed here; bring a fresh short-lived token (outside the repo, deleted after)
        sys.exit("REFUSED: the directory token is expired; get a fresh one (this step never refreshes it)")
    svc = build("people", "v1", credentials=c, cache_discovery=False)
    out, tok = [], None
    while True:
        r = svc.people().listDirectoryPeople(readMask="names,emailAddresses", sources=["DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE"],
                                             pageSize=500, pageToken=tok).execute()
        for p in r.get("people", []):
            em = next((e["value"].lower() for e in p.get("emailAddresses", []) if STAFF_EMAIL.match(e.get("value", "").lower())), None)
            nm = [n.get("displayName", "") for n in p.get("names", []) if n.get("displayName")]
            if em and nm:
                out.append((em, nm))
        tok = r.get("nextPageToken")
        if not tok:
            return out


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--directory-token", help="OAuth token json with directory.readonly (staff subjects); optional")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    staff = load_staff(a.directory_token) if a.directory_token else None
    with psycopg.connect(url) as conn:
        run(conn, apply=a.apply, staff=staff)


if __name__ == "__main__":
    main()
