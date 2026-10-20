"""Round 7's chats: English WildChat-4.8M conversations from shards 40-48, none of them in a WildChat-1M shard any test
used (0-3, 8-13): those Presidio found something in, their markers filled with made-up details as the tests' are, and
as many it found nothing in.  What veil or round 6's tagger hides that wasn't put there is judged before training.

python r7_chats.py build        dl7/r7_chats.json and the judges' batches judge7/wc_b*.json
python r7_chats.py docs         (after judging) dl7/r7_chat_docs.json, train and dev"""
import hashlib
import json
import os
import random
import re
import sys

import pandas as pd

S = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad"
sys.path[:0] = [S]
import build_chats_locked2 as B  # noqa: E402  (fill(), Faker seeded per locale)

J7 = f"{S}/judge7"
CHAT = {"name": "name", "email": "email address", "phone / fax": "phone number", "bank / card / account": "credit card number"}


def test_hashes():
    hs = set()
    for path in [f"{S}/benchdata/wildchat{i}.parquet" for i in (0, 1, 2, 3, 10, 11, 12, 13)] + \
                [f"{S}/dl_locked2/wildchat{i}.parquet" for i in (8, 9)]:
        if os.path.exists(path):
            hs |= set(pd.read_parquet(path, columns=["conversation_hash"]).conversation_hash)
    return hs


def build():
    B.rnd.seed(7007)
    for i, f in enumerate(B.fakers.values()):
        f.seed_instance(7100 + i)
    banned = test_hashes()
    pii, ordinary = [], []
    for shard in range(40, 49):
        d = pd.read_parquet(f"{S}/dl7/wc48_{shard}.parquet", columns=["conversation_hash", "conversation", "language", "redacted"])
        d = d[(d.language == "English") & ~d.conversation_hash.isin(banned)]
        for h, conv, red in zip(d.conversation_hash, d.conversation, d.redacted):
            users = [u["content"] for u in conv if u["role"] == "user"]
            if red:
                if not any(re.search(r"<PRESIDIO_ANONYMIZED_(?:PERSON|EMAIL_ADDRESS|PHONE_NUMBER|CREDIT_CARD)>", u) for u in users):
                    continue
                people, turns = [], []
                for u in users[:4]:
                    if len(u) < 3000 and u.strip():
                        text, spans = B.fill(u, people)
                        turns.append({"text": text, "spans": spans})
                if any(t["spans"] for t in turns):
                    pii.append({"id": h, "turns": turns})
            elif users and 20 < len(users[0]) < 2000 and not B.MARKER.search(users[0]):
                ordinary.append({"id": h, "turns": [{"text": users[0], "spans": []}]})
    rnd = random.Random(70)
    rnd.shuffle(ordinary)
    convs = [dict(c, kind="pii") for c in pii] + [dict(c, kind="ordinary") for c in ordinary[:len(pii)]]
    json.dump(convs, open(f"{S}/dl7/r7_chats.json", "w"))
    print(f"{len(pii)} conversations with details, {min(len(ordinary), len(pii))} without; "
          f"{sum(len(c['turns']) for c in convs)} user turns; {len(banned)} test conversations kept out")


def candidates():
    import round4 as R
    from veil import GENERIC, Redactor
    T = R.T
    convs = json.load(open(f"{S}/dl7/r7_chats.json"))
    found = T.spans(f"{S}/ft/r6_3", [t["text"] for c in convs for t in c["turns"]])
    items = []
    for ci, c in enumerate(convs):
        r = Redactor(GENERIC)
        for ti, t in enumerate(c["turns"]):
            text = t["text"]
            spans = R.runs(text, r.redact_text(text))
            spans |= {(s, e) for s, e, _, _ in T.merged([x for x in found[T.key(text)] if x[3] >= 0.3], text)}
            spans = sorted((s, e) for s, e in spans if not any(a < e and s < b for a, b, _ in t["spans"]))
            if spans:
                items.append({"key": f"{ci}/{ti}", "text": text, "spans": [list(x) for x in spans]})
    for k in range(0, len(items), 120):
        json.dump(items[k:k + 120], open(f"{J7}/wc_b{k // 120}.json", "w"), ensure_ascii=False, indent=0)
    print(len(items), "turns,", sum(len(i["spans"]) for i in items), "spans to judge in", (len(items) + 119) // 120, "batches")


def docs():
    """[(text, [(start, end, label)])] each turn: what was put in, and what was judged a private person's detail, are
    labelled; public names and ordinary words are left. A conversation with an unsure verdict is left out; a fifth of
    the conversations held out for dev by a hash of its id."""
    import glob
    v = {}
    for p in sorted(glob.glob(f"{J7}/wc_b*.json")):
        if p.endswith("_v.json"):
            continue
        vs = json.load(open(p[:-5] + "_v.json"))
        for i, it in enumerate(json.load(open(p))):
            v[it["key"]] = list(zip(map(tuple, it["spans"]), vs[str(i)]))
    out = {"train": [], "dev": []}
    for ci, c in enumerate(json.load(open(f"{S}/dl7/r7_chats.json"))):
        turns = []
        for ti, t in enumerate(c["turns"]):
            here = v.get(f"{ci}/{ti}", [])
            if any(x == "unsure" for _, x in here):
                turns = None
                break
            spans = [(s, e, CHAT[g]) for s, e, g in t["spans"] if g in CHAT]
            spans += [(s, e, x.split(":", 1)[1].strip()) for (s, e), x in here if x.startswith("personal:")]
            turns.append((t["text"], sorted(spans)))
        if turns:
            split = "dev" if int(hashlib.sha1(c["id"].encode()).hexdigest()[:8], 16) % 5 == 0 else "train"
            out[split] += turns
    json.dump(out, open(f"{S}/dl7/r7_chat_docs.json", "w"), ensure_ascii=False)
    print({k: len(x) for k, x in out.items()}, "turns")


if __name__ == "__main__":
    {"build": build, "candidates": candidates, "docs": docs}[sys.argv[1]]()
