"""The locked tests (judged/PROTOCOL.md): five sets made before round 6's model was chosen, every run of words any
system hid in them judged blind, and each scored once after the choice, veil against rounds 2 to 6 of the tagger,
each alone and with veil.  Results in benchmarks/model.md.

  documents   150 documents written by ten agents who never saw the training documents or the earlier tests
              (judged/docgen/locked, labelled inline by their writers); 30 of them, 3 a family, labelled again from
              scratch by two other agents (judged/docgen/locked/relabel.jsonl)
  forms       300 of formgen.py's forms from seed 96, which no other set uses
  tweets      700 tweets and posts: positions 700 to 1,399 of the BTC and WNUT-17 test splits as train_wider.py
              shuffles them (the earlier test took the first 700)
  Enron       197 emails from the mailboxes in the corpus's second file that its first, the earlier sample's,
              doesn't hold
  chats       720 English WildChat conversations from shards 10-13, which no other set uses: 320 Presidio found
              something in, their markers filled with made-up details as chats.py fills them, and 400 it found
              nothing in

judged/locked.json holds the keys (Enron message IDs, WildChat hashes and what was put in each marker) and the
verdicts, by text: every span a system hid, and every person and handle the tweet corpora label, judged in context
to judged/wider_rules.md by reviewers not told which system hid it, and a second reviewer's verdicts on a random
fifth of the items.  A judged set is scored as round 4's test was: a span judged a private person's detail is found
when every word of it is hidden, a public name counts against a system that hides it, a business's detail or an
unsure span counts neither way, and a hidden word no verdict covers is a mistake.  Intervals are 95% bootstrap
intervals over texts (conversations for chats), differences paired.

python locked.py fetch                        the Enron file and WildChat shards these sets come from
python locked.py build                        the Enron and chat sets, from them and judged/locked.json
python locked.py score <model>[@th] ...       the last model is compared with veil and with each of the others
python locked.py agree                        the second reviewers and the second labellers against the first"""

import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import formgen
import pandas as pd
import tagger as T
import tagger_sets
import train_wider as W

from veil import FINANCE, GENERIC, Redactor

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "judged" / "locked.json"
DOCS = HERE / "judged" / "docgen" / "locked"
FILES = {"enron1.parquet": f"{W.RAW}/corbt/enron-emails/resolve/main/data/train-00001-of-00003.parquet",
         **{f"wildchat{i}.parquet": f"{tagger_sets.HF}/allenai/WildChat-1M/parquet/default/train/{i}.parquet"
            for i in range(10, 14)}}
MARKER = re.compile(r"<PRESIDIO_ANONYMIZED_([A-Z_]+)>")
CHAT_GROUP = {"PERSON": "name", "EMAIL_ADDRESS": "email", "PHONE_NUMBER": "phone / fax",
              "CREDIT_CARD": "bank / card / account"}
JUDGED_GROUP = {"public": "ordinary", "business": "outside", "unsure": "outside"}


def manifest():
    return json.load(open(MANIFEST))


def fetch():
    tagger_sets.fetch(FILES)


def build():
    m = manifest()
    e = pd.read_parquet(T.DATA / "enron1.parquet").set_index("message_id")
    emails = []
    for mid in m["enron"]["ids"]:
        x = e.loc[mid]
        to, cc = ", ".join(a for a in x.to if a)[:200], ", ".join(a for a in x.cc if a)[:200]
        emails.append({"key": mid, "text": f"From: {x['from']}\nTo: {to}\n" + (f"Cc: {cc}\n" if cc else "") +
                       f"Subject: {x.subject}\n\n{x.body.strip()[:1800]}"})
    json.dump(emails, open(T.DATA / "enron_locked.json", "w"), ensure_ascii=False)
    users = {}
    for shard in FILES:
        if shard.startswith("wildchat"):
            d = pd.read_parquet(T.DATA / shard, columns=["conversation_hash", "conversation", "language"])
            for h, conv, lang in zip(d.conversation_hash, d.conversation, d.language):
                if lang == "English":
                    users.setdefault(h, [u["content"] for u in conv if u["role"] == "user"])
    convs = []
    for name in ("pii", "ordinary"):
        for c in m["chats"]["sets"][name]:
            turns = []
            for i, values, sha in c["turns"]:
                original, text, spans, pos = users[c["hash"]][i], "", [], 0
                for mk, v in zip(MARKER.finditer(original), values):
                    text += original[pos:mk.start()]
                    spans.append([len(text), len(text) + len(v), CHAT_GROUP.get(mk.group(1), "outside")])
                    text += v
                    pos = mk.end()
                text += original[pos:]
                if hashlib.sha1(text.encode()).hexdigest()[:12] != sha:
                    raise ValueError(f"conversation {c['hash']} turn {i} isn't as it was judged")
                turns.append({"text": text, "spans": spans})
            convs.append({"set": name, "id": c["hash"], "turns": turns})
    json.dump(convs, open(T.DATA / "chats_locked.json", "w"))
    print(f"{len(emails)} emails, {len(convs)} conversations", file=sys.stderr)


# -- the sets -------------------------------------------------------------------------------------------------------

def documents(relabelled=False):
    """{id: (text, spans)} the locked documents (``L03#7`` is the eighth of family L03), or the 30 the second
    labellers marked."""
    if relabelled:
        return {d["id"]: W.unmark(d["text"]) for d in map(json.loads, open(DOCS / "relabel.jsonl")) if d}
    return {f"{p.stem}#{j}": W.unmark(json.loads(line)["text"])
            for p in sorted(DOCS.glob("L*.jsonl")) for j, line in enumerate(x for x in open(p) if x.strip())}


def verdicts(name, key="verdicts"):
    """{text key: [(start, end, verdict)]}: a judged set's verdicts, or the second reviewer's (``key="second"``)."""
    out = {}
    for k, spans, vs in manifest()[name][key]:
        out.setdefault(k, []).extend((s, e, v) for (s, e), v in zip(spans, vs))
    return out


def group(v):
    if v.startswith("personal:"):
        return W.GROUP.get(v.split(":", 1)[1].strip(), "ID number")
    return JUDGED_GROUP.get(v)


def smallest(spans):
    """Every private-person span that holds a smaller one made "outside": a run that took in a name and its email is
    scored as the two details in it."""
    personal = [(a, b) for a, b, g in spans if g not in ("ordinary", "outside")]
    return [(s, e, "outside") if g not in ("ordinary", "outside") and
            any((a, b) != (s, e) and s <= a and b <= e for a, b in personal) else (s, e, g) for s, e, g in spans]


def judged_rows(name, texts, small=False):
    """(key, text, [(start, end, group)]) each text of a judged set."""
    v = verdicts(name)
    out = []
    for k, text in texts:
        sp = [(s, e, group(x)) for s, e, x in v.get(k, []) if group(x)]
        out.append((k, text, smallest(sp) if small else sp))
    return out


def sets():
    docs = documents()
    tweets = [(str(i), t) for i, t in enumerate(W.social("locked"))]
    emails = [(e["key"], e["text"]) for e in json.load(open(T.DATA / "enron_locked.json"))]
    again = documents(True)
    return {"documents (new agents)": [(k, t, sp) for k, (t, sp) in zip(docs, W.rows(docs.values()))],
            "forms (synthetic, seed 96)": [(None, t, sp) for t, sp in W.rows(formgen.docs(300, 96))],
            "tweets and posts": judged_rows("tweets", tweets),
            "Enron emails": judged_rows("enron", emails),
            "tweets and posts (smallest spans)": judged_rows("tweets", tweets, True),
            "Enron emails (smallest spans)": judged_rows("enron", emails, True),
            "30 documents, first labeller": [(k, t, sp) for k, (t, sp) in zip(again, W.rows(docs[k] for k in again))],
            "30 documents, second labeller": [(k, t, sp) for k, (t, sp) in zip(again, W.rows(again.values()))]}


# -- scoring --------------------------------------------------------------------------------------------------------

def runs(text, out):
    """(start, end) runs of words hidden in ``out``."""
    ws = T.bench.words(text)
    _, kept = T.bench.redacted_mask(text, out)
    spans, run = set(), None
    for j, (_, a, b) in enumerate(ws):
        if not kept[j]:
            run = (run[0], b) if run else (a, b)
        elif run:
            spans.add(run)
            run = None
    return spans | ({run} if run else set())


def counts(text, spans, out):
    """[found, details, other words hidden, other words] for one text, counted as tagger.score counts them."""
    ws = T.bench.words(text)
    _, kept = T.bench.redacted_mask(text, out)
    personal = [False] * len(ws)
    hit = tot = 0
    for s, e, g in spans:
        idx = [j for j, (_, a, b) in enumerate(ws) if a < e and b > s]
        if g != "ordinary":
            for j in idx:
                personal[j] = True
        idx = [j for j in idx if ws[j][0].lower() not in T.bench.TITLES]
        if idx and g not in ("ordinary", "outside"):
            tot += 1
            hit += all(not kept[j] for j in idx)
    other = [j for j, (w, _, _) in enumerate(ws) if not personal[j] and w.lower() not in T.bench.TITLES]
    return [hit, tot, sum(not kept[j] for j in other), len(other)]


def chat_counts(conv, outs, here, small=False):
    """[found, details, ordinary words hidden, public words hidden, other words] for one conversation; ``here`` is
    {turn: [(start, end, verdict)]}."""
    hit = tot = ordinary = public = words = 0
    for ti, (t, out) in enumerate(zip(conv["turns"], outs)):
        text, v = t["text"], here.get(ti, [])
        ws = T.bench.words(text)
        _, kept = T.bench.redacted_mask(text, out)
        personal = set()
        known = [(s, e) for s, e, g in t["spans"] if g != "outside"]
        judged_ = [(s, e) for s, e, x in v if x.startswith("personal:")]
        if small:   # a judged span holding a smaller private detail is set aside; the details inside it are scored
            held = {(s, e) for s, e in judged_ if any((a, b) != (s, e) and s <= a and b <= e for a, b in known + judged_)}
            judged_ = [x for x in judged_ if x not in held]
            v = [x for x in v if x[:2] not in held] + [(s, e, "unsure") for s, e in held]
        for s, e in known + judged_:
            idx = {j for j, (w, a, b) in enumerate(ws) if a < e and b > s and w.lower() not in T.bench.TITLES}
            personal |= idx
            if idx:
                tot += 1
                hit += all(not kept[j] for j in idx)
        within = lambda ok: {j for s, e, x in v if ok(x) for j, (_, a, b) in enumerate(ws) if a < e and b > s}  # noqa: E731
        pub, outside = within(lambda x: x == "public"), within(lambda x: x in ("business", "unsure"))
        for j, (w, _, _) in enumerate(ws):
            if j in personal or j in outside or w.lower() in T.bench.TITLES:
                continue
            words += 1
            if not kept[j]:
                public += j in pub
                ordinary += j not in pub
    return [hit, tot, ordinary, public, words]


def boot(per, pairs, n=2000):
    """95% intervals over units for each system's found and other words hidden, and for the paired differences."""
    import numpy as np
    idx = np.random.default_rng(0).integers(0, len(next(iter(per.values()))), (n, len(next(iter(per.values())))))
    stat = {}
    for name, rows in per.items():
        a = np.array(rows, dtype=float)
        s = a[idx].sum(axis=1)
        over = (s[:, 2] + s[:, 3]) / np.maximum(s[:, 4], 1) if a.shape[1] == 5 else s[:, 2] / np.maximum(s[:, 3], 1)
        stat[name] = (s[:, 0] / np.maximum(s[:, 1], 1), over)
    ci = lambda x: [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]  # noqa: E731
    return {"systems": {k: {"found": ci(f), "over": ci(o)} for k, (f, o) in stat.items()},
            "differences": {f"{a} − {b}": {"found": ci(stat[a][0] - stat[b][0]), "over": ci(stat[a][1] - stat[b][1])}
                            for a, b in pairs if a in stat and b in stat}}


def score(specs):
    ss = sets()
    convs = json.load(open(T.DATA / "chats_locked.json"))
    chat_v = {}
    for k, v in verdicts("chats").items():
        name, ci, ti = k.split("/")
        chat_v.setdefault((name, int(ci)), {})[int(ti)] = v
    keys, seen = [], Counter()
    for c in convs:
        keys.append((c["set"], seen[c["set"]]))
        seen[c["set"]] += 1
    texts = [t for rs in ss.values() for _, t, _ in rs] + [t["text"] for c in convs for t in c["turns"]]
    systems = {"veil": None}
    for spec in specs:
        model, _, th = spec.partition("@")
        systems[model.rstrip("/").split("/")[-1]] = (model, float(th or T.THRESHOLD))
    found = {k: T.spans(m, texts) for k, (m, _) in ((k, v) for k, v in systems.items() if v)}

    cover = {k: verdicts(n) for k, n in (("tweets and posts", "tweets"), ("Enron emails", "enron"))}
    per, unjudged = {}, {}
    for setname, rs in ss.items():
        per[setname] = {}
        for name, v in systems.items():
            outs = {"veil": [Redactor(FINANCE).redact_text(t) for _, t, _ in rs]} if v is None else {
                f"{name} alone": [T.alone(t, found[name][T.key(t)], v[1]) for _, t, _ in rs],
                f"veil + {name}": [T.with_veil(t, found[name][T.key(t)], T.checked, v[1]) for _, t, _ in rs]}
            for sysname, o in outs.items():
                per[setname][sysname] = [counts(t, sp, out) for (_, t, sp), out in zip(rs, o)]
                if setname in cover:   # runs no verdict of any kind covers: counted as other words hidden
                    unjudged.setdefault(setname, {})[sysname] = sum(
                        1 for (k, t, _), out in zip(rs, o) for a, b in runs(t, out)
                        if not any(s < b and e > a for s, e, _ in cover[setname].get(k, [])))
    per["chats"] = {}
    for name, v in systems.items():
        if v is None:
            fns = {"veil": lambda c: (lambda r: [r.redact_text(t["text"]) for t in c["turns"]])(Redactor(GENERIC))}
        else:
            fns = {f"{name} alone": lambda c, s=name, th=v[1]: [T.alone(t["text"], found[s][T.key(t["text"])], th)
                                                                for t in c["turns"]],
                   f"veil + {name}": lambda c, s=name, th=v[1]: (lambda r: [
                       T.with_veil(t["text"], found[s][T.key(t["text"])], T.checked, th, redactor=r)
                       for t in c["turns"]])(Redactor(GENERIC))}
        for sysname, fn in fns.items():
            outs = [fn(c) for c in convs]
            per["chats"][sysname] = [chat_counts(c, o, chat_v.get(k, {})) for c, o, k in zip(convs, outs, keys)]
            per.setdefault("chats (smallest spans)", {})[sysname] = [chat_counts(c, o, chat_v.get(k, {}), True)
                                                                   for c, o, k in zip(convs, outs, keys)]

    last = list(systems)[-1]
    pairs = [(f"{last} alone", "veil"), (f"veil + {last}", "veil")] + \
            [(f"{last} alone", f"{k} alone") for k in list(systems)[1:-1]]
    results = {}
    for setname, p in per.items():
        sums = {k: [sum(c) for c in zip(*rows)] for k, rows in p.items()}
        results[setname] = {"units": len(next(iter(p.values()))), "sums": sums, **boot(p, pairs)}
        print(f"\n{setname} ({results[setname]['units']} {'conversations' if setname.startswith('chats') else 'texts'})")
        for k, s in sums.items():
            ci = results[setname]["systems"][k]
            chat = setname.startswith("chats")
            over = (s[2] + s[3]) / s[4] if chat else s[2] / s[3]
            extra = f"  (ordinary {s[2] / s[4]:.2%}, public {s[3] / s[4]:.2%})" if chat else \
                f", {unjudged[setname][k]} hidden runs no verdict covers" if unjudged.get(setname, {}).get(k) else ""
            print(f"  {k:30} found {s[0] / s[1]:6.1%} [{ci['found'][0]:.1%}, {ci['found'][1]:.1%}]   other words "
                  f"hidden {over:5.2%} [{ci['over'][0]:.2%}, {ci['over'][1]:.2%}]   {s[1]} details{extra}")
        for k, d in results[setname]["differences"].items():
            print(f"    {k:44} found {d['found'][0]:+.1%} to {d['found'][1]:+.1%}   "
                  f"other words hidden {d['over'][0]:+.2%} to {d['over'][1]:+.2%}")
    json.dump(results, open(T.DATA / "locked_results.json", "w"), indent=1)


def agree():
    """The second reviewers against the first, on the same spans: raw agreement and Cohen's kappa over the five
    verdicts and over what scoring uses (a private person's detail or not); and the second labellers' spans against
    the writers' on the 30 documents."""
    def kappa(pairs):
        n = len(pairs)
        po = sum(a == b for a, b in pairs) / n
        cats = {x for p in pairs for x in p}
        pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
        return po, (po - pe) / (1 - pe)
    five = lambda v: "personal" if v.startswith("personal:") else v  # noqa: E731
    for name in ("tweets", "enron", "chats"):
        first = {(k, s, e): v for k, vs in verdicts(name).items() for s, e, v in vs}
        pairs = [(first[(k, s, e)], v) for k, vs in verdicts(name, "second").items() for s, e, v in vs]
        p5, k5 = kappa([(five(a), five(b)) for a, b in pairs])
        p2, k2 = kappa([(five(a) == "personal", five(b) == "personal") for a, b in pairs])
        print(f"{name}: {len(pairs)} spans; the five verdicts agree on {p5:.1%} (kappa {k5:.3f}); private or not "
              f"{p2:.1%} (kappa {k2:.3f}); where they differ: "
              f"{dict(Counter(f'{five(a)} → {five(b)}' for a, b in pairs if five(a) != five(b)).most_common(6))}")
    docs, again = documents(), documents(True)
    n1 = n2 = exact = overlap = same = 0
    a_ = b_ = both = words = 0
    for k, (text, s2) in again.items():
        t1, s1 = docs[k]
        assert t1 == text, k
        n1, n2 = n1 + len(s1), n2 + len(s2)
        exact += len({x[:2] for x in s1} & {x[:2] for x in s2})
        used = set()
        for s, e, lab in s1:
            m = next((y for y in s2 if y[0] < e and s < y[1] and y not in used), None)
            if m:
                used.add(m)
                overlap += 1
                same += W.GROUP[lab] == W.GROUP[m[2]]
        for _, p, q in T.bench.words(text):
            x, y = any(s < q and p < e for s, e, _ in s1), any(s < q and p < e for s, e, _ in s2)
            words, a_, b_, both = words + 1, a_ + x, b_ + y, both + (x and y)
    po = (words - a_ - b_ + 2 * both) / words
    pe = (a_ / words) * (b_ / words) + (1 - a_ / words) * (1 - b_ / words)
    print(f"documents: {n1} spans by the writers, {n2} by the second labellers; {exact} the same exactly, {overlap} "
          f"overlapping, {same} of those of one kind; words in a span or not agree on {po:.1%} (kappa "
          f"{(po - pe) / (1 - pe):.3f})")


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":   # formgen's draws go through Faker data kept in sets
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    cmd, *a = sys.argv[1:]
    {"fetch": fetch, "build": build, "score": lambda: score(a), "agree": agree}[cmd]()
