"""Round 9: from round 7's model, on round 8's real public records (agent-labelled, never trained on) and round 9's
targeted documents (r9gen.py: addresses as other countries and scripts write them, one-letter-per-box forms, scanned
copies, names in parts, Japanese, Chinese, Korean and Arabic names, staff numbers in registers), with W-2 layouts and
round 7's mix replayed so nothing learned is lost.  A fifth of each new source is held out for dev (PROTOCOL.md,
"Round 9").

python round9.py build | train <base> <out> <offset> | dev <model>[@th] ..."""
import json
import os
import random
import sys

import r9gen
import round7 as R7
import round8 as R8

R, T, TT, S = R7.R, R7.T, R7.TT, R7.S
_round8_sets = R8.dev_sets


def r9_docs():
    return R7.split_docs(r9gen.docs(3000, 9001))


def build():
    from gliner import GLiNER
    split = GLiNER.from_pretrained(f"{S}/ft/r7_3").data_processor.words_splitter
    rng = random.Random(91)
    replay = json.load(open(f"{T.DATA}/round7_examples_seg3.json"))
    rng.shuffle(replay)
    w2 = TT.examples(R7.shard("trainA", "provA"), split)
    rng.shuffle(w2)
    parts = {"round 9 targeted (r9gen)": TT.examples(r9_docs()["train"], split),
             "public records (round 8, labelled)": TT.examples(R8.public_docs()["train"], split) * 3,
             "W-2 layouts (real IRS form, providers)": w2[:800],
             "round 7, replayed": replay[:6000]}
    data = []
    for k, e in parts.items():
        for x in e:
            if len(x["tokenized_text"]) > 2048:
                x["tokenized_text"] = x["tokenized_text"][:1024]
                x["ner"] = [s for s in x["ner"] if s[1] < 1024]
        data += e
        print(f"{k}: {len(e)} chunks, {sum(len(x['ner']) for x in e)} labels")
    rng.shuffle(data)
    json.dump(data, open(f"{T.DATA}/round9_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def train(base, out, offset):
    TT.train(base, out, lambda splitter: (json.load(open(f"{T.DATA}/round9_examples.json")) * 2)[int(offset):int(offset) + 4000], 500)


def dev_sets():
    sets = _round8_sets()
    d = r9_docs()["dev"]
    if d:
        sets["round 9 targeted (dev)"] = R.rows(d)
    return sets


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    R7.dev_sets = dev_sets   # round 7's dev() reads its own dev_sets(): give it round 9's
    cmd, *a = sys.argv[1:]
    {"build": build, "train": lambda: train(*a), "dev": lambda: R7.dev(a)}[cmd]()
