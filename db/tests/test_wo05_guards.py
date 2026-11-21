r"""
CAT-WO-05 · DB guards for portal postings (008_wo05.sql + pipeline/portals_wo05.py). THROWAWAY BRANCH ONLY.

  py db\tests\test_wo05_guards.py --db-url-file <branch owner url file>

Needs ref.portal_posting loaded (portals_wo05 --apply on the branch). The person-Status test runs in a transaction that
is rolled back. Output: test names and PASS / FAIL only (ids and counts, no names).
"""
import argparse, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
import dbguard_wo03 as dbg
import portals_wo05 as pw

ap = argparse.ArgumentParser()
dbg.add_args(ap)
a = ap.parse_args()
if a.release:
    sys.exit("REFUSED: guard tests never run on main")
URL = dbg.checked_url(a.db_url_file)
import psycopg

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))


conn = psycopg.connect(URL)
cur = conn.cursor()
priv = lambda obj, p: cur.execute("SELECT has_table_privilege('catalog_app', %s, %s)", (obj, p)).fetchone()[0]
check("G-D0 catalog_app reads the posting views only; it cannot read or write the posting tables",
      priv("app.v_doc_posting", "SELECT") and priv("app.v_portal_kind_conflict", "SELECT") and priv("app.v_find_x", "SELECT")
      and not priv("ref.portal_posting", "SELECT") and not priv("ref.portal_posting", "INSERT") and not priv("cat.doc_posting", "SELECT")
      and not priv("ops.portal_kind_conflict", "SELECT") and not priv("ref.portal_fund_map", "UPDATE"))
sb = cur.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'app' AND c.relkind = 'v'
                    AND c.relname IN ('v_find_x', 'v_doc_posting', 'v_portal_kind_conflict')
                    AND 'security_barrier=true' = ANY(c.reloptions)""").fetchone()[0]
check("G-D1 the posting views are security_barrier", sb == 3, f"{sb}/3")

# G-P2 no partner name enters the catalog: the posting tables have no name-like column; every stored value is a code
cols = [r[0] for r in cur.execute("""SELECT column_name FROM information_schema.columns WHERE (table_schema, table_name) IN
         (('ref','portal_posting'), ('cat','doc_posting'), ('ops','portal_kind_conflict'), ('ref','portal_fund_map'), ('ref','portal_export'))""")]
bad_cols = [c for c in cols if re.search(r"(^|_)(name|title|display|legal|email|investor|member_name|address)(_|$)", c) and c != "file_name"]
code_ok = cur.execute(r"""SELECT count(*) = 0 FROM ref.portal_posting WHERE
          coalesce(portal_partner, 'LP-00') !~ '^(LP-[0-9]{2,6}(-[A-Z]{1,4})?|M[0-9]{1,9})$'
          OR coalesce(partner_code, 'LP-00') !~ '^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$'
          OR file_id !~ '^[A-Za-z0-9_-]{10,80}$' OR doc_type !~ '^[A-Z0-9]{1,6}$'""").fetchone()[0]
fname = cur.execute("SELECT count(*) = 0 FROM ref.portal_export WHERE file_name !~ '^(lp|gp)_(postings|member_xwalk)_[0-9]{4}-[0-9]{2}-[0-9]{2}\\.csv$'").fetchone()[0]
check("G-P2 no partner name enters the catalog DB: no name-like column on any posting table, every stored partner / file / "
      "type value is code-shaped, export file names are the dated pattern",
      not bad_cols and code_ok and fname, f"bad cols {bad_cols}")
ids_ok = cur.execute(r"""SELECT count(*) = 0 FROM cat.document WHERE published_ids_auto IS NOT NULL AND
          array_to_string(published_ids_auto, ',') !~ '^(LPD|GPD)-[0-9]{1,12}(,(LPD|GPD)-[0-9]{1,12})*$'""").fetchone()[0]
check("G-P2 the L10 values in the catalog are posting IDs and channel codes only", ids_ok)

# G-P5 idempotent: a second apply changes nothing (documents, links, conflicts)
n_links0 = cur.execute("SELECT count(*) FROM cat.doc_posting").fetchone()[0]
c2 = pw.apply_issued(conn, apply=True, log=lambda m: None)
n_links1 = cur.execute("SELECT count(*) FROM cat.doc_posting").fetchone()[0]
c3 = pw.apply_issued(conn, apply=True, log=lambda m: None)
check("G-P5 a re-run changes nothing: second and third apply change 0 documents and keep the same links",
      c3["documents_changed"] == 0 and c3.get("documents_cleared", 0) == 0 and n_links1 == cur.execute("SELECT count(*) FROM cat.doc_posting").fetchone()[0],
      f"changed {c3['documents_changed']}, cleared {c3.get('documents_cleared')}")
upd0 = cur.execute("SELECT max(updated_at) FROM cat.document WHERE published_ids_auto IS NOT NULL").fetchone()[0]
pw.apply_issued(conn, apply=True, log=lambda m: None)
check("G-P5 no updated_at churn on posted documents from a re-run",
      cur.execute("SELECT max(updated_at) FROM cat.document WHERE published_ids_auto IS NOT NULL").fetchone()[0] == upd0)

# G-P3 a person-set Status is never overwritten (the real apply runs and commits on the branch; the value is restored after)
doc = cur.execute("SELECT document_id FROM cat.doc_posting ORDER BY document_id LIMIT 1").fetchone()[0]
orig = cur.execute("SELECT status_confirmed, issued_date_confirmed FROM cat.document WHERE document_id = %s", (doc,)).fetchone()
cur.execute("UPDATE cat.document SET status_confirmed = 'draft', issued_date_confirmed = '2020-01-02' WHERE document_id = %s", (doc,))
conn.commit()
try:
    pw.apply_issued(conn, apply=True, log=lambda m: None)
    got = cur.execute("SELECT status_confirmed, issued_date_confirmed::text, status_auto FROM cat.document WHERE document_id = %s", (doc,)).fetchone()
    view = cur.execute("SELECT DISTINCT status, issued_date::text FROM app.v_find_x WHERE document_id = %s", (doc,)).fetchall()
    check("G-P3 a person-set Status (and Issued date) is never overwritten: after the posting step the person's Draft stands, "
          "the machine value is only status_auto, and every view shows the person's value",
          got[:2] == ("draft", "2020-01-02") and got[2] == "issued" and all(v == ("draft", "2020-01-02") for v in view), f"{got} {view}")
finally:
    cur.execute("UPDATE cat.document SET status_confirmed = %s, issued_date_confirmed = %s WHERE document_id = %s", (orig[0], orig[1], doc))
    conn.commit()
src = open(pw.__file__, encoding="utf-8").read()
check("G-P3 the posting module never writes a *_confirmed column (person values) anywhere",
      not re.search(r"(SET|,)\s*\w+_confirmed\s*=", src))

# Subject: a person's Subject codes are never replaced by a portal partner
pc = cur.execute("""SELECT count(*) FROM cat.document d JOIN cat.doc_posting dp ON dp.document_id = d.document_id
                    WHERE d.subject_codes_confirmed IS NOT NULL AND d.subject_rule LIKE 'SUBJ-PORTAL%%'""").fetchone()[0]
check("G-S1 a person's Subject codes win: no person-confirmed document carries a portal subject rule", pc == 0, str(pc))

dup = cur.execute("""SELECT count(*) FROM cat.document WHERE subject_codes_auto IS NOT NULL
                     AND cardinality(subject_codes_auto) <> (SELECT count(DISTINCT x) FROM unnest(subject_codes_auto) x)""").fetchone()[0]
check("G-S2 (coder review) no document carries the same Subject code twice (a duplicate would freeze the label as person-set)", dup == 0, str(dup))
fl = cur.execute("SELECT count(*) FROM cat.document WHERE status_rule = 'VF-superseded' AND published_ids_auto IS NOT NULL").fetchone()[0]
check("G-P6 (coder review) a posted document is never made Superseded by the family step (no nightly flip)", fl == 0, str(fl))

# G-M1 memory: the apply on the whole branch stays small
import tracemalloc
tracemalloc.start()
t = time.time()
pw.apply_issued(conn, apply=False, log=lambda m: None)
peak = tracemalloc.get_traced_memory()[1] / 2**20
tracemalloc.stop()
check("G-M1 memory stays streamed: a full apply_issued peaks under 100 MB of Python allocations", peak < 100, f"{peak:.0f} MB")
print(f"   (apply_issued dry pass: {time.time() - t:.0f}s, peak {peak:.1f} MB)")

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
