r"""
CAT-WO-04 item 6 · guard "label writes leave modifiedTime unchanged (one pilot file, restored)".

  py C:\DriveCatalog\app\scripts\pilot_wo04_mtime.py --db-url-file <url file> [--release] [--file <file id>]

Run from C:\DriveCatalog (the re-sync's own token, token_labels_apply.json). Needs L6 "Version" PUBLISHED and in
labels_schema.json. Picks one labelled file of a high-confidence family that has no L6 value yet (or --file), then:
  1. reads modifiedTime + its L6 values;
  2. writes the catalog's L6 values (exactly what the re-sync would write);
  3. reads modifiedTime again;
  4. restores the file's L6 to what it was before (removes the label if it had none);
  5. reads modifiedTime a third time.
PASS when all three modifiedTimes are equal and the L6 values are back as they were. Prints ids and codes only.
"""
import argparse, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg, catalog_labels as cl, label_sync_wo02 as ls

ap = argparse.ArgumentParser(); dbg.add_args(ap)
ap.add_argument("--file")
a = ap.parse_args()
import psycopg
schema = cl.Schema(cl.load_schema())
if "version" not in schema.S:
    sys.exit("STOP: L6 Version is not in labels_schema.json (publish it, then labels_setup_wo04.py --read-published --release)")
FIELDS = ["version_family", "version_role", "version_supersedes", "version_amends"]
conn = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
cur = conn.cursor()
fid = a.file
if not fid:
    cur.execute("""SELECT x.file_id FROM app.v_find_x x JOIN app.labelled_file l USING (file_id)
                   WHERE x.version_role = 'superseded' AND x.is_primary ORDER BY md5(x.file_id) LIMIT 1""")
    fid = cur.fetchone()[0]
row = cl.catalog_rows(cur, [fid])[fid]
e = cl.expected(row, schema)
sys.path.insert(0, os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"))
import labels_sync as lsync
from googleapiclient.discovery import build
svc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)


def state():
    r = svc.files().get(fileId=fid, fields="modifiedTime,labelInfo", includeLabels=schema.include_labels(), supportsAllDrives=True).execute()
    d = schema.decode(r.get("labelInfo"))
    had = any(L.get("id") == schema.S["version"]["label_id"] for L in (r.get("labelInfo") or {}).get("labels", []))
    return r["modifiedTime"], {f: d[f] for f in FIELDS}, had


m0, v0, had0 = state()
print(f"pilot file {fid} (document {row['document_id']}): L6 before {'set' if had0 else 'absent'}; writing {[(f, e[f]) for f in FIELDS]}")
svc.files().modifyLabels(fileId=fid, body={"labelModifications": ls.mods_for(FIELDS, e, schema)}).execute()
time.sleep(2)
m1, v1, _ = state()
if had0:
    restore = ls.mods_for(FIELDS, v0, schema)
else:
    restore = [{"labelId": schema.S["version"]["label_id"], "removeLabel": True}]
svc.files().modifyLabels(fileId=fid, body={"labelModifications": restore}).execute()
time.sleep(2)
m2, v2, had2 = state()
wrote = all(cl.norm(v1[f]) == cl.norm(e[f]) for f in FIELDS)
back = had2 == had0 and all(cl.norm(v2[f]) == cl.norm(v0[f]) for f in FIELDS)
print(f"modifiedTime before / after write / after restore: {'same' if m0 == m1 == m2 else 'CHANGED'}; "
      f"L6 written as planned: {wrote}; restored: {back}")
ok = m0 == m1 == m2 and wrote and back
print(("PASS" if ok else "FAIL") + "  G-V6 label writes leave modifiedTime unchanged (one pilot file, restored)")
sys.exit(0 if ok else 1)
