"""Round 10: from round 7's published model, on conversations (PROTOCOL.md, "Round 10"): chatgen.py's generated
conversations (source A), agent-written chats with the two new labels (source B, r10/chats/), and round 7's mix and
round 2's judged WildChat turns replayed (source C), at 45%, 15% and 40% of the chunks.  Half of A's and B's
conversations are trained as one text and half a message at a time (source D).  A fifth of A's and of B's
conversations is held out for dev.

The tagger gains two labels, "password or access code" and "api key", both veil's ID placeholder.  Dev asks every
model, round 7's too, for all the labels, with their spans cached apart from earlier rounds' (cache_r10/), so round 7's
bound and round 10's candidates are measured alike.  PII-TRACE's dev half is printed after the dev slices as a
readout, outside the slices the choice is made on; its test half is never read here.

B's files are JSONL, one conversation a line: {"family": ..., "locale": ..., "messages": ["...", ...]}, each message
marked as RULES.md says (⟦label|text⟧), with the two new labels.

python round10.py build | train <base> <out> <offset> | dev <model>[@th] ... | mark <model dir> ...

At most four segments, offsets 0, 4000, 8000 and 12000, the first from round 7's published model (ft/r7_3).  The chosen
model's folder, and its ONNX export's, is marked before it's published: veil.tagged asks a model for the new labels only
when its gliner_config.json lists them under "veil_labels"."""
import glob
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # pii_trace.py, one level up

import chatgen  # noqa: E402
import round7 as R7  # noqa: E402
import round9 as R9  # noqa: E402

R, T, TT, S = R7.R, R7.T, R7.TT, R7.S
_round9_sets = R9.dev_sets

NEW = {"password or access code": "ID", "api key": "ID"}   # the tagger's new labels -> veil's kind (decided: ID)
SHARES = {"A": 0.45, "B": 0.15, "C": 0.40}
REPLAY = 6000         # chunks of round 7's mix
B_REPEAT = 3          # B's training conversations at most three times over, as round 8's public records
CHATS = f"{S}/r10/chats"


def know_new_labels():
    """Ask for the new labels at dev, score them as their own group, and keep their spans in a cache of their own."""
    T.LABELS.update(NEW)
    T.CACHE = T.DATA / "cache_r10"
    for m in list(sys.modules.values()):
        g = getattr(m, "GROUP", None)
        if isinstance(g, dict) and "customer id" in g:   # the docgen label -> scoring group maps (unmark, rows)
            for lab in NEW:
                g.setdefault(lab, "secret")


def a_convs():
    """Source A: 4,000 of chatgen.py's conversations, split by conversation."""
    return R7.split_docs(chatgen.conversations(4000, 10001), key=lambda c: c[0][0])


def b_convs():
    """Source B: the agent-written chats, each a list of (text, spans) messages, split by conversation."""
    convs = []
    for p in sorted(glob.glob(f"{CHATS}/*.jsonl")):
        for line in open(p):
            if line.strip():
                convs.append([R.unmark(m) for m in json.loads(line)["messages"]])
    return R7.split_docs([c for c in convs if c], key=lambda c: c[0][0])


def sizes(n_c):
    """Chunks to take from each source, so the replay (all of it, ``n_c`` chunks) is C's share."""
    total = n_c / SHARES["C"]
    return {k: round(total * v) for k, v in SHARES.items()}


def build():
    from gliner import GLiNER
    know_new_labels()
    split = GLiNER.from_pretrained(f"{S}/ft/r7_3").data_processor.words_splitter
    rng = random.Random(101)
    b = b_convs()
    if not b["train"]:
        sys.exit(f"no agent-written chats in {CHATS}: source B is part of round 10's mix")
    replay = json.load(open(f"{T.DATA}/round7_examples_seg3.json"))
    rng.shuffle(replay)
    c = replay[:REPLAY] + TT.examples(TT.chat_docs("train"), split)
    want = sizes(len(c))
    a = TT.examples(chatgen.docs(a_convs()["train"], 10002), split)
    b_ex = TT.examples(chatgen.docs(b["train"], 10003), split)
    parts = {"A: generated conversations (chatgen)": (a, want["A"]),
             "B: agent-written chats": (b_ex * B_REPEAT, want["B"]),
             "C: round 7's mix and round 2's chats, replayed": (c, want["C"])}
    data = []
    for k, (e, n) in parts.items():
        for x in e:
            if len(x["tokenized_text"]) > 2048:
                x["tokenized_text"] = x["tokenized_text"][:1024]
                x["ner"] = [s for s in x["ner"] if s[1] < 1024]
        rng.shuffle(e)
        data += e[:n]
        short = f" (wanted {n})" if len(e) < n else ""
        print(f"{k}: {min(len(e), n)} of {len(e)} chunks{short}, {sum(len(x['ner']) for x in e[:n])} labels")
    rng.shuffle(data)
    json.dump(data, open(f"{T.DATA}/round10_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def train(base, out, offset):
    TT.train(base, out, lambda splitter: (json.load(open(f"{T.DATA}/round10_examples.json")) * 2)[int(offset):int(offset) + 4000], 500)


def dev_sets():
    sets = _round9_sets()
    for name, convs in (("conversations (chatgen, dev)", a_convs()["dev"]), ("chats (round 10 agents, dev)", b_convs()["dev"])):
        if convs:
            sets[name] = R.rows(chatgen.docs(convs, 10004))
    return sets


def pii_trace_rows():
    """PII-TRACE's dev half without dates and URLs: one row a user message, and one a conversation joined."""
    import pii_trace as P
    convs = [c for c in P.load() if P.half(c["id"]) == "dev"]
    keep = lambda lab: lab not in ("private_date", "private_url")  # noqa: E731
    one = [(u, [(s, e, lab) for t2, s, e, lab, _ in c["gold"] if t2 == t and keep(lab)])
           for c in convs for t, u in enumerate(c["users"])]
    whole = []
    for c in convs:
        starts, pos = [], 0
        for u in c["users"]:
            starts.append(pos)
            pos += len(u) + len(P.SEP)
        whole.append((P.SEP.join(c["users"]), [(starts[t] + s, starts[t] + e, lab) for t, s, e, lab, _ in c["gold"] if keep(lab)]))
    return {"one message": one, "whole conversation": whole}


def pii_trace_readout(models):
    """Found / other words hidden on PII-TRACE's dev half, the model alone; reported, not chosen on."""
    sets = pii_trace_rows()
    texts = [t for rs in sets.values() for t, _ in rs]
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        cells = {k: T.score(rs, [t for t, _ in rs], [T.alone(t, found[T.key(t)], th) for t, _ in rs]) for k, rs in sets.items()}
        print(f"{spec.split('/')[-1]}  PII-TRACE dev (readout, not chosen on):  " +
              "  ".join(f"{k} {r['found']:.1%}/{r['over']:.2%}" for k, r in cells.items()), flush=True)


def mark(dirs):
    """List the new labels under "veil_labels" in each model folder's gliner_config.json."""
    for d in dirs:
        path = Path(d) / "gliner_config.json"
        config = json.loads(path.read_text())
        config["veil_labels"] = sorted(set(config.get("veil_labels", [])) | set(NEW))
        path.write_text(json.dumps(config, indent=2) + "\n")
        print(f"{path}: veil_labels {config['veil_labels']}")


def dev(models):
    know_new_labels()
    R7.dev(models)
    pii_trace_readout(models)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    R7.dev_sets = dev_sets   # round 7's dev() reads its own dev_sets(): give it round 10's
    cmd, *a = sys.argv[1:]
    {"build": build, "train": lambda: train(*a), "dev": lambda: dev(a), "mark": lambda: mark(a)}[cmd]()
