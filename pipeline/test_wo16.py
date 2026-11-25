"""CAT-WO-16 · BANK-L4. Offline (no DB, no Drive). Invented digits and entity codes only."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bank_wo16 as b

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

M = {"4711": {"FUND-A"}, "0815": {"FUND-B"}, "2024": {"FUND-C"}}
RX = b.cue_regex(M)
F = lambda t: b.find_codes(t, RX, M)
check("B1 cues: x1234, ****1234, #1234, 'ending 1234', 'ending in 1234', acct / account no. ...1234",
      all(F(t) == {"FUND-A"} for t in ["Stmt x4711 Jan.pdf", "Statement ****4711", "acct #4711", "Checking ending 4711",
                                         "ending in 4711", "Acct...4711", "Account No. 4711", "account number: xx4711", "ACCT-4711"]),
      str([t for t in ["Stmt x4711 Jan.pdf", "Statement ****4711", "acct #4711", "Checking ending 4711", "ending in 4711", "Acct...4711",
                       "Account No. 4711", "account number: xx4711", "ACCT-4711"] if F(t) != {"FUND-A"}]))
check("B2 whole token only: 47110, 14711 inside a longer number never match", F("x47110 statement") == set() and F("acct 1234711") == set())
check("B3 no cue, no match: a bare 4-digit number (e.g. a year or an amount) is never taken",
      F("Statement 2024 0815.pdf") == set() and F("Bank 4711 summary") == set() and F("box4711") == set())
check("B4 a leading zero is kept", F("x0815") == {"FUND-B"})
check("B5 two different accounts -> both found (decide makes it ambiguous)", F("from x4711 to x0815") == {"FUND-A", "FUND-B"})
D = lambda **k: b.decide(k.get("names", []), k.get("paths", []), k.get("page"), k.get("person", False), k.get("auto", set()), M, RX)
check("B6 order: the file name wins over the folder path and page 1", D(names=["x4711.pdf"], paths=["Cash/x0815"], page={"FUND-B"}) == ("set", "FUND-A", "name"))
check("B7 the folder path when the name has nothing; page 1 last", D(paths=["03-Cash/acct 0815"]) == ("set", "FUND-B", "path")
      and D(page={"FUND-A"}) == ("set", "FUND-A", "page1"))
check("B8 a person's entity is never touched", D(names=["x4711"], person=True) == ("person", None, None))
check("B9 a machine entity that contradicts it -> conflict (Content disagrees), never written",
      D(names=["x4711"], auto={"FUND-B"}) == ("conflict", "FUND-A", "name"))
check("B10 the same entity already on the document -> agrees", D(names=["x4711"], auto={"FUND-A"}) == ("agrees", "FUND-A", "name"))
check("B11 two accounts of different entities -> ambiguous, nothing set", D(names=["x4711 x0815"]) == ("ambiguous", None, "name"))
check("B12 nothing found -> none", D(names=["statement.pdf"]) == ("none", None, None))
check("B13 page 1 is read only for documents without a person entity and with no name / path match",
      [d["document_id"] for d in b.unmatched_by_name_path([{"document_id": 1, "names": ["x4711"], "paths": []},
                                                           {"document_id": 2, "names": ["stmt"], "paths": ["a/b"]},
                                                           {"document_id": 3, "names": ["stmt"], "paths": [], "person": True}], RX, M)] == [2])
# ------------------------------------------------------------------ v2 (R-068)
M2 = {"4711": {"FUND-A"}, "0815": {"FUND-B"}, "1121": {"FUND-C"}, "0285": {"FUND-D"}}
DC = lambda n: b.delimited_codes(n, M2)
check("V1 delimited token after letters: 'Bank-4711-.pdf', 'Chk_4711_Jan.pdf', 'Bank 4711 statement.pdf'",
      DC("Bank-4711-.pdf") == {"FUND-A"} and DC("Chk_4711_Jan.pdf") == {"FUND-A"} and DC("Bank 4711 statement.pdf") == {"FUND-A"})
check("V2 never inside letters or a longer number: 'ab4711', '47112', '14711'", DC("ab4711.pdf") == set() and DC("x_47112.pdf") == set() and DC("Stmt 14711") == set())
check("V3 date guard: MMDD-YYYY, YYYY-MMDD, MMDD-YY, MM-DD-YY pieces are skipped",
      DC("Stmt_1121-2024.pdf") == set() and DC("Stmt 2024-1121.pdf") == set() and DC("Stmt 1121_24.pdf") == set()
      and DC("Stmt 05-0285-24") == set())
check("V4 not a date when the neighbour is no year / day piece: 'Chk_1121_Statement.pdf', 'Wells_4711_2024.pdf' (47/11 is no MMDD)",
      DC("Chk_1121_Statement.pdf") == {"FUND-C"} and DC("Wells_4711_2024.pdf") == {"FUND-A"})
sk = __import__("collections").Counter(); b.delimited_codes("Stmt 1121-2024", M2, sk)
check("V5 skipped date-shaped tokens are counted (codes only)", sk["1121"] == 1)
check("V6 the extension is not a token: 'Bank-4711.0815' keeps only 4711? no: '.0815' is the extension -> dropped",
      DC("Bank-4711.0815") == {"FUND-A"})
check("V7 v2 name: two different mapped accounts in one name -> ambiguous",
      b.decide(["Xfer 4711 to 0815.pdf"], [], None, False, set(), M2, b.cue_regex(M2), {"name_delimited": True})[0] == "ambiguous")
check("V8 v1 spec ignores the delimited form", b.decide(["Bank-4711-.pdf"], [], None, False, set(), M2, b.cue_regex(M2), {})[0] == "none")
LC = lambda t: b.long_number_codes(t, M2)
check("V9 page 1: the last 4 of a longer account number after Account / Acct / Account Number / A/C",
      LC("Account Number: 1234567894711")[0] == {"FUND-A"} and LC("Acct 98-7654-0815")[0] == {"FUND-B"} and LC("A/C 0000004711")[0] == {"FUND-A"})
check("V10 page 1: an account number that is not mapped -> seen, no code; no account number -> not seen",
      LC("Account 1234567890000") == (set(), True) and LC("Total 1,234.56") == (set(), False))
print(f"\n{sum(R)}/{len(R)} passed")
