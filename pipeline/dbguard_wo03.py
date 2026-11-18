"""CAT-WO-03 · which database a pipeline step may touch.

Every WO-03 step takes an explicit --db-url-file (never a default). Before CAT-WO-03 is released, a URL whose Neon
endpoint is main's is REFUSED unless --release is given (release steps run on Ryan's go-ahead only). Main's endpoint
id is read from C:\\DriveCatalog\\catalog_db_url.txt; the URL itself is never printed.
"""
import os, re, sys

MAIN_URL_FILE = os.environ.get("CATALOG_MAIN_URL_FILE", r"C:\DriveCatalog\catalog_db_url.txt")
EP_RE = re.compile(r"@(ep-[a-z0-9-]+?)(-pooler)?\.")


def read_url(path):
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        v = line if line.startswith("postgres") else line.partition("=")[2].strip().strip("'\"")
        if v.startswith("postgres"):
            return v
    sys.exit("no postgres URL in the url file")


def endpoint(url):
    m = EP_RE.search(url)
    return m.group(1) if m else None


def main_endpoint():
    try:
        return endpoint(read_url(MAIN_URL_FILE))
    except (OSError, SystemExit):
        return None


def checked_url(path, release=False):
    """The URL in `path`, refused when it points at main and release is False."""
    url = read_url(path)
    ep, main = endpoint(url), main_endpoint()
    if ep is None:
        sys.exit("REFUSED: cannot tell which Neon endpoint the url file points at")
    if main is None and not release:
        sys.exit("REFUSED: cannot read main's endpoint to compare (set CATALOG_MAIN_URL_FILE)")
    if ep == main and not release:
        sys.exit("REFUSED: this url file points at MAIN. WO-03 steps run on main only as release steps (--release, Ryan's go-ahead).")
    return url


def add_args(ap):
    ap.add_argument("--db-url-file", required=True, help="Postgres URL file (a throwaway branch; main only with --release)")
    ap.add_argument("--release", action="store_true", help="allow main (release step, on Ryan's go-ahead)")
