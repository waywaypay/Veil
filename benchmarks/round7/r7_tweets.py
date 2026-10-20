"""Round 7's tweets: TweetNER7's training and validation tweets (2020-2021), rebuilt as text.  Its de-identification
left {{USERNAME}} for an ordinary user, {@Name@} for a verified account and {{URL}} for a link: an ordinary user
becomes a made-up private handle (labelled), a verified account its handle (left, as a public account), a link a
t.co link (left).  The persons TweetNER7 tags are judged private or public before they're labelled.

python r7_tweets.py build    candidates in judge7/tweetner_b*.json, the rebuilt tweets in dl7/tweetner_rebuilt.json
python r7_tweets.py docs     (after judging) the labelled tweets, train and dev, in dl7/tweetner_docs.json"""
import hashlib
import json
import random
import re
import string
import sys

import pandas as pd
from faker import Faker

S = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad"
J7 = f"{S}/judge7"
PERSON = {5, 12}            # B-person, I-person
NO_SPACE_BEFORE = {",", ".", ":", ";", "!", "?", ")", "]", "%", "'s", "n't", "'"}
NO_SPACE_AFTER = {"(", "[", "#", "$", "@"}


def handle(rng, fakers):
    f = rng.choice(fakers)
    first, last = f.first_name(), f.last_name()
    base = re.sub(r"[^A-Za-z0-9_]", "", rng.choice([first + last, first + "_" + last, first[0] + last, first + str(rng.randint(1, 99)),
                                                      last + "_" + first[:3], first.lower() + rng.choice(["xo", "_", "__", "x"]) + str(rng.randint(70, 9999))]))
    return "@" + (base or "user" + str(rng.randint(10, 999)))[:15]


def tco(rng):
    return "https://t.co/" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(10))


def render(tokens, tags, rng, fakers):
    """(text, private handle spans, person spans)."""
    text, handles, persons, cur = "", [], [], None
    prev = None
    for tok, tag in zip(tokens, tags):
        if tok == "{{USERNAME}}":
            piece, kind = handle(rng, fakers), "handle"
        elif tok == "{{URL}}":
            piece, kind = tco(rng), "url"
        elif tok.startswith("{@") and tok.endswith("@}"):
            piece, kind = "@" + re.sub(r"[^A-Za-z0-9_]", "", tok[2:-2])[:15], "verified"
        else:
            piece, kind = tok, "word"
        sep = "" if not text or piece in NO_SPACE_BEFORE or prev in NO_SPACE_AFTER else " "
        text += sep
        start = len(text)
        text += piece
        if kind == "handle":
            handles.append([start, len(text)])
        if tag in PERSON and kind == "word":
            if tag == 5 or cur is None:
                cur = [start, len(text)]
                persons.append(cur)
            else:
                cur[1] = len(text)
        else:
            cur = None
        prev = piece
    return text, handles, persons


def build():
    rng = random.Random(71)
    fakers = [Faker(loc) for loc in ("en_US", "en_GB", "en_IN", "es_ES", "pt_BR", "fr_FR", "de_DE", "it_IT", "ja_JP", "tr_TR")]
    for i, f in enumerate(fakers):
        f.seed_instance(700 + i)
    rows = []
    for split in ("train_2020", "train_2021", "validation_2020", "validation_2021"):
        d = pd.read_parquet(f"{S}/dl7/tweetner7_{split}.parquet")
        for tokens, tags, tid in zip(d.tokens, d.tags, d.id):
            text, handles, persons = render(list(tokens), list(tags), rng, fakers)
            rows.append({"id": f"{split}/{tid}", "text": text, "handles": handles, "persons": persons})
    json.dump(rows, open(f"{S}/dl7/tweetner_rebuilt.json", "w"), ensure_ascii=False)
    items = [{"key": r["id"], "text": r["text"], "spans": r["persons"]} for r in rows if r["persons"]]
    import os
    os.makedirs(J7, exist_ok=True)
    for k in range(0, len(items), 150):
        json.dump(items[k:k + 150], open(f"{J7}/tweetner_b{k // 150}.json", "w"), ensure_ascii=False, indent=0)
    print(len(rows), "tweets,", len(items), "with persons to judge,", sum(len(i["spans"]) for i in items), "spans in",
          (len(items) + 149) // 150, "batches;", sum(len(r["handles"]) for r in rows), "private handles written in")


def docs():
    """[(text, [(start, end, label)]), split]: private handles and persons judged private labelled; a tweet with an
    unsure verdict, or with a phone, email or card number veil's rules find (which the corpus wouldn't have tagged),
    left out; a fifth held out for dev by a hash of its id."""
    import glob
    verdicts = {}
    for p in sorted(glob.glob(f"{J7}/tweetner_b*.json")):
        if p.endswith("_v.json"):
            continue
        vs = json.load(open(p[:-5] + "_v.json"))
        for i, it in enumerate(json.load(open(p))):
            verdicts[it["key"]] = list(zip(map(tuple, it["spans"]), vs[str(i)]))
    from veil import GENERIC, Redactor
    out = {"train": [], "dev": []}
    dropped = 0
    for r in json.load(open(f"{S}/dl7/tweetner_rebuilt.json")):
        v = verdicts.get(r["id"], [])
        if any(x == "unsure" for _, x in v):
            continue
        if re.search(r"\b(?:PHONE|EMAIL|ACCOUNT|CARD|SSN|IBAN)_\d+", Redactor(GENERIC).redact_text(r["text"])):
            dropped += 1   # a phone, email or card number the corpus doesn't tag would be an unlabelled detail
            continue
        spans = [(s, e, "username") for s, e in r["handles"]]
        spans += [(s, e, x.split(":", 1)[1].strip()) for (s, e), x in v if x.startswith("personal:")]
        split = "dev" if int(hashlib.sha1(r["id"].encode()).hexdigest()[:8], 16) % 5 == 0 else "train"
        out[split].append((r["text"], sorted(spans)))
    json.dump(out, open(f"{S}/dl7/tweetner_docs.json", "w"), ensure_ascii=False)
    print({k: len(v) for k, v in out.items()}, "tweets;", dropped, "dropped (rule-found details);", sum(len(s) for _, s in out["train"]), "train labels")


if __name__ == "__main__":
    {"build": build, "docs": docs}[sys.argv[1]]()
