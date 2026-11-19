r"""
CAT-WO-03.1 · DB guards for app edits reaching the catalog at once (006_wo031.sql). THROWAWAY BRANCH ONLY.

  py db\tests\test_wo031_guards.py --db-url-file <branch owner url file>

Everything runs in ONE transaction that is rolled back (app.review_event is append-only): nothing is left behind.
Events are inserted AS catalog_app (SET LOCAL ROLE) when the owner may assume it, as the app does.
Output: test names and PASS / FAIL only (ids, no names).
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
import dbguard_wo03 as dbg

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
check("G-A0 catalog_app still cannot UPDATE cat.document (the trigger, not a grant, applies edits)",
      not priv("cat.document", "UPDATE") and priv("app.review_event", "INSERT") and not priv("app.review_event", "UPDATE"))
fn_public = cur.execute("SELECT has_function_privilege('public', 'app.tg_review_event_apply()', 'EXECUTE')").fetchone()[0]
check("G-A0b the trigger function is not executable by PUBLIC", not fn_public)

# five catalogued files of different documents, nothing person-set on the fields used here
cur.execute("""SELECT v.file_id, v.document_id FROM app.v_find_x v JOIN cat.document d ON d.document_id = v.document_id
               WHERE d.status_confirmed IS NULL AND d.kind_confirmed IS NULL AND d.execution_stage_confirmed IS NULL
                 AND d.subject_codes_confirmed IS NULL AND d.fiscal_year_confirmed IS NULL
               ORDER BY md5(v.file_id) LIMIT 400""")
seen, files = set(), []
for f, d in cur.fetchall():
    if d not in seen:
        seen.add(d); files.append((f, d))
    if len(files) == 6:
        break
(f1, d1), (f2, d2), (f3, d3), (f4, d4), (f5, d5), (f6, d6) = files

try:
    cur.execute("SET LOCAL ROLE catalog_app"); as_app = True
except psycopg.Error:
    conn.rollback(); cur = conn.cursor(); as_app = False


def ev(fid, did, status, labels, edits, source="find_single", stage=None, executed=None):
    cur.execute("""INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, stage, executed_date, labels_written, source, edits)
                   VALUES (%s, %s, 'ryan@allegiscapital.com', %s, %s, %s::date, %s::text[], %s, %s::jsonb)""",
                (fid, did, status, stage, executed, labels, source, json.dumps(edits) if edits is not None else None))


def doc(did, cols):
    cur.execute("RESET ROLE")
    r = cur.execute(f"SELECT {cols} FROM cat.document WHERE document_id = %s", (did,)).fetchone()
    if as_app: cur.execute("SET LOCAL ROLE catalog_app")
    return r


# single edit (Find side panel): Status = Issued + fiscal year, written to Drive -> catalog at once, as person-set
ev(f1, d1, "confirmed", ["exec", "doc", "review"], {"status": "issued", "fiscal_year": 2024})
st, fy = doc(d1, "status_confirmed, fiscal_year_confirmed")
filt = cur.execute("SELECT count(*) FROM app.v_find_x WHERE file_id = %s AND status = 'issued' AND fiscal_year = 2024", (f1,)).fetchone()[0]
check("G-A1 a single edit's values reach *_confirmed and the Find filter at once" + (" (as catalog_app)" if as_app else " (as owner)"),
      st == "issued" and fy == 2024 and filt == 1, f"{st} {fy} {filt}")

# bulk edit ("edited", find_bulk): Status set on the file's document
ev(f2, d2, "edited", ["exec"], {"status": "issued"}, source="find_bulk")
check("G-A2 a bulk edit's field reaches the catalog at once", doc(d2, "status_confirmed")[0] == "issued")

# nothing written to Drive (labels_written empty): the catalog is NOT changed
ev(f3, d3, "edited", [], {"kind": "k1"}, source="find_single")
check("G-A3 an event with no label written changes nothing", doc(d3, "kind_confirmed")[0] is None)

# a value the catalog refuses: the audit event still lands, nothing applied
n0 = cur.execute("SELECT count(*) FROM app.review_event WHERE file_id = %s", (f4,)).fetchone()[0] if not as_app else None
ev(f4, d4, "edited", ["exec"], {"status": "not-a-status"}, source="find_bulk")
cur.execute("RESET ROLE")
n1 = cur.execute("SELECT count(*) FROM app.review_event WHERE file_id = %s AND edits->>'status' = 'not-a-status'", (f4,)).fetchone()[0]
bad = cur.execute("SELECT status_confirmed FROM cat.document WHERE document_id = %s", (d4,)).fetchone()[0]
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
check("G-A4 a refused value never blocks the audit event (event kept, catalog unchanged)", n1 == 1 and bad is None, f"{n1} {bad}")

# Review form: stage in the event's own column (no edits) -> execution stage; Subject "none" stays '{}'
ev(f5, d5, "confirmed", ["exec", "review"], None, source="review", stage="fully_executed", executed="2025-03-31")
stg, sd = doc(d5, "execution_stage_confirmed, signed_date_confirmed")
check("G-A5 the Review form's stage / executed date reach the catalog at once", stg == "fully_executed" and str(sd) == "2025-03-31", f"{stg} {sd}")
ev(f6, d6, "edited", ["parties"], {"subject_codes": []}, source="match_subject")
check("G-A6 a person's Subject 'none' is stored as '{}' (never NULL)", doc(d6, "subject_codes_confirmed")[0] == [])

conn.rollback()
conn.close()
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
