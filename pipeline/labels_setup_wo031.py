r"""
CAT-WO-03.1 · one new Kind choice on Allegis Document, DRAFTED for Ryan to publish in Label manager (as CAT-WO-02/03):

  Kind + "Audited Financial Statements" (code audited_financial_statements)

  py pipeline\labels_setup_wo031.py --check                       # reads Label manager (read-only)
  py pipeline\labels_setup_wo031.py --create-drafts --release     # unpublished delta only; Ryan reviews and PUBLISHES
  py pipeline\labels_setup_wo031.py --read-published --release    # after Ryan publishes: id -> src/lib/labels_schema.json

Never publishes. Run from C:\DriveCatalog (reuses labels_setup.py's sign-in).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCHEMA_PATH = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")
NEW_KIND = ("audited_financial_statements", "Audited Financial Statements")
MAX_CHOICES = 200


def plan(schema):
    """Pure: what is still to add against the PUBLISHED schema, and the limit check."""
    kinds = schema["doc"]["fields"]["kind"].get("choices", {})
    add = NEW_KIND[0] not in kinds
    n = len(kinds) + (1 if add else 0)
    return {"add_kind": add, "kind_n": n, "problems": [f"Kind: {n} choices > {MAX_CHOICES}"] if n > MAX_CHOICES else []}


def main():
    mode = next((a for a in sys.argv[1:] if a in ("--plan", "--check", "--create-drafts", "--read-published")), None)
    if not mode: sys.exit(__doc__)
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    p = plan(schema)
    print(f"Kind: {'+ ' + NEW_KIND[1] if p['add_kind'] else NEW_KIND[1] + ' already published'} -> {p['kind_n']} choices (limit {MAX_CHOICES})")
    if mode == "--plan" or p["problems"]:
        print("--plan: offline." if not p["problems"] else "PROBLEMS: " + "; ".join(p["problems"])); return
    sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))
    import labels_setup as ls
    import labels_setup_wo02 as w2
    from googleapiclient.discovery import build
    svc = build("drivelabels", "v2", credentials=ls.creds(), cache_discovery=False)
    labs = w2._labels(svc)
    doc = labs["Allegis Document"]
    lc = doc.get("lifecycle", {})
    print(f"  Allegis Document: state {lc.get('state')}, unpublished changes {bool(lc.get('hasUnpublishedChanges'))}")
    probs = w2._perm_problems(svc, labs)
    print("permissions: " + ("Ryan only, Parties matches Allegis Document" if not probs else "PROBLEMS: " + "; ".join(probs)))
    if mode == "--check":
        print("--check: nothing created, nothing published."); return
    if "--release" not in sys.argv:
        sys.exit("--create-drafts / --read-published are release steps: add --release (Ryan's go-ahead).")
    if probs: sys.exit("STOP: permissions differ - fix in Label manager first.")
    kind_f = w2._field(doc, "Kind")
    have = {c["properties"]["displayName"]: c for c in kind_f.get("selectionOptions", {}).get("choices", [])}
    if mode == "--create-drafts":
        reqs = [] if NEW_KIND[1] in have else [{"createSelectionChoice": {"fieldId": kind_f["id"], "choice": {"properties": {"displayName": NEW_KIND[1]}}}}]
        if reqs: svc.labels().delta(name=w2._base(doc), body={"useAdminAccess": True, "requests": reqs}).execute()
        print(f"~ Allegis Document: {len(reqs)} unpublished Kind choice ({NEW_KIND[1]})")
        print("Drafts only. Ryan: review and PUBLISH in Admin console > Label manager, then run --read-published --release.")
        return
    if lc.get("hasUnpublishedChanges"): sys.exit("STOP: Allegis Document still has unpublished changes in Label manager")
    c = have.get(NEW_KIND[1])
    if not c or c.get("lifecycle", {}).get("disabledPolicy"): sys.exit(f"STOP: Kind choice {NEW_KIND[1]} not on the published label")
    schema["doc"]["fields"]["kind"]["choices"][NEW_KIND[0]] = c["id"]
    json.dump(schema, open(SCHEMA_PATH, "w", encoding="utf-8"), indent=1)
    print(f"Wrote {os.path.normpath(SCHEMA_PATH)} - review the diff and commit it before the deploy.")


if __name__ == "__main__":
    main()
