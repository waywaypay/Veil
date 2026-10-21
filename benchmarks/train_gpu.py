"""The data-or-model control: GLiNER PII large and edge, each trained once from its public base on the same
examples with the same recipe, on a GPU.  If large trained this way matches veil-tagger-edge, the gain is the data;
if it beats it, a bigger model is worth having.

    python benchmarks/train_gpu.py build EXAMPLES... --out train.jsonl.gz    the examples, deduplicated
    python benchmarks/train_gpu.py train BASE train.jsonl.gz OUT [--steps N]
    python benchmarks/train_gpu.py segments BASE round8.jsonl.gz OUT [--n 4]    round 8's four 500-step segments

BASE: knowledgator/gliner-pii-large-v1.0 or knowledgator/gliner-pii-edge-v1.0.  The recipe is fixed in advance and
is the one the tagger's rounds used: lr 1e-5 (others 2e-5), batch 8, focal loss (alpha 0.75, gamma 2), warmup 0.1,
weight decay 0.01, one pass over the examples unless --steps says otherwise.  No test documents are among the
examples; score the result with veilbench.py on the locked test, once."""
import argparse
import gzip
import hashlib
import json
import random
import sys
import time


def build(paths, out):
    seen, rows = set(), []
    for path in paths:
        for x in json.load(open(path)):
            key = hashlib.sha1(json.dumps([x["tokenized_text"], x["ner"]]).encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                rows.append({"tokenized_text": x["tokenized_text"], "ner": x["ner"]})
    random.Random(0).shuffle(rows)
    with gzip.open(out, "wt") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    print(f"{len(rows)} examples from {len(paths)} files to {out}", file=sys.stderr)


def train(base, data, out, steps=None, rows=None):
    import torch
    from gliner import GLiNER
    rows = rows if rows is not None else [json.loads(line) for line in gzip.open(data, "rt")]
    steps = steps or len(rows) // 8
    gpu = torch.cuda.is_available()
    model = GLiNER.from_pretrained(base)
    if gpu:
        model = model.to("cuda")
    args = model.create_training_args(output_dir=out, learning_rate=1e-5, others_lr=2e-5, weight_decay=0.01,
                                      focal_loss_alpha=0.75, focal_loss_gamma=2, per_device_train_batch_size=8,
                                      max_steps=steps, save_steps=max(steps // 4, 100), save_total_limit=1,
                                      logging_steps=50, use_cpu=not gpu, dataloader_num_workers=2 if gpu else 0,
                                      warmup_ratio=0.1, bf16=True, seed=0)
    t0 = time.perf_counter()
    model.train_model(train_dataset=rows, eval_dataset=None, training_args=args)
    model.save_pretrained(out)
    print(f"{base}: {steps} steps on {len(rows)} examples in {time.perf_counter() - t0:.0f} s, saved to {out}",
          file=sys.stderr)


def segments(base, data, out, n=4, steps=500):
    """The CPU rounds' way, on a GPU: ``n`` segments of ``steps`` steps on the next ``steps * 8`` examples of the data
    taken twice over in order, each from the last one's weights; the data is not shuffled or deduplicated (a source's
    repeats are its weighting).  Saves OUT_1 ... OUT_n."""
    rows = [json.loads(line) for line in gzip.open(data, "rt")] * 2
    for i in range(n):
        piece = rows[i * steps * 8:(i + 1) * steps * 8]
        train(base if i == 0 else f"{out}_{i}", None, f"{out}_{i + 1}", steps, rows=piece)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("examples", nargs="+")
    b.add_argument("--out", default="train.jsonl.gz")
    t = sub.add_parser("train")
    t.add_argument("base")
    t.add_argument("data")
    t.add_argument("out")
    t.add_argument("--steps", type=int)
    c = sub.add_parser("segments")
    c.add_argument("base")
    c.add_argument("data")
    c.add_argument("out")
    c.add_argument("--n", type=int, default=4)
    a = p.parse_args()
    if a.cmd == "segments":
        segments(a.base, a.data, a.out, a.n)
    elif a.cmd == "build":
        build(a.examples, a.out)
    else:
        train(a.base, a.data, a.out, a.steps)


if __name__ == "__main__":
    main()
