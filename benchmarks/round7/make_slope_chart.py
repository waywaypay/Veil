"""Writes slope.html: dev scores by training segment, from slope.json (made from the dev logs)."""
import html
import json

D = json.load(open("/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/slope.json"))
X = ["Round 6\n(start)", "Segment 1", "Segment 2", "Segment 3", "Segment 4"]
CHUNKS = ["0", "4,000", "8,000", "12,000", "16,000"]      # chunks trained this round, cumulative
W, H, L, R, T, B = 380, 250, 46, 78, 14, 52


def panel(pid, title, ylabel, series, lo, hi, step, note=""):
    xs = [L + i * (W - L - R) / (len(X) - 1) for i in range(len(X))]
    y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))   # noqa: E731
    out = [f'<figure class="panel"><figcaption><b>{html.escape(title)}</b><span>{html.escape(note)}</span></figcaption>',
           f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">']
    v = lo
    while v <= hi + 1e-9:
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="tick" x="{L - 6}" y="{y(v) + 3:.1f}" text-anchor="end">{v:g}</text>')
        v += step
    for i, x in enumerate(xs):
        for j, ln in enumerate(X[i].split("\n")):
            out.append(f'<text class="tick" x="{x:.1f}" y="{H - B + 14 + j * 11}" text-anchor="middle">{html.escape(ln)}</text>')
    out.append(f'<text class="axis" x="{L}" y="{T - 3}" >{html.escape(ylabel)}</text>')
    for k, (name, color, vals, dash) in enumerate(series):
        pts = [(xs[i], y(v)) for i, v in enumerate(vals) if v is not None]
        d = " ".join(("M" if i == 0 else "L") + f"{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="var({color})" stroke-width="2" {"stroke-dasharray=" + chr(34) + "5 3" + chr(34) if dash else ""}/>')
        for i, v in enumerate(vals):
            if v is None:
                continue
            out.append(f'<circle class="pt" cx="{xs[i]:.1f}" cy="{y(v):.1f}" r="4" fill="var({color})" stroke="var(--surface)" stroke-width="2" '
                       f'data-tip="{html.escape(name)} · {html.escape(X[i].replace(chr(10), " "))} · {v:.2f}%"/>')
        lx, ly = pts[-1]
        out.append(f'<text class="dlabel" x="{lx + 8:.1f}" y="{ly + 4:.1f}">{html.escape(name)}</text>'
                   f'<text class="dval" x="{lx + 8:.1f}" y="{ly + 16:.1f}">{vals[[v is not None for v in vals].index(True) if False else len(vals) - 1 - [v is not None for v in vals][::-1].index(True)]:.1f}%</text>')
    out.append("</svg></figure>")
    return "".join(out)


p, w2 = D["pts"], D["w2"]
five = lambda v: v   # noqa: E731
found = [("0.40 threshold", "--s1", five([x[0] if x else None for x in p["0.4"]]), False),
         ("0.35 threshold", "--s2", five([x[0] if x else None for x in p["0.35"]]), False)]
over = [("0.40 threshold", "--s1", five([x[1] if x else None for x in p["0.4"]]), False),
        ("0.35 threshold", "--s2", five([x[1] if x else None for x in p["0.35"]]), False)]
wp = [("generated", "--s3", five(w2["gen"]), False), ("hand-written", "--s4", five(w2["agent"]), False)]
tp = [("generated", "--s3", five(w2["tgen"]), False), ("hand-written", "--s4", five(w2["tagent"]), False)]

tables = ["<table><thead><tr><th>Run</th><th>Chunks trained</th><th>Found 0.40</th><th>Hidden 0.40</th><th>Found 0.35</th><th>Hidden 0.35</th>"
          "<th>W-2 generated</th><th>W-2 hand-written</th><th>Tax generated</th><th>Tax hand-written</th></tr></thead><tbody>"]
f = lambda v: "–" if v is None else f"{v:.1f}"   # noqa: E731
for i in range(5):
    a, b = p["0.4"][i], p["0.35"][i]
    tables.append(f"<tr><td>{X[i].replace(chr(10), ' ')}</td><td>{CHUNKS[i]}</td><td>{f(a[0])}</td><td>{f(a[1])}</td>"
                  f"<td>{f(b[0] if b else None)}</td><td>{f(b[1] if b else None)}</td><td>{f(w2['gen'][i])}</td><td>{f(w2['agent'][i])}</td>"
                  f"<td>{f(w2['tgen'][i])}</td><td>{f(w2['tagent'][i])}</td></tr>")
tables.append("</tbody></table>")

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dev scores by training segment</title>
<style>
:root{{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e6e5e1;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#6250d6}}
@media (prefers-color-scheme:dark){{:root{{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#34332f;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#9085e9}}}}
body{{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:880px;margin:0 auto;padding:20px 16px 40px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--ink2);margin:0 0 16px;max-width:70ch}}
.grid4{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px 22px}}
.panel{{margin:0}} figcaption{{display:flex;flex-direction:column;margin-bottom:2px}} figcaption span{{color:var(--ink2);font-size:12px}}
svg{{width:100%;height:auto;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:1}} .tick{{fill:var(--ink2);font-size:10px}} .axis{{fill:var(--ink2);font-size:10px}}
.pending{{stroke:var(--grid);stroke-width:1.5;stroke-dasharray:4 3}}
.dlabel{{fill:var(--ink);font-size:11px;font-weight:600}} .dval{{fill:var(--ink2);font-size:10px}}
.pt{{cursor:pointer}} .pt:hover{{r:6}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 10px;font-size:12px;color:var(--ink2)}} .legend i{{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle;border-radius:2px}}
#tip{{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:4px 8px;border-radius:4px;font-size:12px;opacity:0}}
details{{margin-top:22px}} summary{{cursor:pointer;color:var(--ink2)}} table{{border-collapse:collapse;font-size:12px;margin-top:8px;width:100%}} th,td{{padding:4px 6px;border-bottom:1px solid var(--grid);text-align:right}} th:first-child,td:first-child{{text-align:left}}
.foot{{color:var(--ink2);font-size:12px;margin-top:14px;max-width:80ch}}
</style></head><body><main>
<h1>Is more data still helping? Dev scores by training segment</h1>
<p class="sub">Each segment is 500 training steps (4,000 chunks) on a growing mix, starting from the one before. Top row: the mean over the same 23 dev slices for every run, so the points are comparable. Bottom row: the W-2 and tax-form dev slices, which joined the mix at segment 3.</p>
<div class="legend"><span><i style="background:var(--s1)"></i>0.40 threshold</span><span><i style="background:var(--s2)"></i>0.35 threshold</span>
<span><i style="background:var(--s3)"></i>generated by my script (bottom row)</span><span><i style="background:var(--s4)"></i>hand-written by agents (bottom row)</span></div>
<div class="grid4">
{panel("a", "Private details found", "% of details hidden (higher is better)", found, 92, 96, 1, "mean of 23 dev slices")}
{panel("b", "Harmless words hidden by mistake", "% of other words hidden (lower is better)", over, 2, 3.5, 0.5, "mean of the same 23 slices")}
{panel("c", "W-2s, found", "% found (higher is better)", wp, 80, 100, 5, "small dev sets: about 10 hand-written documents")}
{panel("d", "Other US tax forms, found", "% found (higher is better)", tp, 80, 100, 5, "same split as the W-2s")}
</div>
<p class="foot"><b>Reading it.</b> Top row: from the round 6 model to segment 3, finds rose from 92.9% to 94.0% at the 0.40 threshold, but all of that came in segment 1 (94.5%); finds then drifted down about half a point while false hides kept falling, from 3.1% to 2.3%. So more of the same mix is trading finds for fewer false hides, not adding to both. Bottom row (0.40 threshold): segment 3 added generated W-2 and tax data, and the generated slices jumped to 98.5% and 99.5% while the hand-written ones stayed near 85%. The model learned my templates, not W-2s in general: variety, not volume, is what is missing. Segment 4 (real IRS-form and payroll-provider layouts, trained on W-2-focused data) dropped the top-row mean by about 1.5 points because the model forgot some general ability; it lifted the two W-2 layouts it was trained on (IRS form 94.3% to 98.9%, provider layouts 93.1% to 96.6% at the 0.35 threshold) but not the hand-written W-2s (88.1% to 86.4%), so the gap to real documents is still open.</p>
<details><summary>Table view</summary>{"".join(tables)}</details>
</main><div id="tip"></div>
<script>
const tip=document.getElementById('tip');
document.querySelectorAll('.pt').forEach(p=>{{p.addEventListener('mousemove',e=>{{tip.textContent=p.dataset.tip;tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';tip.style.opacity=1}});p.addEventListener('mouseleave',()=>tip.style.opacity=0)}});
</script></body></html>"""
open("/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/slope.html", "w").write(page)
print(len(page), "bytes")
