"""CAT-WO-17 R-062 · zip listing, offline (invented content).   py pipeline\\test_wo17.py"""
import hashlib, io, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zips_wo17 as z


def mk(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in files:
            zf.writestr(n, d)
    return b.getvalue()


inner = mk([("deep/a.txt", b"alpha")])
outer = mk([("folder/", b""), ("folder/b.pdf", b"%PDF-invented"), ("x.zip", inner), ("folder/b.pdf", b"dup name")])
st, rows = z.list_zip(outer)
assert st == "listed", st
by = {(r["parent_member"], r["member_path"]): r for r in rows}
assert by[("", "folder/")]["is_dir"] and by[("", "folder/")]["md5"] is None
assert by[("", "folder/b.pdf")]["md5"] == hashlib.md5(b"%PDF-invented").hexdigest()      # first of two same-name entries kept
assert by[("", "x.zip")]["nested_zip"]
assert by[("x.zip", "deep/a.txt")]["md5"] == hashlib.md5(b"alpha").hexdigest()
assert len(rows) == 4, len(rows)
assert z.list_zip(b"not a zip at all") == ("not_a_zip", [])

# budget: once the expanded bytes pass the cap, members are listed without an md5
old = z.MAX_EXPANDED_PER_ZIP
z.MAX_EXPANDED_PER_ZIP = 10
st, rows = z.list_zip(mk([("a.txt", b"0123456789abc"), ("b.txt", b"x")]))
z.MAX_EXPANDED_PER_ZIP = old
assert [r["md5"] for r in rows][0] is None

# scope SQL never reaches the Secret tier and only Finance / Confidential
assert "handling <> 'secret'" in z.SCOPE_SQL and "LIMITED - Finance" in z.SCOPE_SQL and "Confidential - RYAN and CECILIA only" in z.SCOPE_SQL
print("test_wo17: all passed")
