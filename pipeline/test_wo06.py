"""CAT-WO-06 · first-page reading. Offline (no DB, no Drive): synthetic PDFs built in memory with INVENTED names, codes
and numbers only. DB guards (schema holds no text, re-run idempotent, person values survive, Secret never downloaded)
are in db/tests/test_wo06_guards.py."""
import io, inspect, json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf as fitz
import pages_wo06 as pw
import subject_wo03 as sw
import catalog_labels as cl

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

# ------------------------------------------------------------------ invented roster
ALIASES = [("LP-0101", "Quillon Harrowgate Family Trust"), ("LP-0101", "Quillon Harrowgate"),
           ("LP-0102", "Ostrava Pemberly Holdings LLC"), ("LP-0103", "Mirelle Vantongeren"),
           ("LP-0202", "Zebulon Krateros Partners"), ("GPM-01", "Invented Ventures Fund IV GP LLC")]
PARTY = [("TESTF", "LP-0101", False), ("TESTF", "LP-0102", False), ("TESTF", "LP-0103", False), ("TESTF", "GPM-01", True),
         ("OTHERF", "LP-0202", False)]
ENTS = [("Invented Ventures Fund IV LP", "TESTF"), ("Other Invented Fund LP", "OTHERF")]
NAMES = pw.NameIndex(ALIASES, PARTY)
EIDX = pw.EntityIndex(ENTS)
RULES = pw.load_rules(None)
FAKE_TIN = "-".join(["123", "45", "6789"])          # built at run time: no TIN-shaped literal in the repo (guard G-L3)
SECRETS = [a for _, a in ALIASES] + [FAKE_TIN, "".join(["98", "-", "7654321"]), "1 Invented Way"]


def k1_page(doc, partner_lines, fund="Invented Ventures Fund IV LP", year="2025", amended=False, tin=None):
    p = doc.new_page(width=612, height=792)
    p.insert_text((40, 40), f"Schedule K-1 (Form 1065) {year}", fontsize=11)
    p.insert_text((40, 56), "Department of the Treasury Internal Revenue Service", fontsize=7)
    if amended:
        p.insert_text((330, 56), "X Amended K-1", fontsize=8)
    p.insert_text((40, 120), "Part I Information About the Partnership", fontsize=9)
    p.insert_text((40, 140), "B Partnership's name, address, city, state, and ZIP code", fontsize=7)
    p.insert_text((40, 156), fund, fontsize=9)
    p.insert_text((40, 168), "1 Invented Way", fontsize=9)
    p.insert_text((40, 200), "C IRS center where partnership filed return", fontsize=7)
    p.insert_text((40, 260), "Part II Information About the Partner", fontsize=9)
    if tin:
        p.insert_text((40, 276), f"E Partner's TIN {tin}", fontsize=7)
    p.insert_text((40, 290), "F Name, address, city, state, and ZIP code for partner entered in E. See instructions.", fontsize=7)
    y = 306
    for ln in partner_lines:
        p.insert_text((40, y), ln, fontsize=9); y += 12
    p.insert_text((40, 360), "G General partner or LLC member-manager", fontsize=7)
    p.insert_text((330, 120), "Part III Partner's Share of Current Year Income", fontsize=9)
    return p


def pdf_bytes(build):
    doc = fitz.open()
    build(doc)
    b = doc.tobytes(); doc.close()
    return b


def read(b, kind, roster=("TESTF",), rules=RULES):
    return pw.read_document(b, kind, NAMES, EIDX, rules, set(roster), None)


# ------------------------------------------------------------------ K-1 single / bundle
r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust", "1 Invented Way"], tin=FAKE_TIN)), "k1")
st, cls = r["statements"][0]
check("K-1 single: Part II item F -> one exact roster partner, certain anchor -> HIGH (R-036 roster gate passed)",
      r["outcome"] == "ok" and cls == [("LP-0101", "TESTF", "high", None)] and st.anchor == "K1-PII-F" and st.page_from == 1, f"{r['outcome']} {cls}")
check("K-1 single: Part I item B -> entity code; tax year from the form header", st.entity == "TESTF" and st.fy == 2025, f"{st.entity} {st.fy}")
check("R-037 presence: page 1 TIN pattern -> tin True; roster partner matched -> lp_pii True", r["tin"] is True and r["lp_pii"] is True)

r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust"], amended=True)), "k1")
check("K-1 Amended box marked -> amended (joins the original's family)", r["statements"][0][0].amended is True)


def bundle(d):
    k1_page(d, ["Quillon Harrowgate Family Trust"])
    d.new_page().insert_text((40, 60), "Statement A - Partner's share of items (supplemental)", fontsize=9)
    k1_page(d, ["Ostrava Pemberly Holdings LLC"])
    d.new_page().insert_text((40, 60), "State Schedule K-1 equivalent - not a federal K-1", fontsize=9)
    k1_page(d, ["Mirelle Vantongeren"])
r = read(pdf_bytes(bundle), "k1")
got = [(st.page_from, st.page_to, cls[0][0], cls[0][2]) for st, cls in r["statements"]]
check("R-035 K-1 bundle: one statement per Schedule K-1 header (statements / state pages skipped), each with its page range",
      got == [(1, 2, "LP-0101", "high"), (3, 4, "LP-0102", "high"), (5, 5, "LP-0103", "high")], str(got))

r = read(pdf_bytes(lambda d: k1_page(d, ["Zebulon Krateros Partners"])), "k1")
check("R-036 a name on ANOTHER fund's roster -> NOT_IN_FUND (never applied)",
      r["statements"][0][1] == [("LP-0202", None, "low", "NOT_IN_FUND")], str(r["statements"][0][1]))
r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate", "c/o Mirelle Vantongeren"])), "k1")
check("two roster partners in one partner block -> MULTIPLE (lane)", {c[3] for c in r["statements"][0][1]} == {"MULTIPLE"} and len(r["statements"][0][1]) == 2)
r = read(pdf_bytes(lambda d: k1_page(d, ["Ostrava Pemberly Holdings"])), "k1")
check("a normalised match (legal suffix dropped) -> MEDIUM (lane), never high", r["statements"][0][1] == [("LP-0102", "TESTF", "medium", None)], str(r["statements"][0][1]))
r = read(pdf_bytes(lambda d: k1_page(d, ["Somebody Notonroster"])), "k1")
check("no roster name in the partner block -> NO_ROSTER_MATCH, no code", r["statements"][0][1] == [(None, None, "none", "NO_ROSTER_MATCH")])
r = read(pdf_bytes(lambda d: k1_page(d, ["Somebody Notonroster"])), "k1")
check("the anchor is recorded even when no roster name is in it (outcome ok, anchor K1-PII-F)",
      r["outcome"] == "ok" and r["statements"][0][0].anchor == "K1-PII-F")
r = read(pdf_bytes(lambda d: k1_page(d, ["Other Invented Fund LP"], fund="Some Portfolio Company LP")), "k1")
check("a K-1 issued TO a catalog entity (its partner block names the entity) -> no code, no reason, never in the lane",
      r["statements"][0][1] == [(None, None, "none", None)] and r["statements"][0][0].received_by == "OTHERF", str(r["statements"][0][1]))
r = read(pdf_bytes(lambda d: k1_page(d, ["Invented Ventures Fund IV GP LLC"])), "k1")
check("the fund's own GP row is matched from a K-1's partner block (gp_rows)", r["statements"][0][1] == [("GPM-01", "TESTF", "high", None)], str(r["statements"][0][1]))

# ------------------------------------------------------------------ rules are data (R-038)
ro = pw.load_rules(None); ro["CNT-K1-PII"] = dict(ro["CNT-K1-PII"], mode="review_only")
r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust"])), "k1", rules=ro)
check("R-038 a review-only rule feeds the lane (medium), never auto-applied", r["statements"][0][1][0][2] == "medium")
vet = pw.load_rules(None); vet["CNT-K1-PII"] = dict(vet["CNT-K1-PII"], active=False)
r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust"])), "k1", rules=vet)
check("R-038 a vetoed rule (active = false) is never used", r["statements"][0][1][0][0] is None)
check("R-038 every CNT rule id has the CNT-<KIND>-<NAME> shape and its regexes compile",
      all(re.match(r"^CNT-[A-Z0-9]{1,6}(-[A-Z0-9]{1,10}){1,3}$", rid) for rid in pw.RULE_IDS)
      and all(re.compile(v) for _, _, _, s, _ in pw.CNT_RULES for k, v in s.items() if k in ("rx", "start", "end", "label", "with")))


# ------------------------------------------------------------------ PCAP single / package
def pcap_page(d, label_line, period="September 30, 2025", fund="Invented Ventures Fund IV LP", title=True):
    p = d.new_page(width=612, height=792)
    p.insert_text((40, 40), fund, fontsize=12)
    if title:
        p.insert_text((40, 58), "Partner's Capital Account Statement", fontsize=11)
    p.insert_text((40, 74), f"For the period ended {period}", fontsize=9)
    if label_line:
        p.insert_text((40, 100), label_line, fontsize=9)
    p.insert_text((40, 300), "Beginning capital balance        1,234,567", fontsize=9)
    return p
r = read(pdf_bytes(lambda d: [pcap_page(d, "Partner: Quillon Harrowgate Family Trust"), pcap_page(d, "Partner: Mirelle Vantongeren"),
                              pcap_page(d, "Partner: Ostrava Pemberly Holdings LLC")]), "capital_statement")
got = [(st.page_from, st.page_to, cls[0][0], cls[0][2], st.fy, st.quarter) for st, cls in r["statements"]]
check("R-035 PCAP package: one statement per page whose top region holds the title; label -> HIGH; period -> FY 2025 Q3",
      got == [(1, 1, "LP-0101", "high", 2025, 3), (2, 2, "LP-0103", "high", 2025, 3), (3, 3, "LP-0102", "high", 2025, 3)], str(got))
check("PCAP header: the fund's name -> entity code", all(st.entity == "TESTF" for st, _ in r["statements"]))
r = read(pdf_bytes(lambda d: pcap_page(d, "Quillon Harrowgate Family Trust")), "capital_statement")
check("PCAP without a label: a roster name in the top region -> MEDIUM (uncertain anchor)", r["statements"][0][1] == [("LP-0101", "TESTF", "medium", None)], str(r["statements"][0][1]))
r = read(pdf_bytes(lambda d: pcap_page(d, "Partner: Quillon Harrowgate Family Trust", period="December 31, 2024")), "capital_statement")
check("PCAP year-end statement -> FY 2024 Q4", (r["statements"][0][0].fy, r["statements"][0][0].quarter) == (2024, 4))


# ------------------------------------------------------------------ subscription agreement / side letter
def sub(d):
    p = d.new_page(); p.insert_text((40, 60), "Invented Ventures Fund IV LP", fontsize=12); p.insert_text((40, 80), "SUBSCRIPTION AGREEMENT", fontsize=12)
    for _ in range(5): d.new_page().insert_text((40, 60), "Terms and conditions.", fontsize=9)
    s = d.new_page(); s.insert_text((40, 60), "SIGNATURE PAGE", fontsize=11); s.insert_text((40, 100), "Name of Investor: Mirelle Vantongeren", fontsize=9)
    s.insert_text((40, 130), "By: ______________________", fontsize=9)
r = read(pdf_bytes(sub), "subscription_agreement")
st, cls = r["statements"][0]
check("subscription agreement: the investor-name label on a signature page -> HIGH, page number kept; fund -> entity",
      cls == [("LP-0103", "TESTF", "high", None)] and st.page_from == 7 and st.entity == "TESTF", f"{cls} p{st.page_from} {st.entity}")


def sl(d):
    p = d.new_page()
    p.insert_text((40, 60), "Invented Ventures Fund IV LP", fontsize=11)
    p.insert_text((40, 120), "Ostrava Pemberly Holdings LLC", fontsize=9)
    p.insert_text((40, 132), "1 Invented Way", fontsize=9)
    p.insert_text((40, 170), "Dear Ostrava Pemberly Holdings LLC:", fontsize=9)
    p.insert_text((40, 200), "This letter sets out certain agreements.", fontsize=9)
r = read(pdf_bytes(sl), "side_letter")
check("side letter: the 'Dear ...' line -> HIGH", r["statements"][0][1] == [("LP-0102", "TESTF", "high", None)], str(r["statements"][0][1]))

# ------------------------------------------------------------------ no text layer
r = pw.read_document(pdf_bytes(lambda d: d.new_page()), "k1", NAMES, EIDX, RULES, {"TESTF"}, None)
check("a page with no text layer and no OCR -> outcome ocr_needed (counted, carry on)", r["outcome"] == "ocr_needed", r["outcome"])
r = pw.read_document(b"not a pdf at all", "k1", NAMES, EIDX, RULES, {"TESTF"}, None)
check("an unreadable file -> open_error (never raises)", r["outcome"] == "open_error")

# ------------------------------------------------------------------ local OCR (Tesseract through a pipe)
exe = pw.tesseract_exe()
if exe:
    src_pdf = fitz.open(stream=pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust"])), filetype="pdf")
    pix = src_pdf[0].get_pixmap(dpi=200); src_pdf.close()
    img = fitz.open(); pg = img.new_page(width=612, height=792); pg.insert_image(pg.rect, stream=pix.tobytes("png"))
    scanned = img.tobytes(); img.close()
    before = set(os.listdir(tempfile.gettempdir()))
    r = pw.read_document(scanned, "k1", NAMES, EIDX, RULES, {"TESTF"}, exe)
    after = set(os.listdir(tempfile.gettempdir()))
    cls = r["statements"][0][1] if r.get("statements") else []
    check("OCR: a scanned K-1 (no text layer) is read locally -> the same partner code; text_layer False, ocr_used True",
          r.get("ocr_used") and r.get("text_layer") is False and cls and cls[0][0] == "LP-0101", f"{r.get('outcome')} {cls}")
    check("OCR writes no file (image in through stdin, TSV out through stdout)", not {f for f in after - before if "catwo06" in f.lower() or f.lower().endswith((".png", ".tif"))})
else:
    check("OCR: Tesseract is installed", False, "not found")

# ------------------------------------------------------------------ R-033 nothing but codes leaves memory
r = read(pdf_bytes(lambda d: k1_page(d, ["Quillon Harrowgate Family Trust", "1 Invented Way"], tin=FAKE_TIN)), "k1")
st = r["statements"][0][0]
check("R-033 Line / Page / Stmt reprs carry no text (a traceback can't print a name)",
      all(s not in repr(x) for s in SECRETS for x in [st, pw.Line("Quillon Harrowgate", 0, 0, 1, 1), pw.Page([pw.Line("Quillon Harrowgate", 0, 0, 1, 1)], 10, 10)]))


class FakeCur:
    def __init__(self, log): self.log = log; self.rowcount = 1
    def execute(self, sql, params=None): self.log.append((sql, params))
    def executemany(self, sql, rows): self.log.append((sql, list(rows)))
    def fetchone(self): return (None,)
    def fetchall(self): return []
class FakeCon:
    def __init__(self): self.log = []
    def cursor(self): return FakeCur(self.log)
    def commit(self): pass
    def rollback(self): pass
fc = FakeCon()
pw.write_batch(fc, [({"document_id": 7, "version_key": "0" * 32, "file_id": "1AbCdEfGhIjKlMnOpQ"}, dict(r, ms=12))])
blob = json.dumps(fc.log, default=str)
tin_rx = re.compile(r"\d{3}-\d{2}-\d{4}|\d{2}-\d{7}|XXX-XX-\d{4}")
check("R-033 / G-T1 what is written holds codes, pages and reasons only: no alias, no address, no TIN pattern",
      all(s not in blob for s in SECRETS) and not tin_rx.search(blob) and "LP-0101" in blob and "K1-PII-F" in blob, blob[:300])
check("R-033 the write SQL names no text column (doc_page_read / doc_content_match / content check)",
      not re.search(r"\b(text|page_text|name|address|raw|snippet)\b\s*[,)]", " ".join(s for s, _ in fc.log if isinstance(s, str))))

# ------------------------------------------------------------------ the module itself
src = inspect.getsource(pw)
check("G-N2 no outside service: no HTTP client, no cloud OCR / LLM import; OCR is local Tesseract through a pipe",
      not re.search(r"\b(requests|urllib|httpx|aiohttp|openai|anthropic|vision|textract|boto3)\b\s*(\.|import)", src)
      and "\"stdin\", \"stdout\"" in src)
check("G-D1 Drive access is read-only: get_media / export_media only (no create / update / delete / modifyLabels)",
      not re.search(r"files\(\)\.(create|update|delete|modifyLabels|emptyTrash|copy)\(", src) and "get_media" in src and "export_media" in src)
check("G-L1 the reader logs counts only: no log() call formats a Line, a name line or page text",
      not re.search(r"log\(f?[\"'][^\n]*\{[^}]*(name_line|\.text|alias|lines)\b", src))
check("G-TMP the temp folder is emptied before and after every run (run() wraps the batches in try/finally clean_temp)",
      "clean_temp()" in inspect.getsource(pw.run) and "finally:" in inspect.getsource(pw.run))
td = tempfile.mkdtemp(); pw.TEMP_DIR = os.path.join(td, "catwo06"); os.makedirs(pw.TEMP_DIR)
open(os.path.join(pw.TEMP_DIR, "left_by_a_killed_run.pdf"), "wb").write(b"x")
pw.clean_temp()
check("G-TMP a file left by a run killed mid-batch is removed by the next run's start", os.listdir(pw.TEMP_DIR) == [])

code = ("import sys, socket; sys.path.insert(0, %r); import pages_wo06 as pw; pw.net_guard()\n"
        "try:\n    socket.getaddrinfo('example.com', 443); print('OPEN')\nexcept PermissionError:\n    print('BLOCKED')\n"
        "try:\n    socket.getaddrinfo('www.googleapis.com', 443); print('G-OK')\nexcept PermissionError:\n    print('G-BLOCKED')\nexcept OSError:\n    print('G-OK')\n") % os.path.dirname(os.path.abspath(__file__))
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60).stdout
check("G-N1 the reader's network guard refuses any host but the Google APIs and Neon", "BLOCKED" in out and "G-OK" in out, out)

# ------------------------------------------------------------------ R-034 merge (pure)
def row(seq, cand, p, e, conf, reason=None, pf=1, pt=1):
    return dict(seq=seq, cand=cand, page_from=pf, page_to=pt, anchor="K1-PII-F", partner=p, roster_entity=e, confidence=conf, reason=reason)
o, m, ru, pages, low, lane = sw.merge_content("high", [("LP-0102", "TESTF", "name")], "SUBJ-HIGH", None, set(), [row(1, 1, "LP-0101", "TESTF", "high")], False, True)
check("R-034 content HIGH replaces a name match", o == "high" and m == [("LP-0101", "TESTF", "content")] and ru == "SUBJ-CONTENT" and pages["LP-0101"][0] == 1)
o, m, ru, pages, low, lane = sw.merge_content("confirmed", [("LP-0102", None, "label")], "SUBJ-PERSON", ["LP-0102"], set(), [row(1, 1, "LP-0101", "TESTF", "high")], False, True)
check("R-034 a person's Subject wins; a disagreeing content HIGH -> lane CONFLICT_PERSON, nothing overwritten",
      m == [("LP-0102", None, "label")] and lane[(1, 1)] == (True, "CONFLICT_PERSON"))
o, m, ru, pages, low, lane = sw.merge_content("high", [("LP-0102", "TESTF", "portal")], "SUBJ-PORTAL", None, {"LP-0102"}, [row(1, 1, "LP-0101", "TESTF", "high")], False, True)
check("R-034 a portal-derived code wins; a disagreeing content HIGH -> lane CONFLICT_PORTAL",
      m == [("LP-0102", "TESTF", "portal")] and lane[(1, 1)] == (True, "CONFLICT_PORTAL"))
o, m, ru, pages, low, lane = sw.merge_content("high", [("LP-0102", "TESTF", "portal")], "SUBJ-PORTAL", None, {"LP-0102"}, [row(1, 1, "LP-0102", "TESTF", "high", pf=4, pt=5)], False, True)
check("an agreeing content match lends its page range to the portal row (p. N in the checklist)", pages == {"LP-0102": (4, 5, "K1-PII-F")} and lane[(1, 1)][0] is False)
crow = [row(1, 1, "LP-0101", "TESTF", "high", pf=1, pt=1), row(2, 1, "LP-0102", "TESTF", "high", pf=2, pt=2), row(3, 1, "LP-0103", "TESTF", "medium", pf=3, pt=3)]
o, m, ru, pages, low, lane = sw.merge_content("none", [], None, None, set(), crow, False, True)
check("R-035 a package: every HIGH partner gets a row; a medium statement -> low row + lane",
      [x[0] for x in m] == ["LP-0101", "LP-0102"] and low == [("LP-0103", "TESTF", 3, 3, "K1-PII-F", None)] and lane[(3, 1)][0] is True)
o, m, ru, pages, low, lane = sw.merge_content("none", [], None, None, set(), [row(1, 1, "LP-0202", None, "low", "NOT_IN_FUND")], False, True)
check("R-036 NOT_IN_FUND -> lane only, never a doc_party row", m == [] and low == [] and lane[(1, 1)] == (True, "NOT_IN_FUND"))
o, m, ru, pages, low, lane = sw.merge_content("none", [], None, None, set(), [row(1, 1, None, None, "none", "NO_ROSTER_MATCH")], False, False)
check("NO_ROSTER_MATCH on a document with no roster (not a checklist candidate) -> counted, not in the lane", lane[(1, 1)][0] is False)
o, m, ru, pages, low, lane = sw.merge_content("none", [], None, None, set(), [row(1, 1, None, None, "none", "NO_ROSTER_MATCH")], False, True)
check("NO_ROSTER_MATCH on a checklist candidate -> lane", lane[(1, 1)][0] is True)
o, m, ru, pages, low, lane = sw.merge_content("none", [], None, None, set(), [row(1, 1, "LP-0202", None, "low", "NOT_IN_FUND")], True, True)
check("a person's decision after the read takes the row out of the lane", lane[(1, 1)][0] is False)
o, m, ru, pages, low, lane = sw.merge_content("confirmed", [], "SUBJ-PERSON", ["LP-0102"], set(), [row(1, 1, "LP-0101", "TESTF", "high", "CONFLICT_PERSON")], False, True)
o2 = sw.merge_content("confirmed", [], "SUBJ-PERSON", ["LP-0101"], set(), [row(1, 1, "LP-0101", "TESTF", "high", "CONFLICT_PERSON")], False, True)
check("a conflict that no longer holds goes back to the read's own reason", o2[5][(1, 1)] == (False, None))
codes = [f"LP-{i:04d}" for i in range(1, 30)]
check("label fit: a code list over the label's text limit / 20 codes does not fit (written as none; DB keeps the page map)",
      sw.fits_label(["LP-0101", "LP-0102"]) and not sw.fits_label(codes) and not sw.fits_label(codes[:12]))

# ------------------------------------------------------------------ R-037 Handling flags
class FS(cl.Schema):
    pass
fs = cl.Schema({"handling": {"label_id": "H", "fields": {"tier": {"field_id": "t", "choices": {"normal": "n", "restricted": "r", "secret": "s"}},
                                                         "contains": {"field_id": "c", "choices": {"lp_pii": "l", "tax_id": "x", "personnel": "p"}}}}})
check("R-037 Contains + Tax ID / LP PII from page 1; the tier is unchanged",
      cl.handling_raise({"_content_contains": ["lp_pii", "tax_id"]}, {"tier": "normal", "contains": []}, fs) == {"contains": ["lp_pii", "tax_id"]})
check("R-037 a flag the machine wrote before and a person removed is never added back",
      cl.handling_raise({"_content_contains": ["tax_id"]}, {"tier": "normal", "contains": []}, fs, {"contains": ["tax_id"]}) == {})
check("R-037 only raises: an existing choice is kept; nothing to add -> no write",
      cl.handling_raise({"_content_contains": ["tax_id"]}, {"tier": "restricted", "contains": ["tax_id", "bank_details"]}, fs) == {}
      and cl.handling_raise({"_content_contains": ["tax_id"]}, {"tier": "normal", "contains": ["bank_details"]}, fs) == {"contains": ["bank_details", "tax_id"]})
check("R-037 an unpublished choice is never written",
      cl.handling_raise({"_content_contains": ["tax_id"]}, {"tier": "normal", "contains": []},
                        cl.Schema({"handling": {"label_id": "H", "fields": {"contains": {"field_id": "c", "choices": {"lp_pii": "l"}}}}})) == {})
e = cl.expected({"content_flags": ["tax_id", "lp_pii", "something_else"]}, fs)
check("expected() carries only the two R-037 flag codes", e["_content_contains"] == ["lp_pii", "tax_id"])

# ------------------------------------------------------------------ CAT-WO-06.1 read new first
import datetime as _dt
now = _dt.datetime(2026, 11, 23, tzinfo=_dt.timezone.utc)
docs = [dict(document_id=1, fresh=now - _dt.timedelta(days=400), learn=False, changed=False),     # backlog, oldest id
        dict(document_id=2, fresh=now - _dt.timedelta(days=300), learn=False, changed=False),     # backlog
        dict(document_id=900, fresh=now - _dt.timedelta(hours=3), learn=False, changed=False),    # new today
        dict(document_id=901, fresh=now - _dt.timedelta(days=2), learn=False, changed=False),     # new this week
        dict(document_id=5, fresh=now - _dt.timedelta(days=90), learn=False, changed=True),       # read before, md5 changed
        dict(document_id=7, fresh=now - _dt.timedelta(days=500), learn=True, changed=False)]      # person-picked lane doc
order = [d["document_id"] for d in sorted(docs, key=lambda d: pw.fresh_key(d, now))]
check("CAT-WO-06.1 the pages step reads lane-learning documents first, then new / changed documents newest first, then the backlog oldest first",
      order == [7, 900, 901, 5, 1, 2], str(order))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
