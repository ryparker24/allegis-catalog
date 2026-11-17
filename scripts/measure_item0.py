"""
CAT-WO-01 item 0 - measure (READ-ONLY: catalog DB + Drive). Prints codes and counts only - never names.

  py measure_item0.py [--root C:\\DriveCatalog] [--sample 200] [--seed 20261117]

Reads: <root>/catalog_db_url.txt (via drive_crawl.db), <root>/labels_done.txt (labelled file IDs),
       <root>/labels_schema.json, <root>/token_labels_apply.json (drive.metadata; refreshed IN MEMORY, never written back).
Drive calls: files.get(fields=id,labelInfo, includeLabels=...) only.
"""
import os, sys, json, time, random, argparse
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=r"C:\DriveCatalog")
ap.add_argument("--sample", type=int, default=200)
ap.add_argument("--seed", type=int, default=20261117)
a = ap.parse_args()
sys.path.insert(0, a.root); os.chdir(a.root)
import drive_crawl as dc
import labels_sync as ls          # reuse build_mods(): the exact values the labelling run wrote
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

S = json.load(open("labels_schema.json"))
ids = open("labels_done.txt").read().split()


def q(cur, sql, p=None):
    cur.execute(sql, p or {})
    return cur.fetchall()


with dc.db() as c, c.cursor() as cur:
    cur.execute("SET TRANSACTION READ ONLY")
    P = {"ids": ids}
    print("== 0.1 labelled files by drive x kind x handling tier")
    rows = q(cur, """SELECT coalesce(f.drive_name,'(no drive)'), coalesce(coalesce(d.kind_confirmed,d.kind_auto),'(none)'), f.handling, count(*)
                     FROM cat.file f JOIN cat.file_document fd USING(file_id) JOIN cat.document d USING(document_id)
                     WHERE f.file_id = ANY(%(ids)s) GROUP BY 1,2,3 ORDER BY 1,4 DESC""", P)
    for r in rows:
        print(f"   {r[0]:<20} {r[1]:<24} {r[2]:<10} {r[3]:>6,}")
    tot = q(cur, "SELECT handling, count(*) FROM cat.file WHERE file_id = ANY(%(ids)s) GROUP BY 1 ORDER BY 1", P)
    print("   tier totals:", ", ".join(f"{t}={n:,}" for t, n in tot), f"| labelled IDs={len(ids):,}")
    secret_ids = [r[0] for r in q(cur, "SELECT file_id FROM cat.file WHERE handling='secret' AND removed_run IS NULL")]
    print(f"   secret-tier files in catalog: {len(secret_ids)}; of these in labelled set (DB): {len(set(secret_ids) & set(ids))}")

    print("== 0.2 review queue sizes (labelled files)")
    base = """FROM cat.file f JOIN cat.file_document fd USING(file_id) JOIN cat.document d USING(document_id)
              LEFT JOIN LATERAL (SELECT confidence FROM cat.doc_content_check k WHERE k.document_id=d.document_id ORDER BY checked_at DESC LIMIT 1) k ON true
              WHERE f.file_id = ANY(%(ids)s) AND f.handling <> 'secret'"""
    st = "coalesce(d.execution_stage_confirmed,d.execution_stage_auto)"
    rx = "coalesce(d.requires_execution_confirmed,d.requires_execution_auto)"
    kd = "coalesce(d.kind_confirmed,d.kind_auto)"
    r = q(cur, f"""SELECT count(*) FILTER (WHERE {rx} AND {st}='unknown'),
                          count(*) FILTER (WHERE {st}='fully_executed' AND k.confidence='low'),
                          count(*) FILTER (WHERE {kd} IS NULL),
                          count(*) FILTER (WHERE ({rx} AND {st}='unknown') OR ({st}='fully_executed' AND k.confidence='low') OR {kd} IS NULL) {base}""", P)[0]
    print(f"   stage unknown={r[0]:,}  fully executed @ low confidence={r[1]:,}  no kind={r[2]:,}  union (distinct files)={r[3]:,}")

    print("== 0.3 label drift: sample of", a.sample)
    random.seed(a.seed)
    sample = random.sample(ids, a.sample)
    cur.execute(ls.SQL.format(scope="f.file_id = ANY(%s)"), (sample,))
    cols = [x.name for x in cur.description]
    dbrows = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    c.rollback()

lab_by_id = {v["label_id"]: k for k, v in S.items()}
fld_by_id = {(k, f["field_id"]): fk for k, v in S.items() for fk, f in v["fields"].items()}


def norm_mod_value(m):
    for key in ("setSelectionValues", "setIntegerValues", "setTextValues", "setUserValues"):
        if key in m:
            return tuple(sorted(str(x) for x in m[key]))
    if "setDateValues" in m:
        return tuple(sorted(f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}" for d in m["setDateValues"]))


def expected(r):
    mods, _ = ls.build_mods(r, S, None)
    out = {}
    for lm in mods:
        lk = lab_by_id[lm["labelId"]]
        out[(lk, "_present")] = True
        for fm in lm["fieldModifications"]:
            out[(lk, fld_by_id[(lk, fm["fieldId"])])] = norm_mod_value(fm)
    return out


def live(labelInfo):
    out = {}
    for L in (labelInfo or {}).get("labels", []):
        lk = lab_by_id.get(L["id"])
        if not lk:
            continue
        out[(lk, "_present")] = True
        for fid, fv in (L.get("fields") or {}).items():
            fk = fld_by_id.get((lk, fid))
            if not fk:
                continue
            if "selection" in fv: v = fv["selection"]
            elif "integer" in fv: v = fv["integer"]
            elif "text" in fv: v = fv["text"]
            elif "dateString" in fv: v = fv["dateString"]
            elif "user" in fv: v = [u.get("emailAddress", "") for u in fv["user"]]
            else: v = []
            out[(lk, fk)] = tuple(sorted(str(x) for x in v))
    return out


cr = Credentials.from_authorized_user_file("token_labels_apply.json", ["https://www.googleapis.com/auth/drive.metadata"])
if not cr.valid:
    cr.refresh(Request())          # in memory only - the token file is NOT rewritten
svc = build("drive", "v3", credentials=cr, cache_discovery=False)
INCL = ",".join(v["label_id"] for v in S.values())


def batch_get(file_ids):
    res, errs = {}, {}

    def cb(rid, resp, exc):
        if exc is None:
            res[rid] = resp
        else:
            errs[rid] = getattr(exc, "status_code", None) or getattr(getattr(exc, "resp", None), "status", None)
    b = svc.new_batch_http_request(callback=cb)
    for fid in file_ids:
        b.add(svc.files().get(fileId=fid, fields="id,labelInfo", includeLabels=INCL, supportsAllDrives=True), request_id=fid)
    t = time.perf_counter()
    b.execute()
    return res, errs, time.perf_counter() - t


timings, live_vals, errors = [], {}, Counter()
for i in range(0, len(sample), 50):
    res, errs, dt = batch_get(sample[i:i + 50])
    timings.append(dt)
    for fid, resp in res.items():
        live_vals[fid] = live(resp.get("labelInfo"))
    for fid, code in errs.items():
        errors[code] += 1

mism, compared = Counter(), Counter()
files_mis = 0
for fid in sample:
    if fid not in live_vals or fid not in dbrows:
        continue
    e, l = expected(dbrows[fid]), live_vals[fid]
    files_mis += e != l
    for key in set(e) | set(l):
        compared[key] += 1
        if e.get(key) != l.get(key):
            mism[key] += 1
print(f"   files compared: {len(live_vals)} live / {len(dbrows)} in DB; Drive errors: {dict(errors) or 0}")
print(f"   files with >=1 mismatch: {files_mis}")
for (lk, fk), n in sorted(compared.items()):
    print(f"   {lk + '.' + fk:<26} mismatches {mism[(lk, fk)]:>3} / {n}")

print("== 0.4 Drive API cost: one batch files.get x50 with includeLabels (4 batches = the sample)")
print("   seconds per batch:", ", ".join(f"{t:.2f}" for t in timings), f"| mean {sum(timings) / len(timings):.2f}s")

print("== 0.1b live check: do any secret-tier files carry a catalog label in Drive?")
carried, seen, errs_s = 0, 0, Counter()
for i in range(0, len(secret_ids), 50):
    res, errs, _ = batch_get(secret_ids[i:i + 50])
    seen += len(res)
    errs_s.update(errs.values())
    carried += sum(1 for r in res.values() if (r.get("labelInfo") or {}).get("labels"))
print(f"   secret-tier files checked live: {seen} (errors: {dict(errs_s) or 0}); carrying any catalog label: {carried}")
