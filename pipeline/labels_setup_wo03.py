r"""
CAT-WO-03 · label changes, DRAFTED for Ryan to publish in Admin console > Label manager (same as CAT-WO-02 Part 2).

  Parties             + "Subject code(s)"  text: roster codes only (LP- / GM- / GPM-), R-026
                      + "Subject (person)" user: a current staff @allegiscapital.com account, R-026
                      + the 11 new entity choices on Issuing entity and Receiving entity
  Allegis Document    + the 11 new entity choices on Entity
  Handling            + "Personnel info" on Contains (code: personnel), R-026

  py pipeline\labels_setup_wo03.py --plan --db-url-file <url file>                # OFFLINE: what would change, limits check. No Drive call.
  py pipeline\labels_setup_wo03.py --check --db-url-file <url file>               # + reads Label manager (read-only)
  py pipeline\labels_setup_wo03.py --create-drafts --release --db-url-file <...>  # unpublished deltas only; Ryan reviews and PUBLISHES
  py pipeline\labels_setup_wo03.py --read-published --release --db-url-file <...> # after Ryan publishes: ids -> src/lib/labels_schema.json

This script never publishes. Run from C:\DriveCatalog (reuses labels_setup.py's sign-in, token_labels.json).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCHEMA_PATH = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")

SUBJECT_CODES = "Subject code(s)"
SUBJECT_PERSON = "Subject (person)"
PERSONNEL = ("personnel", "Personnel info")
MAX_FIELDS, MAX_CHOICES = 10, 200


def ref_entities(cur):
    cur.execute("SELECT entity_code FROM ref.entity WHERE active IS NOT FALSE ORDER BY entity_code")
    return [r[0] for r in cur.fetchall()]


def plan(schema, entities):
    """Pure: the changes against the PUBLISHED schema (labels_schema.json) and the limit check.
    -> {new_entities, doc_entity_n, issuing_n, receiving_n, parties_fields_n, add_subject_fields, add_personnel, problems}"""
    have = set(schema["doc"]["fields"]["entity"]["choices"])
    new = [e for e in entities if e not in have]
    P = schema.get("parties", {"fields": {}})["fields"]
    iss = len(P.get("issuing_entity", {}).get("choices", {})) + len([e for e in new if e not in P.get("issuing_entity", {}).get("choices", {})])
    rcv = len(P.get("receiving_entities", {}).get("choices", {})) + len([e for e in new if e not in P.get("receiving_entities", {}).get("choices", {})])
    add_subj = [f for f in ("subject_codes", "subject_person") if f not in P]
    pf = len(P) + len(add_subj)
    add_pers = PERSONNEL[0] not in schema["handling"]["fields"]["contains"].get("choices", {})
    out = {"new_entities": new, "doc_entity_n": len(have) + len(new), "issuing_n": iss, "receiving_n": rcv,
           "parties_fields_n": pf, "add_subject_fields": add_subj, "add_personnel": add_pers,
           "doc_fields_n": len(schema["doc"]["fields"])}
    probs = []
    for k in ("doc_entity_n", "issuing_n", "receiving_n"):
        if out[k] > MAX_CHOICES: probs.append(f"{k}: {out[k]} choices > {MAX_CHOICES}")
    if pf > MAX_FIELDS: probs.append(f"Parties: {pf} fields > {MAX_FIELDS}")
    out["problems"] = probs
    return out


def print_plan(p):
    print(f"new entity choices: {len(p['new_entities'])} ({', '.join(p['new_entities'])})")
    print(f"  Allegis Document Entity: {p['doc_entity_n']} choices · Parties Issuing: {p['issuing_n']} · Receiving: {p['receiving_n']} (limit {MAX_CHOICES})")
    print(f"Parties: + {', '.join(p['add_subject_fields']) or 'nothing'} -> {p['parties_fields_n']} fields (limit {MAX_FIELDS})")
    print(f"Handling Contains: {'+ Personnel info' if p['add_personnel'] else 'Personnel info already there'}")
    print("design check: " + ("OK" if not p["problems"] else "PROBLEMS: " + "; ".join(p["problems"])))


def _db_entities():
    import psycopg
    import dbguard_wo03 as dbg
    i = sys.argv.index("--db-url-file") if "--db-url-file" in sys.argv else -1
    if i < 0: sys.exit("--db-url-file <url file> is required (ref.entity is read from it, read-only)")
    url = dbg.checked_url(sys.argv[i + 1], "--release" in sys.argv)
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
        return ref_entities(cur)


def main():
    mode = next((a for a in sys.argv[1:] if a in ("--plan", "--check", "--create-drafts", "--read-published")), None)
    if not mode: sys.exit(__doc__)
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    p = plan(schema, _db_entities())
    print_plan(p)
    if mode == "--plan" or p["problems"]:
        print("--plan: offline, nothing read from or written to Drive."); return
    sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))
    import labels_setup as ls
    import labels_setup_wo02 as w2
    from googleapiclient.discovery import build
    svc = build("drivelabels", "v2", credentials=ls.creds(), cache_discovery=False)
    labs = w2._labels(svc)
    for t in ("Allegis Document", "Parties", "Handling"):
        lc = labs[t].get("lifecycle", {})
        print(f"  {t}: state {lc.get('state')}, unpublished changes {bool(lc.get('hasUnpublishedChanges'))}")
    probs = w2._perm_problems(svc, labs)
    print("permissions: " + ("Ryan only, Parties matches Allegis Document" if not probs else "PROBLEMS: " + "; ".join(probs)))
    if mode == "--check":
        print("--check: nothing created, nothing published."); return
    if "--release" not in sys.argv:
        sys.exit("--create-drafts / --read-published are CAT-WO-03 release steps: add --release (Ryan's go-ahead).")
    if probs: sys.exit("STOP: permissions differ - fix in Label manager first.")
    if mode == "--create-drafts":
        create_drafts(svc, labs, p)
    else:
        read_published(svc, p)


def create_drafts(svc, labs, p):
    """Unpublished deltas only. Idempotent (re-running skips what is there). Never publishes."""
    import labels_setup as ls
    import labels_setup_wo02 as w2
    doc, par, han = labs["Allegis Document"], labs["Parties"], labs["Handling"]

    def add_choices(lab, display, codes):
        f = w2._field(lab, display)
        have = {c["properties"]["displayName"] for c in f.get("selectionOptions", {}).get("choices", [])}
        return [{"createSelectionChoice": {"fieldId": f["id"], "choice": {"properties": {"displayName": c}}}} for c in codes if c not in have]

    reqs = add_choices(doc, "Entity", p["new_entities"])
    if reqs: svc.labels().delta(name=w2._base(doc), body={"useAdminAccess": True, "requests": reqs}).execute()
    print(f"~ Allegis Document: {len(reqs)} unpublished Entity choice(s)")
    reqs = add_choices(par, "Issuing entity", p["new_entities"]) + add_choices(par, "Receiving entity", p["new_entities"])
    if not w2._field(par, SUBJECT_CODES):
        spec, _ = ls.text(SUBJECT_CODES)
        reqs.append({"createField": {"field": spec}})
    if not w2._field(par, SUBJECT_PERSON):
        spec, _ = ls.user(SUBJECT_PERSON)
        reqs.append({"createField": {"field": spec}})
    if reqs: svc.labels().delta(name=w2._base(par), body={"useAdminAccess": True, "requests": reqs}).execute()
    print(f"~ Parties: {len(reqs)} unpublished change(s) (entity choices, {SUBJECT_CODES}, {SUBJECT_PERSON})")
    reqs = add_choices(han, "Contains", [PERSONNEL[1]])
    if reqs: svc.labels().delta(name=w2._base(han), body={"useAdminAccess": True, "requests": reqs}).execute()
    print(f"~ Handling: {len(reqs)} unpublished change(s) (Contains + {PERSONNEL[1]})")
    print("Drafts only. Ryan: review and PUBLISH in Admin console > Label manager, then run --read-published --release.")


def read_published(svc, p):
    """After Ryan publishes: refuse while anything is still unpublished, then write the ids into labels_schema.json."""
    import labels_setup_wo02 as w2
    labs = w2._labels(svc)
    pend = [t for t in ("Allegis Document", "Parties", "Handling") if labs[t].get("lifecycle", {}).get("hasUnpublishedChanges")]
    if pend: sys.exit(f"STOP: still unpublished in Label manager: {pend}")
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))

    def ids(lab, display):
        f = w2._field(lab, display)
        return f, {c["properties"]["displayName"]: c["id"] for c in f.get("selectionOptions", {}).get("choices", []) if not c.get("lifecycle", {}).get("disabledPolicy")}

    _, g = ids(labs["Allegis Document"], "Entity")
    for e in p["new_entities"]:
        if e not in g: sys.exit(f"STOP: Entity choice {e} not on the published label")
        schema["doc"]["fields"]["entity"]["choices"][e] = g[e]
    for fk, disp in (("issuing_entity", "Issuing entity"), ("receiving_entities", "Receiving entity")):
        _, g = ids(labs["Parties"], disp)
        for e in p["new_entities"]:
            if e not in g: sys.exit(f"STOP: {disp} choice {e} not on the published label")
            schema["parties"]["fields"][fk]["choices"][e] = g[e]
    sc, sp = w2._field(labs["Parties"], SUBJECT_CODES), w2._field(labs["Parties"], SUBJECT_PERSON)
    if not sc or not sp: sys.exit("STOP: the Subject fields are not on the published Parties label")
    schema["parties"]["fields"]["subject_codes"] = {"field_id": sc["id"], "type": "textOptions"}
    schema["parties"]["fields"]["subject_person"] = {"field_id": sp["id"], "type": "userOptions"}
    _, g = ids(labs["Handling"], "Contains")
    if PERSONNEL[1] not in g: sys.exit("STOP: Contains 'Personnel info' not on the published Handling label")
    schema["handling"]["fields"]["contains"]["choices"][PERSONNEL[0]] = g[PERSONNEL[1]]
    json.dump(schema, open(SCHEMA_PATH, "w", encoding="utf-8"), indent=1)
    print(f"Wrote {os.path.normpath(SCHEMA_PATH)} - review the diff and commit it before the deploy.")


if __name__ == "__main__":
    main()
