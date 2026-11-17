"""
CAT-WO-01 G3 manual check helper (READ-ONLY): files.get(fields=id) as Ryan for every labelled file ID,
in batches of 50, to find a REAL file Ryan cannot open (if one exists). Prints counts and file IDs only.

  py scripts/access_sweep.py [--root C:\\DriveCatalog] [--out <file for no-access IDs>]
"""
import os, sys, time, argparse
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=r"C:\DriveCatalog")
ap.add_argument("--out", default=None)
a = ap.parse_args()
os.chdir(a.root)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

cr = Credentials.from_authorized_user_file("token_labels_apply.json", ["https://www.googleapis.com/auth/drive.metadata"])
if not cr.valid:
    cr.refresh(Request())   # in memory only
svc = build("drive", "v3", credentials=cr, cache_discovery=False)
ids = open("labels_done.txt").read().split()
status, noaccess = Counter(), []
t0 = time.time()
for i in range(0, len(ids), 50):
    chunk = ids[i:i + 50]
    retry = []

    def cb(rid, resp, exc):
        if exc is None:
            status[200] += 1
            return
        code = getattr(getattr(exc, "resp", None), "status", 0)
        if code in (429, 500, 502, 503) or (code == 403 and "rate" in str(exc).lower()):
            retry.append(rid)
        else:
            status[code] += 1
            noaccess.append(rid)
    for attempt in range(4):
        b = svc.new_batch_http_request(callback=cb)
        for fid in (chunk if attempt == 0 else retry[:]):
            b.add(svc.files().get(fileId=fid, fields="id", supportsAllDrives=True), request_id=fid)
        if attempt:
            retry.clear()
        b.execute()
        if not retry:
            break
        time.sleep(3 * (attempt + 1))
    status["unresolved"] += len(retry)
    if (i // 50) % 100 == 0:
        print(f"  {i + len(chunk):,}/{len(ids):,} {dict(status)} {time.time() - t0:.0f}s", flush=True)
print(f"DONE {len(ids):,} checked: {dict(status)} in {time.time() - t0:.0f}s; no-access ids: {len(noaccess)}")
if a.out and noaccess:
    open(a.out, "w").write("\n".join(noaccess))
