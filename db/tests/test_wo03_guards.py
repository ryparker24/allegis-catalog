r"""
CAT-WO-03 item 6 · DB guard tests. THROWAWAY BRANCH ONLY (main is refused; see pipeline/dbguard_wo03.py).

  py db\tests\test_wo03_guards.py --db-url-file <branch owner url file>

  G-W3 test_catalog_app_reads_ref_party_only_through_its_view
  G-W4 test_override_survives_two_rebuilds
  G-W5 test_document_marked_wrong_is_never_best
  G-W6 test_no_lp_name_in_logs_labels_or_exports    (pipeline output, label values, review_event edits, export names)
  G-W7 test_subject_codes_are_codes_only             (DB CHECK refuses a typed name)
  G-W8 test_requirement_override_is_append_only

Output: test names and PASS / FAIL only. LP names are read into memory to SEARCH for them and are never printed.
"""
import argparse, contextlib, io, json, os, re, subprocess, sys, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
import dbguard_wo03 as dbg
import requirements_wo03 as rq

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


def rebuild(conn):
    with conn.cursor() as cur:
        run, rows, _ = rq.build(cur, datetime.date.today(), log=lambda *x: None)
        rq.write(cur, run, rows)
    conn.commit()


conn = psycopg.connect(URL)
cur = conn.cursor()

# ---------------------------------------------------------------- G-W3 privileges (has_*_privilege: no login as catalog_app needed)
priv = lambda obj, p: cur.execute("SELECT has_table_privilege('catalog_app', %s, %s)", (obj, p)).fetchone()[0]
schema_usage = cur.execute("SELECT has_schema_privilege('catalog_app', 'ref', 'USAGE')").fetchone()[0]
direct = [t for t in ("ref.party", "ref.party_alias", "ops.requirement", "cat.doc_party", "app.requirement_override") if priv(t, "SELECT")]
# every app view granted to catalog_app that reads ref.party / ref.party_alias (directly)
cur.execute("""SELECT DISTINCT v.relname FROM pg_depend d JOIN pg_rewrite rw ON rw.oid = d.objid JOIN pg_class v ON v.oid = rw.ev_class
               JOIN pg_namespace n ON n.oid = v.relnamespace JOIN pg_class t ON t.oid = d.refobjid JOIN pg_namespace tn ON tn.oid = t.relnamespace
               WHERE n.nspname = 'app' AND tn.nspname = 'ref' AND t.relname IN ('party', 'party_alias') AND v.oid <> t.oid""")
readers = sorted(r[0] for r in cur.fetchall())
granted_readers = [v for v in readers if priv(f"app.{v}", "SELECT")]
others = cur.execute("""SELECT count(*) FROM information_schema.role_table_grants WHERE table_schema = 'app' AND table_name = 'v_party'
                        AND grantee NOT IN ('catalog_app') AND grantee <> (SELECT tableowner FROM pg_tables WHERE false UNION SELECT viewowner FROM pg_views WHERE schemaname='app' AND viewname='v_party')""").fetchone()[0]
check("G-W3 test_catalog_app_reads_ref_party_only_through_its_view",
      not schema_usage and not direct and granted_readers == ["v_party"] and priv("app.v_party", "SELECT") and not priv("app.v_party", "INSERT") and others == 0,
      f"ref usage={schema_usage} direct={direct} readers={granted_readers} other_grantees={others}")
cols = [r[0] for r in cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='app' AND table_name='v_party' ORDER BY ordinal_position")]
check("G-W3b app.v_party exposes the display name and codes only (no legal name)", "legal_name" not in cols and set(cols) <= {"entity_code", "partner_code", "display_name", "interest_kind", "is_company_gp", "datum_company_kind"}, str(cols))
check("G-W3c catalog_app may INSERT overrides but not read, update or delete them",
      priv("app.requirement_override", "INSERT") and not any(priv("app.requirement_override", p) for p in ("SELECT", "UPDATE", "DELETE", "TRUNCATE")))

# ---------------------------------------------------------------- G-W4 an override survives two rebuilds
rebuild(conn)
cur.execute("SELECT req_key, result FROM ops.requirement WHERE rule_id = 'LP-SUB' AND result = 'missing' ORDER BY req_key LIMIT 1")
key, before = cur.fetchone()
cur.execute("INSERT INTO app.requirement_override (req_key, action, note, by_email) VALUES (%s, 'not_required', 'CATWO03 guard test', 'guard-test@allegiscapital.com') RETURNING override_id", (key,))
oid = cur.fetchone()[0]; conn.commit()
rebuild(conn); rebuild(conn)
built = cur.execute("SELECT result, override_id FROM ops.requirement WHERE req_key = %s", (key,)).fetchone()
shown = cur.execute("SELECT result, override_action FROM app.v_requirement WHERE req_key = %s", (key,)).fetchone()
check("G-W4 test_override_survives_two_rebuilds", built == ("not_required", oid) and shown == ("not_required", "not_required"), f"{built} {shown}")
cur.execute("INSERT INTO app.requirement_override (req_key, action, by_email) VALUES (%s, 'clear', 'guard-test@allegiscapital.com')", (key,))
conn.commit(); rebuild(conn)
check("G-W4b Clear override returns the row to the machine result", cur.execute("SELECT result FROM app.v_requirement WHERE req_key = %s", (key,)).fetchone()[0] == before)

# ---------------------------------------------------------------- G-W5 a document marked Wrong is never best
cur.execute("""SELECT req_key, best_document_id, best_file_id FROM ops.requirement WHERE best_document_id IS NOT NULL AND best_source = 'auto'
               ORDER BY n_candidates DESC, req_key LIMIT 1""")
key, doc, fid = cur.fetchone()
files = [r[0] for r in cur.execute("SELECT file_id FROM cat.file_document WHERE document_id = %s", (doc,))]
saved = {r[0]: r[1] for r in cur.execute("SELECT file_id, review_status FROM ops.label_state WHERE file_id = ANY(%s)", (files,))}
cur.execute("UPDATE ops.label_state SET review_status = 'wrong' WHERE file_id = %s", (fid,)); conn.commit()
rebuild(conn)
after = cur.execute("SELECT best_document_id, candidates FROM ops.requirement WHERE req_key = %s", (key,)).fetchone()
wrong_anywhere = cur.execute("SELECT count(*) FROM ops.requirement WHERE best_document_id = %s OR candidates @> %s::jsonb", (doc, json.dumps([{"document_id": doc}]))).fetchone()[0]
cur.execute("UPDATE ops.label_state SET review_status = %s WHERE file_id = %s", (saved.get(fid), fid)); conn.commit()
rebuild(conn)
check("G-W5 test_document_marked_wrong_is_never_best (nor a candidate anywhere)", after[0] != doc and wrong_anywhere == 0,
      f"best after={after[0]} wrong-doc rows={wrong_anywhere}")
check("G-W5b restored: the document is best again once Wrong is removed",
      cur.execute("SELECT best_document_id FROM ops.requirement WHERE req_key = %s", (key,)).fetchone()[0] == doc)

# ---------------------------------------------------------------- G-W6 no LP name in logs, labels or exports
names = {r[0] for r in cur.execute("SELECT alias FROM ref.party_alias UNION SELECT display_name FROM ref.party UNION SELECT legal_name FROM ref.party")}
# a fund's own GP row is named after the GP company: an ENTITY name / code (printed as a code by design), not an LP name
entity_names = {r[0].strip().lower() for r in cur.execute("""SELECT datum_company_code FROM ref.party UNION SELECT datum_company_name FROM ref.party
                                                            UNION SELECT entity_code FROM ref.entity UNION SELECT alias FROM ref.entity_alias""") if r[0]}
names = {n.strip().lower() for n in names if n and len(n.strip()) >= 6} - entity_names
py = sys.executable
outs = []
for script in ("roster_load_wo03.py", "applicability_load_wo03.py", "subject_wo03.py", "requirements_wo03.py"):
    p = subprocess.run([py, os.path.join(HERE, "..", "..", "pipeline", script), "--db-url-file", a.db_url_file], capture_output=True, text=True, encoding="utf-8", errors="replace")
    outs.append(p.stdout + p.stderr)
log_hits = sum(1 for o in outs for n in names if n in o.lower())
check("G-W6a test_no_lp_name_in_any_pipeline_log_line (roster, applicability, subject, requirements dry runs)", log_hits == 0 and all(outs), f"hits={log_hits}")
lab = cur.execute("""SELECT coalesce(string_agg(array_to_string(coalesce(subject_codes_confirmed, subject_codes_auto), ','), ','), '')
                     FROM cat.document WHERE subject_codes_auto IS NOT NULL OR subject_codes_confirmed IS NOT NULL""").fetchone()[0]
bad_codes = [c for c in lab.split(",") if c and not re.match(r"^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$", c)]
ev = " ".join(r[0] or "" for r in cur.execute("SELECT edits::text FROM app.review_event WHERE edits IS NOT NULL")).lower()
req = " ".join(r[0] or "" for r in cur.execute("SELECT coalesce(best_reason,'') || ' ' || candidates::text FROM ops.requirement")).lower()
ov = " ".join(r[0] or "" for r in cur.execute("SELECT req_key FROM app.requirement_override")).lower()
check("G-W6b test_no_lp_name_in_any_label_value (Subject codes are codes; events, requirement reasons, override keys hold no name)",
      not bad_codes and not any(n in ev or n in req or n in ov for n in names), f"bad_codes={len(bad_codes)}")
src = open(os.path.join(HERE, "..", "..", "src", "app", "api", "export", "route.ts"), encoding="utf-8").read()
fn = re.findall(r'filename="([^"]+)"', src)
check("G-W6c test_no_lp_name_in_any_export_file_name (export names are a fixed prefix + timestamp)",
      fn and all(re.fullmatch(r"catalog-export-\$\{stamp\}\.(xlsx|csv)", f) for f in fn), str(fn))

# ---------------------------------------------------------------- G-W7 / G-W8 database refusals
def refused(sql, params=()):
    try:
        with conn.transaction():
            cur.execute(sql, params)
            raise psycopg.Rollback()
    except psycopg.Rollback:
        return False
    except psycopg.Error:
        return True
    return False

any_doc = cur.execute("SELECT document_id FROM cat.document LIMIT 1").fetchone()[0]
check("G-W7 test_no_typed_name_reaches_subject_codes (CHECK refuses a name, accepts codes)",
      refused("UPDATE cat.document SET subject_codes_auto = ARRAY['Zephyrine Quillfeather'] WHERE document_id = %s", (any_doc,))
      and refused("UPDATE cat.document SET subject_person_auto = 'someone@gmail.com' WHERE document_id = %s", (any_doc,))
      and not refused("UPDATE cat.document SET subject_codes_auto = ARRAY['LP-0001'] WHERE document_id = %s", (any_doc,)))
check("G-W7b cat.doc_party refuses a non-code partner", refused("INSERT INTO cat.doc_party (document_id, partner_code, method, confidence) VALUES (%s, 'Some Name', 'name', 'high')", (any_doc,)))
check("G-W8 test_requirement_override_is_append_only (UPDATE / DELETE / TRUNCATE refused, even for the owner)",
      refused("UPDATE app.requirement_override SET note = 'x' WHERE override_id = %s", (oid,))
      and refused("DELETE FROM app.requirement_override WHERE override_id = %s", (oid,))
      and refused("TRUNCATE app.requirement_override"))
conn.close()
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
