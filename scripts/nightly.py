r"""
CAT-WO-03.1 · the nightly run (Windows scheduled task "Allegis Catalog nightly" on the ThinkPad, 22:00 + at the next wake
when 22:00 was missed). Runs from C:\DriveCatalog\app-main (a checkout of main), in C:\DriveCatalog (tokens, DB url):

  1. crawl        drive_crawl.incremental (Drive changes since the last crawl)
  1b. portals     CAT-WO-05: the newest dated portal exports (C:\DriveCatalog\portal_exports) -> ref.portal_posting (codes only).
                  Only when Ryan's read-only logins exist (lp_portal_url.txt / gp_portal_url.txt) are the portals contacted,
                  with three SELECTs in a READ ONLY session, refused if the login could write. Partners map to last night's roster.
  2. derive       rules + apply_derive_wo02 (kinds, audited FS, parties, status, locations)
  3. readback     labels -> catalog (a person's edits become person-set values)
  4. resync       catalog -> labels on labelled files, never over a person's value        (--apply writes; else dry run)
  5. checklists   roster -> Subject -> requirements

Each step is logged (C:\DriveCatalog\logs\nightly_YYYYMMDD_HHMM.log, last 60 kept) and recorded in ops.nightly_run;
the FIRST error stops the run. On failure: a Windows notification, ops.nightly_run.status = failed (the app shows a
banner), exit code 1 (Task Scheduler "Last Run Result"). Never opens a browser: a sign-in that would need one fails.

  py C:\DriveCatalog\app-main\scripts\nightly.py [--apply] [--only crawl,derive,...]
Logs hold counts and codes only (the steps print no names).
"""
import argparse, datetime, glob, io, json, os, socket, subprocess, sys, time, traceback

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # the checkout this script runs from
HOME = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
LOGS = os.path.join(HOME, "logs")
STEPS = ["crawl", "portals", "derive", "readback", "resync", "checklists"]


def mem_mb():
    """(current, peak) working set of this process in MB (Windows; (0, 0) elsewhere). Logged per step so a night that
    grows toward the machine's limit shows up in the log before it is killed."""
    try:
        import ctypes, ctypes.wintypes as w
        class PMC(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = PMC(); c.cb = ctypes.sizeof(PMC)
        k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = w.HANDLE        # 64-bit handle (not truncated)
        ps = ctypes.windll.psapi; ps.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PMC), w.DWORD]
        ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return round(c.WorkingSetSize / 2**20), round(c.PeakWorkingSetSize / 2**20)
    except Exception:
        return 0, 0


class Tee(io.TextIOBase):
    def __init__(self, *s): self.s = s
    def write(self, x):
        for f in self.s: f.write(x); f.flush()
        return len(x)
    def flush(self):
        for f in self.s: f.flush()


def toast(title, text):
    """A Windows notification (stays in the notification centre). Best effort, never raises."""
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
          "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
          f"$t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('{title}')) > $null; $t.Item(1).AppendChild($x.CreateTextNode('{text}')) > $null;"
          "$n = [Windows.UI.Notifications.ToastNotification]::new($x);"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=30, capture_output=True)
    except Exception:
        pass


class NoBrowser:
    """Stands in for InstalledAppFlow: a token that can't be refreshed silently is a failure, not a hung task."""
    @staticmethod
    def from_client_secrets_file(*a, **k):
        raise RuntimeError("sign-in needed: a Google token could not be refreshed without a browser - run the step by hand once")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="the re-sync writes to Drive (the scheduled task passes it)")
    ap.add_argument("--only", help="comma-separated steps (default: all, in order)")
    a = ap.parse_args()
    steps = [s for s in STEPS if not a.only or s in a.only.split(",")]
    os.makedirs(LOGS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    run_id = f"nightly_{stamp}{'' if a.apply else '_dry'}"
    log = open(os.path.join(LOGS, f"{run_id}.log"), "w", encoding="utf-8")
    sys.stdout = Tee(sys.__stdout__, log); sys.stderr = Tee(sys.__stderr__, log)
    for old in sorted(glob.glob(os.path.join(LOGS, "nightly_*.log")))[:-60]:
        try: os.remove(old)
        except OSError: pass

    os.chdir(HOME)
    os.environ["CATALOG_APP_DIR"] = APP                  # derive / read-back / checklists load THIS checkout's pipeline
    sys.path.insert(0, HOME); sys.path.insert(0, os.path.join(APP, "pipeline"))
    import drive_crawl as dc, labels_sync as lsync
    dc.InstalledAppFlow = NoBrowser; lsync.InstalledAppFlow = NoBrowser
    from googleapiclient.discovery import build

    def rec(sql, params):
        try:
            with dc.db() as c, c.cursor() as cur:
                cur.execute(sql, params)
        except Exception as e:                            # the record is a convenience; the run goes on
            print(f"  (ops.nightly_run not updated: {type(e).__name__})")

    rec("INSERT INTO ops.nightly_run (run_id, dry_run, status, host) VALUES (%s, %s, 'running', %s) ON CONFLICT (run_id) DO NOTHING",
        (run_id, not a.apply, socket.gethostname()[:64]))
    print(f"NIGHTLY {run_id} · app {APP} · steps {', '.join(steps)} · re-sync {'APPLY' if a.apply else 'dry run'}")
    try:
        sha = subprocess.run(["git", "-C", APP, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        print(f"  code: {sha}")
    except Exception:
        pass
    timings, svc = {}, {}

    def drive():
        if "drive" not in svc: svc["drive"] = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        return svc["drive"]

    for step in steps:
        t0 = time.time()
        print(f"\n== {step} · {datetime.datetime.now():%H:%M:%S}")
        rec("UPDATE ops.nightly_run SET last_step=%s WHERE run_id=%s", (step, run_id))
        try:
            if step == "crawl":
                dc.incremental(drive(), post=False)
            elif step == "portals":
                import portals_wo05 as pw
                c = dc.db()
                try:
                    pw.export_from_portals(log=print)        # only with Ryan's read-only logins; else the newest exports
                    pw.load(c, apply=True, log=print)
                finally:
                    c.close()
            elif step == "derive":
                c = dc.db(); dc.derive(c); c.close()
            elif step == "readback":
                dc.wo02_readback(dc.db, drive())
            elif step == "resync":
                import catalog_labels as cl, label_sync_wo02 as ls
                hold = open("resync_hold_entities.txt").read().split() if os.path.exists("resync_hold_entities.txt") else []
                lsvc = build("drive", "v3", credentials=lsync.creds(), cache_discovery=False)
                ls.resync(dc.db, lsvc, cl.Schema(cl.load_schema()), apply=a.apply, hold_entities=hold, log=print)
            elif step == "checklists":
                dc.wo03_checklists(dc.db)
        except BaseException as e:
            timings[step] = round(time.time() - t0)
            print(f"\nFAILED at step {step} after {timings[step]}s: {type(e).__name__}")
            traceback.print_exc()
            rec("UPDATE ops.nightly_run SET status='failed', finished_at=now(), failed_step=%s, error_class=%s, steps=%s::jsonb WHERE run_id=%s",
                (step, type(e).__name__[:80], json.dumps(timings), run_id))
            toast("Allegis Catalog nightly FAILED", f"Step {step} ({type(e).__name__}). Log: {LOGS}")
            sys.exit(1)
        timings[step] = round(time.time() - t0)
        cur_mb, peak_mb = mem_mb()
        timings[f"{step}_peak_mb"] = peak_mb
        print(f"   {step} ok · {timings[step]}s · memory now {cur_mb} MB, process peak so far {peak_mb} MB")
    rec("UPDATE ops.nightly_run SET status='ok', finished_at=now(), steps=%s::jsonb WHERE run_id=%s", (json.dumps(timings), run_id))
    print(f"\nNIGHTLY OK · {json.dumps(timings)}")


if __name__ == "__main__":
    main()
