r"""CAT-WO-06 release: read the FY2025-onward candidates first (K-1 / PCAP with FY >= 2025 or blank FY in a roster entity,
plus all subscription agreements and side letters), so the dry run is not gated on the full backfill. The rest of the
backlog is left to the nightly cap. Counts only.

  py scripts\release_wo06_targeted_read.py --db-url-file <url file> [--release] [--apply]
"""
import argparse, collections, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline")); sys.path.insert(0, HERE)
import dbguard_wo03 as dbg
import pages_wo06 as pw
from measure_wo06_targeted import CAND_SQL


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    pw.net_guard()
    con = psycopg.connect(url); cur = con.cursor()
    cur.execute(CAND_SQL, (list(pw.KINDS),))
    cand = dict(cur.fetchall())
    docs = {d["document_id"]: d for d in pw.scope(cur)}
    readable = [d for d in cand if d in docs and pw.fmt_of(docs[d]["mime"]) in ("pdf", "gdoc")]
    con.commit()
    print(f"FY2025+ candidates {len(cand):,} · readable {len(readable):,} · "
          + ", ".join(f"{k} {n:,}" for k, n in sorted(collections.Counter(cand[d] for d in readable).items())))
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    sys.path.insert(0, home); os.chdir(home)
    import drive_crawl as dc
    dc.InstalledAppFlow = pw._NoBrowser
    from googleapiclient.discovery import build
    svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
    t0 = time.time()
    pw.run(con, svc, incremental=True, apply=a.apply, log=print, only_ids=readable, connect=lambda: psycopg.connect(url))
    print(f"read time {(time.time() - t0) / 60:.0f} min · memory peak {pw.mem_mb()[1]} MB")
    con = psycopg.connect(url)
    pw.apply_content(con, apply=a.apply)
    con.close()


if __name__ == "__main__":
    main()
