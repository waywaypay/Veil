"""Parser + model on digital W-2 PDFs (same forms as parse_eval, seed 71): the model reads the text layer (words in reading
order, as lines), its spans are mapped back to words, and a word is hidden if the parser or the model hid it.
python combo_parse.py <seed> <n per source> <model>@<th> ..."""
import os, random, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
from faker import Faker
import round4 as R
import w2real as W, w2prov as P, w2parse as WP, parse_eval as E
T = R.T


def layer_text(words):
    """Text of the layer in reading order and each word's (start, end) in it."""
    ch = sorted(WP.chunks(words), key=lambda c: ((c[1] + c[3]) / 2, c[0]))
    text, pos, last_y = "", {}, None
    for c in ch:
        y = (c[1] + c[3]) / 2
        if last_y is not None:
            text += "\n" if abs(y - last_y) > 0.45 * (c[3] - c[1]) else "  "
        last_y = y
        for k, i in enumerate(c[5]):
            if k:
                text += " "
            pos[i] = (len(text), len(text) + len(words[i][4]))
            text += words[i][4]
    return text, pos


def main(seed, n, specs):
    rng = random.Random(seed)
    us = Faker("en_US"); us.seed_instance(seed)
    fakes = {l: Faker(l) for l in set(W.LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(seed + i + 1)
    docs = []
    for src in ("IRS form", "provider layout"):
        for _ in range(n):
            form = W.one_form(rng, fakes[rng.choice(W.LOCALES)], us)
            if src == "IRS form":
                pdf, copies = W.fill(rng.choice(W.PAGES), [form]), 1
            else:
                form = P.fix_case(rng, form)
                form["year"] = rng.choice(["2023", "2024", "2025"])
                pdf, copies = P.provider_pdf(rng, form)
            words, hide = WP.parse(pdf)
            text, pos = layer_text(words)
            docs.append((src, words, hide, text, pos, E.truth(words, form, copies)))
    for spec in specs:
        model, _, th = spec.partition("@")
        th = float(th)
        found = T.spans(model, [d[3] for d in docs])
        print(os.path.basename(model) + f"@{th:g}")
        for src in ("IRS form", "provider layout"):
            res = {k: [0, 0, 0, 0] for k in ("model", "parser", "parser+model")}
            for s, words, hide, text, pos, vals in docs:
                if s != src:
                    continue
                sp = T.merged([x for x in found[T.key(text)] if x[3] >= th], text)
                mh = {i for i, (a, b) in pos.items() if any(a < e and b > st for st, e, _, _ in sp)}
                priv = {i for k, occ in vals for o in occ for i in o}
                for name, h in (("model", mh), ("parser", hide), ("parser+model", hide | mh)):
                    for k, occ in vals:
                        for o in occ:
                            res[name][1] += 1
                            res[name][0] += all(i in h for i in o)
                    other = [i for i in range(len(words)) if i not in priv]
                    res[name][2] += sum(i in h for i in other)
                    res[name][3] += len(other)
            for name, (a, b, c, d) in res.items():
                print(f"  {src:16} {name:13} values hidden {a}/{b} = {a / b:.2%}   other words hidden {c / d:.2%}")


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:])
