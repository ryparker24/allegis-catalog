"""
CAT-WO-01 item 5 - DB guard tests. RUN ONLY AGAINST A THROWAWAY NEON BRANCH (never main).

  py db/tests/test_guards.py --owner-url-file <owner url file> --app-url-file <catalog_app url file>

  G1  test_secret_tier_never_returned_by_any_app_view    (SQL test against fixture rows)
  G2  test_catalog_app_role_refusals                     (role test: INSERT on cat, UPDATE on app.review_event, ...)

Fixture rows use file IDs prefixed CATWO01-FIXTURE- and are removed at the end.
Output: test names and PASS/FAIL only (codes and counts - no names).
"""
import argparse, sys, psycopg

ap = argparse.ArgumentParser()
ap.add_argument("--owner-url-file", required=True)
ap.add_argument("--app-url-file", required=True)
a = ap.parse_args()
OWNER = open(a.owner_url_file).read().strip()
APP = open(a.app_url_file).read().strip()

# refuse to run against the main branch's endpoint (main host is read from catalog_db_url.txt if present)
try:
    import re
    mains = [re.search(r"@([^/:?]+)", l).group(1).replace("-pooler", "")
             for l in open(r"C:\DriveCatalog\catalog_db_url.txt", encoding="utf-8-sig") if "@" in l]
    for u in (OWNER, APP):
        if re.search(r"@([^/:?]+)", u).group(1) in mains:
            sys.exit("REFUSED: this URL points at the MAIN branch. Use a throwaway branch.")
except FileNotFoundError:
    pass

FX = "CATWO01-FIXTURE-"
SECRET_ID, RESTRICTED_ID, NORMAL_ID = FX + "secret", FX + "restricted", FX + "normal"
# (cat.file.handling is NOT NULL, so a null tier cannot exist; the views still treat NULL as secret - fail closed)
VIEWS = ["app.v_find", "app.v_review_queue"]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def setup(c):
    with c.cursor() as cur:
        cur.execute("INSERT INTO cat.document (kind_auto, requires_execution_auto, execution_stage_auto) "
                    "VALUES (NULL, true, 'unknown') RETURNING document_id")
        doc = cur.fetchone()[0]
        for fid, tier in ((SECRET_ID, "secret"), (RESTRICTED_ID, "restricted"), (NORMAL_ID, "normal")):
            cur.execute("INSERT INTO cat.file (file_id, name, mime_type, handling, drive_name) VALUES (%s, %s, %s, %s, %s)",
                        (fid, "fixture", "application/pdf", tier, "LIMITED - Finance"))
            cur.execute("INSERT INTO cat.file_document (file_id, document_id, file_role) VALUES (%s, %s, 'primary')", (fid, doc))
            cur.execute("INSERT INTO app.labelled_file (file_id, source) VALUES (%s, 'fixture')", (fid,))
    c.commit()
    return doc


def teardown(c, doc):
    with c.cursor() as cur:
        cur.execute("ALTER TABLE app.review_event DISABLE TRIGGER review_event_append_only")
        cur.execute("DELETE FROM app.review_event WHERE file_id LIKE %s", (FX + "%",))
        cur.execute("ALTER TABLE app.review_event ENABLE TRIGGER review_event_append_only")
        cur.execute("DELETE FROM app.saved_view WHERE owner_email LIKE 'catwo01-fixture%%'")
        cur.execute("DELETE FROM app.labelled_file WHERE file_id LIKE %s", (FX + "%",))
        cur.execute("DELETE FROM cat.file_document WHERE file_id LIKE %s", (FX + "%",))
        cur.execute("DELETE FROM cat.file WHERE file_id LIKE %s", (FX + "%",))
        cur.execute("DELETE FROM cat.document WHERE document_id = %s", (doc,))
    c.commit()


def refused(conn, stmt, params=None):
    """True if the statement is refused with a privilege error."""
    try:
        with conn.cursor() as cur:
            cur.execute(stmt, params)
        conn.rollback()
        return False, "executed"
    except psycopg.errors.InsufficientPrivilege as e:
        conn.rollback()
        return True, e.diag.message_primary
    except Exception as e:
        conn.rollback()
        return False, f"{type(e).__name__}: {e.diag.message_primary if hasattr(e, 'diag') else e}"


with psycopg.connect(OWNER) as owner, psycopg.connect(APP) as app:
    doc = setup(owner)
    try:
        print("== G1 test_secret_tier_never_returned_by_any_app_view")
        for who, conn in (("owner", owner), ("catalog_app", app)):
            for v in VIEWS:
                n = conn.execute(f"SELECT count(*) FROM {v} WHERE file_id = %s", (SECRET_ID,)).fetchone()[0]
                check(f"G1 {v} as {who}: secret-tier fixture returned = {n}", n == 0)
                m = conn.execute(f"SELECT count(*) FROM {v} WHERE tier IS DISTINCT FROM 'normal' AND tier IS DISTINCT FROM 'restricted'").fetchone()[0]
                check(f"G1 {v} as {who}: rows with tier outside (normal, restricted) = {m}", m == 0)
            conn.rollback()
        n = app.execute("SELECT count(*) FROM app.v_find WHERE file_id = %s", (NORMAL_ID,)).fetchone()[0]
        check(f"G1 control: normal-tier fixture IS returned by app.v_find = {n}", n == 1)
        n = app.execute("SELECT count(*) FROM app.v_review_queue WHERE file_id = %s", (NORMAL_ID,)).fetchone()[0]
        check(f"G1 control: normal-tier fixture IS in app.v_review_queue = {n}", n == 1)
        n = app.execute("SELECT count(*) FROM app.v_find WHERE file_id = %s AND tier = 'restricted'", (RESTRICTED_ID,)).fetchone()[0]
        check(f"G1 control (Decision 2): restricted-tier fixture IS returned, badged by tier = {n}", n == 1)
        # flip the control fixture to secret: it must vanish from every view at once
        owner.execute("UPDATE cat.file SET handling='secret' WHERE file_id=%s", (NORMAL_ID,)); owner.commit()
        for v in VIEWS:
            n = app.execute(f"SELECT count(*) FROM {v} WHERE file_id = %s", (NORMAL_ID,)).fetchone()[0]
            check(f"G1 {v}: control fixture after flip to secret returned = {n}", n == 0)
        app.rollback()
        owner.execute("UPDATE cat.file SET handling='normal' WHERE file_id=%s", (NORMAL_ID,)); owner.commit()

        print("== G2 test_catalog_app_role_refusals")
        for label, stmt, p in [
            ("INSERT on cat.file", "INSERT INTO cat.file (file_id, name, mime_type) VALUES (%s, 'x', 'x')", (FX + "x",)),
            ("SELECT on cat.file", "SELECT count(*) FROM cat.file", None),
            ("UPDATE on cat.document", "UPDATE cat.document SET notes = notes WHERE false", None),
            ("SELECT on ref.lp", "SELECT count(*) FROM ref.lp", None),
            ("SELECT on ops.run", "SELECT count(*) FROM ops.run", None),
            ("UPDATE on app.review_event", "UPDATE app.review_event SET note = 'x' WHERE file_id = %s", (NORMAL_ID,)),
            ("DELETE on app.review_event", "DELETE FROM app.review_event WHERE file_id = %s", (NORMAL_ID,)),
            ("SELECT on app.review_event (insert-only)", "SELECT count(*) FROM app.review_event", None),
            ("SELECT on app.labelled_file", "SELECT count(*) FROM app.labelled_file", None),
            ("CREATE TABLE in app", "CREATE TABLE app.x (i int)", None),
        ]:
            ok, msg = refused(app, stmt, p)
            check(f"G2 catalog_app refused {label}", ok, msg)
        # allowed paths (control)
        with app.cursor() as cur:
            cur.execute("INSERT INTO app.review_event (file_id, reviewer_email, status, labels_written) "
                        "VALUES (%s, 'fixture@allegiscapital.com', 'confirmed', ARRAY['review'])", (NORMAL_ID,))
            check("G2 control: catalog_app INSERT on app.review_event allowed", cur.rowcount == 1)
            cur.execute("INSERT INTO app.saved_view (owner_email, name, spec) VALUES ('catwo01-fixture@allegiscapital.com', 'fx', '{}')")
            cur.execute("UPDATE app.saved_view SET name='fx2' WHERE owner_email='catwo01-fixture@allegiscapital.com'")
            cur.execute("DELETE FROM app.saved_view WHERE owner_email='catwo01-fixture@allegiscapital.com'")
            check("G2 control: catalog_app INSERT/UPDATE/DELETE on app.saved_view allowed", cur.rowcount == 1)
        app.commit()
        n = app.execute("SELECT count(*) FROM app.v_review_queue WHERE file_id = %s", (NORMAL_ID,)).fetchone()[0]
        check(f"G2/queue: a file with a review event leaves the queue = {n}", n == 0)
        app.rollback()
        # append-only holds even for the owner
        try:
            owner.execute("UPDATE app.review_event SET note='x' WHERE file_id=%s", (NORMAL_ID,)); owner.commit()
            check("G2 append-only trigger refuses UPDATE even for the owner", False, "executed")
        except psycopg.Error as e:
            owner.rollback(); check("G2 append-only trigger refuses UPDATE even for the owner", True, e.diag.message_primary)
    finally:
        teardown(owner, doc)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
