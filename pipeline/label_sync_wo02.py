r"""
CAT-WO-02 item 7 · nightly two-way label sync.

  readback : read every labelled file's labels (as the token's user) -> ops.label_state, app.labelled_file,
             and cat.document.*_confirmed where a PERSON set or confirmed a value.
  resync   : push changed catalog values to files already labelled. NEVER overwrites a person's value
             (Catalog Review = Confirmed, or a live value that differs from the last machine write): skipped, counted.

  py pipeline/label_sync_wo02.py readback --db-url-file <url file> --token <token json> [--apply]
  py pipeline/label_sync_wo02.py resync   --db-url-file <url file> --token <token json> [--apply] [--only <file id> ...]

--db-url-file is REQUIRED (no default: this never picks up the main DB by accident). Without --apply nothing is
written anywhere (Drive or DB); the run report is printed. Counts and IDs only; never file names.
At release, drive_crawl.py incremental calls readback() and labels_sync.py --resync calls resync() (handoff R-steps).
"""
import sys, os, argparse, datetime, json, time, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_labels as cl

APPROVED_DRIVES = ("LIMITED - Finance",)   # R-019; same list as labels_sync.APPROVED_DRIVES
BATCH = 25

# field -> cat.document column(s) for a person's confirmed value
CONFIRM_COL = {
    "kind": "kind_confirmed", "entities": "entities_confirmed", "portcos": "portcos_confirmed",
    "fiscal_year": "fiscal_year_confirmed", "effective_date": "effective_date_confirmed",
    "stage": "execution_stage_confirmed", "executed_date": "signed_date_confirmed",
    "status": "status_confirmed", "issued_date": "issued_date_confirmed",
    "issuing_entity": "issuing_entity_confirmed", "receiving_entities": "receiving_entities_confirmed",
    # period is split into fiscal_quarter_confirmed / fye_flag_confirmed below
}


# ------------------------------------------------------------------ the rule (pure; unit-tested)
def person_owned(live, machine, schema_fields):
    """Fields a person owns on one file: fields whose live value differs from the last machine write (a person set
    OR cleared them), plus - when Catalog Review = Confirmed / Wrong with Reviewed by - every field with a live value."""
    fields = [f for f in cl.PERSON_FIELDS if f in schema_fields]
    owned = set(cl.diff(live, machine, fields)) if machine is not None else set()
    if live.get("review_status") in ("confirmed", "wrong") and live.get("reviewed_by_set"):
        owned |= {f for f in fields if cl.norm(live.get(f)) != ""}
    return sorted(owned)


def plan_resync(expected, live, machine, prior_person, schema_fields):
    """-> (fields to write, fields skipped because a person owns them). Only fields where the catalog differs from Drive."""
    owned = set(prior_person) | set(person_owned(live, machine, schema_fields))
    fields = [f for f in cl.RESYNC_FIELDS if f in schema_fields]
    # a value the label cannot hold yet (choice not published) is never written - and never written as a blank
    differs = [f for f in cl.diff(expected, live, fields) if f not in expected.get("_unwritable", ())]
    return [f for f in differs if f not in owned], [f for f in differs if f in owned]


def mods_for(fields, expected, schema):
    """labelModifications that set (or unset) exactly these fields to the machine values. Never Handling or Review."""
    per = collections.defaultdict(list)
    for f in fields:
        lk, fk, kind = cl.FIELDS[f]
        if lk in ("handling", "review"):
            continue
        F = schema.S[lk]["fields"][fk]
        v = expected.get(f)
        if v in (None, "", []):
            per[lk].append({"fieldId": F["field_id"], "unsetValues": True}); continue
        if kind == "one": per[lk].append({"fieldId": F["field_id"], "setSelectionValues": [F["choices"][v]]})
        elif kind == "many": per[lk].append({"fieldId": F["field_id"], "setSelectionValues": [F["choices"][c] for c in v]})
        elif kind == "int": per[lk].append({"fieldId": F["field_id"], "setIntegerValues": [str(v)]})
        else:
            y, m, d = (int(x) for x in str(v)[:10].split("-"))
            per[lk].append({"fieldId": F["field_id"], "setDateValues": [{"year": y, "month": m, "day": d}]})
    return [{"labelId": schema.S[lk]["label_id"], "fieldModifications": fm} for lk, fm in per.items()]


# ------------------------------------------------------------------ DB helpers
def scope_ids(cur):
    """Files the read-back reads: approved drives, live, not secret / noise / shortcut (the labelling scope)."""
    cur.execute("""SELECT f.file_id FROM cat.file f WHERE f.drive_name = ANY(%s) AND f.removed_run IS NULL
                   AND f.noise_flag IS NOT TRUE AND coalesce(f.handling,'secret') <> 'secret' AND f.is_shortcut IS NOT TRUE
                   UNION SELECT file_id FROM app.labelled_file ORDER BY 1""", (list(APPROVED_DRIVES),))
    return [r[0] for r in cur.fetchall()]


def load_state(cur, ids):
    cur.execute("SELECT file_id, machine, live, person_fields FROM ops.label_state WHERE file_id = ANY(%s)", (list(ids),))
    return {r[0]: {"machine": r[1], "live": r[2], "person_fields": list(r[3] or [])} for r in cur.fetchall()}


def confirm_updates(doc_id, fields, live):
    """(sql, params) list writing a person's live values to cat.document.*_confirmed."""
    out = []
    for f in fields:
        v = live.get(f)
        if f == "period":
            if v in ("q1", "q2", "q3", "q4"):
                out.append(("UPDATE cat.document SET fiscal_quarter_confirmed=%s, fye_flag_confirmed=false, updated_at=now() WHERE document_id=%s", (int(v[1]), doc_id)))
            elif v == "fy":
                out.append(("UPDATE cat.document SET fiscal_quarter_confirmed=NULL, fye_flag_confirmed=true, updated_at=now() WHERE document_id=%s", (doc_id,)))
            continue   # month / as_of / n_a: no catalog column -> kept on the label only
        col = CONFIRM_COL.get(f)
        if col:
            out.append((f"UPDATE cat.document SET {col}=%s, updated_at=now() WHERE document_id=%s", (v if v not in ("", []) else None, doc_id)))
    return out


def new_run(cur, mode, apply):
    rid = f"{mode}_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    cur.execute("INSERT INTO ops.label_sync_run (run_id, mode, applied) VALUES (%s, %s, %s)", (rid, mode, apply))
    return rid


def finish_run(cur, rid, rep):
    cur.execute("""UPDATE ops.label_sync_run SET finished_at=now(), files_read=%s, confirmed_by_person=%s, resynced=%s,
                   skipped_person=%s, errors=%s, by_field=%s, notes=%s WHERE run_id=%s""",
                (rep["read"], rep["confirmed_by_person"], rep["resynced"], rep["skipped_person"], rep["errors"],
                 json.dumps(rep["by_field"]), rep.get("notes"), rid))


def report_line(mode, rep, apply):
    return (f"{mode.upper()} {'APPLIED' if apply else 'DRY RUN (nothing written)'}: read {rep['read']:,} · "
            f"confirmed by a person {rep['confirmed_by_person']:,} · re-synced {rep['resynced']:,} · "
            f"skipped as person-owned {rep['skipped_person']:,} · errors {rep['errors']:,}" + (f" · Entity held for Review {rep['held_for_review']:,}" if rep.get('held_for_review') else ""))


# ------------------------------------------------------------------ 7.1 read-back
def readback(connect, svc, schema, apply=False, ids=None, log=print):
    """connect(): a NEW DB connection. The Drive read takes many minutes, so the write phase opens its own."""
    fields = schema.active_fields()
    rep = {"read": 0, "confirmed_by_person": 0, "resynced": 0, "skipped_person": 0, "errors": 0, "by_field": {}}
    with connect() as conn, conn.cursor() as cur:
        ids = ids or scope_ids(cur)
        state = load_state(cur, ids)
        rows = {}
        for i in range(0, len(ids), 5000):
            rows.update(cl.catalog_rows(cur, ids[i:i + 5000]))
    by_field = collections.Counter()
    labelled, unlabelled, upd_state, confirms = [], [], [], []

    def one(fid, L):
        if L["http"] == 404:
            return                         # gone / no access: the crawl handles removals
        if L["http"] != 200:
            rep["errors"] += 1; return
        rep["read"] += 1
        d = schema.decode(L["labelInfo"])
        rep["unknown_choices"] = rep.get("unknown_choices", 0) + d["unknown_choices"]
        if not d["has_doc_label"] or d["tier"] == "secret":
            unlabelled.append(fid); return     # secret tier (R-010): out of the app's labelled set, never confirmed
        labelled.append(fid)
        st = state.get(fid) or {}
        live_codes = {k: d[k] for k in fields} | {"review_status": d["review_status"], "reviewed_by_set": d["reviewed_by_set"]}
        # first sight of a file: its live labels ARE the machine's bulk write (item 0.3: 0 drift), so a catalog value
        # that changed since is NOT mistaken for a person's edit (coder review)
        machine = st.get("machine") or {k: d[k] for k in fields}
        owned = person_owned(d, machine, fields)
        prior = set(st.get("person_fields") or [])
        prev_live = st.get("live") or {}
        # newly owned, or owned and changed again since the last read (a second edit is captured too)
        new = [f for f in owned if f not in prior or cl.norm(d.get(f)) != cl.norm(prev_live.get(f))]
        if new:
            rep["confirmed_by_person"] += 1
            by_field.update(new)
            doc = (rows.get(fid) or {}).get("document_id")
            if doc is not None:
                confirms += confirm_updates(doc, new, d)
        upd_state.append((fid, json.dumps(machine, default=str), json.dumps(live_codes, default=str), d["review_status"], d["reviewed_by_set"],
                          sorted(set(st.get("person_fields") or []) | set(owned))))

    seen = set()
    cl.read_labels(svc, ids, schema.include_labels(), on_item=lambda fid, L: (seen.add(fid), one(fid, L)))
    rep["errors"] += len(set(ids) - seen)      # never answered after all retries
    rep["by_field"] = dict(by_field)
    rep["notes"] = f"labelled {len(labelled):,}; read but without the Allegis Document label {len(unlabelled):,}"
    if apply:
        with connect() as conn, conn.cursor() as cur:
            rid = new_run(cur, "readback", True)
            cur.executemany("""INSERT INTO ops.label_state (file_id, machine, machine_at, live, live_at, review_status, reviewed_by_set, person_fields)
                               VALUES (%s, %s::jsonb, now(), %s::jsonb, now(), %s, %s, %s)
                               ON CONFLICT (file_id) DO UPDATE SET live=EXCLUDED.live, live_at=now(), review_status=EXCLUDED.review_status,
                                 reviewed_by_set=EXCLUDED.reviewed_by_set, person_fields=EXCLUDED.person_fields,
                                 machine=coalesce(ops.label_state.machine, EXCLUDED.machine),
                                 machine_at=coalesce(ops.label_state.machine_at, EXCLUDED.machine_at)""", upd_state)
            for sql, p in confirms:
                cur.execute(sql, p)
            # app.labelled_file now comes from Drive: add what carries the label, drop what no longer does
            cur.executemany("INSERT INTO app.labelled_file (file_id, source) VALUES (%s, 'drive_readback') ON CONFLICT (file_id) DO UPDATE SET source='drive_readback', loaded_at=now()", [(f,) for f in labelled])
            if unlabelled:
                cur.execute("DELETE FROM app.labelled_file WHERE file_id = ANY(%s)", (unlabelled,))
            finish_run(cur, rid, rep)
    log(report_line("readback", rep, apply))
    log(f"  by field (newly person-confirmed): {rep['by_field']}  · {rep['notes']}")
    return rep


# ------------------------------------------------------------------ 7.2 re-sync
def resync(connect, svc, schema, apply=False, only=None, log=print, sleep=time.sleep, hold_entities=()):
    """hold_entities: file ids whose Entity is NOT written (an entity conflict sent to Review, e.g. NL-I + NL-II)."""
    hold_entities = set(hold_entities or ())
    held = set()
    fields = schema.active_fields()
    rep = {"read": 0, "confirmed_by_person": 0, "resynced": 0, "skipped_person": 0, "errors": 0, "by_field": {}, "no_state": 0}
    conn = connect()
    with conn.cursor() as cur:
        if only:
            ids = list(only)
        else:
            cur.execute("SELECT file_id FROM app.labelled_file ORDER BY 1")
            ids = [r[0] for r in cur.fetchall()]
        state = load_state(cur, ids)
        if not state:
            conn.close()
            raise SystemExit("REFUSED: no ops.label_state for these files - run `readback --apply` first (the re-sync needs the machine snapshot).")
        rows = {}
        for i in range(0, len(ids), 5000):
            rows.update(cl.catalog_rows(cur, ids[i:i + 5000]))
    conn.commit()
    conn.close()          # the Drive read is long: reconnect for the writes
    # read live labels right before writing, so a person's edit since the last read-back is still respected
    plans, skipped_by_field, write_by_field = [], collections.Counter(), collections.Counter()

    def plan_one(fid, L):
        """-> (write fields, skip fields, expected) or None when the file is not a re-sync candidate."""
        if L["http"] != 200:
            return None
        d = schema.decode(L["labelInfo"])
        if not d["has_doc_label"] or d["tier"] == "secret":
            return None                   # not labelled (bulk labeller's job) / secret tier: never written
        st = state.get(fid)
        if not st or not st.get("machine"):
            return "no_state"             # never seen by a read-back: nothing known about who set what -> not touched
        e = cl.expected(rows.get(fid, {}), schema)
        write, skip = plan_resync(e, d, st["machine"], st.get("person_fields") or [], fields)
        if fid in hold_entities and "entities" in write:
            write = [f for f in write if f != "entities"]; held.add(fid)   # a set: the per-batch re-plan calls this again
        return write, skip, e

    def one(fid, L):
        if L["http"] != 200:
            rep["errors"] += L["http"] != 404; return
        rep["read"] += 1
        p = plan_one(fid, L)
        if p == "no_state":
            rep["no_state"] += 1; return
        if not p: return
        write, skip, e = p
        if skip:
            rep["skipped_person"] += 1; skipped_by_field.update(skip)
        if write:
            plans.append((fid, write, e)); write_by_field.update(write)

    seen = set()
    cl.read_labels(svc, ids, schema.include_labels(), on_item=lambda fid, L: (seen.add(fid), one(fid, L)))
    rep["errors"] += len(set(ids) - seen)
    rep["by_field"] = {"write": dict(write_by_field), "skipped_person": dict(skipped_by_field)}
    rep["held_for_review"] = len(held)
    if not apply:
        rep["resynced"] = 0
        rep["notes"] = f"would re-sync {len(plans):,} files"
        log(report_line("resync", rep, apply)); log(f"  {rep['notes']}; by field: {rep['by_field']}")
        return rep
    conn = connect()
    with conn.cursor() as cur:
        rid = new_run(cur, "resync", True)
    conn.commit()
    sampled = changed_mtime = 0
    queue = list(plans)
    tries = collections.Counter()   # retry cap per file (coder review): a persistent 429 can't loop forever
    while queue:
        chunk, queue = queue[:BATCH], queue[BATCH:]
        # re-read THIS batch's labels just before writing and re-plan: an edit made since the first read wins
        fresh = cl.read_labels(svc, [c[0] for c in chunk], schema.include_labels())
        replanned = []
        for fid, _w, _e in chunk:
            p = plan_one(fid, fresh.get(fid) or {"http": 0})
            if p == "no_state": continue
            if not p or not p[0]:
                if p and p[1]: rep["skipped_person"] += 1; skipped_by_field.update(p[1])
                continue
            replanned.append((fid, p[0], p[2]))
        chunk = replanned
        if not chunk:
            continue
        smp = chunk[0][0]
        before = svc.files().get(fileId=smp, fields="modifiedTime", supportsAllDrives=True).execute().get("modifiedTime")
        retry, ok = [], []

        def cb(req_id, resp, exc, _c=chunk):
            item = _c[int(req_id)]
            if exc is None:
                ok.append(item); return
            st = getattr(getattr(exc, "resp", None), "status", 0) or getattr(exc, "status_code", 0)
            if (st in (429, 500, 502, 503) or (st == 403 and "rate" in str(exc).lower())) and tries[item[0]] < 4:
                tries[item[0]] += 1
                if item not in retry: retry.append(item)
            else:
                rep["errors"] += 1

        b = svc.new_batch_http_request(callback=cb)
        for i, (fid, write, e) in enumerate(chunk):
            b.add(svc.files().modifyLabels(fileId=fid, body={"labelModifications": mods_for(write, e, schema)}), request_id=str(i))
        b.execute()
        after = svc.files().get(fileId=smp, fields="modifiedTime", supportsAllDrives=True).execute().get("modifiedTime")
        sampled += 1; changed_mtime += before != after
        with conn.cursor() as cur:
            for fid, write, e in ok:
                cur.execute("""INSERT INTO ops.label_state (file_id, machine, machine_at) VALUES (%s, %s::jsonb, now())
                               ON CONFLICT (file_id) DO UPDATE SET machine = coalesce(ops.label_state.machine, '{}'::jsonb) || EXCLUDED.machine, machine_at = now()""",
                            (fid, json.dumps({f: e.get(f) for f in write}, default=str)))
        conn.commit()
        rep["resynced"] += len(ok)
        if retry:
            queue = retry + queue; sleep(5 + random.random() * 5)
        else:
            sleep(1.0)
    rep["notes"] = f"modifiedTime changed on {changed_mtime} of {sampled} sampled files; never read back (not touched) {rep['no_state']:,}"
    rep["by_field"]["mtime_sampled"] = sampled
    rep["by_field"]["mtime_changed"] = changed_mtime
    with conn.cursor() as cur:
        finish_run(cur, rid, rep)
    conn.commit()
    conn.close()
    log(report_line("resync", rep, apply)); log(f"  {rep['notes']}; by field: {rep['by_field']}")
    return rep


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["readback", "resync"])
    ap.add_argument("--db-url-file", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--hold-entities", nargs="*", default=[], help="file ids whose Entity is not re-synced (sent to Review)")
    a = ap.parse_args()
    schema = cl.Schema(cl.load_schema())
    scopes = ["https://www.googleapis.com/auth/drive.metadata"] if a.mode == "resync" else ["https://www.googleapis.com/auth/drive.readonly"]
    svc = cl.drive_service(a.token, scopes)
    url = open(a.db_url_file).read().strip()

    def connect():
        return psycopg.connect(url)
    if a.mode == "readback":
        readback(connect, svc, schema, apply=a.apply, ids=a.only or None)
    else:
        resync(connect, svc, schema, apply=a.apply, only=a.only, hold_entities=a.hold_entities)


if __name__ == "__main__":
    main()
