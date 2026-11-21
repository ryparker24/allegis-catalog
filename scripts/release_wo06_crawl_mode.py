r"""CAT-WO-06 release step: add `pages` to C:\DriveCatalog\drive_crawl.py (outside git) as a thin mode that calls the app
repo's pipeline/pages_wo06.py. Keeps a .pre-catwo06.bak copy. Idempotent. Run ONLY after the nightly has finished.

  py scripts\release_wo06_crawl_mode.py [--check]
  then: py drive_crawl.py pages --backfill | --incremental [--limit N] [--dry-run]
"""
import os, shutil, sys

PATH = os.path.join(os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog"), "drive_crawl.py")
MARK = "# CAT-WO-06 pages mode"
OLD_CHECK = 'if mode not in ("full", "incremental", "derive"):'
NEW_CHECK = 'if mode not in ("full", "incremental", "derive", "pages"):'
OLD_USAGE = 'sys.exit("usage: py drive_crawl.py full [--reuse] | incremental | derive")'
NEW_USAGE = 'sys.exit("usage: py drive_crawl.py full [--reuse] | incremental | derive | pages --backfill|--incremental [--limit N] [--dry-run]")'
OLD_DERIVE = '    if mode == "derive":'
NEW_PAGES = f'''    if mode == "pages":                       {MARK}: first-page reading (app repo pipeline/pages_wo06.py)
        wo02_pipeline()
        import pages_wo06
        svc = build("drive", "v3", credentials=creds(), cache_discovery=False)
        c = db()
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else (None if "--backfill" in sys.argv else pages_wo06.NIGHTLY_CAP)
        pages_wo06.run(c, svc, incremental="--backfill" not in sys.argv, limit=lim, apply="--dry-run" not in sys.argv)
        pages_wo06.apply_content(c, apply="--dry-run" not in sys.argv)
        c.close(); sys.exit(0)
'''


def main():
    s = open(PATH, encoding="utf-8").read()
    if MARK in s:
        print("already has the pages mode"); return
    if not all(x in s for x in (OLD_CHECK, OLD_USAGE, OLD_DERIVE)):
        sys.exit("STOP: drive_crawl.py differs from what this step expects; edit by hand")
    if "--check" in sys.argv:
        print("ok: the patch applies cleanly (nothing written)"); return
    shutil.copy2(PATH, PATH + ".pre-catwo06.bak")
    s = s.replace(OLD_CHECK, NEW_CHECK).replace(OLD_USAGE, NEW_USAGE).replace(OLD_DERIVE, NEW_PAGES + OLD_DERIVE, 1)
    open(PATH, "w", encoding="utf-8").write(s)
    print("drive_crawl.py: pages mode added (backup .pre-catwo06.bak)")


if __name__ == "__main__":
    main()
