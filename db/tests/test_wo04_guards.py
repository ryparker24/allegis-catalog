r"""
CAT-WO-04 · DB guards for version families (007_wo04.sql + pipeline/families_wo04.py). THROWAWAY BRANCH ONLY.

  py db\tests\test_wo04_guards.py --db-url-file <branch owner url file>

Everything runs in ONE transaction that is rolled back: the person actions are app.review_event INSERTs as
catalog_app (as the app sends them), and the "nightly" is the family build run twice without committing.
Output: test names and PASS / FAIL only (ids and counts, no names).
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
import dbguard_wo03 as dbg
import families_wo04 as fw

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
check("G-D0 catalog_app cannot write family tables; it reads the app views and only INSERTs events",
      not priv("cat.doc_family", "INSERT") and not priv("cat.doc_family_member", "UPDATE") and not priv("cat.doc_family_member", "SELECT")
      and priv("app.v_family_member", "SELECT") and priv("app.v_link_versions", "SELECT") and priv("app.review_event", "INSERT")
      and not cur.execute("SELECT has_function_privilege('public', 'app.tg_review_event_version()', 'EXECUTE')").fetchone()[0])
sb = cur.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'app' AND c.relkind = 'v'
                    AND c.relname IN ('v_find_x', 'v_family_member', 'v_link_versions')
                    AND coalesce(array_to_string(c.reloptions, ','), '') LIKE '%%security_barrier=true%%'""").fetchone()[0]
check("G-D0b the new / changed views are security_barrier", sb == 3, str(sb))

# G4 · families never mix entities or subjects unless a person merged them (the whole catalog, as built)
mixed = cur.execute("""
  SELECT count(*) FROM (
    SELECT m.family_id FROM cat.doc_family_member m JOIN cat.doc_family f ON f.family_id = m.family_id
    JOIN app.v_find_x x ON x.document_id = m.document_id AND x.is_primary IS NOT FALSE
    WHERE f.confidence <> 'person'
    GROUP BY m.family_id
    HAVING count(DISTINCT array_to_string(ARRAY(SELECT unnest(x.entities) ORDER BY 1), ',')) > 1
        OR count(DISTINCT nullif(array_to_string(ARRAY(SELECT unnest(x.subject_codes) ORDER BY 1), ','), '')) > 1
        OR count(DISTINCT x.kind) > 1 AND NOT bool_or(x.kind IN ('lpa_amendment', 'operating_agreement_amendment'))) z""").fetchone()[0]
nfam = cur.execute("SELECT count(*) FROM cat.doc_family WHERE confidence <> 'person'").fetchone()[0]
check("G-D4 families never mix entities, subjects or kinds unless a person merged them (whole catalog)", mixed == 0 and nfam > 0, f"{mixed} of {nfam}")

# G5 · no file name in a family row or a label value: reasons are codes, L6 values are numbers / role codes
reasons = {r for (rs,) in cur.execute("SELECT DISTINCT reason FROM cat.doc_family") for r in rs}
allowed = {"stem", "similar stem", "same name", "kind", "entities", "subject", "period", "one key missing", "no version marker",
           "amendment base unclear", "person", "single", "dates only"}
import catalog_labels as cl
cur.execute("""SELECT f.file_id FROM app.v_find_x f JOIN cat.doc_family_member m ON m.document_id = f.document_id LIMIT 2000""")
ids = [r[0] for r in cur.fetchall()]
rows = cl.catalog_rows(cur, ids)
bad = [k for r in rows.values() for k in ("version_family", "version_supersedes", "version_amends")
       if r.get(k) is not None and not re.fullmatch(r"[0-9]{1,12}", str(r[k]))]
roles = {r.get("version_role") for r in rows.values()} - {None, "current", "superseded", "amends", "redline", "draft_of"}
check("G-D5 no file name in any family row or L6 value (reasons are codes; Family / Supersedes / Amends are catalog numbers)",
      reasons <= allowed and not bad and not roles and len(rows) > 0, f"{sorted(reasons - allowed)} {len(bad)} {roles}")

# ------------------------------------------------------------------ person actions, then two "nightly" runs
fam = cur.execute("""SELECT f.family_id FROM cat.doc_family f WHERE f.confidence = 'high' AND f.n_members >= 3
                     AND NOT EXISTS (SELECT 1 FROM cat.doc_family_member m WHERE m.family_id = f.family_id AND (m.person_set OR m.role = 'amends'))
                     ORDER BY f.family_id LIMIT 1""").fetchone()[0]
mem = cur.execute("""SELECT m.document_id, m.role, x.file_id FROM cat.doc_family_member m
                     JOIN LATERAL (SELECT file_id FROM app.v_find_x WHERE document_id = m.document_id LIMIT 1) x ON true
                     WHERE m.family_id = %s ORDER BY m.document_id""", (fam,)).fetchall()
pick = next(m for m in mem if m[1] != "current")         # a person picks a member the machine did not
other = [m for m in mem if m[0] != pick[0]]

try:
    cur.execute("SET LOCAL ROLE catalog_app"); as_app = True
except psycopg.Error:
    conn.rollback(); cur = conn.cursor(); as_app = False


def ev(fid, did, version):
    cur.execute("""INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, labels_written, source, edits)
                   VALUES (%s, %s, 'ryan@allegiscapital.com', 'edited', '{}'::text[], 'version_link', %s::jsonb)""",
                (fid, did, json.dumps({"version": version})))


def owner(sql, p=()):
    cur.execute("RESET ROLE")
    r = cur.execute(sql, p).fetchall()
    if as_app: cur.execute("SET LOCAL ROLE catalog_app")
    return r


ev(pick[2], pick[0], {"action": "mark_current", "document": str(pick[0])})
st = owner("SELECT document_id, role, person_set, person_current, supersedes FROM cat.doc_family_member WHERE family_id = %s", (fam,))
check("G-D1 'mark as current' applies at once as person-set (as catalog_app): one current, the rest superseded by it",
      all(r[2] for r in st) and [r[0] for r in st if r[1] == "current"] == [pick[0]] and all(r[4] == pick[0] for r in st if r[1] == "superseded"),
      str([(r[1], r[2]) for r in st]))
stat = owner("SELECT coalesce(status_confirmed, status_auto) FROM cat.document WHERE document_id = %s", (pick[0],))[0][0]
check("G-D1b the new current member's machine Superseded status is cleared at once", stat != "superseded", str(stat))

cur.execute("RESET ROLE")
for night in (1, 2):
    fw.run(conn, apply=True, log=lambda m: None, commit=False)
st2 = owner("SELECT document_id, role, person_current FROM cat.doc_family_member WHERE family_id = %s", (fam,))
check("G-D2 a person-set current survives two nightly runs (G-V3 on the real catalog)",
      [r[0] for r in st2 if r[1] == "current"] == [pick[0]] and any(r[2] for r in st2) and len(st2) == len(st), str(st2))

# remove / merge / split / amends / a bad action
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
ev(other[0][2], other[0][0], {"action": "remove", "document": str(other[0][0])})
rm = owner("SELECT family_id, person_set FROM cat.doc_family_member WHERE document_id = %s", (other[0][0],))[0]
cur.execute("RESET ROLE"); fw.run(conn, apply=True, log=lambda m: None, commit=False)
rm2 = owner("SELECT family_id FROM cat.doc_family_member WHERE document_id = %s", (other[0][0],))[0]
check("G-D3 'remove from family' is person-set and the nightly never groups the document again", rm == (None, True) and rm2[0] is None)

two = owner("""SELECT x.document_id, x.file_id FROM app.v_find_x x WHERE x.document_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM cat.doc_family_member m WHERE m.document_id = x.document_id)
               ORDER BY md5(x.file_id) LIMIT 2""")
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
ev(two[0][1], two[0][0], {"action": "merge", "documents": [str(two[0][0]), str(two[1][0])]})
mg = owner("SELECT family_id, role, person_set FROM cat.doc_family_member WHERE document_id = ANY(%s)", ([two[0][0], two[1][0]],))
check("G-D6 'merge selected' makes one person family (one current) across documents of any entity",
      len(mg) == 2 and mg[0][0] == mg[1][0] and sorted(r[1] for r in mg) == ["current", "superseded"] and all(r[2] for r in mg), str(mg))
mfam = mg[0][0]
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
ev(two[1][1], two[1][0], {"action": "amends", "document": str(two[1][0]), "base": str(two[0][0])})
am = owner("SELECT role, amends, supersedes FROM cat.doc_family_member WHERE document_id = %s", (two[1][0],))[0]
check("G-D7 'mark as amendment of' sets Role = Amends -> base, never a supersession (R-028)", am == ("amends", two[0][0], None), str(am))
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
ev(two[1][1], two[1][0], {"action": "split", "family": str(mfam), "documents": [str(two[1][0])]})
sp = owner("SELECT family_id FROM cat.doc_family_member WHERE document_id = %s", (two[1][0],))[0][0]
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
n0 = owner("SELECT count(*) FROM cat.doc_family_member")[0][0]
if as_app: cur.execute("SET LOCAL ROLE catalog_app")
ev(two[0][1], two[0][0], {"action": "drop_everything"})
n1 = owner("SELECT count(*) FROM cat.doc_family_member")[0][0]
evs = owner("SELECT count(*) FROM app.review_event WHERE source = 'version_link' AND edits->'version'->>'action' = 'drop_everything'")[0][0]
check("G-D8 'split' takes the ticked member out; an unknown action changes nothing and the audit event still lands",
      sp is None and n0 == n1 and evs == 1, f"{sp} {n0} {n1} {evs}")

conn.rollback()
conn.close()
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
