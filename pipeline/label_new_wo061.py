r"""
CAT-WO-06.1 · label the readable files in the labelled scope (R-019: all of LIMITED - Finance) that carry no catalog
label yet: the 614 found on 2026-11-23 now, and every new file from then on (nightly step `label`, after derive).

  py pipeline\label_new_wo061.py --db-url-file <url file> [--release] [--apply] [--limit N]

Same path as the original bulk labeller (labels_sync.py --drive): the catalog's values for the full label set
(Allegis Document incl. Catalog ID, Execution, Parties, Version, Published To, Handling, Catalog Review = Needs review).
Guards:
  - Secret tier never: Secret / noise / shortcut / trashed / removed files are not in scope, and a file whose live
    Handling tier is Secret is skipped
  - a person's value is never overwritten: each file's live labels are read right before writing; a file that already
    carries ANY catalog label (someone labelled it since the last read-back) is skipped and left to the read-back
  - dates are RFC 3339 strings (label_sync_wo02.mods_for, CAT-WO-03.2)
  - streamed in batches of 25 files; idempotent (a labelled file joins app.labelled_file at once and is never in scope
    again); counts and codes only, never a file name
"""
import argparse, collections, json, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_labels as cl
import label_sync_wo02 as ls

APPROVED_DRIVES = ls.APPROVED_DRIVES
BATCH = 25
FULL = ["kind", "entities", "portcos", "fiscal_year", "period", "effective_date", "workstream", "issuer", "stage", "executed_date",
        "status", "issued_date", "issuing_entity", "receiving_entities", "subject_codes", "subject_person",
        "version_family", "version_role", "version_supersedes", "version_amends",
        "published_channels", "published_date", "published_ids"]

SCOPE_SQL = """
SELECT f.file_id FROM cat.file f
WHERE f.drive_name = ANY(%s) AND f.removed_run IS NULL AND f.noise_flag IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'
  AND f.is_shortcut IS NOT TRUE AND f.trashed IS NOT TRUE
  AND NOT EXISTS (SELECT 1 FROM app.labelled_file l WHERE l.file_id = f.file_id)
ORDER BY f.file_id
"""


def scope(cur):
    cur.execute(SCOPE_SQL, (list(APPROVED_DRIVES),))
    return [r[0] for r in cur.fetchall()]


def full_mods(row, schema):
    """labelModifications for a never-labelled file: every catalog value the published labels can hold (no unsets),
    plus Catalog ID, Handling (tier + Contains, raise rules) and Catalog Review = Needs review. -> (mods, fields written)"""
    e = cl.expected(row, schema)
    fields = [f for f in FULL if schema.has(f) and e.get(f) not in (None, "", []) and f not in e.get("_unwritable", ())]
    mods = ls.mods_for(fields, e, schema)
    by = {m["labelId"]: m for m in mods}
    S = schema.S

    def add(lk, fm):
        lid = S[lk]["label_id"]
        if lid not in by:
            by[lid] = {"labelId": lid, "fieldModifications": []}; mods.append(by[lid])
        by[lid]["fieldModifications"].append(fm)
    if "catalog_id" in S["doc"]["fields"] and row.get("document_id"):
        add("doc", {"fieldId": S["doc"]["fields"]["catalog_id"]["field_id"], "setTextValues": [str(row["document_id"])]})
    elif S["doc"]["label_id"] not in by:
        add("doc", {"fieldId": S["doc"]["fields"]["kind"]["field_id"], "unsetValues": True})   # the label itself must be applied
    H = S["handling"]["fields"]
    tier = row.get("handling") if row.get("handling") in (H["tier"].get("choices") or {}) else None
    contains = set(e.get("contains") or []) | set(e.get("_content_contains") or [])
    raise_ = cl.handling_raise(e, {"tier": tier, "contains": sorted(contains)}, schema)
    tier = raise_.get("tier", tier)
    contains = set(raise_.get("contains", contains))
    if tier == "secret":
        return None, []                                       # never (Secret files are out of scope; belt and braces)
    if tier:
        add("handling", {"fieldId": H["tier"]["field_id"], "setSelectionValues": [H["tier"]["choices"][tier]]})
    ch = H["contains"].get("choices") or {}
    if contains & set(ch):
        add("handling", {"fieldId": H["contains"]["field_id"], "setSelectionValues": [ch[c] for c in sorted(contains & set(ch))]})
    R = S["review"]["fields"]["status"]
    add("review", {"fieldId": R["field_id"], "setSelectionValues": [R["choices"]["needs_review"]]})
    return mods, fields


def run(connect, svc, schema, apply=False, limit=None, log=print, sleep=time.sleep):
    """connect(): a NEW DB connection (the Drive part is long). -> report dict (counts only)."""
    with connect() as conn, conn.cursor() as cur:
        ids = scope(cur)
    if limit:
        ids = ids[:limit]
    rep = collections.Counter()
    by_kind, by_ent, by_field = collections.Counter(), collections.Counter(), collections.Counter()
    sampled = changed_mtime = 0
    tries = collections.Counter()
    labelled_ids = []
    for s0 in range(0, len(ids), 500):
        seg = ids[s0:s0 + 500]
        with connect() as conn, conn.cursor() as cur:
            rows = cl.catalog_rows(cur, seg)
        live = cl.read_labels(svc, seg, schema.include_labels())          # right before writing: a person's label wins
        plans = []
        for fid in seg:
            L = live.get(fid) or {"http": 0}
            if L["http"] != 200:
                rep["read_error" if L["http"] != 404 else "gone"] += 1; continue
            d = schema.decode(L["labelInfo"])
            if (L.get("labelInfo") or {}).get("labels"):
                rep["already_carries_a_label (left to the read-back)"] += 1; continue
            if d.get("tier") == "secret":
                rep["secret_skipped"] += 1; continue
            r = rows.get(fid)
            if not r:
                rep["no_catalog_row"] += 1; continue
            mods, fields = full_mods(r, schema)
            if not mods:
                rep["secret_skipped"] += 1; continue
            plans.append((fid, mods))
            by_kind[r.get("kind") or "(no kind)"] += 1
            for e in (r.get("entities") or ["(no entity)"]):
                by_ent[e] += 1
            by_field.update(fields)
        rep["to_label"] += len(plans)
        if not apply:
            labelled_ids += [f for f, _ in plans]           # dry run: the files that WOULD be labelled
        if not apply or not plans:
            continue
        queue = list(plans)
        while queue:
            chunk, queue = queue[:BATCH], queue[BATCH:]
            smp = chunk[0][0]
            before = svc.files().get(fileId=smp, fields="modifiedTime", supportsAllDrives=True).execute().get("modifiedTime")
            ok, retry = [], []

            def cb(req_id, resp, exc, _c=chunk, ok=ok, retry=retry):
                item = _c[int(req_id)]
                if exc is None:
                    ok.append(item); return
                st = getattr(getattr(exc, "resp", None), "status", 0) or getattr(exc, "status_code", 0)
                if (st in (429, 500, 502, 503) or (st == 403 and "rate" in str(exc).lower())) and tries[item[0]] < 4:
                    tries[item[0]] += 1; retry.append(item)
                else:
                    rep["errors"] += 1
                    rep[f"error:{st}"] += 1
            b = svc.new_batch_http_request(callback=cb)
            for i, (fid, mods) in enumerate(chunk):
                b.add(svc.files().modifyLabels(fileId=fid, body={"labelModifications": mods}), request_id=str(i))
            b.execute()
            after = svc.files().get(fileId=smp, fields="modifiedTime", supportsAllDrives=True).execute().get("modifiedTime")
            sampled += 1; changed_mtime += before != after
            if ok:
                with connect() as conn, conn.cursor() as cur:
                    cur.executemany("INSERT INTO app.labelled_file (file_id, source) VALUES (%s, 'label_new') ON CONFLICT (file_id) DO NOTHING",
                                    [(f,) for f, _ in ok])
                labelled_ids += [f for f, _ in ok]
                rep["labelled"] += len(ok)
            if retry:
                queue = retry + queue; sleep(5 + random.random() * 5)
            else:
                sleep(1.0)
    rep["in_scope"] = len(ids)
    log(f"LABEL NEW {'APPLIED' if apply else 'DRY RUN (nothing written)'}: in scope {len(ids):,} · to label {rep['to_label']:,} · "
        f"labelled {rep['labelled']:,} · errors {rep['errors']:,} · " + " · ".join(f"{k} {v:,}" for k, v in sorted(rep.items())
        if k not in ("to_label", "labelled", "errors", "in_scope")) + (f" · modifiedTime changed on {changed_mtime} of {sampled} sampled" if apply else ""))
    log("  by kind: " + ", ".join(f"{k} {n:,}" for k, n in by_kind.most_common(15)))
    log("  by entity: " + ", ".join(f"{k} {n:,}" for k, n in by_ent.most_common(15)))
    log("  fields written: " + ", ".join(f"{k} {n:,}" for k, n in sorted(by_field.items())))
    rep["mtime_sampled"], rep["mtime_changed"] = sampled, changed_mtime
    return rep, labelled_ids


def nightly_step(connect, apply, log=print):
    """CAT-WO-06.1 nightly `label` (after derive): label new files in the labelled scope, then re-run the WO-02 derive
    part (status, parties, families, portal Issued) so the newly labelled documents get their Status the same night,
    before the read-back and re-sync. A Drive failure is reported and never stops the nightly."""
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    if home not in sys.path: sys.path.insert(0, home)
    import labels_sync as lsync
    from googleapiclient.discovery import build
    try:
        svc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)
        rep, done = run(connect, svc, cl.Schema(cl.load_schema()), apply=apply, log=log)
    except (Exception, SystemExit) as e:
        log(f"   label NOT run ({type(e).__name__}); new files stay unlabelled until the next night")
        return
    if apply and done:
        import apply_derive_wo02
        os.environ["CATWO06_PAGES"], old = "0", os.environ.get("CATWO06_PAGES")
        try:
            c = connect()
            apply_derive_wo02.run(c, apply=True, log=log)
            c.close()
        finally:
            if old is None: os.environ.pop("CATWO06_PAGES", None)
            else: os.environ["CATWO06_PAGES"] = old


def main():
    import psycopg
    import dbguard_wo03 as dbg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    sys.path.insert(0, home); os.chdir(home)
    import labels_sync as lsync
    import pages_wo06
    lsync.InstalledAppFlow = pages_wo06._NoBrowser          # never a browser window
    from googleapiclient.discovery import build
    svc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)
    run(lambda: psycopg.connect(url), svc, cl.Schema(cl.load_schema()), apply=a.apply, limit=a.limit)


if __name__ == "__main__":
    main()
