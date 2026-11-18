r"""Run a migration file through psycopg (no psql on this machine). Same guard as the WO-03 pipeline: main is refused
unless --release.   py scripts\run_sql_wo03.py --db-url-file <url file> db\migrations\005_wo03.sql [--release]"""
import argparse, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg

ap = argparse.ArgumentParser()
dbg.add_args(ap)
ap.add_argument("files", nargs="+")
a = ap.parse_args()
url = dbg.checked_url(a.db_url_file, a.release)
import psycopg
with psycopg.connect(url, autocommit=True) as con:
    for f in a.files:
        t = time.time()
        con.execute(open(f, encoding="utf-8").read())   # the files carry their own BEGIN / COMMIT blocks
        print(f"ran {os.path.basename(f)} in {time.time() - t:.1f}s")
