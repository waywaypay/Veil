"""python checkdocs.py <file.jsonl> <agent task id> <own folder prefix>: validate an agent's labelled documents and list
the scratchpad paths its transcript touched outside its own folder and the rules/specs."""
import collections, json, re, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import round4 as R
path, tid, own = sys.argv[1:4]
docs = [json.loads(l) for l in open(path) if l.strip()]
c = collections.Counter()
for d in docs:
    t, sp = R.unmark(d["text"])
    assert "⟦" not in t and "⟧" not in t, path
    for s, e, l in sp:
        assert t[s:e].strip() == t[s:e] and t[s:e], (d.get("type"), t[s:e])
        assert l in R.GROUP, l
        c[l] += 1
print(path.split("/")[-1], len(docs), "docs", sum(c.values()), "spans", dict(c))
paths = set()
for line in open(f"/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/tasks/{tid}.output"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") != "assistant": continue
    for x in e.get("message", {}).get("content", []):
        if x.get("type") == "tool_use":
            paths |= set(re.findall(r"scratchpad/[\w./-]*", json.dumps(x["input"])))
ok = ("scratchpad/docgen/RULES.md", "scratchpad/w2_spec.txt", "scratchpad/taxforms_spec.txt")
print("outside own folder:", sorted(p for p in paths if own not in p and p not in ok and p.rstrip("/.") not in ("scratchpad", "scratchpad/" + own.split("/")[0], "scratchpad/docgen", "scratchpad/docgen/round7")))
