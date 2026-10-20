"""Frozen parser (w2parse_frozen) and parser+model on W-2s printed from independently written HTML templates (w2html/agent),
rendered to PDF with Chromium.  python html_eval.py <seed> <forms per template> <model>@<th> ..."""
import importlib.util, os, random, subprocess, sys, tempfile
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/w2html/" + os.environ.get("TDIR", "agent"))
from faker import Faker
import round4 as R
import w2real as W, parse_eval as E
import importlib
WP = importlib.import_module(os.environ.get("PARSER", "w2parse_frozen"))
import combo_parse as CP
import templates as TP
T = R.T
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
CP.WP = WP


def render(html):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/p.html", "w").write(html)
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={d}/p.pdf", f"file://{d}/p.html"],
                       capture_output=True, timeout=90)
        return open(f"{d}/p.pdf", "rb").read()


def main(seed, per, specs):
    rng = random.Random(seed)
    us = Faker("en_US"); us.seed_instance(seed)
    fakes = {l: Faker(l) for l in set(W.LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(seed + i + 1)
    docs = []
    for ti, fn in enumerate(TP.TEMPLATES):
        for _ in range(per):
            form = W.one_form(rng, fakes[rng.choice(W.LOCALES)], us)
            form["year"] = rng.choice(["2023", "2024", "2025"])
            if rng.random() < 0.5:
                form["control"] = ""
            pdf = render(fn(form))
            words, hide = WP.parse(pdf)
            text, pos = CP.layer_text(words)
            vals = E.truth(words, form, 1)
            docs.append((ti, words, hide, text, pos, vals))
    print(len(docs), "documents")
    results = {}
    for spec, mode in [(None, "parser")] + [(x, m) for x in specs for m in ("model", "parser+model")]:
        if spec:
            model, _, th = spec.partition("@")
            th = float(th)
            found = T.spans(model, [d[3] for d in docs])
        per_t = {}
        for ti, words, hide, text, pos, vals in docs:
            priv = {i for k, occ in vals for o in occ for i in o}
            if spec:
                sp = T.merged([x for x in found[T.key(text)] if x[3] >= th], text)
                mh = {i for i, (a, b) in pos.items() if any(a < e and b > s for s, e, _, _ in sp)}
                h = mh if mode == "model" else hide | mh
            else:
                h = hide
            r = per_t.setdefault(ti, [0, 0, 0, 0, 0])
            for k, occ in vals:
                if not occ:
                    r[4] += 1
                for o in occ:
                    r[1] += 1
                    r[0] += all(i in h for i in o)
            other = [i for i in range(len(words)) if i not in priv]
            r[2] += sum(i in h for i in other)
            r[3] += len(other)
        name = "parser" if not spec else mode + " " + os.path.basename(spec)
        tot = [sum(r[i] for r in per_t.values()) for i in range(5)]
        print(f"{name:28} values hidden {tot[0]}/{tot[1]} = {tot[0] / tot[1]:.2%}   other words hidden {tot[2] / tot[3]:.2%}   unscorable {tot[4]}")
        print("   by template:", " ".join(f"{ti}:{r[0]}/{r[1]}" for ti, r in per_t.items()))


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:])
