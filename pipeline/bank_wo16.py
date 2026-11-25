r"""
CAT-WO-16 · rule BANK-L4: a bank statement's (or wire confirmation's) entity from the account's last 4 digits.

  py pipeline\bank_wo16.py --db-url-file <url file> --load-map <csv: ryan_label,catalog_code,last4[,note]>   (ref.bank_account)
  py pipeline\bank_wo16.py --db-url-file <url file> [--pages [--limit N]] [--apply]                          (the rule)

Scope: documents of kind bank_stmt / wire_confirmation, and documents with no kind that have a copy under a "03-Cash" folder.
Match: a mapped last 4 as a whole 4-digit token right after an account cue (x1234, ****1234, #1234, "ending 1234", "ending in
1234", acct / account (no.) ...1234). The file names first, then the folder paths, then page 1 (--pages: Drive READ, in memory,
local OCR as CAT-WO-06; the text is never stored). Two different entities found -> ambiguous, nothing set.
Writes (codes only):
  - no machine entity on the document, or the found entity is already one of them: an entity signal on every copy
    (cat.file_signal source 'bank', rule BANK-L4), re-added after every derive
  - a machine entity that contradicts it: NOT written; cat.doc_content_check.content_entity = the found entity, so the
    Content disagrees lane shows the document (CAT-WO-06 content check); nothing is overwritten
  - a person-set entity (entities_confirmed): never touched
Prints codes and counts only - never a name, a path or a digit.
"""
import argparse, collections, csv, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RULE_ID = "BANK-L4"
KINDS = ("bank_stmt", "wire_confirmation")
CASH_FOLDER = "03-Cash"
NIGHTLY_CAP = 300
CUE = (r"(?:(?<![A-Za-z])x|\*{2,}|#|(?<![A-Za-z])ending(?:\s+in)?[\s:]*|(?<![A-Za-z])(?:acc(?:oun)?t|acct)\.?\s*(?:no\.?|number|#)?"
       r"[\s:.\-]*(?:x+|\*+|\.{2,}|-)?\s*)")


# ------------------------------------------------------------------ pure (unit-tested)
def cue_regex(last4s):
    alts = "|".join(sorted({l for l in last4s if re.fullmatch(r"[0-9]{4}", l)}))
    return re.compile(r"(?i)" + CUE + r"(" + (alts or "(?!x)x") + r")(?![0-9])") if alts else None


def find_codes(text, rx, l4map):
    """-> set of entity codes whose last 4 appears after an account cue in `text` (whole token)."""
    if not text or rx is None:
        return set()
    out = set()
    for m in rx.finditer(text):
        out |= l4map.get(m.group(1), set())
    return out


def decide(names, paths, page_codes, person_set, auto_ents, l4map, rx):
    """One document. -> (outcome, code|None, source|None).
    outcome: person | ambiguous | conflict | agrees | set | none."""
    if person_set:
        return "person", None, None
    for source, texts in (("name", names), ("path", paths)):
        found = set()
        for t in texts:
            found |= find_codes(t, rx, l4map)
        if found:
            break
    else:
        source, found = ("page1", set(page_codes or ())) if page_codes else (None, set())
    if not found:
        return "none", None, None
    if len(found) > 1:
        return "ambiguous", None, source
    code = next(iter(found))
    if auto_ents and code not in auto_ents:
        return "conflict", code, source
    return ("agrees" if code in (auto_ents or ()) else "set"), code, source


def unmatched_by_name_path(docs, rx, l4map):
    """the documents page 1 is read for: a person has not set the entity and no name / path gives a last 4"""
    return [d for d in docs if not d.get("person")
            and not any(find_codes(t, rx, l4map) for t in (d.get("names") or []) + (d.get("paths") or []))]


# ------------------------------------------------------------------ DB
def available(cur):
    cur.execute("SELECT to_regclass('ref.bank_account') IS NOT NULL")
    return bool(cur.fetchone()[0])


def load_map(cur):
    cur.execute("SELECT last4, entity_code FROM ref.bank_account")
    m = collections.defaultdict(set)
    for l4, e in cur.fetchall():
        m[l4].add(e)
    return m


def load_map_csv(conn, path, log=print):
    """ref.bank_account from Ryan's map. Codes not in ref.entity are listed (codes only) and skipped, never invented."""
    cur = conn.cursor()
    cur.execute("SELECT entity_code FROM ref.entity")
    known = {r[0] for r in cur.fetchall()}
    rows, unknown = [], collections.Counter()
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        l4, code = (r.get("last4") or "").strip(), (r.get("catalog_code") or "").strip()
        if not re.fullmatch(r"[0-9]{4}", l4) or not code:
            unknown["(bad row)"] += 1; continue
        if code not in known:
            unknown[code] += 1; continue
        rows.append((l4, code, (r.get("ryan_label") or "").strip() or None, (r.get("note") or "").strip() or None))
    cur.executemany("""INSERT INTO ref.bank_account (last4, entity_code, ryan_label, note) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (last4, entity_code) DO UPDATE SET ryan_label = EXCLUDED.ryan_label, note = EXCLUDED.note""", rows)
    cur.execute("SELECT last4 FROM ref.bank_account GROUP BY 1 HAVING count(*) > 1")
    shared = len(cur.fetchall())
    conn.commit()
    log(f"BANK MAP: {len(rows)} rows loaded · {len({c for _, c, _, _ in rows})} entities · not in ref.entity (skipped): "
        + (", ".join(f"{c} ({n})" for c, n in sorted(unknown.items())) or "none") + f" · last-4s mapped to 2+ entities: {shared}")
    return dict(loaded=len(rows), unknown=dict(unknown), shared=shared)


DOCS_SQL = """
WITH d AS (
  SELECT DISTINCT fd.document_id
  FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id JOIN cat.document x ON x.document_id = fd.document_id
  WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret' AND f.noise_flag IS NOT TRUE
    AND (coalesce(x.kind_confirmed, x.kind_auto) = ANY(%(kinds)s)
         OR (coalesce(x.kind_confirmed, x.kind_auto) IS NULL AND (f.folder_path ILIKE %(cash1)s OR f.folder_path ILIKE %(cash2)s)))
)
SELECT x.document_id, coalesce(x.kind_confirmed, x.kind_auto), x.entities_confirmed IS NOT NULL,
       array_agg(DISTINCT f.file_id), array_agg(DISTINCT f.name), array_agg(DISTINCT f.folder_path)
FROM d JOIN cat.document x ON x.document_id = d.document_id
JOIN cat.file_document fd ON fd.document_id = x.document_id JOIN cat.file f ON f.file_id = fd.file_id
WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'
GROUP BY 1, 2, 3
"""


def auto_entities(cur, ids):
    """machine entities per document (non-generic, from any copy), WITHOUT this rule's own signals"""
    cur.execute("""SELECT fd.document_id, array_agg(DISTINCT e.entity_code)
                   FROM cat.file_document fd JOIN cat.v_file_entity e ON e.file_id = fd.file_id
                   WHERE fd.document_id = ANY(%s) AND NOT coalesce(e.from_generic_only, false) AND e.via <> 'bank'
                   GROUP BY 1""", (ids,))
    return {d: set(e) for d, e in cur.fetchall()}


def scope(cur):
    cur.execute(DOCS_SQL, {"kinds": list(KINDS), "cash1": f"%/{CASH_FOLDER}/%", "cash2": f"%/{CASH_FOLDER}"})
    return [dict(zip(["document_id", "kind", "person", "files", "names", "paths"], r)) for r in cur.fetchall()]


def read_pages(conn, svc, docs, rx, l4map, limit=None, log=print, connect=None):
    """page 1 of each document not read yet (or changed), in memory; stores codes only in ops.bank_page_read."""
    import pages_wo06 as pw
    cur = conn.cursor()
    cur.execute("SELECT document_id, version_key FROM ops.bank_page_read")
    done = dict(cur.fetchall())
    ids = [d["document_id"] for d in docs]
    cur.execute("""SELECT DISTINCT ON (fd.document_id) fd.document_id, f.file_id, f.mime_type, f.size_bytes,
                          coalesce(f.md5, 'rev:' || coalesce(f.head_revision_id, f.modified_time::text))
                   FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
                   WHERE fd.document_id = ANY(%s) AND f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
                     AND coalesce(f.handling, 'secret') <> 'secret' AND f.noise_flag IS NOT TRUE
                   ORDER BY fd.document_id, (fd.file_role = 'primary') DESC, (f.mime_type = 'application/pdf') DESC, f.file_id""", (ids,))
    todo = [r for r in cur.fetchall() if done.get(r[0]) != r[4]]
    conn.commit()
    if limit is not None:
        todo = todo[:limit]
    exe = pw.tesseract_exe()
    c = collections.Counter()
    t0 = last = time.time()
    batch = []
    for i, (did, fid, mime, size, vk) in enumerate(todo, 1):
        if time.time() - last > 60:
            try: conn.execute("SELECT 1"); conn.commit()
            except Exception:
                if connect is None: raise
                conn = connect()
            last = time.time()
        if pw.fmt_of(mime) not in ("pdf", "gdoc"):
            batch.append((did, vk, "skipped_format", None)); c["skipped_format"] += 1; continue
        try:
            data = pw.download(svc, fid, mime, size)
        except Exception:
            data = False
        if data is None:
            batch.append((did, vk, "too_large", None)); c["too_large"] += 1; continue
        if data is False:
            batch.append((did, vk, "download_error", None)); c["download_error"] += 1; continue
        try:
            rd = pw.Reader(data, exe)
            try:
                text = rd.page(1).text() if rd.n else ""
            finally:
                rd.close()
        except Exception:
            text = None
        del data
        if text is None:
            batch.append((did, vk, "open_error", None)); c["open_error"] += 1; continue
        codes = sorted(find_codes(text, rx, l4map))
        del text
        oc = "ok" if len(codes) == 1 else "multi" if codes else "no_match"
        batch.append((did, vk, oc, codes or None)); c[oc] += 1
        if len(batch) >= 100 or i == len(todo):
            _write_reads(conn, batch); batch = []
            log(f"  bank page 1: {i:,}/{len(todo):,} read")
    if batch:
        _write_reads(conn, batch)
    log(f"BANK PAGES: read {len(todo):,} · {time.time() - t0:.0f}s · " + " · ".join(f"{k} {v:,}" for k, v in sorted(c.items())))
    return conn, c


def _write_reads(conn, rows):
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO ops.bank_page_read (document_id, version_key, outcome, codes, read_at) VALUES (%s, %s, %s, %s, now())
                           ON CONFLICT (document_id) DO UPDATE SET version_key = EXCLUDED.version_key, outcome = EXCLUDED.outcome,
                             codes = EXCLUDED.codes, read_at = now()""", rows)
    conn.commit()


def apply(conn, apply=True, log=print):
    """BANK-L4 over the scope: signals (re-added after every derive) and Content-disagrees entities. Commits when apply."""
    cur = conn.cursor()
    if not available(cur):
        return {}
    l4map = load_map(cur)
    rx = cue_regex(l4map)
    cur.execute("SELECT version FROM ops.decomposition_rule WHERE rule_id = %s AND active ORDER BY version DESC LIMIT 1", (RULE_ID,))
    v = cur.fetchone()
    if v is None or rx is None:
        conn.rollback(); log("BANK-L4: rule inactive or map empty - nothing done"); return {}
    version = v[0]
    docs = scope(cur)
    ids = [d["document_id"] for d in docs]
    cur.execute("DELETE FROM cat.file_signal WHERE rule_id = %s", (RULE_ID,))    # this rule's signals only (re-derived below)
    auto = auto_entities(cur, ids)
    cur.execute("SELECT document_id, codes FROM ops.bank_page_read WHERE outcome IN ('ok', 'multi')")
    pages = {d: set(c or ()) for d, c in cur.fetchall()}
    sig, content, out = [], [], collections.Counter()
    by_ent, by_src = collections.Counter(), collections.Counter()
    for d in docs:
        oc, code, src = decide(d["names"] or [], d["paths"] or [], pages.get(d["document_id"]), d["person"], auto.get(d["document_id"]), l4map, rx)
        out[(d["kind"] or "(no kind)", oc)] += 1
        if src: by_src[src] += 1
        if oc in ("set", "agrees"):
            by_ent[code] += 1
            sig += [(f, "entity", code.upper(), RULE_ID, version, 5, "bank", 0, RULE_ID) for f in d["files"]]
            content.append((d["document_id"], d["files"][0], code))
        elif oc == "conflict":
            content.append((d["document_id"], d["files"][0], code))
    if sig:
        with cur.copy("COPY cat.file_signal (file_id, field, value, rule_id, rule_version, priority, source, distance, matched) FROM STDIN") as cp:
            cp.set_types(["text", "text", "text", "text", "int4", "int4", "text", "int4", "text"])
            for r in sig:
                cp.write_row(r)
    # the found entity as the document's content entity (the CAT-WO-06 content check compares it with the document's entities:
    # a contradiction -> Content disagrees). content_read_at moves only when the entity changes (a decided lane row stays closed).
    cur.executemany("""INSERT INTO cat.doc_content_check (document_id, file_id, content_entity, content_read_at) VALUES (%s, %s, %s, now())
                       ON CONFLICT (document_id) DO UPDATE SET content_entity = EXCLUDED.content_entity,
                         content_read_at = CASE WHEN cat.doc_content_check.content_entity IS DISTINCT FROM EXCLUDED.content_entity
                                                THEN now() ELSE coalesce(cat.doc_content_check.content_read_at, now()) END
                       WHERE cat.doc_content_check.content_entity IS NULL OR cat.doc_content_check.content_entity = EXCLUDED.content_entity
                          OR cat.doc_content_check.content_read_at IS NULL""", content)
    if apply:
        conn.commit()
        import pages_wo06
        pages_wo06.apply_content(conn, apply=True, log=log)
    else:
        conn.rollback()
    log(f"BANK-L4 {'APPLIED' if apply else 'DRY RUN'}: documents {len(docs):,} · signals {len(sig):,} on "
        f"{sum(by_ent.values()):,} documents · conflicts {sum(n for (k, o), n in out.items() if o == 'conflict'):,} · by source "
        + ", ".join(f"{k} {n:,}" for k, n in sorted(by_src.items())))
    return dict(outcomes=out, by_entity=by_ent, by_source=by_src, documents=len(docs), signals=len(sig))


def nightly_step(conn, log=print, cap=NIGHTLY_CAP):
    """after derive: page 1 of new / changed scope documents (capped; a Drive failure never stops the nightly), then the rule."""
    cur = conn.cursor()
    if not available(cur):
        return
    conn.commit()
    if os.environ.get("CATWO16_PAGES", "1") != "0":
        try:
            home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
            if home not in sys.path: sys.path.insert(0, home)
            import drive_crawl as dc
            from googleapiclient.discovery import build
            svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
            l4map = load_map(cur); rx = cue_regex(l4map)
            conn, _ = read_pages(conn, svc, unmatched_by_name_path(scope(cur), rx, l4map), rx, l4map, limit=cap, log=log)
        except (Exception, SystemExit) as e:
            conn.rollback()
            log(f"   bank pages NOT run ({type(e).__name__}); earlier reads stay in use")
    apply(conn, apply=True, log=log)


def main():
    import psycopg
    import dbguard_wo03 as dbg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--load-map")
    ap.add_argument("--pages", action="store_true", help="read page 1 of scope documents not matched by name / path (Drive read)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    with psycopg.connect(url) as conn:
        if a.load_map:
            load_map_csv(conn, a.load_map); return
        if a.pages:
            import pages_wo06 as pw
            pw.net_guard()
            home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
            if home not in sys.path: sys.path.insert(0, home)
            cwd = os.getcwd(); os.chdir(home)
            import drive_crawl as dc
            dc.InstalledAppFlow = pw._NoBrowser
            from googleapiclient.discovery import build
            svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
            os.chdir(cwd)
            cur = conn.cursor()
            l4map = load_map(cur); rx = cue_regex(l4map)
            conn, _ = read_pages(conn, svc, unmatched_by_name_path(scope(cur), rx, l4map), rx, l4map, limit=a.limit,
                                 connect=lambda: psycopg.connect(url))
        apply(conn, apply=a.apply)


if __name__ == "__main__":
    main()
