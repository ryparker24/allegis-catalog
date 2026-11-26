r"""CAT-WO-16 release steps on MAIN (Ryan 2026-11-26: "Release cat-wo-16 with version 2 of the bank rule"). Run AFTER migration 016,
`bank_wo16.py --load-map`, BANK-L4 v2 activated, with the nightly disabled.

  py scripts\release_wo16.py --db-url-file <main url file> --release derive   (full derive + page 1 + BANK-L4 v2 + checklists)
  py scripts\release_wo16.py --db-url-file <main url file> --release labels   (re-sync the labelled files whose Entity changed)

derive: snapshot the labelled bank-scope files' entities; folder ancestors, server rules, documents, content checks, apply_derive
(pages off: the reads run next, uncapped); page 1 of the scope documents v2's name / path did not match (Drive READ); BANK-L4;
checklists; snapshot again; the labelled files whose Entity changed are listed (file ids only) for the labels step.
labels: label_sync_wo02.resync(only=those files) with the LABEL login (labels_sync.creds), never over a person's value.
Codes and counts only."""
import argparse, collections, datetime, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg

CHANGED = os.path.join(r"C:\DriveCatalog\logs", "release_wo16_changed_file_ids.txt")
SCOPE_FILES = """SELECT x.file_id, coalesce(x.kind, '(no kind)'), x.entities FROM app.v_find_x x JOIN cat.file f ON f.file_id = x.file_id
                 WHERE x.kind IN ('bank_stmt', 'wire_confirmation') OR (x.kind IS NULL AND (f.folder_path ILIKE '%/03-Cash/%' OR f.folder_path ILIKE '%/03-Cash'))"""


def q(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchall() if cur.description else None
    con.commit()
    return r


def snap(con):
    return {f: (k, tuple(sorted(e or []))) for f, k, e in q(con, SCOPE_FILES)}


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("step", choices=["derive", "labels"])
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    connect = lambda: psycopg.connect(url)
    lg = lambda m: print(m, flush=True)
    import bank_wo16 as bw
    with connect() as con:
        cur = con.cursor()
        if not bw.available(cur):
            sys.exit("REFUSED: migration 016 is not on this database")
        v, spec = bw.rule_spec(cur)
        con.commit()
        if v != 2:
            sys.exit(f"REFUSED: the active BANK-L4 version is {v}, not 2")
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    if home not in sys.path: sys.path.insert(0, home)
    import pages_wo06 as pw
    if a.step == "derive":
        with connect() as con:
            before = snap(con)
        os.environ["CATWO06_PAGES"] = "0"; os.environ["CATWO16_PAGES"] = "0"
        with connect() as con:
            for fn in ("ops.rebuild_folder_ancestors()", "ops.apply_rules()", "ops.build_documents()", "ops.apply_content_checks()"):
                t = time.time(); rows = q(con, f"SELECT * FROM {fn}")
                lg(f"  {fn}: " + (", ".join(f"{r[0]} {r[1]}" for r in rows if len(r) > 1) if rows and len(rows[0]) > 1 else "done") + f" ({time.time() - t:.0f}s)")
            import apply_derive_wo02
            apply_derive_wo02.run(con, apply=True, log=lg)
        pw.net_guard()
        cwd = os.getcwd(); os.chdir(home)                   # the crawler's token file lives there (never read here)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        os.chdir(cwd)
        with connect() as con:
            cur = con.cursor()
            l4 = bw.load_map(cur); rx = bw.cue_regex(l4)
            todo = bw.unmatched_by_name_path(bw.scope(cur), rx, l4, spec)
            con.commit()
            con, _ = bw.read_pages(con, svc, todo, rx, l4, log=lg, connect=connect)
        with connect() as con:
            res = bw.apply(con, apply=True, log=lg)
            oc = collections.Counter()
            for (k, o), n in res["outcomes"].items():
                oc[o] += n
            lg("BANK-L4 v2 outcomes: " + ", ".join(f"{o} {n:,}" for o, n in sorted(oc.items())))
        import requirements_wo03
        with connect() as con:
            requirements_wo03.run_build(con, datetime.date.today(), apply=True, log=lg)
        with connect() as con:
            after = snap(con)
            lane = q(con, """SELECT count(DISTINCT document_id) FROM app.v_review_queue WHERE queue_reason = 'content_disagrees'
                             AND kind IN ('bank_stmt', 'wire_confirmation')""")[0][0]
        changed = sorted(f for f, (k, e) in after.items() if before.get(f) and before[f][1] != e)
        noent = lambda s, kind: sum(1 for k, e in s.values() if k == kind and not e)
        lg(f"labelled bank statements with no entity: {noent(before, 'bank_stmt'):,} -> {noent(after, 'bank_stmt'):,} · "
           f"wire confirmations: {noent(before, 'wire_confirmation'):,} -> {noent(after, 'wire_confirmation'):,} · "
           f"bank documents in Content disagrees: {lane:,} · labelled files whose Entity changed: {len(changed):,}")
        open(CHANGED, "w", encoding="ascii").write("\n".join(changed))
    else:
        ids = [x.strip() for x in open(CHANGED, encoding="ascii").read().split() if x.strip()]
        import catalog_labels as cl, label_sync_wo02 as ls
        cwd = os.getcwd(); os.chdir(home)
        import labels_sync as lsync
        lsync.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        lsvc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)   # the LABEL login (writes)
        os.chdir(cwd)
        hold = open(os.path.join(home, "resync_hold_entities.txt")).read().split() if os.path.exists(os.path.join(home, "resync_hold_entities.txt")) else []
        lg(f"re-sync of {len(ids):,} labelled files whose Entity changed")
        rep = ls.resync(connect, lsvc, cl.Schema(cl.load_schema()), apply=True, only=ids, hold_entities=hold, log=lg)
        lg("LABELS (resync) done: " + ", ".join(f"{k} {v}" for k, v in sorted((rep or {}).items()) if not isinstance(v, dict)))


if __name__ == "__main__":
    main()
