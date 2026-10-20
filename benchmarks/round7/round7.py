"""Round 7: from round 6's model, on much more varied data (PROTOCOL.md, "Round 7 on"): agent-written documents aimed
at round 6's misses (docgen/round7, waves of 40), filled-in forms of many kinds, synthetic email headers and rosters
(listgen), misread and all-caps copies of training documents (augment), TweetNER7's tweets with their persons judged
and private handles written in, WildChat-4.8M chats with their hidden runs judged, real Enron emails labelled by
agents, fresh forms and tax snippets, and round 6's mix replayed.  A fifth of each new source is held out for dev.

python round7.py build | train <base> <out> <offset> | dev <model>[@th] ..."""
import glob
import hashlib
import json
import os
import random
import sys

import augment
import formgen
import listgen
import lockedtest as LT
import round4 as R
import round6 as R6
import taxgen
import usgen
import w2gen

T, TT = R.T, R.TT
S = R.S


def split_docs(docs, key=None):
    """{"train", "dev"} by a hash of the text (or of ``key(doc)``): a fifth to dev."""
    out = {"train": [], "dev": []}
    for d in docs:
        k = key(d) if key else d[0]
        out["dev" if int(hashlib.sha1(k.encode()).hexdigest()[:8], 16) % 5 == 0 else "train"].append(d)
    return out


def round7_docs():
    docs = []
    for p in sorted(glob.glob(f"{S}/docgen/round7/w*.jsonl")):
        for line in open(p):
            if line.strip():
                docs.append(R.unmark(json.loads(line)["text"]))
    return split_docs(docs)


def enron_docs():
    docs = []
    for p in sorted(glob.glob(f"{S}/r7_enron/batch_*_marked.jsonl")):
        for line in open(p):
            if line.strip():
                docs.append(R.unmark(json.loads(line)["text"]))
    return split_docs(docs)


def w2_docs():
    """Agent-written W-2s for training (w2train/), a fifth held out for dev; the locked W-2 test is in w2test/."""
    docs = []
    for p in sorted(glob.glob(f"{S}/w2train/*.jsonl")):
        for line in open(p):
            if line.strip():
                docs.append(R.unmark(json.loads(line)["text"]))
    return split_docs(docs)


def shard(*names):
    """[(text, [(start, end, label)])] from w2real_shards/<name>.json (w2real.py and w2prov.py output)."""
    out = []
    for n in names:
        path = f"{S}/w2real_shards/{n}.json"
        if os.path.exists(path):
            out += [(t, [tuple(x) for x in sp]) for t, sp in json.load(open(path))]
    return out


def tax_docs():
    """Agent-written K-1s, W-9s, W-4s, 1099s, 1040s, 1095s and 1098s for training (taxtrain/), a fifth for dev; the
    locked test is in taxtest/."""
    docs = []
    for p in sorted(glob.glob(f"{S}/taxtrain/*.jsonl")):
        for line in open(p):
            if line.strip():
                docs.append(R.unmark(json.loads(line)["text"]))
    return split_docs(docs)


def tweet_docs():
    p = f"{S}/dl7/tweetner_docs.json"
    return json.load(open(p)) if os.path.exists(p) else {"train": [], "dev": []}


def chat_docs():
    p = f"{S}/dl7/r7_chat_docs.json"
    return json.load(open(p)) if os.path.exists(p) else {"train": [], "dev": []}


def augmented(rng):
    """Misread and all-caps copies of the agent-written training documents of rounds 4, 6 and 7, one copy each."""
    base = R.docgen()["train"] + R6.round6_docs()["train"] + round7_docs()["train"]
    out = []
    for d in base:
        out.append(augment.ocr(d, rng) if rng.random() < 0.6 else augment.upper(d))
    return out


def build():
    from gliner import GLiNER
    split = GLiNER.from_pretrained(f"{S}/ft/r6_3").data_processor.words_splitter
    rng = random.Random(31)
    ex = lambda docs: TT.examples(docs, split)  # noqa: E731
    parts = {
        "documents (round 7 agents)": ex(round7_docs()["train"]) * 2,
        "documents (rounds 4 and 6 agents)": ex(R.docgen()["train"] + R6.round6_docs()["train"]),
        "augmented copies (misread, caps)": ex(augmented(random.Random(32))),
        "lists (synthetic)": ex(listgen.docs(600, 71)),
        "tweets (TweetNER7, judged)": ex([(t, s) for t, s in tweet_docs()["train"]]),
        "chats (WildChat-4.8M, judged)": ex([(t, s) for t, s in chat_docs()["train"]]),
        "Enron emails (labelled)": ex(enron_docs()["train"]) * 2,
        "forms (synthetic, fresh)": ex(formgen.docs(1500, 23)),
        "tax forms (synthetic, fresh)": ex(taxgen.docs(600, 14)),
        "W-2s (synthetic)": ex(w2gen.docs(1500, 41)),
        "W-2s (agents)": ex(w2_docs()["train"]) * 3,
        "US tax forms (synthetic)": ex(usgen.docs(2100, 43)),
        "US tax forms (agents)": ex(tax_docs()["train"]) * 3,
        "round 6, replayed": json.load(open(f"{T.DATA}/round6_examples.json")),
    }
    sizes = {"documents (round 7 agents)": 9000, "documents (rounds 4 and 6 agents)": 2500,
             "augmented copies (misread, caps)": 2500, "lists (synthetic)": 1500, "tweets (TweetNER7, judged)": 5000,
             "chats (WildChat-4.8M, judged)": 1500, "Enron emails (labelled)": 1500, "forms (synthetic, fresh)": 1500,
             "tax forms (synthetic, fresh)": 600, "W-2s (synthetic)": 1500, "W-2s (agents)": 600,
             "US tax forms (synthetic)": 2100, "US tax forms (agents)": 600,
             "round 6, replayed": 4000}
    data = []
    for k, e in parts.items():
        for x in e:   # an example over 2,048 tokens is cut to 1,024 (train_wider.py's examples())
            if len(x["tokenized_text"]) > 2048:
                x["tokenized_text"] = x["tokenized_text"][:1024]
                x["ner"] = [s for s in x["ner"] if s[1] < 1024]
        rng.shuffle(e)
        data += e[:sizes[k]]
        print(f"{k}: {min(len(e), sizes[k])} of {len(e)} chunks, {sum(len(x['ner']) for x in e[:sizes[k]])} labels")
    rng.shuffle(data)
    json.dump(data, open(f"{T.DATA}/round7_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def build4():
    """Segment 4: W-2-focused, on top of segment 3.  About 70% W-2s (the real IRS form through real extractors and OCR,
    payroll-provider layouts, agent-written, generated), 10% other US tax forms, 20% replay of the segment 3 mix."""
    from gliner import GLiNER
    split = GLiNER.from_pretrained(f"{S}/ft/r7_3").data_processor.words_splitter
    rng = random.Random(81)
    ex = lambda docs: TT.examples(docs, split)  # noqa: E731
    main = json.load(open(f"{T.DATA}/round7_examples_seg3.json"))
    parts = {"W-2s (real IRS form)": (ex(shard("trainA", "trainB")), 1300),
             "W-2s (provider layouts)": (ex(shard("provA", "provB")), 900),
             "W-2s (agents)": (ex(w2_docs()["train"]) * 2, 400),
             "W-2s (synthetic)": (ex(w2gen.docs(400, 82)), 200),
             "US tax forms (synthetic)": (ex(usgen.docs(400, 83)), 200),
             "US tax forms (agents)": (ex(tax_docs()["train"]) * 2, 200),
             "replay of the segment 3 mix": (main, 800)}
    data = []
    for k, (e, n) in parts.items():
        for x in e:
            if len(x["tokenized_text"]) > 2048:
                x["tokenized_text"] = x["tokenized_text"][:1024]
                x["ner"] = [s for s in x["ner"] if s[1] < 1024]
        rng.shuffle(e)
        data += e[:n]
        print(f"{k}: {min(len(e), n)} of {len(e)} chunks, {sum(len(x['ner']) for x in e[:n])} labels")
    rng.shuffle(data)
    json.dump(data, open(f"{T.DATA}/round7_seg4_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def train4(base, out):
    TT.train(base, out, lambda splitter: json.load(open(f"{T.DATA}/round7_seg4_examples.json"))[:4000], 500)


def train(base, out, offset):
    TT.train(base, out, lambda splitter: (json.load(open(f"{T.DATA}/round7_examples.json")) * 2)[int(offset):int(offset) + 4000],
             500)


def dev_sets():
    """Round 6's dev slices, the first locked test's five sets (development data now), and a held-out fifth of each
    new source.  Judged sets: a hidden run no verdict covers counts against the model."""
    sets = R.dev_sets()
    sets["documents (round 6 agents)"] = R.rows(R6.round6_docs()["dev"])
    docs = []
    for i in range(1, 11):
        docs += [R.unmark(json.loads(l)["text"]) for l in open(f"{LT.L}/L{i:02d}.jsonl") if l.strip()]
    sets["documents (locked 1)"] = R.rows(docs)
    sets["forms (locked 1, seed 96)"] = R.rows(formgen.docs(300, 96))
    sets["tweets (locked 1)"] = [(t, sp) for _, t, sp in LT.judged_rows("tweets")]
    sets["Enron (locked 1)"] = [(t, sp) for _, t, sp in LT.judged_rows("enron")]
    sets["documents (round 7 agents)"] = R.rows(round7_docs()["dev"])
    sets["W-2s (synthetic, seed 42)"] = R.rows(w2gen.docs(200, 42))
    if w2_docs()["dev"]:
        sets["W-2s (agents)"] = R.rows(w2_docs()["dev"])
    if shard("dev"):
        sets["W-2s (real IRS form, seed 53)"] = R.rows(shard("dev"))
    if shard("provdev"):
        sets["W-2s (provider layouts, seed 63)"] = R.rows(shard("provdev"))
    sets["US tax forms (synthetic, seed 44)"] = R.rows(usgen.docs(280, 44))
    if tax_docs()["dev"]:
        sets["US tax forms (agents)"] = R.rows(tax_docs()["dev"])
    sets["lists (synthetic)"] = listgen.docs(120, 72)
    sets["lists (synthetic)"] = [(t, [(s, e, R.GROUP[l]) for s, e, l in sp]) for t, sp in sets["lists (synthetic)"]]
    for name, d in (("tweets (TweetNER7)", tweet_docs()), ("chats (WildChat-4.8M)", chat_docs()), ("Enron (labelled)", enron_docs())):
        if d["dev"]:
            sets[name] = R.rows(d["dev"])
    return {k: rs for k, rs in sets.items() if rs}   # a source not made yet has no slice


def locked_chats(found, th):
    """Found and ordinary / public words hidden on the first locked test's chats, the model alone."""
    convs = [(sn, ci, c) for sn in ("pii", "ordinary") for ci, c in enumerate(json.load(open(f"{LT.L}/chats_{sn}_locked.json")))]
    cv = {}
    for (k, s, e), v in LT.judged("chats").items():
        sn, ci, ti = k.split("/")
        cv.setdefault((sn, int(ci)), {}).setdefault(int(ti), []).append((s, e, v))
    tot = [0] * 5
    for sn, ci, c in convs:
        outs = [T.alone(t["text"], found[T.key(t["text"])], th) for t in c["turns"]]
        for i, x in enumerate(LT.chat_counts(c, outs, cv.get((sn, ci), {}))):
            tot[i] += x
    return {"found": tot[0] / tot[1], "ordinary": tot[2] / tot[4], "public": tot[3] / tot[4]}


def dev(models):
    from veil import FINANCE, Redactor
    sets = dev_sets()
    convs = json.load(open(f"{T.DATA}/chats_dev.json"))
    lchats = [t["text"] for sn in ("pii", "ordinary") for c in json.load(open(f"{LT.L}/chats_{sn}_locked.json")) for t in c["turns"]]
    texts = [t for rs in sets.values() for t, _ in rs] + [t["text"] for c in convs for t in c["turns"]] + lchats
    base = {k: T.score(rs, [t for t, _ in rs], [Redactor(FINANCE).redact_text(t) for t, _ in rs]) for k, rs in sets.items()}
    print("veil:  " + "  ".join(f"{k} {r['found']:.1%}/{r['over']:.2%}" for k, r in base.items()), flush=True)
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        cells = {k: T.score(rs, [t for t, _ in rs], [T.alone(t, found[T.key(t)], th) for t, _ in rs]) for k, rs in sets.items()}
        c = TT.chat_dev(found, th)
        lc = locked_chats(found, th)
        print(f"{spec.split('/')[-1]}:  " + "  ".join(f"{k} {r['found']:.1%}/{r['over']:.2%}" for k, r in cells.items()) +
              f"  chats {c['alone']['found']:.1%}/{c['alone']['ordinary']:.2%}+{c['alone']['public']:.2%}"
              f"  chats (locked 1) {lc['found']:.1%}/{lc['ordinary']:.2%}+{lc['public']:.2%}", flush=True)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":   # formgen's draws go through Faker data kept in sets
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    cmd, *a = sys.argv[1:]
    {"build": build, "train": lambda: train(*a), "dev": lambda: dev(a), "build4": build4,
     "train4": lambda: train4(*a)}[cmd]()
