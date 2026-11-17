"""
Load the labelled-file IDs (labels_done.txt, file IDs only) into app.labelled_file.

  py db/load_labelled.py --url-file <file holding the OWNER url> [--ids C:\\DriveCatalog\\labels_done.txt]

Full replace in one transaction (the resume list is the source of truth until CAT-WO-02's read-back).
Prints counts only. Never prints the URL.
"""
import argparse, psycopg

ap = argparse.ArgumentParser()
ap.add_argument("--url-file", required=True)
ap.add_argument("--ids", default=r"C:\DriveCatalog\labels_done.txt")
a = ap.parse_args()


def read_url(path):
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line:
            continue
        k, sep, v = line.partition("=")
        if sep and not line.startswith("postgres"):
            if "UNPOOLED" in k.upper():
                return v.strip().strip("'\"")
            continue
        return line.strip("'\"")
    raise SystemExit("no URL found in --url-file")


ids = sorted(set(open(a.ids).read().split()))
with psycopg.connect(read_url(a.url_file)) as c, c.cursor() as cur:
    cur.execute("DELETE FROM app.labelled_file")
    with cur.copy("COPY app.labelled_file (file_id) FROM STDIN") as cp:
        for i in ids:
            cp.write_row((i,))
    cur.execute("SELECT count(*), count(*) FILTER (WHERE f.file_id IS NULL), count(*) FILTER (WHERE f.handling='secret') "
                "FROM app.labelled_file l LEFT JOIN cat.file f USING (file_id)")
    n, missing, secret = cur.fetchone()
    c.commit()
print(f"app.labelled_file: {n:,} IDs loaded; not in cat.file: {missing}; secret tier: {secret} (hidden by the views regardless)")
