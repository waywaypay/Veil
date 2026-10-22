"""Round 8: from round 7's model, on real public records labelled by agents (SEC Form 4, Form D, employment and
separation agreements, IRS 990s, CORD receipts; r8_fetch.py, r8/LABEL.md), with round 7's mix replayed so nothing
learned is lost.  A fifth of the public records is held out for dev; 40 more (r8/heldout_40.jsonl) are kept out of
everything, for people to label as a real-document test.

python round8.py build | train <base> <out> <offset> | dev <model>[@th] ..."""
import glob
import json
import os
import random
import sys

import round7 as R7

R, T, TT, S = R7.R, R7.T, R7.TT, R7.S
_round7_sets = R7.dev_sets


def public_docs():
    docs = []
    for p in sorted(glob.glob(f"{S}/r8/label/batch_*_marked.jsonl")):
        for line in open(p):
            if line.strip():
                docs.append(R.unmark(json.loads(line)["text"]))
    return R7.split_docs(docs)


def build():
    from gliner import GLiNER
    split = GLiNER.from_pretrained(f"{S}/ft/r7_3").data_processor.words_splitter
    rng = random.Random(81)
    pub = TT.examples(public_docs()["train"], split)
    replay = json.load(open(f"{T.DATA}/round7_examples_seg3.json"))
    rng.shuffle(replay)
    parts = {"public records (labelled)": pub * 3, "round 7, replayed": replay[:6000]}
    data = []
    for k, e in parts.items():
        for x in e:
            if len(x["tokenized_text"]) > 2048:
                x["tokenized_text"] = x["tokenized_text"][:1024]
                x["ner"] = [s for s in x["ner"] if s[1] < 1024]
        data += e
        print(f"{k}: {len(e)} chunks, {sum(len(x['ner']) for x in e)} labels")
    rng.shuffle(data)
    json.dump(data, open(f"{T.DATA}/round8_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def train(base, out, offset):
    TT.train(base, out, lambda splitter: (json.load(open(f"{T.DATA}/round8_examples.json")) * 2)[int(offset):int(offset) + 4000], 500)


def dev_sets():
    sets = _round7_sets()
    d = public_docs()["dev"]
    if d:
        sets["public records (round 8 dev)"] = R.rows(d)
    return sets


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    R7.dev_sets = dev_sets   # round 7's dev() reads its own dev_sets(): give it round 8's
    cmd, *a = sys.argv[1:]
    {"build": build, "train": lambda: train(*a), "dev": lambda: R7.dev(a)}[cmd]()
