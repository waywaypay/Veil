"""python w2real_build.py <name> <n> <seed>: w2real documents to w2real_shards/<name>.json, written every 25 documents
(and extended on a rerun with the same name, so a container restart loses little)."""
import json, os, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import importlib
W = importlib.import_module(os.environ.get("W2_MODULE", "w2real"))
name, n, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
path = f"/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/w2real_shards/{name}.json"
have = json.load(open(path)) if os.path.exists(path) else []
while len(have) < n:
    chunk = W.docs(25, seed * 1000 + len(have))      # a new seed for each chunk, so a rerun doesn't repeat
    have += [[t, s] for t, s in chunk]
    json.dump(have, open(path + ".tmp", "w"))
    os.replace(path + ".tmp", path)
    print(name, len(have), flush=True)
