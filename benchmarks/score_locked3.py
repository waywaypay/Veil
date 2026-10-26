"""The third locked test (judged/locked3/README.md): conversations people send an AI assistant, scored once, after
round 10's model is chosen and frozen.  Three steps, in this order:

    python benchmarks/score_locked3.py run --round7 <model> --round10 <model>     every system, and the files to judge
    python benchmarks/score_locked3.py agree                                     the reviewers' agreement
    python benchmarks/score_locked3.py score                                     once, after every verdict is in

The folder (--dir, judged/locked3 by default) holds the written conversations (W01.jsonl to W10.jsonl, WRITERS.md's
format), the WildChat draw (wildchat.jsonl: {"id", "redacted", "messages": [user turns]}) and, for the second
labeller, relabel.jsonl (15 written conversations marked again from scratch, as WRITERS.md asks, with "file" and
"line" naming the conversation).  Only user messages are read.

Systems, each one message at a time and over the whole conversation (its user messages joined by a blank line, as
pii_trace.SEP), the spans of the joined text mapped back to each message:

* veil: veil's rules alone (GENERIC), one Redactor a conversation;
* round 7, round 10: the model alone (TaggedRedactor's spans at the model's threshold);
* round 7 + veil, round 10 + veil: TaggedRedactor's redactor (veil with the model as its finder), one a conversation;
* PII-Tracer: perplexity-ai/PII-Tracer, alone (pii_trace.py's runs, cached by veilbench).

run writes runs.json (every system's hidden spans) and judge/: the runs of words any system hides, pooled one item a
message and shuffled, without the systems (locked_chats_bNN.json, wider_rules.md's "Chats" format), key.json (which
message each item is), and second/ (a random fifth of the items again, for the second reviewer).  In written
conversations, the writer's marks are cut out of the runs, so only what they leave is judged.  Reviewers write
locked_chats_bNN_verdicts.json beside each file, and second/locked_chats_bNN_verdicts.json.

score counts, for each system and mode:

* details: a writer's mark, or a run judged personal:<label>; found when every word of it is hidden;
* other words hidden: the share hidden of the words no detail covers (public and ordinary spans among them, so hiding
  them is a mistake); words of business and unsure spans count neither way;
* recurring details: a value (its letters and digits, lower case) a conversation mentions more than once, counted as
  found when every mention is;

on the written and WildChat conversations apart and together, and by label, with 95% intervals from 2,000 bootstrap
resamples over conversations (seed 0), and the paired differences that matter: round 10 against round 7, alone and with
veil, round 10 alone against PII-Tracer, and round 10 + veil against veil.  On relabel.jsonl's 15 conversations, the
models are scored on both labellings.  It writes scores.json."""
import argparse
import glob
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pii_trace as P  # noqa: E402
import train_wider as W  # noqa: E402

from veil import GENERIC, tagged  # noqa: E402

DIR = Path(__file__).resolve().parent / "judged" / "locked3"
MODES = ("one message", "whole conversation")
SEED = 0
_WORD = re.compile(r"\w+")
for _lab in tagged.SECRET_LABELS:   # round 10's labels, in the writers' marks and the verdicts
    W.GROUP.setdefault(_lab, "secret")


# -- the conversations ----------------------------------------------------------------------------------------------

def load(d):
    """[{"id", "part", "users": [text], "marks": [[(start, end, label)] per message]}]: written, then WildChat."""
    convs = []
    for f in sorted(glob.glob(str(d / "W[0-9][0-9].jsonl"))):
        for i, line in enumerate(open(f, encoding="utf-8")):
            if line.strip():
                msgs = [W.unmark(m) for m in json.loads(line)["messages"]]
                convs.append({"id": f"{Path(f).stem}:{i}", "part": "written", "users": [t for t, _ in msgs],
                              "marks": [s for _, s in msgs]})
    path = d / "wildchat.jsonl"
    if path.exists():
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                convs.append({"id": f"wildchat:{r['id']}", "part": "wildchat", "users": r["messages"],
                              "marks": [[] for _ in r["messages"]]})
    return convs


def starts(users):
    out, pos = [], 0
    for u in users:
        out.append(pos)
        pos += len(u) + len(P.SEP)
    return out


def to_turns(spans, users):
    """Spans of the joined text -> [(turn, start, end)] in each message."""
    out = []
    for s, e in spans:
        for t, (a, u) in enumerate(zip(starts(users), users)):
            if s < a + len(u) and e > a:
                out.append((t, max(s, a) - a, min(e, a + len(u)) - a))
    return out


# -- the systems -----------------------------------------------------------------------------------------------------

class Cached(tagged.TaggedRedactor):
    """A TaggedRedactor that reads each text once, at a floor, and keeps what it found for every later call."""
    def __init__(self, model, threshold):
        super().__init__(model=model, threshold=threshold, profile=GENERIC)
        self.seen = {}

    def model_spans(self, texts, threshold=None):
        todo = [t for t in dict.fromkeys(texts) if t not in self.seen]
        if todo:
            for t, f in zip(todo, super().model_spans(todo, threshold=0.1)):
                self.seen[t] = f
        th = self.threshold if threshold is None else threshold
        return [[x for x in self.seen[t] if x[3] >= th] for t in texts]


def veil_runs(c, finder=None):
    """veil (with the model as its finder, if given), one Redactor a conversation: hidden spans, both modes."""
    r = P.Watched(GENERIC, finder=finder) if finder else P.Watched(GENERIC)
    r.written = []
    one = [(t, s, e) for t, u in enumerate(c["users"]) for s, e in P.hidden(u, r)]
    r = P.Watched(GENERIC, finder=finder) if finder else P.Watched(GENERIC)
    r.written = []
    whole = to_turns(P.hidden(P.SEP.join(c["users"]), r), c["users"])
    return {"one message": one, "whole conversation": whole}


def model_runs(c, m):
    one = [(t, s, e) for t, u in enumerate(c["users"])
           for s, e, _, _ in tagged.merged(m.model_spans([u])[0], u)]
    j = P.SEP.join(c["users"])
    whole = to_turns([(s, e) for s, e, _, _ in tagged.merged(m.model_spans([j])[0], j)], c["users"])
    return {"one message": one, "whole conversation": whole}


def finder_of(m):
    return lambda text: [(s, e, k) for s, e, k, _ in tagged.merged(m.model_spans([text])[0], text)]


def run_systems(convs, round7, th7, round10, th10):
    m7, m10 = Cached(round7, th7), Cached(round10, th10)
    out = {c["id"]: {} for c in convs}
    for c in convs:
        out[c["id"]]["veil"] = veil_runs(c)
        out[c["id"]]["round 7"] = model_runs(c, m7)
        out[c["id"]]["round 10"] = model_runs(c, m10)
        out[c["id"]]["round 7 + veil"] = veil_runs(c, finder_of(m7))
        out[c["id"]]["round 10 + veil"] = veil_runs(c, finder_of(m10))
    pc = [{"users": c["users"]} for c in convs]
    for c, one, whole in zip(convs, P.tracer_spans(pc), P.tracer_conv_spans(pc)):
        out[c["id"]]["PII-Tracer"] = {"one message": [(t, s, e) for t, s, e, _ in one],
                                      "whole conversation": [(t, s, e) for t, s, e, _ in whole]}
    return out


# -- judging ---------------------------------------------------------------------------------------------------------

def merge(spans):
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def minus(runs, cut):
    """The pieces of ``runs`` outside ``cut``."""
    out = []
    for s, e in runs:
        pos = s
        for a, b in sorted(cut):
            if b <= pos or a >= e:
                continue
            if a > pos:
                out.append([pos, a])
            pos = max(pos, b)
        if pos < e:
            out.append([pos, e])
    return out


def to_judge(c, runs, t):
    """What to judge in message ``t``: every run any system hides, a writer's marks cut out, keeping pieces with a word."""
    u = c["users"][t]
    hidden = merge([(s, e) for sysruns in runs.values() for mode in sysruns.values() for t2, s, e in mode if t2 == t])
    pieces = minus(hidden, [(s, e) for s, e, _ in c["marks"][t]])
    return [[s, e] for s, e in pieces if _WORD.search(u[s:e])]


def write_judging(convs, runs, d, per_file=200):
    items = [(c["id"], t, to_judge(c, runs[c["id"]], t)) for c in convs for t in range(len(c["users"]))]
    items = [x for x in items if x[2]]
    random.Random(SEED).shuffle(items)
    text = {c["id"]: c["users"] for c in convs}
    (d / "judge" / "second").mkdir(parents=True, exist_ok=True)
    key = []
    second = set(random.Random(SEED + 1).sample(range(len(items)), len(items) // 5))
    for b in range(0, len(items), per_file):
        chunk = items[b:b + per_file]
        name = f"locked_chats_b{b // per_file + 1:02d}.json"
        json.dump([{"text": text[cid][t], "spans": sp} for cid, t, sp in chunk], open(d / "judge" / name, "w"), indent=0)
        again = [(i, x) for i, x in enumerate(chunk) if b + i in second]
        json.dump([{"text": text[cid][t], "spans": sp} for _, (cid, t, sp) in again],
                  open(d / "judge" / "second" / name, "w"), indent=0)
        key += [{"file": name, "item": i, "id": cid, "turn": t, "spans": sp, "second": b + i in second}
                for i, (cid, t, sp) in enumerate(chunk)]
    json.dump(key, open(d / "judge" / "key.json", "w"), indent=0)
    print(f"{len(items)} messages to judge, {sum(len(x[2]) for x in items)} spans, in "
          f"{(len(items) + per_file - 1) // per_file} files; {len(second)} again for the second reviewer")


def verdicts(d, second=False):
    """{(conversation, turn, start, end): verdict} from the reviewers' files."""
    key = json.load(open(d / "judge" / "key.json"))
    out = {}
    by_file = defaultdict(list)
    for k in key:
        if k["second"] or not second:
            by_file[k["file"]].append(k)
    for name, ks in by_file.items():
        path = d / "judge" / ("second" if second else "") / name.replace(".json", "_verdicts.json")
        v = json.load(open(path))
        for n, k in enumerate(ks):
            got = v[str(n if second else k["item"])]
            if len(got) != len(k["spans"]):
                raise ValueError(f"{path}: item {n if second else k['item']} has {len(got)} verdicts for {len(k['spans'])} spans")
            for (s, e), x in zip(k["spans"], got):
                out[(k["id"], k["turn"], s, e)] = x
    return out


def kappa(pairs):
    n = len(pairs)
    agree = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expect = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return agree, (agree - expect) / (1 - expect) if expect < 1 else 1.0


def coarse(v):
    return "personal" if v.startswith("personal:") else v


# -- scoring ---------------------------------------------------------------------------------------------------------

def gold(c, verdict):
    """Per message: [(start, end, label or "outside")] details and spans that count neither way."""
    out = [[(s, e, lab) for s, e, lab in m] for m in c["marks"]]
    for (cid, t, s, e), v in verdict.items():
        if cid == c["id"]:
            if v.startswith("personal:"):
                out[t].append((s, e, v.split(":", 1)[1]))
            elif v in ("business", "unsure"):
                out[t].append((s, e, "outside"))
    return out


def counts(c, spans, hidden):
    """One conversation, one system and mode: found and missed by label, other words hidden, recurring details."""
    by, ow, ow_tot, values = defaultdict(lambda: [0, 0]), 0, 0, defaultdict(list)
    for t, u in enumerate(c["users"]):
        hid = [(s, e) for t2, s, e in hidden if t2 == t]
        words = [(m.start(), m.end()) for m in _WORD.finditer(u)]
        gone = [any(a < e and s < b for s, e in hid) for a, b in words]
        covered = [False] * len(words)
        for s, e, lab in spans[t]:
            idx = [i for i, (a, b) in enumerate(words) if a < e and s < b]
            for i in idx:
                covered[i] = True
            if lab == "outside" or not idx:
                continue
            hit = all(gone[i] for i in idx)
            by[lab][0] += hit
            by[lab][1] += 1
            values[re.sub(r"\W", "", u[s:e]).lower()].append(hit)
        for i in range(len(words)):
            if not covered[i]:
                ow_tot += 1
                ow += gone[i]
    rec = [all(v) for v in values.values() if len(v) > 1]
    return {"by": dict(by), "ow": ow, "ow_tot": ow_tot, "rec": sum(rec), "rec_tot": len(rec)}


def total(cs):
    hit = sum(h for c in cs for h, _ in c["by"].values())
    tot = sum(n for c in cs for _, n in c["by"].values())
    return {"found": hit / max(1, tot), "details": tot, "over": sum(c["ow"] for c in cs) / max(1, sum(c["ow_tot"] for c in cs)),
            "recurring": sum(c["rec"] for c in cs) / max(1, sum(c["rec_tot"] for c in cs)),
            "recurring_n": sum(c["rec_tot"] for c in cs)}


def bootstrap(per, systems, pairs, n=2000):
    """95% intervals over conversations for each system's found and other words hidden, and paired differences."""
    ids = list(next(iter(per.values())))
    flat = {k: [(sum(h for h, _ in per[k][i]["by"].values()), sum(m for _, m in per[k][i]["by"].values()),
                 per[k][i]["ow"], per[k][i]["ow_tot"]) for i in ids] for k in systems}
    rng = random.Random(SEED)
    draws = defaultdict(list)
    for _ in range(n):
        s = [rng.randrange(len(ids)) for _ in ids]
        cell = {}
        for k in systems:
            h, t, o, ot = (sum(flat[k][i][j] for i in s) for j in range(4))
            cell[k] = (h / max(1, t), o / max(1, ot))
            draws[k].append(cell[k])
        for a, b in pairs:
            draws[(a, b)].append((cell[a][0] - cell[b][0], cell[a][1] - cell[b][1]))
    ci = lambda xs: (sorted(xs)[int(0.025 * n)], sorted(xs)[int(0.975 * n)])  # noqa: E731
    return {k: {"found": ci([x for x, _ in v]), "over": ci([y for _, y in v])} for k, v in draws.items()}


def score(d):
    convs = load(d)
    runs = json.load(open(d / "runs.json"))
    verdict = verdicts(d)
    systems = list(next(iter(runs.values())))
    keys = [(s, m) for s in systems for m in MODES]
    pairs = [(("round 10", m), ("round 7", m)) for m in MODES] + \
            [(("round 10 + veil", m), ("round 7 + veil", m)) for m in MODES] + \
            [(("round 10", m), ("PII-Tracer", m)) for m in MODES] + \
            [(("round 10 + veil", m), ("veil", m)) for m in MODES]
    report = {}
    for part in ("written", "wildchat", "both"):
        cs = [c for c in convs if part == "both" or c["part"] == part]
        if not cs:
            continue
        golds = {c["id"]: gold(c, verdict) for c in cs}
        per = {k: {c["id"]: counts(c, golds[c["id"]], [tuple(x) for x in runs[c["id"]][k[0]][k[1]]]) for c in cs}
               for k in keys}
        ci = bootstrap(per, keys, pairs)
        report[part] = {}
        print(f"\n{part}: {len(cs)} conversations")
        for k in keys:
            r = total(list(per[k].values()))
            by = defaultdict(lambda: [0, 0])
            for c in per[k].values():
                for lab, (h, n) in c["by"].items():
                    by[lab][0] += h
                    by[lab][1] += n
            report[part][" / ".join(k)] = {**r, "found_ci": ci[k]["found"], "over_ci": ci[k]["over"], "by": dict(by)}
            print(f"  {k[0]:16} {k[1]:18} found {r['found']:.1%} [{ci[k]['found'][0]:.1%}, {ci[k]['found'][1]:.1%}] "
                  f"of {r['details']}   other words hidden {r['over']:.2%} [{ci[k]['over'][0]:.2%}, {ci[k]['over'][1]:.2%}]"
                  f"   recurring {r['recurring']:.1%} of {r['recurring_n']}")
        for a, b in pairs:
            f, o = ci[(a, b)]["found"], ci[(a, b)]["over"]
            tie = lambda iv: " (tie)" if iv[0] <= 0 <= iv[1] else ""  # noqa: E731
            report[part][f"{' / '.join(a)} - {' / '.join(b)}"] = {"found": f, "over": o}
            print(f"  {' / '.join(a)} - {' / '.join(b)}: found [{f[0]:+.1%}, {f[1]:+.1%}]{tie(f)}   "
                  f"other words [{o[0]:+.2%}, {o[1]:+.2%}]{tie(o)}")
    path = d / "relabel.jsonl"
    if path.exists():
        report["relabel"] = relabel(d, convs, runs, keys)
    json.dump(report, open(d / "scores.json", "w"), indent=1)
    print(f"\n{d / 'scores.json'}")


def relabel(d, convs, runs, keys):
    """The models on the second labeller's 15 conversations, scored on each labelling, and agreement over words."""
    by_id = {c["id"]: c for c in convs}
    firsts, seconds, words = [], [], []
    for line in open(d / "relabel.jsonl", encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        c = by_id[f"{Path(r['file']).stem}:{r['line']}"]
        msgs = [W.unmark(m) for m in r["messages"]]
        if [t for t, _ in msgs] != c["users"]:
            raise ValueError(f"{r['file']}:{r['line']}: the second labelling's text differs from the first's")
        second = dict(c, marks=[s for _, s in msgs])
        firsts.append(c)
        seconds.append(second)
        for t, u in enumerate(c["users"]):
            for m in _WORD.finditer(u):
                inside = lambda marks: any(s < m.end() and m.start() < e for s, e, _ in marks)  # noqa: E731
                words.append((inside(c["marks"][t]), inside(second["marks"][t])))
    agree, k = kappa(words)
    out = {"conversations": len(firsts), "word agreement": agree, "kappa": k}
    print(f"\nsecond labelling, {len(firsts)} conversations: words agree {agree:.1%}, kappa {k:.3f}")
    for name, cs in (("first", firsts), ("second", seconds)):
        for key in keys:
            r = total([counts(c, [list(m) for m in c["marks"]], [tuple(x) for x in runs[c["id"]][key[0]][key[1]]])
                       for c in cs])
            out[f"{name} / {' / '.join(key)}"] = r
            print(f"  {name:6} labelling  {key[0]:16} {key[1]:18} found {r['found']:.1%} of {r['details']}   "
                  f"other words hidden {r['over']:.2%}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("run", "agree", "score"))
    ap.add_argument("--dir", type=Path, default=DIR)
    ap.add_argument("--round7", default=tagged.MODEL)
    ap.add_argument("--round10")
    ap.add_argument("--th7", type=float, default=tagged.THRESHOLD)
    ap.add_argument("--th10", type=float, default=tagged.THRESHOLD)
    a = ap.parse_args()
    if a.step == "run":
        if not a.round10:
            ap.error("run needs --round10, the frozen round 10 model")
        convs = load(a.dir)
        print(f"{sum(c['part'] == 'written' for c in convs)} written and {sum(c['part'] == 'wildchat' for c in convs)} "
              f"WildChat conversations, {sum(len(c['users']) for c in convs)} user messages")
        runs = run_systems(convs, a.round7, a.th7, a.round10, a.th10)
        json.dump(runs, open(a.dir / "runs.json", "w"))
        write_judging(convs, runs, a.dir)
    elif a.step == "agree":
        first, second = verdicts(a.dir), verdicts(a.dir, second=True)
        pairs = [(first[k], v) for k, v in second.items()]
        raw, k = kappa(pairs)
        braw, bk = kappa([(coarse(x) == "personal", coarse(y) == "personal") for x, y in pairs])
        fraw, fk = kappa([(coarse(x), coarse(y)) for x, y in pairs])
        print(f"{len(pairs)} spans judged twice: verdicts agree {raw:.1%} (kappa {k:.3f}); over the five verdicts "
              f"{fraw:.1%} (kappa {fk:.3f}); private person's detail or not {braw:.1%} (kappa {bk:.3f})")
        json.dump({"spans": len(pairs), "verdicts": [raw, k], "five": [fraw, fk], "personal": [braw, bk]},
                  open(a.dir / "agreement.json", "w"), indent=1)
    else:
        score(a.dir)


if __name__ == "__main__":
    main()
