"""Writes breakdown.html from breakdown.json: one overall score, then every dev slice (format) and every type of data."""
import json

S = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad"
data = json.load(open(f"{S}/breakdown.json"))
TYPES = ["name", "address", "email", "phone", "SSN", "tax / national ID", "passport", "driver licence", "credit card",
         "account number", "IBAN", "SWIFT", "date of birth", "customer ID", "employee ID", "username", "other"]
FAMILIES = [
    ("Agent-written documents", ["documents (agents)", "documents (round 6 agents)", "documents (round 7 agents)", "documents (locked 1)"]),
    ("Forms and tax forms", ["forms (synthetic)", "forms (locked 1, seed 96)", "tax forms", "US tax forms (synthetic, seed 44)", "US tax forms (agents)",
                             "W-2s (synthetic, seed 42)", "W-2s (agents)", "W-2s (real IRS form, seed 53)", "W-2s (provider layouts, seed 63)"]),
    ("Emails and chats", ["Enron (locked 1)", "Enron (labelled)", "chats (WildChat-4.8M)"]),
    ("Tweets and posts", ["tweets and posts", "tweets (locked 1)", "tweets (TweetNER7)"]),
    ("Receipts and résumés", ["receipts", "résumés"]),
    ("Public benchmarks", ["Gretel", "Gretel en-v1", "Gretel, other languages", "Nemotron", "TAB"]),
]
out = {}
for model, slices in data.items():
    m = {}
    for name, r in slices.items():
        m[name] = {"found": r["found"], "over": r["over"], "details": r["details"], "by": r["by"]}
    out[model] = m
payload = json.dumps({"models": out, "families": FAMILIES, "types": TYPES})

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scores by format and type of data</title>
<style>
:root{color-scheme:light;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e6e5e1;--s1:#2a78d6;--s2:#eb6834;--r0:#e8f1fb;--r1:#17508f;--na:#efeeea}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#34332f;--s1:#3987e5;--s2:#d95926;--r0:#23262b;--r1:#7fb2f0;--na:#262523}}
body{margin:0;background:var(--surface);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
main{max-width:960px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:30px 0 4px} .sub{color:var(--ink2);margin:0 0 14px;max-width:72ch;font-size:13px}
.bar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:10px 0 14px;font-size:13px}
select{font:inherit;background:var(--surface);color:var(--ink);border:1px solid var(--grid);border-radius:6px;padding:4px 8px}
.hero{display:flex;gap:28px;flex-wrap:wrap;margin:6px 0 4px} .hero div{min-width:150px} .big{font-size:34px;font-weight:650;line-height:1.1} .cap{color:var(--ink2);font-size:12px}
svg{width:100%;height:auto;overflow:visible;display:block} .grid{stroke:var(--grid)} .tick{fill:var(--ink2);font-size:10.5px} .lab{fill:var(--ink);font-size:11.5px} .fam{fill:var(--ink2);font-size:11px;font-weight:650;letter-spacing:.02em}
.tgt{stroke:var(--ink2);stroke-dasharray:3 3} .cellt{font-size:10.5px;pointer-events:none}
.legend{display:flex;gap:18px;font-size:12px;color:var(--ink2);margin:0 0 8px} .legend i{display:inline-block;width:12px;height:8px;margin-right:6px;border-radius:2px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:4px 8px;border-radius:4px;font-size:12px;opacity:0;max-width:300px}
rect.hit:hover{opacity:.85} .foot{color:var(--ink2);font-size:12px;margin-top:22px;max-width:80ch} details{margin-top:18px} summary{cursor:pointer;color:var(--ink2)}
table{border-collapse:collapse;font-size:12px;margin-top:8px;width:100%} th,td{padding:3px 6px;border-bottom:1px solid var(--grid);text-align:right} th:first-child,td:first-child{text-align:left}
</style></head><body><main>
<h1>How the model scores, by format and by type of data</h1>
<p class="sub">The small model alone (no rules), on every dev set. “Found” is the share of private details it hides; “other words hidden” is the share of harmless words it hides by mistake. Dev sets, not the locked tests.</p>
<div class="bar"><label>Model <select id="model"></select></label><span class="cap" id="nsl"></span></div>
<div class="hero"><div><div class="big" id="h1">–</div><div class="cap">found, average over formats</div></div>
<div><div class="big" id="h2">–</div><div class="cap">other words hidden, average</div></div>
<div><div class="big" id="h3">–</div><div class="cap">found, over every detail pooled</div></div>
<div><div class="big" id="h4">–</div><div class="cap">formats at or above 99% found</div></div></div>

<h2>By format</h2>
<p class="sub">One row per dev set. Left: details found (dashed line is the 99% target). Right: other words hidden by mistake (the target is under 1%).</p>
<div class="legend"><span><i style="background:var(--s1)"></i>found (%)</span><span><i style="background:var(--s2)"></i>other words hidden (%)</span></div>
<svg id="fmt"></svg>

<h2>By type of data</h2>
<p class="sub">Details found, pooled over all formats, for every type of data. The number on the right is how many such details the dev sets hold.</p>
<svg id="typ"></svg>

<h2>Every format by every type of data</h2>
<p class="sub">Found rate for each pairing. Darker is better; grey means fewer than 10 such details, too few to judge. Hover a cell for its counts.</p>
<svg id="heat"></svg>

<details><summary>Table view</summary><div id="tbl"></div></details>
<p class="foot">Each type is scored on its own, across every dev set that labels it; the public benchmarks' own labels are mapped to the same types (for example Gretel's ssn to SSN, bank_routing_number to account number). “Address” includes street, city and postcode lines. “Other” is Gretel en-v1's non-name details, which that benchmark does not type. The generated lists set is left out: its text differs on every run, so it can't be compared across models.</p>
</main><div id="tip"></div>
<script>
const D=__DATA__;
const sel=document.getElementById('model'),tip=document.getElementById('tip');
Object.keys(D.models).forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;sel.appendChild(o)});
sel.onchange=draw; matchMedia('(prefers-color-scheme:dark)').onchange=draw;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const hex=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
function ramp(v){const a=hex(css('--r0')),b=hex(css('--r1'));const t=Math.max(0,Math.min(1,(v-.5)/.5));const c=a.map((x,i)=>Math.round(x+(b[i]-x)*t));return c}
function ink(c){const L=(0.299*c[0]+0.587*c[1]+0.114*c[2]);return L>150?'#0b0b0b':'#f7f6f2'}
const NS='http://www.w3.org/2000/svg';
function el(p,t,a,txt){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(txt!=null)e.textContent=txt;p.appendChild(e);return e}
function tipOn(e,s){e.addEventListener('mousemove',ev=>{tip.textContent=s;tip.style.left=ev.clientX+12+'px';tip.style.top=ev.clientY+12+'px';tip.style.opacity=1});e.addEventListener('mouseleave',()=>tip.style.opacity=0)}
function draw(){
 const m=D.models[sel.value],names=[];D.families.forEach(f=>f[1].forEach(n=>{if(m[n])names.push([f[0],n])}));
 const sl=names.map(x=>m[x[1]]);
 const meanF=sl.reduce((s,r)=>s+r.found,0)/sl.length,meanO=sl.reduce((s,r)=>s+r.over,0)/sl.length;
 let h=0,t=0;sl.forEach(r=>{for(const k in r.by){h+=r.by[k][0];t+=r.by[k][1]}});
 const n99=sl.filter(r=>r.found>=.99).length;
 document.getElementById('h1').textContent=(meanF*100).toFixed(1)+'%';document.getElementById('h2').textContent=(meanO*100).toFixed(2)+'%';
 document.getElementById('h3').textContent=(h/t*100).toFixed(1)+'%';document.getElementById('h4').textContent=n99+' of '+sl.length;
 document.getElementById('nsl').textContent=sl.length+' dev sets, '+t.toLocaleString()+' details';
 // by format
 const svg=document.getElementById('fmt');svg.innerHTML='';
 const rh=19,L=220,W=900,pw=300,x0=L,x1=L+pw+70,pw2=200;let y=10,last='';
 const rows=[];names.forEach(([f,n])=>{if(f!==last){rows.push(['fam',f]);last=f}rows.push(['row',n])});
 const H=rows.length*rh+40;svg.setAttribute('viewBox','0 0 '+W+' '+H);
 const fx=v=>x0+pw*Math.max(0,(v*100-50)/50),ox=v=>x1+pw2*Math.min(1,v*100/8);
 [50,60,70,80,90,100].forEach(v=>{el(svg,'line',{class:'grid',x1:fx(v/100),x2:fx(v/100),y1:6,y2:H-24});el(svg,'text',{class:'tick',x:fx(v/100),y:H-10,'text-anchor':'middle'},v)});
 [0,2,4,6,8].forEach(v=>{el(svg,'line',{class:'grid',x1:ox(v/100),x2:ox(v/100),y1:6,y2:H-24});el(svg,'text',{class:'tick',x:ox(v/100),y:H-10,'text-anchor':'middle'},v)});
 el(svg,'line',{class:'tgt',x1:fx(.99),x2:fx(.99),y1:6,y2:H-24});el(svg,'line',{class:'tgt',x1:ox(.01),x2:ox(.01),y1:6,y2:H-24});
 rows.forEach(([k,v])=>{
  if(k==='fam'){y+=4;el(svg,'text',{class:'fam',x:0,y:y+11},v.toUpperCase());y+=rh-4;return}
  const r=m[v];el(svg,'text',{class:'lab',x:L-8,y:y+12,'text-anchor':'end'},v);
  const a=el(svg,'rect',{class:'hit',x:x0,y:y+2,width:Math.max(1,fx(r.found)-x0),height:11,rx:2,fill:css('--s1')});
  el(svg,'text',{class:'tick',x:fx(r.found)+4,y:y+12},(r.found*100).toFixed(1));
  const b=el(svg,'rect',{class:'hit',x:x1,y:y+2,width:Math.max(1,ox(r.over)-x1),height:11,rx:2,fill:css('--s2')});
  el(svg,'text',{class:'tick',x:ox(r.over)+4,y:y+12},(r.over*100).toFixed(2));
  [a,b].forEach(e=>tipOn(e,v+': found '+(r.found*100).toFixed(1)+'%, other words hidden '+(r.over*100).toFixed(2)+'%, '+r.details+' details'));
  y+=rh});
 // by type
 const ty=document.getElementById('typ');ty.innerHTML='';
 const tot={};sl.forEach(r=>{for(const k in r.by){const a=tot[k]=tot[k]||[0,0];a[0]+=r.by[k][0];a[1]+=r.by[k][1]}});
 const ts=D.types.filter(k=>tot[k]);ty.setAttribute('viewBox','0 0 '+W+' '+(ts.length*rh+30));
 [50,60,70,80,90,100].forEach(v=>{el(ty,'line',{class:'grid',x1:fx(v/100),x2:fx(v/100),y1:2,y2:ts.length*rh+4});el(ty,'text',{class:'tick',x:fx(v/100),y:ts.length*rh+18,'text-anchor':'middle'},v)});
 el(ty,'line',{class:'tgt',x1:fx(.99),x2:fx(.99),y1:2,y2:ts.length*rh+4});
 ts.forEach((k,i)=>{const f=tot[k][0]/tot[k][1];el(ty,'text',{class:'lab',x:L-8,y:i*rh+14,'text-anchor':'end'},k);
  const b=el(ty,'rect',{class:'hit',x:x0,y:i*rh+4,width:Math.max(1,fx(f)-x0),height:11,rx:2,fill:css('--s1')});
  el(ty,'text',{class:'tick',x:fx(f)+4,y:i*rh+14},(f*100).toFixed(1)+'%   n = '+tot[k][1].toLocaleString());
  tipOn(b,k+': '+tot[k][0]+' of '+tot[k][1]+' found')});
 // heatmap
 const hm=document.getElementById('heat');hm.innerHTML='';
 const cw=52,ch=19,hx=L,hy=58,hh=hy+names.length*ch+8;hm.setAttribute('viewBox','0 0 '+(L+ts.length*cw+10)+' '+hh);
 ts.forEach((k,j)=>{const w=k.split(' ');const two=w.length>1&&k.length>8;const l1=two?w.slice(0,Math.ceil(w.length/2)).join(' '):k,l2=two?w.slice(Math.ceil(w.length/2)).join(' '):'';el(hm,'text',{class:'tick',x:hx+j*cw+cw/2,y:hy-24,'text-anchor':'middle'},l1);if(l2)el(hm,'text',{class:'tick',x:hx+j*cw+cw/2,y:hy-12,'text-anchor':'middle'},l2)});
 names.forEach(([f,n],i)=>{el(hm,'text',{class:'lab',x:hx-8,y:hy+i*ch+13,'text-anchor':'end'},n);
  ts.forEach((k,j)=>{const c=m[n].by[k];const x=hx+j*cw,yy=hy+i*ch;
   if(!c||c[1]<10){el(hm,'rect',{x:x+1,y:yy+1,width:cw-2,height:ch-2,rx:2,fill:css('--na')});if(c)tipOn(el(hm,'rect',{x:x+1,y:yy+1,width:cw-2,height:ch-2,fill:'transparent'}),n+' · '+k+': '+c[0]+' of '+c[1]+' (too few)');return}
   const v=c[0]/c[1],col=ramp(v);const r=el(hm,'rect',{class:'hit',x:x+1,y:yy+1,width:cw-2,height:ch-2,rx:2,fill:'rgb('+col+')'});
   el(hm,'text',{class:'cellt',x:x+cw/2,y:yy+13,'text-anchor':'middle',fill:ink(col)},(v*100).toFixed(0));
   tipOn(r,n+' · '+k+': '+c[0]+' of '+c[1]+' found ('+(v*100).toFixed(1)+'%)')})});
 // table
 let s='<table><thead><tr><th>Format</th><th>Found</th><th>Other hidden</th><th>Details</th>'+ts.map(k=>'<th>'+k+'</th>').join('')+'</tr></thead><tbody>';
 names.forEach(([f,n])=>{const r=m[n];s+='<tr><td>'+n+'</td><td>'+(r.found*100).toFixed(1)+'</td><td>'+(r.over*100).toFixed(2)+'</td><td>'+r.details+'</td>'+ts.map(k=>{const c=r.by[k];return '<td>'+(c?(c[0]+'/'+c[1]):'–')+'</td>'}).join('')+'</tr>'});
 document.getElementById('tbl').innerHTML=s+'</tbody></table>';
}
sel.value=Object.keys(D.models).slice(-1)[0];draw();
</script></body></html>"""
open(f"{S}/breakdown.html", "w").write(PAGE.replace("__DATA__", payload))
print(len(PAGE), "bytes; models:", list(out))
