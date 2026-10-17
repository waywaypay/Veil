"""Fine-tuning a span tagger for veil, on CPU, in 500-step segments (GLiNER's trainer grows in memory over a long run,
so each segment is its own process, starting from the last one's model).  How the models in benchmarks/model.md were
made:

  round 1 (Gretel)   knowledgator/gliner-pii-edge-v1.0, 1,000 steps over Gretel finance's English training split
                     (offset "all"), then segments at offsets 8000, 12000 and 16000
  round 2 (mixed)    from round 1's model: segments at offsets 0 and 4000 of the mixed examples (Gretel chunks round
                     1 didn't take in order, Nemotron-PII's training split, and judged WildChat turns), then a
                     last one weighted to the chats ("heavy")

Choices are made on dev sets: 300 Gretel training documents never trained on, 200 of Nemotron's, and the chat dev
set (chats.py).  Needs gliner, torch, accelerate, onnxruntime and onnx.

python train_tagger.py fetch
python train_tagger.py gretel <base> <out dir> <offset|all> [steps]
python train_tagger.py mixed <base> <out dir> <offset> [heavy]
python train_tagger.py dev <model>[@threshold] ...
python train_tagger.py export <model dir> <out dir>      model.onnx and model_f16.onnx (16-bit weights)"""

import ast
import json
import os
import random
import re
import sys
import time

import chats
import gretel as bench
import pandas as pd
import tagger as T
import tagger_sets

from veil import FINANCE, GENERIC, Redactor

FILES = {"gretel_train.parquet": f"{tagger_sets.HF}/gretelai/synthetic_pii_finance_multilingual/parquet/default/train/0.parquet",
         "nemo_train.parquet": f"{tagger_sets.HF}/nvidia/Nemotron-PII/parquet/default/train/0.parquet"}
# each dataset's labels -> the label names the tagger is asked for (tagger.LABELS)
GRETEL = {"name": "name", "first_name": "name", "last_name": "name", "street_address": "street address",
          "email": "email address", "phone_number": "phone number", "ssn": "ssn", "passport_number": "passport number",
          "driver_license_number": "driver license number", "iban": "iban", "bban": "account number",
          "swift_bic_code": "swift code", "credit_card_number": "credit card number",
          "bank_routing_number": "account number", "date_of_birth": "date of birth", "customer_id": "customer id",
          "employee_id": "employee id"}
NEMO = {"first_name": "name", "last_name": "name", "street_address": "street address", "email": "email address",
        "phone_number": "phone number", "fax_number": "phone number", "ssn": "ssn", "account_number": "account number",
        "credit_debit_card": "credit card number", "bank_routing_number": "account number", "swift_bic": "swift code",
        "date_of_birth": "date of birth", "customer_id": "customer id", "employee_id": "employee id",
        "user_name": "username", "certificate_license_number": "driver license number", "tax_id": "tax id",
        "national_id": "tax id", "passport_number": "passport number"}
PLACE = {"city", "postcode", "state", "county"}   # kept only as part of a street address, as veil hides them
CHAT = {"name": "name", "email": "email address", "phone / fax": "phone number",
        "bank / card / account": "credit card number"}
JUDGED = {"personal:name": "name", "personal:email": "email address", "personal:phone": "phone number",
          "personal:address": "street address", "personal:username": "username", "personal:id": "customer id",
          "personal:dob": "date of birth"}


# -- the data -------------------------------------------------------------------------------------------------------

def gretel_split():
    """Gretel finance's English training documents, in a fixed order: the first 300 are the dev set."""
    d = pd.read_parquet(T.DATA / "gretel_train.parquet")
    d = d[d.language == "English"]
    raw = list(zip(d.generated_text, d.pii_spans))
    order = list(range(len(raw)))
    random.Random(0).shuffle(order)
    return [raw[i] for i in order[:300]], [raw[i] for i in order[300:]]


def gretel_docs(raw):
    """(text, [(start, end, label)]): the benchmark's noise spans (a role taken for a name ...) aren't labelled."""
    out = []
    for t, js in raw:
        spans = [(s["start"], s["end"], GRETEL[s["label"]]) for s in json.loads(js) if s["label"] in GRETEL
                 and not bench.is_noise(t[s["start"]:s["end"]], s["label"], t[s["end"]:s["end"] + 60])]
        out.append((t, spans))
    return out


def nemo_split():
    d = pd.read_parquet(T.DATA / "nemo_train.parquet", columns=["text", "spans"])
    rows = [(t, ast.literal_eval(s)) for t, s in zip(d.text, d.spans)]
    random.Random(1).shuffle(rows)
    return rows[:200], rows[200:]   # dev, train


def nemo_docs(rows):
    """Nemotron's details as the tagger's labels: a first and last name joined, a town, state or postcode only as
    part of the street address before it."""
    out = []
    for text, spans in rows:
        joined = []
        for s, e, lab in sorted((s["start"], s["end"], NEMO.get(s["label"], s["label"] if s["label"] in PLACE else None))
                                for s in spans):
            if not lab or (joined and s < joined[-1][1]):
                continue
            if joined:
                ps, pe, plab = joined[-1]
                gap = text[pe:s]
                if lab == plab == "name" and re.fullmatch(r"[ \t]+", gap) or \
                        plab == "street address" and lab in PLACE | {"street address"} and re.fullmatch(r"[\s,]{0,3}", gap):
                    joined[-1] = (ps, e, plab)
                    continue
            joined.append((s, e, lab))
        out.append((text, [x for x in joined if x[2] not in PLACE]))
    return out


def chat_docs(split):
    """The chat pool's turns: what was put back, and what was judged a private person's detail, are labelled; public
    and fictional names and ordinary words are left unlabelled, so the tagger learns not to mark them."""
    convs = json.load(open(T.DATA / f"chats_{split}.json"))
    extra = {}
    for k, v in json.load(open(chats.MANIFEST))["train_verdicts"].items():
        sp, ci, ti, s, e = k.split("/")
        if sp == split and v in JUDGED:
            extra.setdefault((int(ci), int(ti)), []).append((int(s), int(e), JUDGED[v]))
    return [(t["text"], sorted([(s, e, CHAT[g]) for s, e, g in t["spans"] if g in CHAT] + extra.get((ci, ti), [])))
            for ci, c in enumerate(convs) for ti, t in enumerate(c["turns"])]


def examples(docs, splitter):
    """GLiNER's training format, one example a chunk (chunked as at inference):
    {"tokenized_text": [...], "ner": [[first token, last token, label], ...]}"""
    out = []
    for text, spans in docs:
        for off, piece in T.chunks(text):
            toks = list(splitter(piece))
            ner = []
            for s, e, lab in spans:
                idx = [i for i, (_, a, b) in enumerate(toks) if a < e - off and b > s - off]
                if idx:
                    ner.append([idx[0], idx[-1], lab])
            out.append({"tokenized_text": [t for t, _, _ in toks], "ner": ner})
    return out


def mixed_examples(splitter, heavy=False):
    path = T.DATA / ("mix_examples_heavy.json" if heavy else "mix_examples.json")
    if path.exists():
        return json.load(open(path))
    chat = examples(chat_docs("train"), splitter)
    if heavy:   # each chat chunk twice, with 2,000 of the others
        seen = {json.dumps(x, sort_keys=True) for x in chat}
        others = [x for x in mixed_examples(splitter) if json.dumps(x, sort_keys=True) not in seen]
        data = chat * 2 + others[:2000]
        random.Random(6).shuffle(data)
    else:
        gretel = examples(gretel_docs(gretel_split()[1]), splitter)
        random.Random(1).shuffle(gretel)
        nemo = examples(nemo_docs(nemo_split()[1][:3000]), splitter)[:4000]
        data = gretel[20000:24000] + nemo + chat
        random.Random(5).shuffle(data)
    json.dump(data, open(path, "w"))
    return data


# -- training -------------------------------------------------------------------------------------------------------

def train(base, out, data, steps):
    import torch
    from gliner import GLiNER
    torch.set_num_threads(os.cpu_count())
    model = GLiNER.from_pretrained(base)
    data = data(model.data_processor.words_splitter)
    args = model.create_training_args(output_dir=out, learning_rate=1e-5, others_lr=2e-5, weight_decay=0.01,
                                      focal_loss_alpha=0.75, focal_loss_gamma=2, per_device_train_batch_size=8,
                                      max_steps=steps, save_steps=10 ** 9, logging_steps=25, use_cpu=True,
                                      dataloader_num_workers=0, warmup_ratio=0.1, bf16=True)
    t0 = time.perf_counter()
    model.train_model(train_dataset=data, eval_dataset=None, training_args=args)
    model.save_pretrained(out)
    print(f"{steps} steps on {len(data)} examples in {time.perf_counter() - t0:.0f} s, saved to {out}", file=sys.stderr)


def gretel(base, out, offset, steps=500):
    def data(splitter):
        ex = examples(gretel_docs(gretel_split()[1]), splitter)
        random.Random(1).shuffle(ex)
        return ex if offset == "all" else ex[int(offset):int(offset) + steps * 8]
    train(base, out, data, steps)


def mixed(base, out, offset, heavy=False):
    train(base, out, lambda splitter: (mixed_examples(splitter, heavy) * 2)[int(offset):int(offset) + 4000], 500)


# -- choosing -------------------------------------------------------------------------------------------------------

def chat_dev(found, th):
    """The tagger alone, and veil with its names, on the chat dev set.  A hidden word no verdict covers counts as a
    mistake, so a model that marks new things is scored pessimistically."""
    convs = json.load(open(T.DATA / "chats_dev.json"))
    verdicts = {}
    for k, v in json.load(open(chats.MANIFEST))["train_verdicts"].items():
        sp, ci, ti, s, e = k.split("/")
        if sp == "dev":
            verdicts.setdefault((int(ci), int(ti)), []).append((int(s), int(e), v))
    res = {}
    for name in ("alone", "veil + names"):
        hit = tot = words = 0
        fp = {"ordinary": 0, "public": 0}
        for ci, c in enumerate(convs):
            r = Redactor(GENERIC)
            for ti, t in enumerate(c["turns"]):
                text, here = t["text"], verdicts.get((ci, ti), [])
                sp = found[T.key(text)]
                out = T.alone(text, sp, th) if name == "alone" else T.with_veil(text, sp, T.names_only, th, redactor=r)
                ws = T.bench.words(text)
                _, kept = T.bench.redacted_mask(text, out)
                personal = set()
                for s, e in [(s, e) for s, e, g in t["spans"] if g != "outside"] + \
                            [(s, e) for s, e, v in here if v.startswith("personal")]:
                    idx = {j for j, (w, a, b) in enumerate(ws) if a < e and b > s and w.lower() not in T.bench.TITLES}
                    personal |= idx
                    if idx:
                        tot += 1
                        hit += all(not kept[j] for j in idx)
                public = {j for s, e, v in here if v == "public" for j, (_, a, b) in enumerate(ws) if a < e and b > s}
                for j, (w, _, _) in enumerate(ws):
                    if j not in personal and w.lower() not in T.bench.TITLES:
                        words += 1
                        if not kept[j]:
                            fp["public" if j in public else "ordinary"] += 1
        res[name] = {"found": hit / tot, "ordinary": fp["ordinary"] / words, "public": fp["public"] / words}
    return res


def dev(models):
    g = tagger_sets.gretel_rows(gretel_split()[0])
    n = [(t, [(s["start"], s["end"], tagger_sets._group(s["label"])) for s in spans]) for t, spans in nemo_split()[0]]
    convs = json.load(open(T.DATA / "chats_dev.json"))
    texts = [t for t, _ in g] + [t for t, _ in n] + [t["text"] for c in convs for t in c["turns"]]
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        cells = []
        for rows in (g, n):
            xs = [t for t, _ in rows]
            r = T.score(rows, xs, [T.alone(x, found[T.key(x)], th) for x in xs])
            cells.append(f"{r['found']:.1%} / {r['over']:.2%}")
        c = chat_dev(found, th)
        print(f"{spec}\n  alone: Gretel {cells[0]}  Nemotron {cells[1]}  chats {c['alone']['found']:.1%} / "
              f"{c['alone']['ordinary']:.2%} + {c['alone']['public']:.2%} public\n"
              f"  veil + names, chats: {c['veil + names']['found']:.1%} / {c['veil + names']['ordinary']:.2%} + "
              f"{c['veil + names']['public']:.2%} public", flush=True)
    print("(found / other words hidden; Gretel's and Nemotron's veil alone:",
          *(f"{T.score(rows, [t for t, _ in rows], [Redactor(FINANCE).redact_text(t) for t, _ in rows])['found']:.1%}"
            for rows in (g, n)), ")")


def export(model_dir, out):
    """model.onnx, and model_f16.onnx: the same with its weights stored in 16 bits, cast back to 32 as ONNX Runtime
    loads it, so half the file and the same arithmetic (the same spans as full precision, and as fast).  ONNX
    Runtime's usual int8 (quantize_dynamic, which quantizes activations too) moved this model's scores, many of them
    just over the threshold, enough to lose a fifth of what it finds."""
    import numpy as np
    import onnx
    from gliner import GLiNER
    from onnx import TensorProto, helper, numpy_helper
    GLiNER.from_pretrained(model_dir).export_to_onnx(out)
    m = onnx.load(f"{out}/model.onnx")
    casts = []
    for init in list(m.graph.initializer):
        if init.data_type == TensorProto.FLOAT and int(np.prod(init.dims)) >= 1024:
            half = numpy_helper.from_array(numpy_helper.to_array(init).astype(np.float16), init.name + "__f16")
            casts.append(helper.make_node("Cast", [half.name], [init.name], to=TensorProto.FLOAT,
                                          name=init.name + "__cast"))
            m.graph.initializer.remove(init)
            m.graph.initializer.append(half)
    for node in reversed(casts):
        m.graph.node.insert(0, node)
    onnx.save(m, f"{out}/model_f16.onnx")
    print(f"{out}/model.onnx, {out}/model_f16.onnx")


if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    {"fetch": lambda: tagger_sets.fetch(FILES),
     "gretel": lambda: gretel(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else (1000 if a[2] == "all" else 500)),
     "mixed": lambda: mixed(a[0], a[1], a[2], a[3:] == ["heavy"]),
     "dev": lambda: dev(a),
     "export": lambda: export(a[0], a[1])}[cmd]()
