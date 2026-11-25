r"""CAT-WO-14 dry run on a THROWAWAY branch: Partner Portal + LP Portal (Published Docs) copies.

  py scripts\dryrun_wo14_report.py --db-url-file <throwaway url file> --out docs\CAT-WO-14_DRYRUN.md [--no-pages]

Phases (each on its own connection, committed; the branch is a throwaway):
  0  BEFORE: checklist build as the code stands (CAT-WO-13 cadence, if migration 013 is in), snapshot
  1  migration 014 (label scope, folder rules, R-059); R-059 set to B for the first pass
  2  the would-be labels: in-scope portal files join app.labelled_file (source catwo14-dryrun) - Drive is NOT written;
     the label writes are counted from the catalog's values (label_new_wo061.full_mods)
  3  derive: folder ancestors, server rules, documents, content checks, apply_derive (pages off here)
  4  first-page reading of the portal PCAP / K-1 / capital-call documents (Drive READS only), content check, subject
  5  option B checklist build, snapshot; then R-059 = A (Ryan's ruling), portal status, checklist build, snapshot
Codes and counts only: no file, folder-person, partner or person names."""
import argparse, collections, datetime, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg

PORTAL_FILES = """
SELECT f.file_id FROM cat.file f
WHERE f.drive_name IS NULL AND f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
  AND f.noise_flag IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret' AND ops.in_label_scope(f.drive_name, f.folder_path, true)
"""
SUBTREE = """f.path_segments[2] = 'Confidential - RYAN and CECILIA only' AND f.path_segments[3] IN ('Partner Portal', 'LP Portal (Published Docs)')
             AND f.removed_run IS NULL AND f.trashed IS NOT TRUE"""
# folder level shown in the report: structural names only (never a person's folder)
FOLDER = """CASE WHEN f.path_segments[3] = 'LP Portal (Published Docs)' THEN 'LP Portal / ' || coalesce(f.path_segments[5], '(top)')
                 WHEN f.path_segments[4] = 'Partner Documents' AND f.path_segments[5] IN ('PCAPs', 'K1s') THEN 'Partner Docs / ' || f.path_segments[5] || ' / ' || coalesce(f.path_segments[6], '-')
                 WHEN f.path_segments[4] = 'Partner Documents' AND f.path_segments[5] = 'Capital Calls' THEN 'Partner Docs / Capital Calls / ' || coalesce(f.path_segments[6], '-')
                 WHEN f.path_segments[4] = 'Partner Documents' AND f.path_segments[5] = 'Legal Agreements' THEN 'Partner Docs / Legal Agreements / ' ||
                      CASE WHEN f.path_segments[6] = 'Transfer Agreements' THEN 'Transfer Agreements' ELSE '(GP / fund agreements)' END
                 WHEN f.path_segments[4] = 'Partner Documents' THEN 'Partner Docs / ' || coalesce(f.path_segments[5], '(top)')
                 ELSE 'Partner Portal / ' || coalesce(f.path_segments[4], '(top)') END"""
RULES = ("PCAP-Q", "K1-SET")
RES = ("met", "on_file", "missing", "not_required", "no_roster")


def q(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
    con.commit()
    return rows


def req_snap(con):
    rows = q(con, """SELECT rule_id, entity_code, fiscal_year, fiscal_quarter, result, count(*) FROM app.v_requirement
                     WHERE rule_id = ANY(%s) GROUP BY 1, 2, 3, 4, 5""", (list(RULES),))
    return {(r, e, fy, fq, res): n for r, e, fy, fq, res, n in rows}


def tot(s, rule):
    t = collections.Counter()
    for (r, _, _, _, res), n in s.items():
        if r == rule: t[res] += n
    return t


def folder_kinds(con):
    rows = q(con, f"""SELECT {FOLDER} AS folder, coalesce(d.kind_confirmed, d.kind_auto, '(none)'), count(*)
                      FROM cat.file f LEFT JOIN cat.file_document fd ON fd.file_id = f.file_id LEFT JOIN cat.document d ON d.document_id = fd.document_id
                      WHERE {SUBTREE} GROUP BY 1, 2""")
    return {(a, k): n for a, k, n in rows}


def partner_state(con):
    """per-partner portal documents: matched (a doc_party row high/confirmed), any match, by kind."""
    rows = q(con, f"""WITH d AS (SELECT DISTINCT fd.document_id, coalesce(x.kind_confirmed, x.kind_auto) kind
                                 FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document x ON x.document_id = fd.document_id
                                 WHERE {SUBTREE} AND coalesce(x.kind_confirmed, x.kind_auto) IN ('capital_statement', 'k1', 'capital_call_notice'))
                      SELECT d.kind, count(*),
                             count(*) FILTER (WHERE EXISTS (SELECT 1 FROM cat.doc_party p WHERE p.document_id = d.document_id AND p.confidence IN ('high', 'confirmed'))),
                             count(*) FILTER (WHERE EXISTS (SELECT 1 FROM cat.doc_party p WHERE p.document_id = d.document_id)),
                             count(*) FILTER (WHERE EXISTS (SELECT 1 FROM cat.doc_party p WHERE p.document_id = d.document_id AND p.method = 'content'))
                      FROM d GROUP BY 1 ORDER BY 1""")
    return {k: dict(docs=n, high=h, any=a, content=c) for k, n, h, a, c in rows}


def doc_fields(con):
    return {d: (k, fy, fq) for d, k, fy, fq in q(con, f"""
        SELECT DISTINCT fd.document_id, coalesce(x.kind_confirmed, x.kind_auto), coalesce(x.fiscal_year_confirmed, x.fiscal_year_auto),
               coalesce(x.fiscal_quarter_confirmed, x.fiscal_quarter_auto)
        FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document x ON x.document_id = fd.document_id
        WHERE {SUBTREE}""")}


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-pages", action="store_true", help="skip the first-page reading (no Drive reads)")
    ap.add_argument("--branch-name", default="catwo14-throwaway", help="the throwaway's name, for the report")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: the CAT-WO-14 dry run never runs on main")
    url = dbg.checked_url(a.db_url_file, False)
    connect = lambda: psycopg.connect(url)
    log, T = [], {}
    lg = lambda m: (log.append(m), print(m, flush=True))
    import requirements_wo03 as rq
    today = datetime.date.today()

    # ---- 0 BEFORE
    with connect() as con:
        if q(con, "SELECT to_regclass('ops.label_scope') IS NOT NULL")[0][0]:
            sys.exit("REFUSED: migration 014 is already on this branch - reset the throwaway from main (with 013) first")
        cad = q(con, "SELECT to_regclass('ops.requirement_cadence') IS NOT NULL")[0][0]
        t = time.time(); rq.run_build(con, today, apply=True, log=lg); T["build before"] = time.time() - t
        before = req_snap(con)
        kinds_before = folder_kinds(con)
        partners_before = partner_state(con)
        fields_before = doc_fields(con)
        fin = q(con, f"""WITH p AS (SELECT f.file_id, f.dup_group_id, fd.document_id FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id WHERE {SUBTREE}),
                         fin AS (SELECT f.dup_group_id, array_agg(DISTINCT fd.document_id) docs FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                                 WHERE f.drive_name = 'LIMITED - Finance' AND f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.dup_group_id IS NOT NULL GROUP BY 1)
                    SELECT count(*), count(*) FILTER (WHERE fin.dup_group_id IS NOT NULL), count(*) FILTER (WHERE p.document_id = ANY(fin.docs)),
                           count(*) FILTER (WHERE fin.dup_group_id IS NOT NULL AND NOT p.document_id = ANY(fin.docs)), count(DISTINCT p.document_id),
                           count(DISTINCT p.document_id) FILTER (WHERE p.document_id = ANY(fin.docs))
                    FROM p LEFT JOIN fin ON fin.dup_group_id = p.dup_group_id""")[0]

    # ---- 1 migration 014, option B first
    with psycopg.connect(url, autocommit=True) as mc:
        mc.execute(open(os.path.join(HERE, "..", "db", "migrations", "014_wo14.sql"), encoding="utf-8").read())
    with connect() as con:
        q(con, "UPDATE ops.catalog_setting SET value = 'B' WHERE key = 'R-059'")
        scope_n = q(con, f"""SELECT {FOLDER}, count(*) FROM cat.file f WHERE {SUBTREE} AND f.file_id IN ({PORTAL_FILES}) GROUP BY 1 ORDER BY 1""")
        out_n = q(con, f"""SELECT count(*) FROM cat.file f WHERE {SUBTREE} AND f.file_id NOT IN ({PORTAL_FILES})""")[0][0]
        empty_n = q(con, f"""SELECT count(*) FROM cat.file f WHERE {SUBTREE} AND f.folder_path ILIKE '%%/0_Empty Partner Folders%%'""")[0][0]

    # ---- 2 would-be labels (no Drive write)
    with connect() as con:
        ids = [r[0] for r in q(con, PORTAL_FILES)]
        already = q(con, f"SELECT count(*) FROM app.labelled_file WHERE file_id IN ({PORTAL_FILES})")[0][0]
        q(con, f"INSERT INTO app.labelled_file (file_id, source) SELECT file_id, 'catwo14-dryrun' FROM ({PORTAL_FILES}) s ON CONFLICT DO NOTHING")

    # ---- 3 derive (pages off; they run in phase 4 on the portal documents only)
    os.environ["CATWO06_PAGES"] = "0"
    with connect() as con:
        t = time.time()
        for fn in ("ops.rebuild_folder_ancestors()", "ops.apply_rules()", "ops.build_documents()", "ops.apply_content_checks()"):
            rows = q(con, f"SELECT * FROM {fn}")
            lg(f"  {fn}: " + (", ".join(f"{r[0]} {r[1]}" for r in rows if len(r) > 1) if rows and len(rows[0]) > 1 else "done"))
        T["server derive"] = time.time() - t
        import apply_derive_wo02
        t = time.time(); apply_derive_wo02.run(con, apply=True, log=lg); T["apply_derive"] = time.time() - t

    # ---- 4 first-page reading of portal PCAP / K-1 / capital-call documents (Drive reads), content, subject
    pages_c = None
    if not a.no_pages:
        import pages_wo06 as pw
        pw.net_guard()
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        if home not in sys.path: sys.path.insert(0, home)
        cwd = os.getcwd(); os.chdir(home)               # the crawler's token file lives there (never read here)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        os.chdir(cwd)
        with connect() as con:
            docs = [r[0] for r in q(con, f"""SELECT DISTINCT fd.document_id FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                                             JOIN cat.document x ON x.document_id = fd.document_id
                                             WHERE f.file_id IN ({PORTAL_FILES}) AND coalesce(x.kind_confirmed, x.kind_auto) IN ('capital_statement', 'k1', 'capital_call_notice')""")]
            q(con, "SELECT 1")
            t = time.time()
            pages_c, pages_k, _ = pw.run(con, svc, incremental=False, limit=None, apply=True, log=lg, only_ids=docs, connect=connect)
            T["pages"] = time.time() - t
        with connect() as con:
            pw.apply_content(con, apply=True, log=lg)
    with connect() as con:
        import subject_wo03
        t = time.time(); subject_wo03.run(con, apply=True, staff=None, log=lg); T["subject"] = time.time() - t

    # ---- 5 option B, then option A (Ryan's ruling)
    import portal_wo14
    with connect() as con:
        portal_wo14.apply(con, apply=True, log=lg)
        rq.run_build(con, today, apply=True, log=lg)
        snap_b = req_snap(con)
    with connect() as con:
        q(con, "UPDATE ops.catalog_setting SET value = 'A' WHERE key = 'R-059'")
        pa = portal_wo14.apply(con, apply=True, log=lg)
        rq.run_build(con, today, apply=True, log=lg)
        snap_a = req_snap(con)
        kinds_after = folder_kinds(con)
        partners_after = partner_state(con)
        fields_after = doc_fields(con)
        ents = q(con, f"""SELECT {FOLDER}, coalesce(string_agg(DISTINCT e.entity_code, ', '), '(none)'), count(DISTINCT f.file_id)
                          FROM cat.file f LEFT JOIN cat.v_file_entity e ON e.file_id = f.file_id
                          WHERE {SUBTREE} AND f.file_id IN ({PORTAL_FILES}) AND ({FOLDER}) ~ '(PCAPs|K1s|Capital Calls|Final PCAPs|K-1s)'
                          GROUP BY 1 ORDER BY 1""")
        hand = q(con, f"""SELECT coalesce(f.handling, '-'), coalesce(x.pii_lp_flag_confirmed, x.pii_lp_flag_auto, false), count(*)
                          FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document x ON x.document_id = fd.document_id
                          WHERE f.file_id IN ({PORTAL_FILES}) GROUP BY 1, 2 ORDER BY 1, 2""")
        status = q(con, f"""SELECT coalesce(coalesce(x.status_confirmed, x.status_auto), '(none)'), count(DISTINCT x.document_id)
                            FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document x ON x.document_id = fd.document_id
                            WHERE f.file_id IN ({PORTAL_FILES}) GROUP BY 1 ORDER BY 2 DESC""")
        # label writes the nightly `label` step would make (label_new_wo061.full_mods), counted - Drive is not touched
        import catalog_labels as cl, label_new_wo061 as ln
        schema = cl.Schema(cl.load_schema())
        with con.cursor() as cur:
            rows = cl.catalog_rows(cur, ids)
        con.commit()
        lw = collections.Counter(); lf = collections.Counter(); lk = collections.Counter(); lt = collections.Counter()
        for fid in ids:
            r = rows.get(fid)
            if not r:
                lw["no_catalog_row"] += 1; continue
            mods, fields = ln.full_mods(r, schema)
            if not mods:
                lw["secret_skipped"] += 1; continue
            lw["files_to_label"] += 1
            lw["field_writes"] += sum(len(m["fieldModifications"]) for m in mods)
            lf.update(fields); lk[r.get("kind") or "(no kind)"] += 1
            for m in mods:
                if m["labelId"] == schema.S["handling"]["label_id"]:
                    for fm in m["fieldModifications"]:
                        lt["handling field set"] += 1
    changed = collections.Counter()
    for d, (k, fy, fq) in fields_after.items():
        b = fields_before.get(d)
        if b is None: changed["new document"] += 1; continue
        if b[0] != k: changed["kind"] += 1
        if b[1] != fy: changed["fiscal year"] += 1
        if b[2] != fq: changed["quarter"] += 1

    # ---- report
    L = ["# CAT-WO-14 · Partner Portal + LP Portal folders · dry run (throwaway)", "",
         f"Run {datetime.datetime.now():%Y-%m-%d %H:%M} local on throwaway `{a.branch_name}` (main untouched). No Drive or label writes: "
         "Drive was only READ (first-page reading). Codes and counts only.", "",
         "Branch base: `cat-wo-14` sits on `cat-wo-13`, and migration 013 is on this throwaway, so every checklist figure below has the "
         "CAT-WO-13 PCAP cadence applied." if cad else "CAT-WO-13 cadence NOT applied (migration 013 missing on this branch).", "",
         "R-059 = **option A** (Ryan, 2026-11-25): portal copies are Issued and count toward checklists. Option B is shown only for comparison.", "",
         "## Files in scope by folder", "", "| Folder | Files in label scope |", "|---|---:|"]
    L += [f"| {f} | {n:,} |" for f, n in scope_n]
    L += [f"| **Total** | **{sum(n for _, n in scope_n):,}** |", "",
          f"Left out under the two subtrees: {out_n:,} file(s) (\"0_Empty Partner Folders\": {empty_n:,}; secret / noise / shortcut: the rest). "
          f"Already labelled before: {already:,}.", "",
          "## Kinds assigned (files, before -> after)", "", "| Folder | Kind | Before | After |", "|---|---|---:|---:|"]
    for fk in sorted(set(kinds_before) | set(kinds_after)):
        b, c = kinds_before.get(fk, 0), kinds_after.get(fk, 0)
        if b or c: L.append(f"| {fk[0]} | {fk[1]} | {b:,} | {c:,} |")
    L += ["", "Documents under the two subtrees whose machine fields changed: " +
          (", ".join(f"{k} {n:,}" for k, n in sorted(changed.items())) or "none") + f" (of {len(fields_after):,} documents).", "",
          "## Entity from the folder (per-partner folders, files)", "", "| Folder | Entity codes | Files |", "|---|---|---:|"]
    L += [f"| {f} | {e} | {n:,} |" for f, e, n in ents]
    L += ["", "## Partner match (per-partner documents: PCAPs, K-1s, capital calls)", "",
          "| Kind | Documents | High / confirmed before | High / confirmed after | Rate after | Any match after | From page reading |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for k in sorted(set(partners_before) | set(partners_after)):
        b, c = partners_before.get(k, {}), partners_after.get(k, {})
        n = c.get("docs", 0)
        L.append(f"| {k} | {n:,} | {b.get('high', 0):,} | {c.get('high', 0):,} | {(100 * c.get('high', 0) / n if n else 0):.0f}% | {c.get('any', 0):,} | {c.get('content', 0):,} |")
    if pages_c is not None:
        L += ["", "First-page reading of the portal documents: " + ", ".join(f"{k} {v:,}" for k, v in sorted(pages_c.items()) if v) + "."]
    else:
        L += ["", "First-page reading skipped (--no-pages)."]
    L += ["", "## Joined existing Finance documents (exact copies)", "",
          f"Files under the two subtrees: {fin[0]:,}. In a dup group with a Finance file: {fin[1]:,}; of those, already in the Finance file's "
          f"document: {fin[2]:,}; in a different document: {fin[3]:,}. Documents: {fin[4]:,}, of which {fin[5]:,} are Finance documents the "
          "portal copy joins (the Finance copy stays primary: shared-drive copies rank first). No new document is made for an exact copy "
          "(ops.build_documents groups by md5).", "",
          "## Status and handling (portal files, option A)", "", "| Status | Documents |", "|---|---:|"]
    L += [f"| {s} | {n:,} |" for s, n in status]
    L += ["", f"Option A set Issued on {pa.get('set_issued', 0):,} of {pa.get('portal_documents', 0):,} documents with a portal copy "
          "(never a person's status, a superseded version or an executable kind).", "",
          "| Handling tier | Contains LP PII | Files |", "|---|---|---:|"]
    L += [f"| {h} | {'yes' if p else 'no'} | {n:,} |" for h, p, n in hand]
    L += ["", "## Checklists: PCAP-Q and K1-SET (before -> option A; option B for comparison)", "",
          "| Rule | Result | Before | Option A | Option B |", "|---|---|---:|---:|---:|"]
    for r in RULES:
        tb, ta, tB = tot(before, r), tot(snap_a, r), tot(snap_b, r)
        for res in RES:
            if tb[res] or ta[res] or tB[res]:
                L.append(f"| {r} | {res} | {tb[res]:,} | {ta[res]:,} | {tB[res]:,} |")
        L.append(f"| {r} | **rows** | {sum(tb.values()):,} | {sum(ta.values()):,} | {sum(tB.values()):,} |")
    L += ["", "### Per entity (Met / Missing): before -> option A (option B)", "",
          "| Rule | Entity | Met | Missing |", "|---|---|---|---|"]
    for r in RULES:
        for e in sorted({k[1] for k in list(before) + list(snap_a) if k[0] == r}):
            def m(s, res): return sum(n for (rr, ee, _, _, x), n in s.items() if rr == r and ee == e and x == res)
            if any(m(s, "met") != m(before, "met") or m(s, "missing") != m(before, "missing") for s in (snap_a, snap_b)):
                L.append(f"| {r} | {e} | {m(before, 'met')} -> {m(snap_a, 'met')} ({m(snap_b, 'met')}) | {m(before, 'missing')} -> {m(snap_a, 'missing')} ({m(snap_b, 'missing')}) |")
    L += ["", "Entities not listed: no change.", "",
          "## Label writes it would make (nightly `label` step; not written)", "",
          f"Files to label: {lw['files_to_label']:,} · field writes: {lw['field_writes']:,} · Handling field writes: {lt['handling field set']:,}"
          + (f" · no catalog row: {lw['no_catalog_row']:,}" if lw['no_catalog_row'] else "") + (f" · secret skipped: {lw['secret_skipped']:,}" if lw['secret_skipped'] else "")
          + ". Every file also gets Catalog ID and Catalog Review = Needs review.", "",
          "| Field | Files |", "|---|---:|"]
    L += [f"| {k} | {n:,} |" for k, n in lf.most_common()]
    L += ["", "| Kind (labelled) | Files |", "|---|---:|"] + [f"| {k} | {n:,} |" for k, n in lk.most_common()]
    L += ["", "## Timings", "", ", ".join(f"{k} {v:.0f}s" for k, v in T.items()), "", "## Log", "", "```"] + log + ["```", ""]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
