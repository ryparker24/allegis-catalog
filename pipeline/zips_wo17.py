r"""CAT-WO-17 · R-062 · zip contents, read-only.

Each zip in LIMITED - Finance and My Drive/Confidential - RYAN and CECILIA only (never the Secret tier) is downloaded
IN MEMORY with the crawler's drive.readonly login, its member list (names, sizes, CRC, dates) is read, and each member
is hashed (md5) while streamed so it can be matched to catalog files. Nested zips: one level. Encrypted members: names
only. Nothing is written to disk or to Drive. The net guard (Google APIs / Neon only) is on. Logs carry counts only.

  py pipeline\zips_wo17.py --db-url-file <throwaway url file> [--limit N] [--apply] [--workers 4]

A zip is listed again only when its md5 changes (cat.zip_listing.zip_md5).
"""
import argparse, collections, hashlib, io, os, sys, threading, time, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MAX_ZIP_BYTES = 1_500_000_000         # bigger zips: 'too_large' (counted, not downloaded)
MAX_MEMBER_HASH = 500_000_000         # members bigger than this are listed without an md5
MAX_NESTED_BYTES = 300_000_000        # a nested zip is opened in memory only up to this size
MAX_EXPANDED_PER_ZIP = 8_000_000_000  # zip-bomb guard: stop hashing once this much has been decompressed
RULE_VERSION = 1
SCOPE_SQL = """
SELECT f.file_id, f.md5, f.size_bytes
FROM cat.file f
LEFT JOIN cat.zip_listing z ON z.zip_file_id = f.file_id
WHERE f.removed_run IS NULL AND f.handling <> 'secret' AND coalesce(f.size_bytes, 0) > 0
  AND (lower(f.file_ext) = 'zip' OR f.mime_type IN ('application/zip', 'application/x-zip-compressed', 'application/x-zip'))
  AND (f.drive_name = 'LIMITED - Finance' OR f.folder_path LIKE 'My Drive/Confidential - RYAN and CECILIA only%%')
  AND (z.zip_file_id IS NULL OR z.zip_md5 IS DISTINCT FROM f.md5 OR z.status = 'failed')
ORDER BY (f.drive_name = 'LIMITED - Finance') DESC, f.size_bytes, f.file_id"""


def _md5_member(zf, info, budget):
    """md5 of one member, streamed; None when encrypted, too big or over the zip's budget."""
    if info.flag_bits & 0x1 or info.file_size > MAX_MEMBER_HASH or budget[0] + info.file_size > MAX_EXPANDED_PER_ZIP:
        return None
    h = hashlib.md5()
    with zf.open(info) as fh:
        while True:
            b = fh.read(4 * 2**20)
            if not b:
                break
            budget[0] += len(b)
            if budget[0] > MAX_EXPANDED_PER_ZIP:
                return None
            h.update(b)
    return h.hexdigest()


def _dt(info):
    try:
        y, mo, d, hh, mi, ss = info.date_time
        return f"{y:04d}-{mo:02d}-{d:02d} {hh:02d}:{mi:02d}:{min(ss, 59):02d}" if y >= 1980 and 1 <= mo <= 12 and 1 <= d <= 31 else None
    except Exception:
        return None


def list_zip(data):
    """bytes -> (status, rows). rows: dicts for cat.zip_member. Never raises for a bad member; the zip's status says."""
    rows, budget = [], [0]
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return "not_a_zip", []
    any_enc = False
    with zf:
        for info in zf.infolist():
            enc = bool(info.flag_bits & 0x1)
            any_enc |= enc
            name = info.filename[:1000]
            is_dir = info.is_dir()
            nested = (not is_dir) and name.lower().endswith(".zip")
            md5 = None
            if not is_dir:
                try:
                    md5 = _md5_member(zf, info, budget)
                except Exception:
                    md5 = None
            rows.append(dict(parent_member="", member_path=name, is_dir=is_dir, size_bytes=info.file_size,
                             compressed_bytes=info.compress_size, crc32=f"{info.CRC:08x}", member_mtime=_dt(info),
                             md5=md5, encrypted=enc, nested_zip=nested))
            if nested and not enc and info.file_size <= MAX_NESTED_BYTES:
                try:
                    inner = zipfile.ZipFile(io.BytesIO(zf.read(info)))
                except Exception:
                    continue
                with inner:
                    for ii in inner.infolist():
                        ienc = bool(ii.flag_bits & 0x1)
                        imd5 = None
                        if not ii.is_dir():
                            try:
                                imd5 = _md5_member(inner, ii, budget)
                            except Exception:
                                imd5 = None
                        rows.append(dict(parent_member=name, member_path=ii.filename[:1000], is_dir=ii.is_dir(),
                                         size_bytes=ii.file_size, compressed_bytes=ii.compress_size, crc32=f"{ii.CRC:08x}",
                                         member_mtime=_dt(ii), md5=imd5, encrypted=ienc, nested_zip=False))
    # a member listed twice under the same name (zips allow it) keeps its first entry
    seen, out = set(), []
    for r in rows:
        k = (r["parent_member"], r["member_path"])
        if k not in seen:
            seen.add(k); out.append(r)
    status = "encrypted" if any_enc and all(r["encrypted"] or r["is_dir"] for r in out) else "listed"
    return status, out


def download(svc, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True), chunksize=16 * 2**20)
    done = False
    while not done:
        _, done = dl.next_chunk(num_retries=5)
        if buf.tell() > MAX_ZIP_BYTES:
            return None
    return buf.getvalue()


def save(con, file_id, zmd5, status, rows, note=None):
    with con.cursor() as cur:
        cur.execute("DELETE FROM cat.zip_listing WHERE zip_file_id = %s", (file_id,))
        cur.execute("""INSERT INTO cat.zip_listing (zip_file_id, zip_md5, status, member_count, note, rule_version)
                       VALUES (%s, %s, %s, %s, %s, %s)""", (file_id, zmd5, status, len(rows), note, RULE_VERSION))
        if rows:
            cur.executemany("""INSERT INTO cat.zip_member (zip_file_id, parent_member, member_path, is_dir, size_bytes,
                                 compressed_bytes, crc32, member_mtime, md5, encrypted, nested_zip)
                               VALUES (%(z)s, %(parent_member)s, %(member_path)s, %(is_dir)s, %(size_bytes)s, %(compressed_bytes)s,
                                       %(crc32)s, %(member_mtime)s, %(md5)s, %(encrypted)s, %(nested_zip)s)""",
                            [dict(r, z=file_id) for r in rows])
    con.commit()


def run(url, svc_factory, limit=None, apply=False, workers=4, log=print):
    import psycopg
    with psycopg.connect(url) as con:
        todo = con.execute(SCOPE_SQL).fetchall()
    if limit:
        todo = todo[:limit]
    log(f"zips to list: {len(todo):,} ({sum(r[2] or 0 for r in todo) / 1e9:.2f} GB)")
    c = collections.Counter()
    lock = threading.Lock()
    local = threading.local()

    def one(row):
        fid, zmd5, size = row
        if size and size > MAX_ZIP_BYTES:
            return fid, zmd5, "too_large", [], None
        if not hasattr(local, "svc"):
            local.svc = svc_factory()
        try:
            data = download(local.svc, fid)
            if data is None:
                return fid, zmd5, "too_large", [], None
            st, rows = list_zip(data)
            return fid, zmd5, st, rows, None
        except Exception as e:                       # error class only; never a name
            return fid, zmd5, "failed", [], type(e).__name__[:60]

    t0 = time.time()
    with psycopg.connect(url) as wcon, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, r) for r in todo]
        for i, fu in enumerate(as_completed(futs), 1):
            fid, zmd5, st, rows, note = fu.result()
            with lock:
                c[st] += 1; c["members"] += len(rows); c["hashed"] += sum(1 for r in rows if r["md5"])
                if apply:
                    save(wcon, fid, zmd5, st, rows, note)
            if i % 50 == 0 or i == len(futs):
                log(f"  {i:,}/{len(futs):,} zips · {dict(c)} · {time.time() - t0:.0f}s")
    log(f"done: {dict(c)}{'' if apply else ' (dry run: nothing written)'}")
    return c


def main():
    import dbguard_wo03 as dbg
    from pages_wo06 import net_guard, _NoBrowser
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--apply", action="store_true", help="write the listing (else count only)")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    net_guard()
    home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
    if home not in sys.path: sys.path.insert(0, home)
    os.chdir(home)                                   # the crawler's token file lives there
    import drive_crawl as dc
    dc.InstalledAppFlow = _NoBrowser
    from googleapiclient.discovery import build
    creds = dc.creds()
    run(url, lambda: build("drive", "v3", credentials=creds, cache_discovery=False), limit=a.limit, apply=a.apply, workers=a.workers)


if __name__ == "__main__":
    main()
