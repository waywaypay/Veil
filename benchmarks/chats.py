"""veil and a span tagger on real AI chats: people's messages to ChatGPT from WildChat-1M (ODC-BY), which its authors
de-identified with Microsoft Presidio, leaving a marker where it took something out.  Results in benchmarks/model.md.

  pii        316 English conversations Presidio found something in (shards 0-3): each user turn under 3,000
             characters, its markers filled with made-up names, emails, phone numbers and card numbers
  ordinary   400 English conversations it found nothing in: the first user turn under 2,000 characters
  train/dev  the same from shards 4-7, for training a tagger (train_tagger.py)

judged/chats.json says which conversations and turns each set holds and what was put in place of each marker, so the
sets are rebuilt exactly from WildChat; it holds none of WildChat's text.  It also holds the verdicts: every run of
words some system hid that wasn't put there, judged in context as "personal" (a private person's detail, many of
them left by Presidio), "public" (a public figure's or a fictional character's name) or "ordinary".  A detail counts
as found when all its words are hidden; the details are those put back and those judged personal, so a detail every
system missed isn't counted.  A word a system hides that no verdict covers counts as a mistake; chats.py score lists
them, to be judged.

python chats.py fetch                     WildChat's shards 0-7, to $VEIL_BENCH_DATA (1.7 GB)
python chats.py build                     the sets, from the shards and judged/chats.json
python chats.py score [model[@th] ...]    veil (as is and typed=True), and each model alone and with veil"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import tagger as T
import tagger_sets

from veil import GENERIC, Redactor

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "judged" / "chats.json"
SHARDS = {f"wildchat{i}.parquet": f"{tagger_sets.HF}/allenai/WildChat-1M/parquet/default/train/{i}.parquet"
          for i in range(8)}
MARKER = re.compile(r"<PRESIDIO_ANONYMIZED_([A-Z_]+)>")
GROUP = {"PERSON": "name", "EMAIL_ADDRESS": "email", "PHONE_NUMBER": "phone / fax", "CREDIT_CARD": "bank / card / account"}


def build():
    manifest = json.load(open(MANIFEST))
    users = {}
    for shard in SHARDS:
        d = pd.read_parquet(T.DATA / shard, columns=["conversation_hash", "conversation", "language"])
        for h, conv, lang in zip(d.conversation_hash, d.conversation, d.language):
            if lang == "English":
                users.setdefault(h, [u["content"] for u in conv if u["role"] == "user"])
    for name, convs in manifest["sets"].items():
        out = []
        for c in convs:
            turns = []
            for i, values, sha in c["turns"]:
                original, text, spans, pos = users[c["hash"]][i], "", [], 0
                for m, v in zip(MARKER.finditer(original), values):
                    text += original[pos:m.start()]
                    spans.append([len(text), len(text) + len(v), GROUP.get(m.group(1), "outside")])
                    text += v
                    pos = m.end()
                text += original[pos:]
                if hashlib.sha1(text.encode()).hexdigest()[:12] != sha:
                    raise ValueError(f"conversation {c['hash']} turn {i} isn't as it was judged")
                turns.append({"text": text, "spans": spans})
            out.append({"id": c["hash"], "turns": turns, **({"kind": c["kind"]} if "kind" in c else {})})
        json.dump(out, open(T.DATA / f"chats_{name}.json", "w"))
        print(f"{name}: {len(out)} conversations, {sum(len(c['turns']) for c in out)} user turns", file=sys.stderr)


def systems(sets, models):
    """name -> function from a conversation to what each of its user turns becomes: one Redactor a conversation."""
    texts = [t["text"] for convs in sets.values() for c in convs for t in c["turns"]]
    out = {}
    for typed in (False, True):
        out[f"veil{' (typed)' if typed else ''}"] = lambda c, typed=typed: (
            lambda r: [r.redact_text(t["text"], typed) for t in c["turns"]])(Redactor(GENERIC))
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        out[f"{spec} alone"] = lambda c, found=found, th=th: [T.alone(t["text"], found[T.key(t["text"])], th)
                                                              for t in c["turns"]]
        for gate in ("names only", "checked"):
            out[f"veil + {spec}, {gate}"] = lambda c, found=found, th=th, gate=gate: (
                lambda r: [T.with_veil(t["text"], found[T.key(t["text"])], T.GATES[gate], th, redactor=r)
                           for t in c["turns"]])(Redactor(GENERIC))
    return out


def score(models):
    sets = {k: json.load(open(T.DATA / f"chats_{k}.json")) for k in ("pii", "ordinary")}
    verdicts = {}
    for k, v in json.load(open(MANIFEST))["verdicts"].items():
        name, ci, ti, s, e = k.split("/")
        verdicts.setdefault((name, int(ci), int(ti)), []).append((int(s), int(e), v))
    results, unjudged = {}, {}
    for system, fn in systems(sets, models).items():
        r = {}
        for name, convs in sets.items():
            hit = tot = words = 0
            fp = {"ordinary": 0, "public": 0}
            for ci, c in enumerate(convs):
                for ti, (t, out) in enumerate(zip(c["turns"], fn(c))):
                    ws = T.bench.words(t["text"])
                    _, kept = T.bench.redacted_mask(t["text"], out)
                    here = verdicts.get((name, ci, ti), [])
                    personal = set()
                    for s, e in [(s, e) for s, e, g in t["spans"] if g != "outside"] + \
                                [(s, e) for s, e, v in here if v == "personal"]:
                        idx = {j for j, (w, a, b) in enumerate(ws) if a < e and b > s and w.lower() not in T.bench.TITLES}
                        personal |= idx
                        if idx:
                            tot += 1
                            hit += all(not kept[j] for j in idx)
                    covered = {j for s, e, _ in here for j, (_, a, b) in enumerate(ws) if a < e and b > s}
                    public = {j for s, e, v in here if v == "public" for j, (_, a, b) in enumerate(ws) if a < e and b > s}
                    outside = {j for s, e, g in t["spans"] if g == "outside" for j, (_, a, b) in enumerate(ws)
                               if a < e and b > s}
                    for j, (w, a, b) in enumerate(ws):
                        if j in personal or j in outside or w.lower() in T.bench.TITLES:
                            continue
                        words += 1
                        if not kept[j]:
                            fp["public" if j in public else "ordinary"] += 1
                            if j not in covered:
                                unjudged[f"{name}/{ci}/{ti}/{a}/{b}"] = t["text"][max(0, a - 80):b + 80]
            r[name] = {"found": hit / tot, "details": tot, "ordinary hidden": fp["ordinary"] / words,
                       "public names hidden": fp["public"] / words}
        results[system] = r
        p, o = r["pii"], r["ordinary"]
        print(f"{system:52} found {p['found']:6.1%}   ordinary words hidden {p['ordinary hidden']:5.2%} / "
              f"{o['ordinary hidden']:5.2%}   public names hidden {o['public names hidden']:5.2%}", flush=True)
    json.dump(results, open(T.DATA / "chats_results.json", "w"), indent=1)
    if unjudged:
        with open(T.DATA / "chats_to_judge.txt", "w") as f:
            for k, ctx in unjudged.items():
                f.write(f"{k}\t{ctx.replace(chr(10), ' ⏎ ')}\n")
        print(f"{len(unjudged)} hidden words no verdict covers, counted as mistakes: {T.DATA / 'chats_to_judge.txt'}")


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    {"fetch": lambda: tagger_sets.fetch(SHARDS), "build": build, "score": lambda: score(rest)}[cmd]()
