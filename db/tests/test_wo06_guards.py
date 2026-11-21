r"""
CAT-WO-06 · DB guards for first-page reading (009_wo06.sql + pipeline/pages_wo06.py). THROWAWAY BRANCH ONLY.

  py db\tests\test_wo06_guards.py --db-url-file <branch owner url file> [--logs C:\DriveCatalog\logs] [--proofs C:\DriveCatalog\proofs\catwo06]

Needs a pages run on the branch (pages_wo06 --incremental --apply --limit N). The person-value tests run in a
transaction that is rolled back. Output: test names and PASS / FAIL with counts only (aliases are held in memory to scan
for, never printed).
"""
import argparse, glob, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "pipeline"))
import dbguard_wo03 as dbg
import pages_wo06 as pw

ap = argparse.ArgumentParser()
dbg.add_args(ap)
ap.add_argument("--logs", default=r"C:\DriveCatalog\logs")
ap.add_argument("--proofs", default=r"C:\DriveCatalog\proofs\catwo06")
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
TIN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)|(?<!\d)\d{2}-\d{7}(?!\d)|XXX-XX-\d{4}")

# ------------------------------------------------------------------ G-S1 the schema can't hold page text
NEW = {("cat", "doc_page_read"): None, ("cat", "doc_content_match"): None,
       ("cat", "doc_content_check"): ("content_fiscal_year", "content_quarter", "content_period_end", "content_entity", "content_amended",
                                      "content_read_at", "content_disagrees"),
       ("cat", "doc_party"): ("page_from", "page_to", "anchor", "reason"), ("cat", "document"): ("content_flags",), ("ops", "requirement"): ("best_page",)}
bad = []
for (s, t), only in NEW.items():
    cols = cur.execute("""SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s""", (s, t)).fetchall()
    checks = " ".join(r[0] for r in cur.execute("""SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c WHERE c.conrelid = %s::regclass
                                                   AND c.contype IN ('c', 'f')""", (f"{s}.{t}",)).fetchall())
    for c, dt, udt in cols:
        if only and c not in only:
            continue
        if dt in ("text", "character varying", "ARRAY", "jsonb", "json", "bytea") and re.search(r"(^|_)(text|page_text|name|address|snippet|raw|ocr_text|line)(_|$)", c):
            bad.append(f"{t}.{c}:name")
        if dt in ("text", "character varying", "ARRAY", "jsonb", "json", "bytea") and c not in ("md5",):
            if not re.search(rf"\b{c}\b", checks):
                bad.append(f"{t}.{c}:unchecked")
    if (s, t) == ("cat", "doc_page_read") and any(dt in ("jsonb", "json", "bytea") for _, dt, _ in cols):
        bad.append("doc_page_read:json")
check("G-S1 no new table or column can hold page text: every new text / array column is a code with a CHECK on its shape "
      "(or a key to ref.entity), no text-like column name, no json / bytea on cat.doc_page_read", not bad, ", ".join(bad))

# ------------------------------------------------------------------ G-S2 / G-T2 stored values: codes only, no TIN pattern
cells = []
for sql in ("SELECT md5, extractor_version, outcome FROM cat.doc_page_read",
            "SELECT anchor, rule_id, partner_code, roster_entity, content_entity, confidence, reason FROM cat.doc_content_match",
            "SELECT content_entity, array_to_string(content_disagrees, ',') FROM cat.doc_content_check WHERE content_read_at IS NOT NULL",
            "SELECT anchor, reason, method FROM cat.doc_party",
            "SELECT array_to_string(content_flags, ',') FROM cat.document WHERE content_flags IS NOT NULL"):
    for row in cur.execute(sql):
        cells += [str(x) for x in row if x is not None]
tin_hits = sum(1 for c in cells if TIN.search(c))
check("G-T2 no TIN pattern in any table this order writes", tin_hits == 0, f"{tin_hits} cells")
# LP / member names only: aliases of the funds' own GP rows and aliases that are an Allegis entity's or company's name
# (fund / GP / manager names, also printed in code and logs) are not personal names and are left out of the scan
org = {pw.norm(x[0]) for x in cur.execute("""SELECT alias FROM ref.entity_alias UNION SELECT name FROM ref.entity UNION SELECT entity_code FROM ref.entity
                                             UNION SELECT datum_company_name FROM ref.party""")}
org |= {" ".join(t for t in o.split() if t not in ("llc", "lp", "l", "p", "inc")) for o in org}
aliases = [x[0] for x in cur.execute("""SELECT a.alias FROM ref.party_alias a WHERE length(a.alias) >= 5
                                        AND NOT EXISTS (SELECT 1 FROM ref.party p WHERE p.partner_code = a.partner_code AND p.is_company_gp)""")]
al_norm = {pw.norm(x) for x in aliases if len(pw.norm(x)) >= 5}
al_norm = {x for x in al_norm if x not in org and " ".join(t for t in x.split() if t not in ("llc", "lp", "l", "p", "inc")) not in org}
alias_hits = sum(1 for c in cells if pw.norm(c) in al_norm)
check("G-S2 no ref.party_alias string is stored in a table this order writes (outside ref.party_alias)", alias_hits == 0, f"{alias_hits} cells")
check("G-S2 cat.doc_page_read holds no free-text value (every cell is an md5 / revision key, version or outcome code)",
      cur.execute("""SELECT count(*) = 0 FROM cat.doc_page_read WHERE md5 !~ '^([0-9a-f]{32}|rev:[A-Za-z0-9_:.+ -]{1,80})$'
                     OR extractor_version !~ '^cnt-[0-9]{1,4}$' OR outcome !~ '^[a-z_]{2,20}$'""").fetchone()[0])


# ------------------------------------------------------------------ G-L logs, proofs and commits carry no alias / TIN
def scan_files(paths):
    a_hits = t_hits = n = 0
    for p in paths:
        try:
            s = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        n += 1
        ns = " " + pw.norm(s) + " "
        a_hits += sum(1 for x in al_norm if len(x.split()) >= 2 and f" {x} " in ns)
        t_hits += len(TIN.findall(s))
    return n, a_hits, t_hits
n, ah, th = scan_files(glob.glob(os.path.join(a.logs, "wo06*")) + glob.glob(os.path.join(a.logs, "nightly_*")))
check(f"G-L1 no alias string and no TIN pattern in any CAT-WO-06 / nightly log ({n} files scanned)", ah == 0 and th == 0, f"alias {ah} tin {th}")
n, ah, th = scan_files(glob.glob(os.path.join(a.proofs, "**", "*"), recursive=True))
check(f"G-L2 no alias string and no TIN pattern in any CAT-WO-06 proof file ({n} files scanned)", ah == 0 and th == 0, f"alias {ah} tin {th}")
diff = subprocess.run(["git", "-C", APP, "log", "-p", "main..HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
# added lines and commit messages only; git's own Author / Date lines (the configured committer identity) are not content
diff = "\n".join(l for l in diff.splitlines() if (l.startswith("+") or l.startswith("    ")) and not l.startswith("+++"))
nd = " " + pw.norm(diff) + " "
ch = sum(1 for x in al_norm if len(x.split()) >= 2 and f" {x} " in nd)
check("G-L3 no alias string in any cat-wo-06 commit (messages and diffs)", ch == 0 and not TIN.search(diff), f"alias {ch}")
labels = cur.execute(r"""SELECT count(*) FROM ops.label_state WHERE live::text ~ '\d{3}-\d{2}-\d{4}' OR machine::text ~ '\d{3}-\d{2}-\d{4}'""").fetchone()[0]
check("G-L4 no TIN pattern in any label value the catalog knows (ops.label_state live / machine)", labels == 0, f"{labels}")

# ------------------------------------------------------------------ privileges / views
priv = lambda obj, p: cur.execute("SELECT has_table_privilege('catalog_app', %s, %s)", (obj, p)).fetchone()[0]
check("G-D0 catalog_app reads v_doc_content only; it cannot read cat.doc_page_read / cat.doc_content_match",
      priv("app.v_doc_content", "SELECT") and not priv("cat.doc_page_read", "SELECT") and not priv("cat.doc_content_match", "SELECT"))
sb = cur.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'app'
                    AND c.relname IN ('v_doc_content', 'v_subject_candidates', 'v_review_queue', 'v_review_counts', 'v_requirement')
                    AND 'security_barrier=true' = ANY(c.reloptions)""").fetchone()[0]
check("G-D1 the views this order changes are security_barrier", sb == 5, f"{sb}/5")

# ------------------------------------------------------------------ Secret tier never downloaded
docs = pw.scope(cur)
fids = [d["file_id"] for d in docs if d["file_id"]]
sec = cur.execute("SELECT count(*) FROM cat.file WHERE file_id = ANY(%s) AND (coalesce(handling, 'secret') = 'secret' OR trashed OR is_shortcut)", (fids,)).fetchone()[0]
check(f"G-SEC Secret-tier, trashed and shortcut files are never in the read scope ({len(fids):,} files in scope)", sec == 0, f"{sec}")
conn.rollback()

# ------------------------------------------------------------------ idempotent re-run (reads nothing new, changes nothing)
class NoDrive:
    def files(self):
        raise AssertionError("a re-run must not download anything")
read_ids = [r[0] for r in cur.execute("SELECT document_id FROM cat.doc_page_read ORDER BY document_id LIMIT 300")]
conn.commit()
before = cur.execute("SELECT count(*), max(read_at), (SELECT count(*) FROM cat.doc_content_match) FROM cat.doc_page_read").fetchone()
conn.commit()
try:
    c, _, _ = pw.run(conn, NoDrive(), incremental=True, apply=True, log=lambda m: None, only_ids=read_ids)
    rerun_ok = c["read"] == 0
except AssertionError:
    rerun_ok = False
after = cur.execute("SELECT count(*), max(read_at), (SELECT count(*) FROM cat.doc_content_match) FROM cat.doc_page_read").fetchone()
conn.commit()
check(f"G-I1 a re-run over {len(read_ids)} documents already read downloads nothing and changes nothing", rerun_ok and before == after, f"{before} -> {after}")
check("G-TMP %TEMP%\\catwo06 is empty after the run", not os.path.isdir(pw.TEMP_DIR) or os.listdir(pw.TEMP_DIR) == [])

# ------------------------------------------------------------------ person values survive (rolled back)
import subject_wo03 as sw
row = cur.execute("""SELECT m.document_id, m.partner_code FROM cat.doc_content_match m WHERE m.confidence = 'high' AND m.partner_code IS NOT NULL
                     ORDER BY m.document_id LIMIT 1""").fetchone()
if row:
    did, code = row
    other = cur.execute("SELECT partner_code FROM ref.party WHERE partner_code <> %s ORDER BY partner_code LIMIT 1", (code,)).fetchone()[0]
    real_commit = conn.commit
    conn.commit = lambda: None
    try:
        cur.execute("UPDATE cat.document SET subject_codes_confirmed = %s WHERE document_id = %s", ([other], did))
        sw.run(conn, apply=True, staff=None, log=lambda m: None)
        conf, auto = cur.execute("SELECT subject_codes_confirmed, subject_codes_auto FROM cat.document WHERE document_id = %s", (did,)).fetchone()
        lane = cur.execute("SELECT bool_or(lane AND reason = 'CONFLICT_PERSON') FROM cat.doc_content_match WHERE document_id = %s", (did,)).fetchone()[0]
        check("G-P1 a person-set Subject is never overwritten by a content match; the disagreement goes to the lane (CONFLICT_PERSON)",
              conf == [other] and lane, f"conf ok {conf == [other]} lane {lane}")
    finally:
        conn.rollback(); conn.commit = real_commit
else:
    check("G-P1 a person-set Subject is never overwritten (needs a content high match on the branch)", False, "no content high match yet")

import catalog_labels as cl
S = cl.Schema(cl.load_schema())
check("G-P2 a person-removed Handling flag is never added back; tier unchanged (catalog_labels.handling_raise)",
      cl.handling_raise({"_content_contains": ["tax_id"]}, {"tier": "normal", "contains": []}, S, {"contains": ["tax_id"]}) == {}
      and "tier" not in cl.handling_raise({"_content_contains": ["tax_id", "lp_pii"]}, {"tier": "normal", "contains": []}, S))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
