"""veil on hand-written hard cases (cases.py): odd formats, scripts, lookalikes, names that are words, and
words that look like names.

  python benchmarks/hard/hard.py build      cases.py -> hard.jsonl (text, spans with offsets)
  python benchmarks/hard/hard.py score      run veil on hard.jsonl and print what it found and missed
  python benchmarks/hard/hard.py score -v   ... and every miss, wrong kind and wrongly hidden word

Scored as benchmarks/gretel.py does: the words of the original are aligned with the words of veil's output,
and a word missing from the output was hidden.

  found      gold detail with every word hidden (titles aside)
  kind       found, and hidden as the right kind (SSN, EIN and TIN count as one)
  kept       text marked as not personal, left whole
  over       other words hidden
  round trip restore_text(redact_text(text)) == text; "damaged" when something outside the personal details
             (a word, a tab, punctuation) didn't come back.  A hidden value coming back normalized
             (523-45-6789 for 523 45 6789) is by design, not damage.

Cases marked beyond=True test what veil's README makes no claim to, and are scored apart from the rest.
"""

import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]

from veil import FINANCE, GENERIC, US_TAX_K1, Redactor  # noqa: E402

PROFILES = {"GENERIC": GENERIC, "FINANCE": FINANCE, "US_TAX_K1": US_TAX_K1}
MARK = re.compile(r"⟦([A-Z/]+)\|(.*?)⟧|⟪(.*?)⟫", re.S)
TOKEN = re.compile(r"\w+|[^\w ]")
WORD = re.compile(r"\w+")
TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "mx", "dame", "captain", "officer", "agent", "rev"}
TAX = {"SSN", "EIN", "TIN"}
PLACEHOLDER = re.compile(r"\b([A-Z]+)_\d{3,}\b")


def parse(marked):
    """The plain text and its spans from cases.py markup."""
    out, spans, pos = [], [], 0
    for m in MARK.finditer(marked):
        out.append(marked[pos:m.start()])
        start = sum(map(len, out))
        body = m.group(2) if m.group(1) else m.group(3)
        out.append(body)
        spans.append({"start": start, "end": start + len(body), "kind": m.group(1) or "KEEP", "text": body})
        pos = m.end()
    out.append(marked[pos:])
    return "".join(out), spans


def build():
    from cases import C
    seen = set()
    with open(HERE / "hard.jsonl", "w") as f:
        for c in C:
            assert c["id"] not in seen, c["id"]
            seen.add(c["id"])
            text, spans = parse(c["text"])
            for s in spans:
                assert text[s["start"]:s["end"]] == s["text"]
            row = {k: v for k, v in c.items() if k != "text"}
            row.update(text=text, spans=spans)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(C)} cases to {HERE / 'hard.jsonl'}")


def words(text, pattern=WORD):
    return [(m.group(), m.start(), m.end()) for m in pattern.finditer(text)]


def align(orig, out, pattern=WORD):
    """The words of ``orig``, which of them ``out`` kept, and for each the placeholders that took its place."""
    a, b = words(orig, pattern), words(out, pattern)
    sm = difflib.SequenceMatcher(None, [w for w, _, _ in a], [w for w, _, _ in b], autojunk=False)
    kept = [False] * len(a)
    took = [set() for _ in a]
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i in range(i1, i2):
                kept[i] = True
        else:
            kinds = {m.group(1) for w, _, _ in b[j1:j2] for m in PLACEHOLDER.finditer(w)}
            for i in range(i1, i2):
                took[i] = kinds
    return a, kept, took


def run_case(row):
    r = Redactor(PROFILES[row.get("profile", "GENERIC")])
    for b in row.get("businesses", []):
        r.add_business(b)
    for p in row.get("people", []):
        r.add_person(p)
    try:
        out = r.redact_text(row["text"], typed=row.get("typed", False))
        back = r.restore_text(out)
    except Exception as e:   # a crash is a result too
        return {"error": f"{type(e).__name__}: {e}"}
    ws, kept, took = align(row["text"], out)
    # damage on the way back: a token outside the personal details that didn't return
    ts, back_kept, _ = align(row["text"], back, TOKEN)
    personal = [(s["start"], s["end"]) for s in row["spans"] if s["kind"] != "KEEP"]
    damaged = [t for (t, a, b), k in zip(ts, back_kept) if not k and not any(x <= a < y for x, y in personal)]
    res = {"out": out, "roundtrip": back == row["text"], "damaged": damaged, "back": back, "spans": [],
           "over": [], "words": 0}
    in_span = [False] * len(ws)
    for s in row["spans"]:
        idx = [j for j, (w, a, b) in enumerate(ws) if a < s["end"] and b > s["start"]]
        for j in idx:
            in_span[j] = True
        idx = [j for j in idx if ws[j][0].lower() not in TITLES]
        if not idx:
            continue
        if s["kind"] == "KEEP":
            res["spans"].append({**s, "ok": all(kept[j] for j in idx)})
        else:
            hidden = all(not kept[j] for j in idx)
            partial = any(not kept[j] for j in idx) and not hidden
            got = set().union(*(took[j] for j in idx)) if hidden else set()
            want = set(s["kind"].split("/"))
            right = want & got or (want & TAX and got & TAX) or s["kind"] == "OUT"
            res["spans"].append({**s, "ok": hidden, "partial": partial, "kind_ok": hidden and bool(right),
                                 "got": sorted(got)})
    for j, (w, _, _) in enumerate(ws):
        if not in_span[j]:
            res["words"] += 1
            if not kept[j]:
                res["over"].append(w)
    return res


def tally(rows, results):
    by_kind = defaultdict(lambda: [0, 0, 0])      # found, as the right kind, total
    by_cat = defaultdict(lambda: [0, 0, 0, 0])    # found, total, kept, keep total
    t = defaultdict(int)
    for row, res in zip(rows, results):
        cat = row["category"]
        if "error" in res:
            t["errors"] += 1
            continue
        t["exact"] += res["roundtrip"]
        t["damaged"] += bool(res["damaged"])
        t["over"] += len(res["over"])
        t["words"] += res["words"]
        for s in res["spans"]:
            if s["kind"] == "KEEP":
                t["keep"] += 1
                t["keep_ok"] += s["ok"]
                by_cat[cat][3] += 1
                by_cat[cat][2] += s["ok"]
                continue
            k = by_kind[s["kind"].split("/")[0]]
            k[0] += s["ok"]
            k[1] += s["kind_ok"]
            k[2] += 1
            if s["kind"] != "OUT":
                t["found"] += s["ok"]
                t["right"] += s["kind_ok"]
                t["total"] += 1
                t["partial"] += s["partial"]
                by_cat[cat][0] += s["ok"]
                by_cat[cat][1] += 1
    return by_kind, by_cat, t


def pct(a, b):
    return f"{a / b:6.0%}" if b else "     -"


def report(title, rows, results, tables=True):
    by_kind, by_cat, t = tally(rows, results)
    print(f"## {title}: {len(rows)} cases, {t['total']} personal details, {t['keep']} look-alikes to keep\n")
    if tables:
        print(f"{'kind':10} {'found':>6} {'right kind':>10} {'n':>4}")
        for k in sorted(by_kind, key=lambda k: (k == "OUT", k)):
            f_, r_, n_ = by_kind[k]
            print(f"{k:10} {pct(f_, n_)} {pct(r_, n_):>10} {n_:4}")
        print(f"\n{'category':16} {'found':>6} {'kept':>6}")
        for c in dict.fromkeys(r["category"] for r in rows):
            f_, n_, k_, kn = by_cat[c]
            print(f"{c:16} {pct(f_, n_)} {pct(k_, kn)}")
        print()
    print(f"found       {t['found']}/{t['total']} ({t['found'] / max(t['total'], 1):.1%}); "
          f"as the right kind {t['right'] / max(t['total'], 1):.1%}; partly hidden (a leak) {t['partial']}")
    print(f"kept        {t['keep_ok']}/{t['keep']} look-alikes ({t['keep_ok'] / max(t['keep'], 1):.1%}); "
          f"other words hidden {t['over']}/{t['words']} ({t['over'] / max(t['words'], 1):.1%})")
    print(f"round trip  exact in {t['exact']}/{len(rows)}; damaged in {t['damaged']}; crashes {t['errors']}\n")


def problems(row, res):
    if "error" in res:
        return [f"CRASH {res['error']}"]
    out = []
    for s in res["spans"]:
        if s["kind"] == "KEEP":
            if not s["ok"]:
                out.append(f"hid {s['text']!r} (should stay)")
        elif not s["ok"]:
            out.append(f"missed {s['kind']} {s['text']!r}" + (" (partly hidden)" if s["partial"] else ""))
        elif not s["kind_ok"]:
            out.append(f"{s['kind']} {s['text']!r} hidden as {'/'.join(sorted(s['got'])) or '?'}")
    if res["over"]:
        out.append(f"also hid {res['over']}")
    if res["damaged"]:
        out.append(f"round trip damaged {res['damaged']}: {res['back']!r}")
    return out


def score(verbose=False):
    rows = [json.loads(line) for line in open(HERE / "hard.jsonl")]
    results = [run_case(row) for row in rows]
    inside = [(r, x) for r, x in zip(rows, results) if not r.get("beyond")]
    beyond = [(r, x) for r, x in zip(rows, results) if r.get("beyond")]
    report("What veil claims to handle", *zip(*inside))
    report("Beyond what veil claims (other scripts, numbers in words, lookalikes)", *zip(*beyond), tables=False)
    report("All", rows, results, tables=False)
    if verbose:
        for row, res in zip(rows, results):
            p = problems(row, res)
            if p:
                print(f"[{row['id']}]{' (beyond)' if row.get('beyond') else ''} {row['why']}\n"
                      f"    in:  {row['text']!r}\n    out: {res.get('out')!r}\n" + "\n".join("    - " + x for x in p) + "\n")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    build() if cmd == "build" else score("-v" in sys.argv)
