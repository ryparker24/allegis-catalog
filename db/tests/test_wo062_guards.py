r"""
CAT-WO-06.2 · guard: a full derive followed by a second WO-02 pass changes nothing (no Parties / Status / kind flip-flop).
Runs in ONE transaction that is rolled back, so it may run against main (--release): nothing is kept.

  py db\tests\test_wo062_guards.py --db-url-file <url file> [--release]
Counts only.
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "pipeline"))
import dbguard_wo03 as dbg

ap = argparse.ArgumentParser()
dbg.add_args(ap)
a = ap.parse_args()
url = dbg.checked_url(a.db_url_file, a.release)
os.environ["CATWO06_PAGES"] = "0"
os.environ["CATALOG_APP_DIR"] = APP
home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
sys.path.insert(0, home); os.chdir(home)
import psycopg
import drive_crawl as dc
import apply_derive_wo02

SNAP = """SELECT document_id, coalesce(kind_confirmed, kind_auto), issuing_entity_auto, receiving_entities_auto, parties_rule, status_auto, status_rule
          FROM cat.document"""
R = []


def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))


def diff(a, b):
    out = {"kind": 0, "parties": 0, "status": 0}
    for d, x in a.items():
        y = b.get(d)
        if y is None: continue
        out["kind"] += x[0] != y[0]
        out["parties"] += x[1:4] != y[1:4]
        out["status"] += x[4:6] != y[4:6]
    return out


con = psycopg.connect(url)
real = con.commit
con.commit = lambda: None
log = lambda m: None
try:
    snap = lambda: {r[0]: r[1:] for r in con.execute(SNAP).fetchall()}
    s0 = snap()
    dc.derive(con)                       # full derive: rules, build_documents (kinds reset), the WO-02 pass
    s1 = snap()
    apply_derive_wo02.run(con, apply=True, log=log)   # a second WO-02 pass, as the nightly label step does
    s2 = snap()
finally:
    con.rollback(); con.commit = real; con.close()
d01, d12 = diff(s0, s1), diff(s1, s2)
print(f"  documents {len(s0):,} · full derive vs the stored state: {d01} · second pass vs first: {d12}")
check("G-D2 a second WO-02 pass after a full derive changes no kind, Parties or Status (no nightly flip-flop)",
      d12 == {"kind": 0, "parties": 0, "status": 0}, str(d12))
check("G-D3 a full derive reproduces the stored Parties (the values written to Drive on 2026-11-23 stay)",
      d01["parties"] == 0, str(d01))
print(f"\n{sum(R)}/{len(R)} passed (rolled back: nothing kept)")
sys.exit(0 if all(R) else 1)
