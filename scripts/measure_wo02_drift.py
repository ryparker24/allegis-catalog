r"""
CAT-WO-02 item 0.3 / 0.4 (READ-ONLY): live labels on every labelled file vs what the machine would write from the
catalog now. Counts only. Drive is read as the token's user (drive.readonly); the DB session is read-only.

  py scripts/measure_wo02_drift.py --db-url-file <catalog url file> --token C:\DriveCatalog\token_census.json
"""
import sys, os, argparse, collections, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
import catalog_labels as cl

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
ap.add_argument("--token", required=True)
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
url = open(a.db_url_file).read().strip()
schema = cl.Schema(cl.load_schema())
fields = schema.active_fields()
with psycopg.connect(url, options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    cur.execute("SELECT file_id FROM app.labelled_file ORDER BY file_id")
    ids = [r[0] for r in cur.fetchall()]
    if a.limit: ids = ids[:a.limit]
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='cat' AND table_name='document' AND column_name='status_auto')")
    v2 = cur.fetchone()[0]
    rows = {}
    for i in range(0, len(ids), 5000):
        rows.update(cl.catalog_rows(cur, ids[i:i + 5000], v1=not v2))
print(f"labelled files: {len(ids):,}; comparing fields: {', '.join(fields)}", flush=True)
svc = cl.drive_service(a.token, ["https://www.googleapis.com/auth/drive.readonly"])
t0 = time.time()
def prog(d, n):
    if d % 5000 < 100: print(f"  read {d:,}/{n:,}  {time.time()-t0:.0f}s", flush=True)
live = cl.read_labels(svc, ids, schema.include_labels(), on_progress=prog)
http = collections.Counter(v["http"] for v in live.values())
by_field = collections.Counter(); person_by_field = collections.Counter(); files_diff = 0; files_person = 0
review = collections.Counter(); no_doc_label = 0
for fid in ids:
    L = live.get(fid)
    if not L or L["http"] != 200: continue
    d = schema.decode(L["labelInfo"])
    review[(d["review_status"], d["reviewed_by_set"])] += 1
    if not d["has_doc_label"]: no_doc_label += 1
    e = cl.expected(rows.get(fid, {}), schema)
    ch = cl.diff(e, d, fields)
    person = d["review_status"] in ("confirmed", "wrong") or d["reviewed_by_set"]
    if ch: files_diff += 1
    if ch and person: files_person += 1
    for f in ch:
        by_field[f] += 1
        if person: person_by_field[f] += 1
print(f"\nDrive read: {dict(http)}  ({time.time()-t0:.0f}s)")
print(f"files without the Allegis Document label live: {no_doc_label:,}")
print("Catalog Review live (status, reviewed_by set):", {f"{k[0]}|{k[1]}": v for k, v in review.most_common()})
print(f"files with any live != machine-expected: {files_diff:,} (of which carry a person's review mark: {files_person:,})")
for f in fields: print(f"  {f:<20} differs {by_field[f]:>7,}   with person mark {person_by_field[f]:>6,}")
