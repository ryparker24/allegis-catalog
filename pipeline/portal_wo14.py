r"""
CAT-WO-14 · Partner Portal + LP Portal (Published Docs) copies (My Drive / Confidential): R-059 status treatment.

  R-059 (ops.catalog_setting, Ryan 2026-11-25 = A):
    A  a document with a portal copy is Issued (status_auto 'issued', rule PORTAL-R059A) and the portal copy is a
       checklist candidate like any other copy
    B  portal copies are reference copies: status untouched, and a portal copy is never a checklist candidate
       (requirements_wo03 drops it; a document that also has a Finance copy still counts through that copy)

Runs at the end of every derive (apply_derive_wo02.run), after families / portals, so it is never undone by the
R-022 status rules. Never over a person's status; never over a superseded version (CAT-WO-04); only kinds that take
a Status (not the executable kinds, which carry an execution stage instead). Counts only.
"""
import collections

SETTING = "R-059"
DEFAULT = "A"
RULE = "PORTAL-R059A"

# documents with at least one live, non-secret portal copy (ops.label_scope rows with portal_copy)
PORTAL_DOCS_SQL = """
SELECT DISTINCT fd.document_id
FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE
  AND coalesce(f.handling, 'secret') <> 'secret' AND f.drive_name IS NULL
  AND ops.in_label_scope(f.drive_name, f.folder_path, true)
"""


def available(cur):
    cur.execute("SELECT to_regclass('ops.catalog_setting') IS NOT NULL AND to_regprocedure('ops.in_label_scope(text,text,boolean)') IS NOT NULL")
    return bool(cur.fetchone()[0])


def option(cur):
    """'A' | 'B' (R-059); 'A' when the setting is missing (Ryan's ruling), None before migration 014."""
    if not available(cur):
        return None
    cur.execute("SELECT value FROM ops.catalog_setting WHERE key = %s", (SETTING,))
    r = cur.fetchone()
    return (r[0] if r and r[0] in ("A", "B") else DEFAULT)


def status_plan(docs, opt, executable):
    """pure: docs = [(document_id, kind, status_auto, status_confirmed)] -> [(document_id)] to set Issued (option A only)."""
    if opt != "A":
        return []
    return [d for d, kind, st, stc in docs
            if stc is None and kind not in executable and st not in ("issued", "superseded")]


def apply(conn, apply=True, log=print):
    cur = conn.cursor()
    opt = option(cur)
    if opt is None:
        return {}
    cur.execute("SELECT code FROM ref.vocab WHERE list_name = 'executable_kind' AND active IS NOT FALSE")
    executable = {r[0] for r in cur.fetchall()}
    cur.execute(f"""SELECT d.document_id, coalesce(d.kind_confirmed, d.kind_auto), d.status_auto, d.status_confirmed
                    FROM cat.document d WHERE d.document_id IN ({PORTAL_DOCS_SQL})""")
    docs = cur.fetchall()
    todo = status_plan(docs, opt, executable)
    c = collections.Counter(portal_documents=len(docs), set_issued=len(todo))
    if apply and todo:
        cur.execute("""UPDATE cat.document SET status_auto = 'issued', status_rule = %s, updated_at = now()
                       WHERE document_id = ANY(%s) AND status_confirmed IS NULL""", (RULE, todo))
    if opt == "A" and apply:   # a document that lost its portal copy loses the Issued this rule gave it
        cur.execute("""UPDATE cat.document SET status_auto = NULL, status_rule = NULL, updated_at = now()
                       WHERE status_rule = %s AND NOT (document_id = ANY(%s))""", (RULE, [d[0] for d in docs]))
        c["cleared"] = cur.rowcount
    if opt == "B":       # switching A -> B: take back what option A set (the R-022 rules refill their own documents)
        cur.execute("""UPDATE cat.document SET status_auto = NULL, status_rule = NULL, updated_at = now()
                       WHERE status_rule = %s""" + ("" if apply else " AND false"), (RULE,))
        c["cleared"] = cur.rowcount
    if apply:
        conn.commit()
    else:
        conn.rollback()
    log(f"PORTAL (CAT-WO-14, R-059 option {opt}) {'APPLIED' if apply else 'DRY RUN'}: documents with a portal copy {len(docs):,} · "
        f"set Issued {len(todo):,}")
    return dict(c, option=opt)
