"""Scores w2parse on digital W-2 PDFs: private values fully hidden / total, and other words hidden by mistake.
python parse_eval.py <seed> <n per source> [verbose]"""
import random, sys, re
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
from faker import Faker
import w2real as W, w2prov as P, w2parse as WP


def truth(words, form, copies):
    """[(label, [occurrences as word-index tuples])] for the private values in the text layer's words."""
    wants = [("ssn", form["ssn"]), ("ein", form["ein"])]
    if form.get("control"):
        wants.append(("control", form["control"]))
    wants += [("first", form["first"]), ("last", form["last"])]
    street, city = form["address"].split("\n")
    wants += [("street", street), ("city", city)]
    # a household employer's own name and address are private too; the parser does not handle that case (the model does)
    wants.append(("stid", form["stid1"]))
    texts = [w[4].lower().strip(",") for w in words]
    vals = []
    for key, v in wants:
        toks = [x.strip(",") for x in v.lower().split()]
        occ = [tuple(range(i, i + len(toks))) for i in range(len(texts) - len(toks) + 1) if texts[i:i + len(toks)] == toks]
        vals.append((key, occ))
    return vals


def main(seed, n, verbose=False):
    rng = random.Random(seed)
    us = Faker("en_US"); us.seed_instance(seed)
    fakes = {l: Faker(l) for l in set(W.LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(seed + i + 1)
    tot = {"IRS form": [0, 0, 0, 0, 0], "provider layout": [0, 0, 0, 0, 0]}
    miss = {}
    for src in tot:
        for _ in range(n):
            form = W.one_form(rng, fakes[rng.choice(W.LOCALES)], us)
            if src == "IRS form":
                pdf, copies = W.fill(rng.choice(W.PAGES), [form]), 1
            else:
                form = P.fix_case(rng, form)
                form["year"] = rng.choice(["2023", "2024", "2025"])
                pdf, copies = P.provider_pdf(rng, form)
            words, hide = WP.parse(pdf)
            vals = truth(words, form, copies)
            priv = set()
            t = tot[src]
            for key, occ in vals:
                if not occ:
                    t[4] += 1          # not found in the text layer: cannot be scored
                    continue
                for o in occ:
                    priv.update(o)
                    t[1] += 1
                    ok = all(i in hide for i in o)
                    t[0] += ok
                    if not ok:
                        miss.setdefault(src, []).append((key, [words[i][4] for i in o]))
            other = [i for i in range(len(words)) if i not in priv]
            t[2] += sum(i in hide for i in other)
            t[3] += len(other)
    for src, t in tot.items():
        print(f"{src:16} values hidden {t[0]}/{t[1]} = {t[0] / max(1, t[1]):.2%}   other words hidden {t[2]}/{t[3]} = {t[2] / max(1, t[3]):.2%}   unscorable values {t[4]}")
    if verbose:
        for src, m in miss.items():
            print(src, len(m))
            for x in m[:30]:
                print("   ", x)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), len(sys.argv) > 3)
