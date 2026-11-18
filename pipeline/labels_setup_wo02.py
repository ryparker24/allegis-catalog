r"""
CAT-WO-02 · R-021 + R-022 label changes, through the labels_setup.py flow (draft -> check limits -> publish).

  L11 "Parties"      Issuing entity (select: every ref.entity code, every portco code, EXTERNAL)
                     Receiving entity (multi-select: every ref.entity code, LP, EXTERNAL)   - never an LP / person name
  "Execution" ->     renamed "Status & Execution"; keeps Stage, Executed date, Evidence;
                     adds Status (Draft / In review / Final / Issued / Superseded) and Issued date.

  py pipeline\labels_setup_wo02.py --check            # limits + design check; lists current labels. CREATES NOTHING.
  py pipeline\labels_setup_wo02.py --create-drafts    # creates L11 as a DRAFT and the Execution changes as an unpublished delta
  py pipeline\labels_setup_wo02.py --publish          # publishes both, then adds them to labels_schema.json

Run from C:\DriveCatalog (it reuses labels_setup.py's sign-in, token_labels.json, and drive_crawl.db() for ref lists).
Publishing is a Part 2 release step (handoff), never done by --check.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))

STATUS = {"draft": "Draft", "in_review": "In review", "final": "Final", "issued": "Issued", "superseded": "Superseded"}
EXTRA_ISSUING = {"EXTERNAL": "External (third party)"}
EXTRA_RECEIVING = {"LP": "LP (outside limited partner)", "EXTERNAL": "External (third party)"}
NEW_EXEC_TITLE = "Status & Execution"
# item 9 RK2 (Ryan): two new choices on the Allegis Document label's Kind field, published WITH Part 2, not before
NEW_KIND_CHOICES = {"operating_agreement": "Operating Agreement", "operating_agreement_amendment": "Operating Agreement Amendment"}
# CYBER-II is not a real entity (AllegisCyber II = CIP-II): its Entity choice is DISABLED at the Part 2 publish, never
# deleted (a deleted choice would orphan any value already on a file; 0 files carry it today)
DISABLE_ENTITY_CHOICES = ["CYBER-II"]


def ref_lists(cur):
    cur.execute("SELECT entity_code FROM ref.entity WHERE active IS NOT FALSE ORDER BY entity_code")   # CYBER-II retired
    ents = {r[0]: r[0] for r in cur.fetchall()}
    cur.execute("SELECT portco_code, coalesce(street_name, name) FROM ref.portco WHERE active ORDER BY 2")
    pcos = {r[0]: r[1] for r in cur.fetchall()}
    return ents, pcos


def design(ents, pcos, sel, date):
    """(parties fields, new exec fields) in labels_setup.py's field-builder shapes."""
    issuing = {**ents, **{c: f"{n} (portco)" for c, n in pcos.items()}, **EXTRA_ISSUING}
    receiving = {**ents, **EXTRA_RECEIVING}
    parties = {"issuing_entity": sel("Issuing entity", issuing), "receiving_entities": sel("Receiving entity", receiving, multi=True)}
    exec_new = {"status": sel("Status", STATUS), "issued_date": date("Issued date")}
    return parties, exec_new


def check(lim_fields, lim_choices, parties, exec_existing_n, exec_new):
    problems = []
    if len(parties) > lim_fields: problems.append(f"Parties: {len(parties)} fields > {lim_fields}")
    if exec_existing_n + len(exec_new) > lim_fields: problems.append(f"Status & Execution: {exec_existing_n + len(exec_new)} fields > {lim_fields}")
    for k, (spec, ch) in {**parties, **exec_new}.items():
        if ch and len(ch) > lim_choices: problems.append(f"{k}: {len(ch)} choices > {lim_choices}")
    return problems


def main():
    import labels_setup as ls          # the existing script: creds(), sel(), date(), limits
    import drive_crawl as dc
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    mode = next((a for a in sys.argv[1:] if a.startswith("--")), "--check")
    if mode not in ("--check", "--create-drafts", "--publish"): sys.exit(__doc__)
    # ref lists (read-only). --db-url-file <file> reads them from that DB (e.g. a throwaway branch) instead of
    # drive_crawl.db() (catalog_db_url.txt = main).
    if "--db-url-file" in sys.argv:
        import psycopg
        url = open(sys.argv[sys.argv.index("--db-url-file") + 1]).read().strip()
        conn = psycopg.connect(url, options="-c default_transaction_read_only=on")
    else:
        conn = dc.db()
        conn.execute("SET default_transaction_read_only = on")   # ref lists only; never writes
    with conn, conn.cursor() as cur:
        ents, pcos = ref_lists(cur)
    parties, exec_new = design(ents, pcos, ls.sel, ls.date)
    svc = build("drivelabels", "v2", credentials=ls.creds(), cache_discovery=False)
    try:
        lim = svc.limits().getLabel(name="limits/label").execute()
    except HttpError as e:
        print(f"(limits endpoint unavailable: {e.status_code} - using documented limits: 10 fields, 200 options)")
        lim = {"maxFields": 10, "fieldLimits": {"selectionLimits": {"maxChoices": 200}}}
    max_fields = lim.get("maxFields", 10)
    max_choices = lim.get("fieldLimits", {}).get("selectionLimits", {}).get("maxChoices", 200)
    labels = svc.labels().list(useAdminAccess=True, view="LABEL_VIEW_FULL", pageSize=200).execute().get("labels", [])
    by_title = {l["properties"]["title"]: l for l in labels}
    exec_lab = by_title.get("Execution") or by_title.get(NEW_EXEC_TITLE)
    exec_n = len(exec_lab.get("fields", [])) if exec_lab else 0
    print(f"limits: {max_fields} fields per label, {max_choices} choices per field")
    print(f"existing labels: {', '.join(sorted(by_title))}")
    print(f"Parties (L11): {'EXISTS' if 'Parties' in by_title else 'not created'} - issuing {len(parties['issuing_entity'][1])} choices "
          f"({len(ents)} entities + {len(pcos)} active portcos + EXTERNAL), receiving {len(parties['receiving_entities'][1])} choices ({len(ents)} entities + LP + EXTERNAL)")
    print(f"Execution: {exec_n} fields now; + Status ({len(STATUS)} choices) + Issued date = {exec_n + 2}; title -> '{NEW_EXEC_TITLE}'")
    problems = check(max_fields, max_choices, parties, exec_n, exec_new)
    print("design check: " + ("OK" if not problems else "PROBLEMS: " + "; ".join(problems)))
    if mode == "--check" or problems:
        print(f"Kind: + {len(NEW_KIND_CHOICES)} choices at publish ({', '.join(NEW_KIND_CHOICES)}); "
              f"Entity: disable {', '.join(DISABLE_ENTITY_CHOICES)} (disable, not delete)")
        print("--check: nothing created, nothing published."); return
    if "--release" not in sys.argv:
        raise SystemExit("--create-drafts / --publish are CAT-WO-02 Part 2 release steps: add --release, and run them only "
                         "on Ryan's go-ahead (handoff, Part 2 release steps).")
    if mode == "--create-drafts":
        create_drafts(svc, by_title, parties, exec_new)
    else:
        publish(svc, parties)


# ---------------------------------------------------------------- release steps (run only with --release)
def _base(lab):
    return lab["name"].split("@")[0]          # always act on the latest revision


def _labels(svc):
    out, tok = {}, None
    while True:
        r = svc.labels().list(useAdminAccess=True, publishedOnly=False, view="LABEL_VIEW_FULL", pageToken=tok).execute()
        for l in r.get("labels", []): out[l["properties"]["title"]] = l
        tok = r.get("nextPageToken")
        if not tok: return out


def _field(lab, display):
    return next((f for f in lab.get("fields", []) if f["properties"]["displayName"] == display), None)


# Ryan: permission and visibility "Ryan only", same as the existing four labels. Every label this step touches must
# have exactly the same permission set as Allegis Document, and that set may name nobody but Ryan.
OWNER = "ryan@allegiscapital.com"
WO02_LABELS = ("Allegis Document", "Parties", NEW_EXEC_TITLE)


def _perms(svc, lab):
    """All permissions of a label (paged) as {(principal kind, principal, role)}; one principal per permission."""
    out, tok = set(), None
    while True:
        r = svc.labels().permissions().list(parent=_base(lab), useAdminAccess=True, pageToken=tok).execute()
        for pm in r.get("labelPermissions", []):
            if pm.get("email"): out.add(("email", pm["email"].lower(), pm["role"]))
            elif pm.get("audience"): out.add(("audience", pm["audience"], pm["role"]))
            else: out.add(("other", pm.get("group") or pm.get("person") or pm.get("name", "?"), pm["role"]))
        tok = r.get("nextPageToken")
        if not tok: return out


def _perm_problems(svc, labs):
    """[] when every WO-02 label has the same permissions as Allegis Document and they name only Ryan."""
    want = _perms(svc, labs["Allegis Document"])
    probs = [f"Allegis Document: a permission for someone other than Ryan ({k})" for k, who, _ in want if not (k == "email" and who == OWNER)]
    if not want: probs.append("Allegis Document: no permissions found")
    for t in WO02_LABELS[1:]:
        if t in labs and _perms(svc, labs[t]) != want:
            probs.append(f"{t}: permissions differ from Allegis Document")
    return probs


def _reconcile_perms(svc, src, dst):
    """Make dst's permissions equal src's (create missing; delete extra). Users / groups by EMAIL only, audiences by
    audience only - one principal per request (the API's oneof; reviews)."""
    want, have = _perms(svc, src), _perms(svc, dst)
    for k, who, role in sorted(want - have):
        body = {"role": role, ("email" if k == "email" else "audience"): who}
        if k == "other": raise SystemExit(f"source label has a permission type this script won't copy ({who}) - set it in Label manager")
        svc.labels().permissions().create(parent=_base(dst), body=body, useAdminAccess=True).execute()
    extra = have - want
    if extra:
        r = svc.labels().permissions().list(parent=_base(dst), useAdminAccess=True).execute()
        for pm in r.get("labelPermissions", []):
            key = ("email", pm["email"].lower(), pm["role"]) if pm.get("email") else ("audience", pm.get("audience"), pm["role"]) if pm.get("audience") else None
            if key in extra:
                svc.labels().permissions().delete(name=pm["name"], useAdminAccess=True).execute()
    return len(want - have), len(extra)


def create_drafts(svc, by_title, parties, exec_new):
    """Drafts / unpublished deltas only - nothing is visible to users until --publish. Idempotent: re-running skips
    what is already there."""
    doc = by_title["Allegis Document"]
    src_probs = [p for p in _perm_problems(svc, {"Allegis Document": doc}) if p.startswith("Allegis Document")]
    if src_probs: raise SystemExit("STOP: " + "; ".join(src_probs))
    # 1. L11 Parties: a new label as a DRAFT, with the same permissions as Allegis Document (Ryan only)
    if "Parties" not in by_title:
        body = {"labelType": "ADMIN", "properties": {"title": "Parties", "description":
                "Who issued the document and who received it (codes only: entity / portco codes, LP, EXTERNAL). CAT-WO-02 R-021."},
                "fields": [spec for spec, _ in parties.values()]}
        lab = svc.labels().create(body=body, useAdminAccess=True).execute()
        print("+ Parties: created as DRAFT")
    else:
        lab = by_title["Parties"]
        print("= Parties: exists")
    added, removed = _reconcile_perms(svc, doc, lab)            # also repairs a half-done earlier run
    print(f"  Parties permissions = Allegis Document's (Ryan only): +{added} / -{removed}")
    # 2. Execution -> "Status & Execution": + Status, + Issued date (unpublished delta)
    ex = by_title.get("Execution") or by_title[NEW_EXEC_TITLE]
    reqs = []
    if ex["properties"]["title"] != NEW_EXEC_TITLE:
        reqs.append({"updateLabel": {"properties": {"title": NEW_EXEC_TITLE}, "updateMask": "title"}})
    for spec, _ in exec_new.values():
        if not _field(ex, spec["properties"]["displayName"]):
            reqs.append({"createField": {"field": spec}})
    if reqs:
        svc.labels().delta(name=_base(ex), body={"useAdminAccess": True, "requests": reqs}).execute()
    print(f"~ {NEW_EXEC_TITLE}: {len(reqs)} unpublished change(s)")
    # 3. Allegis Document: + 2 Kind choices (RK2), Entity choice CYBER-II DISABLED (never deleted)
    reqs = []
    kind_f, ent_f = _field(doc, "Kind"), _field(doc, "Entity")
    have = {c["properties"]["displayName"]: c for c in kind_f.get("selectionOptions", {}).get("choices", [])}
    for code, disp in NEW_KIND_CHOICES.items():
        if disp not in have:
            reqs.append({"createSelectionChoice": {"fieldId": kind_f["id"], "choice": {"properties": {"displayName": disp}}}})
    for c in ent_f.get("selectionOptions", {}).get("choices", []):
        if c["properties"]["displayName"] in DISABLE_ENTITY_CHOICES and not c.get("lifecycle", {}).get("disabledPolicy"):
            reqs.append({"disableSelectionChoice": {"fieldId": ent_f["id"], "id": c["id"],
                                                    "disabledPolicy": {"hideInSearch": False, "showInApply": False}, "updateMask": "*"}})
    if reqs:
        svc.labels().delta(name=_base(doc), body={"useAdminAccess": True, "requests": reqs}).execute()
    print(f"~ Allegis Document: {len(reqs)} unpublished change(s) (Kind +{len(NEW_KIND_CHOICES)}, Entity disable {DISABLE_ENTITY_CHOICES})")
    print("Drafts only. Review in Admin console > Label manager, then run --publish --release.")


def publish(svc, parties):
    """Publish Parties, Status & Execution and Allegis Document, then write their ids into src/lib/labels_schema.json
    (the app reads it at build time: Parties / Status / Issued date become editable and the re-sync writes them)."""
    labs = _labels(svc)
    probs = _perm_problems(svc, labs)
    if probs: raise SystemExit("STOP, nothing published: " + "; ".join(probs))
    # what is pending, so changes someone made by hand in Label manager are not published unseen (CISO review)
    exec_have = {f["properties"]["displayName"] for f in labs[NEW_EXEC_TITLE].get("fields", [])}
    kind_have = {c["properties"]["displayName"] for c in _field(labs["Allegis Document"], "Kind").get("selectionOptions", {}).get("choices", [])}
    for title in ("Parties", NEW_EXEC_TITLE, "Allegis Document"):
        lc = labs[title].get("lifecycle", {})
        print(f"  {title}: state {lc.get('state')}, unpublished changes {bool(lc.get('hasUnpublishedChanges'))}, "
              f"revision {labs[title].get('revisionId')} (published {labs[title].get('publishedRevisionId')})")
    missing = [x for x in ("Status", "Issued date") if x not in exec_have] + [d for d in NEW_KIND_CHOICES.values() if d not in kind_have]
    if missing: raise SystemExit(f"STOP, nothing published: not in the drafts yet: {missing} - run --create-drafts --release")
    if "--yes" not in sys.argv:
        raise SystemExit("Check the lines above against Label manager, then re-run with --publish --release --yes.")
    for title in ("Parties", NEW_EXEC_TITLE, "Allegis Document"):
        lab = labs[title]
        if lab.get("lifecycle", {}).get("state") == "PUBLISHED" and not lab.get("lifecycle", {}).get("hasUnpublishedChanges"):
            print(f"= {title}: nothing to publish"); continue
        svc.labels().publish(name=_base(lab), body={"useAdminAccess": True}).execute()
        print(f"^ {title}: published")
    labs = _labels(svc)
    path = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")
    schema = json.load(open(path, encoding="utf-8"))

    def choices(f, names):
        g = {c["properties"]["displayName"]: c["id"] for c in f.get("selectionOptions", {}).get("choices", [])}
        return {code: g[disp] for code, disp in names.items() if disp in g}

    P = labs["Parties"]
    schema["parties"] = {"label_id": P["id"], "title": "Parties", "fields": {}}
    for key, (spec, names) in parties.items():   # names = the design's code -> display map (entities, portcos, LP, EXTERNAL)
        f = _field(P, spec["properties"]["displayName"])
        ch = choices(f, names)
        missing = sorted(set(names) - set(ch))
        if missing: raise SystemExit(f"Parties.{key}: {len(missing)} designed choice(s) not on the published label - stop")
        schema["parties"]["fields"][key] = {"field_id": f["id"], "type": "selectionOptions", "choices": ch}
    E = labs[NEW_EXEC_TITLE]
    schema["exec"]["title"] = NEW_EXEC_TITLE
    st = _field(E, "Status")
    sch = choices(st, STATUS)
    if set(sch) != set(STATUS): raise SystemExit(f"Status: {len(set(STATUS) - set(sch))} choice(s) missing on the published label - stop")
    schema["exec"]["fields"]["status"] = {"field_id": st["id"], "type": "selectionOptions", "choices": sch}
    schema["exec"]["fields"]["issued_date"] = {"field_id": _field(E, "Issued date")["id"], "type": "dateOptions"}
    D = labs["Allegis Document"]
    kch = choices(_field(D, "Kind"), NEW_KIND_CHOICES)
    if set(kch) != set(NEW_KIND_CHOICES): raise SystemExit("Kind: a new choice is missing on the published label - stop")
    schema["doc"]["fields"]["kind"]["choices"].update(kch)
    for code in DISABLE_ENTITY_CHOICES:
        schema["doc"]["fields"]["entity"]["choices"].pop(code, None)   # disabled: the app never offers or writes it
    json.dump(schema, open(path, "w", encoding="utf-8"), indent=1)
    print(f"Wrote {os.path.normpath(path)} - review the diff (Parties choice codes) and commit it before the deploy.")


if __name__ == "__main__":
    main()
