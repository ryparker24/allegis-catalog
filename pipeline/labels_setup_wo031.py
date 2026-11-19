r"""
CAT-WO-03.1 · Kind: the existing choice "Audit Report" is RENAMED "Audited Financial Statements" (Ryan 2026-11-19: one
kind; "audit report" is only the auditor's opinion). Same choice ID, so every file already carrying it updates by
itself. The catalog code follows: audit_report -> audited_financial_statements (migration 006b + labels_schema.json).
The separate "Audited Financial Statements" choice first drafted here is REMOVED from the draft (never published).

  py pipeline\labels_setup_wo031.py --check                       # reads Label manager (read-only)
  py pipeline\labels_setup_wo031.py --create-drafts --release     # unpublished delta only; Ryan reviews and PUBLISHES
  py pipeline\labels_setup_wo031.py --read-published --release    # after Ryan publishes: labels_schema.json kind code

Never publishes. Run from C:\DriveCatalog (reuses labels_setup.py's sign-in).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCHEMA_PATH = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")
OLD = ("audit_report", "Audit Report")
NEW = ("audited_financial_statements", "Audited Financial Statements")


def plan(schema):
    """Pure: what is left to do against the PUBLISHED schema."""
    k = schema["doc"]["fields"]["kind"].get("choices", {})
    return {"rename_pending": OLD[0] in k and NEW[0] not in k, "old_id": k.get(OLD[0]), "new_id": k.get(NEW[0]), "problems": []}


def choices(field):
    return field.get("selectionOptions", {}).get("choices", [])


def main():
    mode = next((a for a in sys.argv[1:] if a in ("--plan", "--check", "--create-drafts", "--read-published")), None)
    if not mode: sys.exit(__doc__)
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    p = plan(schema)
    print(f"Kind: rename '{OLD[1]}' -> '{NEW[1]}' (same choice id {p['old_id'] or p['new_id']}): {'pending' if p['rename_pending'] else 'already in labels_schema.json'}")
    if mode == "--plan":
        return
    sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))
    import labels_setup as ls
    import labels_setup_wo02 as w2
    from googleapiclient.discovery import build
    svc = build("drivelabels", "v2", credentials=ls.creds(), cache_discovery=False)
    labs = w2._labels(svc)
    doc = labs["Allegis Document"]
    lc = doc.get("lifecycle", {})
    kind_f = w2._field(doc, "Kind")
    by_name = {}
    for c in choices(kind_f):
        by_name.setdefault(c["properties"]["displayName"], []).append(c)
    print(f"  Allegis Document: state {lc.get('state')}, unpublished changes {bool(lc.get('hasUnpublishedChanges'))}")
    print("  Kind choices named: " + ", ".join(f"'{n}' x{len(v)} ({'/'.join(c['id'] for c in v)})" for n, v in by_name.items() if n in (OLD[1], NEW[1])))
    probs = w2._perm_problems(svc, labs)
    print("permissions: " + ("Ryan only, Parties matches Allegis Document" if not probs else "PROBLEMS: " + "; ".join(probs)))
    if mode == "--check":
        print("--check: nothing created, nothing published."); return
    if "--release" not in sys.argv:
        sys.exit("--create-drafts / --read-published are release steps: add --release (Ryan's go-ahead).")
    if probs: sys.exit("STOP: permissions differ - fix in Label manager first.")
    old_id = p["old_id"]
    if mode == "--create-drafts":
        if not old_id: sys.exit("STOP: labels_schema.json has no audit_report choice id to rename")
        reqs = []
        # 1. the separately drafted "Audited Financial Statements" choice (a NEW id, never published) is deleted
        for c in by_name.get(NEW[1], []):
            if c["id"] != old_id:
                reqs.append({"deleteSelectionChoice": {"fieldId": kind_f["id"], "id": c["id"]}})
        # 2. the existing choice keeps its id; only its display name changes
        cur = next((c for c in choices(kind_f) if c["id"] == old_id), None)
        if not cur: sys.exit(f"STOP: the Audit Report choice {old_id} is not on the label")
        if cur["properties"]["displayName"] != NEW[1]:
            props = dict(cur["properties"]); props["displayName"] = NEW[1]
            reqs.append({"updateSelectionChoiceProperties": {"fieldId": kind_f["id"], "id": old_id, "properties": props, "updateMask": "displayName"}})
        if reqs:
            svc.labels().delta(name=w2._base(doc), body={"useAdminAccess": True, "requests": reqs}).execute()
        print(f"~ Allegis Document: {len(reqs)} unpublished change(s): " + "; ".join(next(iter(r)) for r in reqs))
        print("Drafts only. Ryan: review and PUBLISH in Admin console > Label manager, then run --read-published --release.")
        return
    if lc.get("hasUnpublishedChanges"): sys.exit("STOP: Allegis Document still has unpublished changes in Label manager")
    cid = old_id or p["new_id"]
    cur = next((c for c in choices(kind_f) if c["id"] == cid), None)
    if not cur or cur["properties"]["displayName"] != NEW[1]: sys.exit(f"STOP: choice {cid} is not published as '{NEW[1]}'")
    if any(c["id"] != cid for c in by_name.get(NEW[1], [])): sys.exit(f"STOP: a second '{NEW[1]}' choice is published")
    k = schema["doc"]["fields"]["kind"]["choices"]
    k.pop(OLD[0], None); k[NEW[0]] = cid
    json.dump(schema, open(SCHEMA_PATH, "w", encoding="utf-8"), indent=1)
    print(f"Wrote {os.path.normpath(SCHEMA_PATH)}: kind code {NEW[0]} -> choice {cid} (was {OLD[0]}). Review the diff and commit it before the deploy.")


if __name__ == "__main__":
    main()
