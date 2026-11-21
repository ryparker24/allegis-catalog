r"""
CAT-WO-05 · R-030: label L10 "Published To" (Channel, Posted date, Posting ID). Machine-set; a person's value is never
overwritten (the re-sync's person-owned rule, label_sync_wo02) and it is not read back into the catalog.

  py pipeline\labels_setup_wo05.py --check                       # limits + design + permissions (read-only)
  py pipeline\labels_setup_wo05.py --create-drafts --release     # creates "Published To" as a DRAFT, Ryan-only permissions
  py pipeline\labels_setup_wo05.py --read-published --release    # after Ryan PUBLISHES: adds "published" to labels_schema.json

Never publishes (Ryan publishes in Admin console > Label manager). Run from C:\DriveCatalog (labels_setup.py's sign-in).
Values are codes only: Channel (LP portal / GP portal / Datum / Email), Posted date (sent as "YYYY-MM-DD"), Posting ID =
the portal's own document IDs (LPD-<n> / GPD-<n>). Never a partner, a name or a file name.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCHEMA_PATH = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")
TITLE = "Published To"
DESCRIPTION = ("Where and when this document was delivered: the channel (LP portal, GP portal, Datum, Email), the first "
               "posted date and the portal's posting IDs. Set by the catalog from the portals (read-only sources); a "
               "person's value is never overwritten. CAT-WO-05 R-030.")
CHANNELS = {"lp_portal": "LP portal", "gp_portal": "GP portal", "datum": "Datum", "email": "Email"}
FIELDS = {"channel": "Channel", "posted_date": "Posted date", "posting_id": "Posting ID"}


def design(sel, text, date):
    return {"channel": sel(FIELDS["channel"], CHANNELS, multi=True), "posted_date": date(FIELDS["posted_date"]),
            "posting_id": text(FIELDS["posting_id"])}


def check(lim_fields, lim_choices, fields):
    p = []
    if len(fields) > lim_fields: p.append(f"{TITLE}: {len(fields)} fields > {lim_fields}")
    for k, (spec, ch) in fields.items():
        if ch and len(ch) > lim_choices: p.append(f"{k}: {len(ch)} choices > {lim_choices}")
    return p


def main():
    mode = next((a for a in sys.argv[1:] if a in ("--check", "--create-drafts", "--read-published")), None)
    if not mode: sys.exit(__doc__)
    sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))
    import labels_setup as ls
    import labels_setup_wo02 as w2
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    fields = design(ls.sel, ls.text, ls.date)
    svc = build("drivelabels", "v2", credentials=ls.creds(), cache_discovery=False)
    try:
        lim = svc.limits().getLabel(name="limits/label").execute()
    except HttpError:
        lim = {"maxFields": 10, "fieldLimits": {"selectionLimits": {"maxChoices": 200}}}
    mf = lim.get("maxFields", 10); mc = lim.get("fieldLimits", {}).get("selectionLimits", {}).get("maxChoices", 200)
    labs = w2._labels(svc)
    lab = labs.get(TITLE)
    print(f"limits: {mf} fields per label, {mc} choices per field; labels: {len(labs)}")
    print(f"{TITLE} (L10): " + ("not created" if not lab else f"state {lab.get('lifecycle', {}).get('state')}, "
                                 f"unpublished changes {bool(lab.get('lifecycle', {}).get('hasUnpublishedChanges'))}"))
    probs = check(mf, mc, fields)
    print("design check: " + ("OK (3 fields; Channel 4 choices, multi-select)" if not probs else "PROBLEMS: " + "; ".join(probs)))
    pp = w2._perm_problems(svc, labs)
    if lab:
        if w2._perms(svc, lab) != w2._perms(svc, labs["Allegis Document"]): pp.append(f"{TITLE}: permissions differ from Allegis Document")
    print("permissions: " + ("Ryan only, same as Allegis Document" if not pp else "PROBLEMS: " + "; ".join(pp)))
    if mode == "--check":
        print("--check: nothing created, nothing published."); return
    if "--release" not in sys.argv:
        sys.exit("--create-drafts / --read-published are release steps: add --release.")
    if probs: sys.exit("STOP: design problems")
    if mode == "--create-drafts":
        src = [p for p in w2._perm_problems(svc, {"Allegis Document": labs["Allegis Document"]}) if p.startswith("Allegis Document")]
        if src: sys.exit("STOP: " + "; ".join(src))
        if not lab:
            body = {"labelType": "ADMIN", "properties": {"title": TITLE, "description": DESCRIPTION},
                    "fields": [spec for spec, _ in fields.values()]}
            lab = svc.labels().create(body=body, useAdminAccess=True).execute()
            print(f"+ {TITLE}: created as DRAFT")
        else:
            have = {f["properties"]["displayName"] for f in lab.get("fields", [])}
            reqs = [{"createField": {"field": spec}} for spec, _ in fields.values() if spec["properties"]["displayName"] not in have]
            if reqs:
                svc.labels().delta(name=w2._base(lab), body={"useAdminAccess": True, "requests": reqs}).execute()
            print(f"= {TITLE}: exists; {len(reqs)} field(s) added to the draft")
        a, r = w2._reconcile_perms(svc, labs["Allegis Document"], lab)
        print(f"  {TITLE} permissions = Allegis Document's (Ryan only): +{a} / -{r}")
        print("Draft only. Ryan: review and PUBLISH in Admin console > Label manager (on for Drive), then run --read-published --release.")
        return
    # --read-published
    if not lab: sys.exit(f"STOP: no '{TITLE}' label")
    lc = lab.get("lifecycle", {})
    if lc.get("state") != "PUBLISHED" or lc.get("hasUnpublishedChanges"):
        sys.exit(f"STOP: '{TITLE}' is not published (state {lc.get('state')}, unpublished changes {bool(lc.get('hasUnpublishedChanges'))})")
    if pp: sys.exit("STOP: " + "; ".join(pp))
    out = {"label_id": lab["id"], "title": TITLE, "fields": {}}
    for key, disp in FIELDS.items():
        f = w2._field(lab, disp)
        if not f: sys.exit(f"STOP: field '{disp}' is not on the published label")
        if key == "channel":
            g = {c["properties"]["displayName"]: c["id"] for c in f.get("selectionOptions", {}).get("choices", [])}
            ch = {code: g[d] for code, d in CHANNELS.items() if d in g}
            if set(ch) != set(CHANNELS): sys.exit("STOP: a Channel choice is missing on the published label")
            out["fields"][key] = {"field_id": f["id"], "type": "selectionOptions", "multi": True, "choices": ch}
        elif key == "posted_date":
            out["fields"][key] = {"field_id": f["id"], "type": "dateOptions"}
        else:
            out["fields"][key] = {"field_id": f["id"], "type": "textOptions"}
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    schema["published"] = out
    json.dump(schema, open(SCHEMA_PATH, "w", encoding="utf-8"), indent=1)
    print(f"Wrote {os.path.normpath(SCHEMA_PATH)}: 'published' label + 3 fields. Review the diff and commit it before the deploy.")


if __name__ == "__main__":
    main()
