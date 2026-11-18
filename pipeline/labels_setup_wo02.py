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


def ref_lists(cur):
    cur.execute("SELECT entity_code FROM ref.entity ORDER BY entity_code")
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
        print("--check: nothing created, nothing published."); return
    raise SystemExit("--create-drafts / --publish are CAT-WO-02 Part 2 release steps; run them only on Ryan's go-ahead (handoff R-steps).")


if __name__ == "__main__":
    main()
