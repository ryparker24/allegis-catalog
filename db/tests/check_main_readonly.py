"""
CAT-WO-01 release check: G1 + G2 against MAIN, READ-ONLY (every session is SET default_transaction_read_only = on;
nothing is inserted, updated or deleted). The fixture-based test_guards.py stays branch-only.

  py db/tests/check_main_readonly.py --owner-url-file <owner url file> --app-url-file <catalog_app url file>
                                     [--reference-url-file <owner url of a branch where test_guards.py passed>]

G1  real secret-tier files never appear in any app view; tier values only normal/restricted; v_find is
    security_barrier and carries the secret predicate; (optional) every app view definition on main is identical
    to the reference branch, where the fixture tests passed.
G2  catalog_app privilege matrix from the catalog (has_*_privilege) for every relation in cat/ref/ops/app,
    plus real SELECT attempts that must be refused; append-only triggers present.
Prints check names, counts and PASS/FAIL only.
"""
import argparse, sys, psycopg

ap = argparse.ArgumentParser()
ap.add_argument("--owner-url-file", required=True)
ap.add_argument("--app-url-file", required=True)
ap.add_argument("--reference-url-file")
a = ap.parse_args()


def read_url(path):
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if line.startswith("postgres"):
            return line
        k, sep, v = line.partition("=")
        if sep and "UNPOOLED" in k.upper():
            return v.strip().strip("'\"")
    sys.exit(f"no URL in {path}")


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def ro(url):
    c = psycopg.connect(url, autocommit=True)
    c.execute("SET default_transaction_read_only = on")
    return c


APP_VIEWS = ["v_find", "v_review_queue", "v_review_counts", "v_portco", "v_entity"]
owner, app = ro(read_url(a.owner_url_file)), ro(read_url(a.app_url_file))

print("== G1 (read-only, real data)")
n_secret = owner.execute("SELECT count(*) FROM cat.file WHERE handling = 'secret'").fetchone()[0]
print(f"info  secret-tier files in cat.file = {n_secret}")
for v in ("v_find", "v_review_queue"):
    n = owner.execute(f"SELECT count(*) FROM app.{v} x JOIN cat.file f USING (file_id) WHERE coalesce(f.handling,'secret') NOT IN ('normal','restricted')").fetchone()[0]
    check(f"G1 app.{v}: rows whose catalog tier is secret/unknown = {n}", n == 0)
    m = app.execute(f"SELECT count(*) FROM app.{v} WHERE tier IS DISTINCT FROM 'normal' AND tier IS DISTINCT FROM 'restricted'").fetchone()[0]
    check(f"G1 app.{v} as catalog_app: rows with tier outside (normal, restricted) = {m}", m == 0)
n = owner.execute("SELECT count(*) FROM app.labelled_file l JOIN cat.file f USING (file_id) WHERE f.handling = 'secret'").fetchone()[0]
print(f"info  secret-tier files in app.labelled_file = {n} (hidden by the views regardless)")
total = app.execute("SELECT count(*) FROM app.v_find").fetchone()[0]
print(f"info  app.v_find rows as catalog_app = {total}")
opts = dict(owner.execute("SELECT c.relname, coalesce(array_to_string(c.reloptions, ','), '') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app' AND c.relkind='v'").fetchall())
check(f"G1 app views present = {sorted(opts)}", sorted(opts) == sorted(APP_VIEWS))
for v in APP_VIEWS:
    check(f"G1 app.{v} is security_barrier", "security_barrier=true" in opts.get(v, ""))
vdef = owner.execute("SELECT pg_get_viewdef('app.v_find'::regclass, true)").fetchone()[0]
check("G1 app.v_find definition carries the secret-tier exclusion (fail closed on null)", "'secret'" in vdef and "COALESCE" in vdef.upper())
if a.reference_url_file:
    ref = ro(read_url(a.reference_url_file))
    q = "SELECT c.relname, pg_get_viewdef(c.oid, true) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app' AND c.relkind='v' ORDER BY 1"
    same = dict(owner.execute(q).fetchall()) == dict(ref.execute(q).fetchall())
    check("G1 every app view definition on main == the reference branch (where the fixture G1/G2 tests passed)", same)

print("== G2 (read-only, catalog privilege matrix + refused reads)")
rels = owner.execute("""SELECT n.nspname, c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname IN ('cat','ref','ops','app') AND c.relkind IN ('r','v','m','p','f') ORDER BY 1,2""").fetchall()
allowed = {("app", v): {"SELECT"} for v in APP_VIEWS}
allowed[("app", "saved_view")] = {"SELECT", "INSERT", "UPDATE", "DELETE"}
allowed[("app", "review_event")] = {"INSERT"}
bad = []
for sch, rel, _k in rels:
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        has = owner.execute("SELECT has_table_privilege('catalog_app', %s, %s)", (f"{sch}.{rel}", priv)).fetchone()[0]
        if has != (priv in allowed.get((sch, rel), set())):
            bad.append(f"{sch}.{rel}:{priv}={has}")
check(f"G2 catalog_app table privileges exactly as designed across {len(rels)} relations in cat/ref/ops/app", not bad, ", ".join(bad[:10]))
for sch in ("cat", "ref", "ops", "app"):
    cr = owner.execute("SELECT has_schema_privilege('catalog_app', %s, 'CREATE')", (sch,)).fetchone()[0]
    check(f"G2 catalog_app has no CREATE on schema {sch}", not cr)
r = owner.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit FROM pg_roles WHERE rolname='catalog_app'").fetchone()
check("G2 catalog_app role attributes: not superuser/createdb/createrole/bypassrls, noinherit", r == (False, False, False, False, False), str(r))
memb = owner.execute("SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='catalog_app'").fetchone()[0]
check(f"G2 catalog_app is a member of no other role = {memb}", memb == 0)
for label, stmt in [("SELECT on cat.file", "SELECT count(*) FROM cat.file"), ("SELECT on ref.lp", "SELECT count(*) FROM ref.lp"),
                    ("SELECT on ops.run", "SELECT count(*) FROM ops.run"), ("SELECT on app.review_event", "SELECT count(*) FROM app.review_event"),
                    ("SELECT on app.labelled_file", "SELECT count(*) FROM app.labelled_file")]:
    try:
        app.execute(stmt)
        check(f"G2 catalog_app refused {label}", False, "executed")
    except psycopg.errors.InsufficientPrivilege as e:
        check(f"G2 catalog_app refused {label}", True, e.diag.message_primary)
trg = {t for (t,) in owner.execute("SELECT tgname FROM pg_trigger WHERE tgrelid='app.review_event'::regclass AND NOT tgisinternal AND tgenabled <> 'D'").fetchall()}
check(f"G2 append-only triggers on app.review_event enabled = {sorted(trg)}", {"review_event_append_only", "review_event_no_truncate"} <= trg)
sd = owner.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='app' AND p.prosecdef").fetchone()[0]
check(f"G2 SECURITY DEFINER functions in app = {sd}", sd == 0)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
