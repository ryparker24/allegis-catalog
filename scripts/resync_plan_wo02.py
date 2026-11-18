r"""
CAT-WO-02 · the Part 2 re-sync PLAN, offline (READ-ONLY; no Drive call; counts only).

Uses the read-back's stored snapshot (ops.label_state.live / machine / person_fields) in place of a live Drive read,
and the same plan_resync() / expected() as pipeline/label_sync_wo02.py resync. Two passes:
  now          : today's published labels (src/lib/labels_schema.json)
  after publish: the same plus Parties, Status / Issued date and the two new Kind choices, CYBER-II disabled
                 (placeholder choice ids; only the field / choice EXISTENCE matters for the plan)
The live re-sync at release reads Drive right before writing, so its numbers can differ by what people changed since
the last read-back.

  py scripts/resync_plan_wo02.py --db-url-file <catalog url file>
"""
import sys, os, copy, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
import catalog_labels as cl
import label_sync_wo02 as ls
import labels_setup_wo02 as lsw

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
a = ap.parse_args()
S0 = cl.load_schema()
with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    ents, pcos = lsw.ref_lists(cur)
    cur.execute("SELECT file_id, machine, live, person_fields FROM ops.label_state WHERE live IS NOT NULL AND machine IS NOT NULL")
    state = {r[0]: (r[1], r[2], list(r[3] or [])) for r in cur.fetchall()}
    ids = sorted(state)
    rows = {}
    for i in range(0, len(ids), 5000):
        rows.update(cl.catalog_rows(cur, ids[i:i + 5000]))

S1 = copy.deepcopy(S0)
S1["doc"]["fields"]["kind"]["choices"].update({k: f"new-{k}" for k in lsw.NEW_KIND_CHOICES})
for k in lsw.DISABLE_ENTITY_CHOICES: S1["doc"]["fields"]["entity"]["choices"].pop(k, None)
S1["exec"]["fields"]["status"] = {"field_id": "f-status", "type": "selectionOptions", "choices": {k: f"s-{k}" for k in lsw.STATUS}}
S1["exec"]["fields"]["issued_date"] = {"field_id": "f-issued", "type": "dateOptions"}
iss = {**ents, **pcos, **lsw.EXTRA_ISSUING}; rec = {**ents, **lsw.EXTRA_RECEIVING}
S1["parties"] = {"label_id": "l-parties", "title": "Parties", "fields": {
    "issuing_entity": {"field_id": "f-iss", "type": "selectionOptions", "choices": {k: f"i-{k}" for k in iss}},
    "receiving_entities": {"field_id": "f-rec", "type": "selectionOptions", "choices": {k: f"r-{k}" for k in rec}}}}

for title, S in (("now (today's labels)", S0), ("after the label publish", S1)):
    schema = cl.Schema(S)
    fields = schema.active_fields()
    files = skipped_files = 0; write = collections.Counter(); skip = collections.Counter(); kinds = collections.Counter()
    unwritable = collections.Counter()
    for fid in ids:
        machine, live, pf = state[fid]
        if live.get("tier") == "secret": continue
        live = {**{f: ([] if cl.FIELDS[f][2] == "many" else None) for f in cl.FIELDS}, **live}
        e = cl.expected(rows.get(fid, {}), schema)
        w, s = ls.plan_resync(e, live, machine, pf, fields)
        unwritable.update(f for f in e["_unwritable"] if cl.norm(e.get(f)) != cl.norm(live.get(f)))
        if w:
            files += 1; write.update(w)
            if "kind" in w: kinds[f"{live.get('kind') or '(blank)'} -> {e.get('kind') or '(blank)'}"] += 1
        if s:
            skipped_files += 1; skip.update(s)
    print(f"== {title}: {len(ids):,} labelled files with a read-back snapshot")
    print(f"   files the re-sync would write: {files:,}; files with a person-owned field skipped: {skipped_files:,}")
    print("   fields written: " + ", ".join(f"{k} {n:,}" for k, n in write.most_common()))
    print("   person-owned, skipped: " + (", ".join(f"{k} {n:,}" for k, n in skip.most_common()) or "none"))
    print(f"   kind: {sum(kinds.values()):,} (blank -> kind {sum(n for k, n in kinds.items() if k.startswith('(blank)')):,}; "
          f"kind -> other kind {sum(n for k, n in kinds.items() if not k.startswith('(blank)')):,})")
    print("   held back (choice not on the label yet; left as it is, never cleared): " + (", ".join(f"{k} {n:,}" for k, n in unwritable.most_common()) or "none"))
