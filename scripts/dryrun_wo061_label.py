r"""CAT-WO-06.1 · dry run of labelling the unlabelled readable files in LIMITED - Finance, on main, WITHOUT writing:
1. label dry run (live labels read, nothing written): files to label by kind / entity / fields
2. simulation in ONE transaction that is rolled back: the files that would be labelled join app.labelled_file, then the
   WO-02 derive part (status ...), Subject and the checklists are rebuilt; Status of those documents and the checklist
   counts are read, then everything is rolled back. Counts and codes only.

  py scripts\dryrun_wo061_label.py --db-url-file <url file> --release
"""
import argparse, collections, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    sys.path.insert(0, home); os.chdir(home)
    import catalog_labels as cl, label_new_wo061 as ln, pages_wo06
    import labels_sync as lsync
    lsync.InstalledAppFlow = pages_wo06._NoBrowser
    from googleapiclient.discovery import build
    svc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)
    rep, ids = ln.run(lambda: psycopg.connect(url), svc, cl.Schema(cl.load_schema()), apply=False)

    os.environ["CATWO06_PAGES"] = "0"
    import apply_derive_wo02, subject_wo03, requirements_wo03
    con = psycopg.connect(url)
    real_commit = con.commit
    con.commit = lambda: None
    q = lambda s, p=(): con.execute(s, p).fetchall()
    try:
        before = collections.Counter({(r, res): n for r, res, n in q("SELECT rule_id, result, count(*) FROM ops.requirement GROUP BY 1, 2")})
        cip0 = dict(q("SELECT result, count(*) FROM ops.requirement WHERE rule_id='PCAP-Q' AND entity_code='CIP-II' AND fiscal_year=2025 AND fiscal_quarter=4 GROUP BY 1"))
        con.execute("INSERT INTO app.labelled_file (file_id, source) SELECT unnest(%s::text[]), 'label_new' ON CONFLICT DO NOTHING", (ids,))
        apply_derive_wo02.run(con, apply=True, log=lambda m: None)
        subject_wo03.run(con, apply=True, staff=None, log=lambda m: None)
        requirements_wo03.run_build(con, apply=True, log=lambda m: None)
        st = q("""SELECT coalesce(coalesce(d.status_confirmed, d.status_auto), '(blank)'), count(DISTINCT d.document_id) FROM cat.file_document fd
                  JOIN cat.document d ON d.document_id = fd.document_id WHERE fd.file_id = ANY(%s) GROUP BY 1 ORDER BY 2 DESC""", (ids,))
        after = collections.Counter({(r, res): n for r, res, n in q("SELECT rule_id, result, count(*) FROM ops.requirement GROUP BY 1, 2")})
        cip1 = dict(q("SELECT result, count(*) FROM ops.requirement WHERE rule_id='PCAP-Q' AND entity_code='CIP-II' AND fiscal_year=2025 AND fiscal_quarter=4 GROUP BY 1"))
        mq = q("SELECT count(*) FROM app.v_review_queue WHERE file_id = ANY(%s)", (ids,))[0][0]
    finally:
        con.rollback()
        con.commit = real_commit
        con.close()
    print(f"\nSIMULATION (rolled back): Status of the {len(ids):,} files' documents after derive: " + ", ".join(f"{s} {n:,}" for s, n in st))
    print("CHECKLISTS before -> after labelling (Met / On file / Missing / No roster):")
    for r in ("K1-SET", "PCAP-Q", "LP-SUB", "LP-SIDE", "GP-COMMIT", "AUDITED-FS"):
        f = lambda c, k: c.get((r, k), 0)
        print(f"  {r:10} Met {f(before,'met'):5} -> {f(after,'met'):5}  On file {f(before,'on_file'):5} -> {f(after,'on_file'):5}  "
              f"Missing {f(before,'missing'):5} -> {f(after,'missing'):5}  No roster {f(before,'no_roster')} -> {f(after,'no_roster')}")
    print(f"  PCAP-Q CIP-II 2025 Q4: {cip0} -> {cip1}")
    print(f"  newly labelled files in the Review queue: {mq:,}")


if __name__ == "__main__":
    main()
