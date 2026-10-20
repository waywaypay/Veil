import sys, random, importlib
sys.path.insert(0,"."); sys.path.insert(0,"w2html/agent")
from collections import Counter
from faker import Faker
import w2real as W, parse_eval as E, html_eval as H, templates as TP
WP = importlib.import_module(sys.argv[1])
rng = random.Random(81); us = Faker("en_US"); us.seed_instance(81)
fakes = {l: Faker(l) for l in set(W.LOCALES)}
for i, f in enumerate(fakes.values()): f.seed_instance(81 + i + 1)
tot = Counter(); miss = {}
over = Counter(); ow = Counter()
for ti, fn in enumerate(TP.TEMPLATES):
    for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 4):
        form = W.one_form(rng, fakes[rng.choice(W.LOCALES)], us); form["year"] = "2025"
        if rng.random() < .5: form["control"] = ""
        words, hide = WP.parse(H.render(fn(form)))
        vals = E.truth(words, form, 1)
        priv = {i for k, occ in vals for o in occ for i in o}
        for k, occ in vals:
            for o in occ:
                tot[ti] += 1
                if not all(i in hide for i in o): miss.setdefault(ti, Counter())[k] += 1
        over[ti] += sum(i in hide for i in range(len(words)) if i not in priv); ow[ti] += len([i for i in range(len(words)) if i not in priv])
for ti in range(len(TP.TEMPLATES)):
    print(ti, f"{tot[ti]-sum(miss.get(ti,{}).values())}/{tot[ti]}", dict(miss.get(ti, {})), f"over {over[ti]/ow[ti]:.1%}")
a=sum(tot.values()); m=sum(sum(c.values()) for c in miss.values()); print("TOTAL", a-m, "/", a, f"{(a-m)/a:.1%}", f"over {sum(over.values())/sum(ow.values()):.2%}")
