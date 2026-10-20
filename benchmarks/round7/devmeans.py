"""Mean found and mean other words hidden over the dev slices of round 6's dev lines (chats one slice, ordinary and
public together), for PROTOCOL.md's rule."""
import re
import sys

rows = {}
for path in sys.argv[1:]:
    for line in open(path, errors="replace"):
        m = re.match(r"^(r\d_\d@[\d.]+|veil):\s+(.*)", line)
        if not m:
            continue
        cells = re.findall(r"(\d+\.\d)%/(\d+\.\d+)%(?:\+(\d+\.\d+)%)?", m.group(2))
        if m.group(1) == "veil":
            continue
        f = [float(a) for a, _, _ in cells]
        o = [float(b) + float(c or 0) for _, b, c in cells]
        rows[m.group(1)] = (sum(f) / len(f), sum(o) / len(o), len(cells))
for k, (f, o, n) in sorted(rows.items(), key=lambda x: -x[1][0]):
    print(f"{k:14} found {f:6.2f}  over {o:5.2f}  ({n} slices)")
