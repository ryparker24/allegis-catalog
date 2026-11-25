r"""CAT-WO-14 release steps on MAIN (Ryan's go-ahead 2026-11-25). Run AFTER migration 014 and with the nightly disabled.

  py scripts\release_wo14.py --db-url-file <main url file> --release derive      (derive + portal first-page reading + subject + checklists)
  py scripts\release_wo14.py --db-url-file <main url file> --release labels      (label the in-scope portal files: Drive WRITE)

derive: the same phases as the dry run (scripts/dryrun_wo14_report.py) without the option-B pass: folder ancestors, server rules,
documents, content checks, apply_derive (pages off), page 1 of the portal PCAP / K-1 / capital-call documents (Drive READ),
content check, subject, checklists; prints PCAP-Q / K1-SET counts.
labels: label_new_wo061.run(apply=True) - every unlabelled file in the label scope (now incl. the two portal subtrees), the
catalog's values, Catalog Review = Needs review; a file that already carries a label is left to the read-back.
Codes and counts only."""
import argparse, datetime, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg

PORTAL_FILES = """SELECT f.file_id FROM cat.file f
WHERE f.drive_name IS NULL AND f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
  AND f.noise_flag IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret' AND ops.in_label_scope(f.drive_name, f.folder_path, true)"""


def q(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchall() if cur.description else None
    con.commit()
    return r


def drive_svc():
    import pages_wo06 as pw
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    if home not in sys.path: sys.path.insert(0, home)
    cwd = os.getcwd(); os.chdir(home)                    # the crawler's token file lives there (never read here)
    import drive_crawl as dc
    dc.InstalledAppFlow = pw._NoBrowser
    from googleapiclient.discovery import build
    svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
    os.chdir(cwd)
    return svc


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("step", choices=["derive", "labels"])
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    connect = lambda: psycopg.connect(url)
    lg = lambda m: print(m, flush=True)
    with connect() as con:
        if not q(con, "SELECT to_regclass('ops.label_scope') IS NOT NULL")[0][0]:
            sys.exit("REFUSED: migration 014 is not on this database")
    if a.step == "derive":
        os.environ["CATWO06_PAGES"] = "0"
        with connect() as con:
            for fn in ("ops.rebuild_folder_ancestors()", "ops.apply_rules()", "ops.build_documents()", "ops.apply_content_checks()"):
                t = time.time(); rows = q(con, f"SELECT * FROM {fn}")
                lg(f"  {fn}: " + (", ".join(f"{r[0]} {r[1]}" for r in rows if len(r) > 1) if rows and len(rows[0]) > 1 else "done") + f" ({time.time() - t:.0f}s)")
            import apply_derive_wo02
            apply_derive_wo02.run(con, apply=True, log=lg)
        import pages_wo06 as pw
        pw.net_guard()
        svc = drive_svc()
        with connect() as con:
            docs = [r[0] for r in q(con, f"""SELECT DISTINCT fd.document_id FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                                             JOIN cat.document x ON x.document_id = fd.document_id
                                             WHERE f.file_id IN ({PORTAL_FILES}) AND coalesce(x.kind_confirmed, x.kind_auto) IN ('capital_statement', 'k1', 'capital_call_notice')""")]
            pw.run(con, svc, incremental=False, limit=None, apply=True, log=lg, only_ids=docs, connect=connect)
        with connect() as con:
            pw.apply_content(con, apply=True, log=lg)
        import subject_wo03, requirements_wo03, portal_wo14
        with connect() as con:
            subject_wo03.run(con, apply=True, staff=None, log=lg)
        with connect() as con:
            portal_wo14.apply(con, apply=True, log=lg)
            requirements_wo03.run_build(con, datetime.date.today(), apply=True, log=lg)
            for r in q(con, """SELECT rule_id, result, count(*) FROM app.v_requirement WHERE rule_id IN ('PCAP-Q', 'K1-SET')
                               GROUP BY 1, 2 ORDER BY 1, 2"""):
                lg(f"  {r[0]:8} {r[1]:12} {r[2]:,}")
    else:
        import catalog_labels as cl, label_new_wo061 as ln
        svc = drive_svc()
        rep, _ = ln.run(connect, svc, cl.Schema(cl.load_schema()), apply=True, log=lg)
        lg(f"LABELS done: " + ", ".join(f"{k} {v}" for k, v in sorted(rep.items()) if not isinstance(v, dict)))


if __name__ == "__main__":
    main()
