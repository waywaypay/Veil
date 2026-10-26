"""The third locked test's WildChat half (judged/locked3/README.md): 300 English conversations, none of them in the second
locked test or any earlier set, drawn once, before any round 10 training data.  The 150 that Presidio found something
in come from WildChat-4.8M's shards 83 to 85 (June and July 2025; no set has used them, round 7's chats came from
40 to 48): shards 8 and 9 of WildChat-1M, after the second locked test, hold too few.  The 150 it found nothing in come
from WildChat-1M's shards 8 and 9.

    python benchmarks/locked3_draw.py fetch                          the five shards, to $VEIL_BENCH_DATA (2 GB)
    python benchmarks/locked3_draw.py draw --exclude <file> ...      the draw: judged/locked3/draw.json, and the texts
    python benchmarks/locked3_draw.py build                          the texts again, from the shards and draw.json

The rule, the same for every conversation, fixed before the draw:

* a candidate is an English conversation with 1 to 20 user turns, every one non-empty, and at most 3,000 words of
  user text in all, and at most 20 of Presidio's markers (a pasted mailing list would otherwise decide the emails'
  score), read in this order: WildChat-1M's shards 8 and 9, then WildChat-4.8M's 83, 84 and 85, rows in
  each shard's order;
* it isn't excluded: its conversation hash isn't in any --exclude file, and no user turn of 40 characters or more
  (its spaces collapsed, lower case) is a text in one or a user turn of a candidate before it;
* "redacted" candidates, from WildChat-4.8M's shards only: WildChat says Presidio found something, and a user turn
  holds one of its markers (<PRESIDIO_ANONYMIZED_...>); "plain" candidates, from WildChat-1M's shards only: WildChat
  says it found nothing, and no user turn holds a marker;
* random.Random(103) draws 150 of each: rng.sample(redacted, 150), then rng.sample(plain, 150).

A marker is filled with a made-up detail (Faker, en_US, from the same generator): a person's name (full, first or
last; now and then one put in earlier in the conversation, as people come back), an email, a phone number or a card
number, each a detail of its label; any other marker with a made-up value marked "outside" (counted neither way).

--exclude takes JSON or JSONL files: the second locked test's chats, round 7's chats (from WildChat-4.8M's shards
40 to 48; the same conversation can appear in both datasets, with the same hash), judged/locked.json,
judged/chats.json, and any other set's manifest.  Every 32-character hex string in them is taken as a conversation hash to leave out, and every
string of 40 characters or more as a text no drawn turn may be.  Pass the second locked test's chats: the draw refuses
to run without at least one file.

draw.json holds the draw (each conversation's hash, whether it was redacted, and for each user turn what was put in
each marker and a hash of the text), not WildChat's text; build makes the texts from it again, checking each against
its hash.  The texts go to $VEIL_BENCH_DATA/locked3_wildchat.jsonl ({"id", "redacted", "messages", "spans"}), where
score_locked3.py reads them."""
import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("VEIL_BENCH_DATA", HERE / "data"))
DRAW = HERE / "judged" / "locked3" / "draw.json"
OUT = DATA / "locked3_wildchat.jsonl"
HF = "https://huggingface.co/api/datasets/allenai"
PLAIN = {f"wildchat{i}.parquet": f"{HF}/WildChat-1M/parquet/default/train/{i}.parquet" for i in (8, 9)}
REDACTED = {f"wc48_{i}.parquet": f"{HF}/WildChat-4.8M/parquet/default/train/{i}.parquet" for i in (83, 84, 85)}
SHARDS = {**PLAIN, **REDACTED}
SEED, N = 103, 150
MAX_TURNS, MAX_WORDS, MAX_MARKERS = 20, 3000, 20
MARKER = re.compile(r"<PRESIDIO_ANONYMIZED_([A-Z_]+)>")
LABEL = {"PERSON": "name", "EMAIL_ADDRESS": "email address", "PHONE_NUMBER": "phone number",
         "CREDIT_CARD": "credit card number"}
_HASH = re.compile(r"[0-9a-f]{32}")


def norm(text):
    return " ".join(text.split()).lower()


def sha(text):
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def excluded(paths):
    """Conversation hashes and texts (normalised) found anywhere in the files."""
    hashes, texts = set(), set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(k)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            if _HASH.fullmatch(x):
                hashes.add(x)
            elif len(x) >= 40:
                texts.add(norm(x))

    for p in paths:
        with open(p, encoding="utf-8") as f:
            if str(p).endswith(".jsonl"):
                for line in f:
                    if line.strip():
                        walk(json.loads(line))
            else:
                walk(json.load(f))
    return hashes, texts


def conversations():
    """(shard, hash, redacted, [user turns]) of the English conversations of the five shards, in order."""
    import pyarrow.parquet as pq
    for name in SHARDS:   # in batches: a WildChat-4.8M shard is half a gigabyte
        for batch in pq.ParquetFile(DATA / name).iter_batches(
                batch_size=2000, columns=["conversation_hash", "conversation", "language", "redacted"]):
            for r in batch.to_pylist():
                if r["language"] == "English":
                    yield name, r["conversation_hash"], bool(r["redacted"]), \
                        [u["content"] or "" for u in r["conversation"] if u["role"] == "user"]


def candidates(hashes, texts):
    redacted, plain, seen = [], [], set(texts)
    for shard, h, red, users in conversations():
        if h in hashes or not 1 <= len(users) <= MAX_TURNS or not all(u.strip() for u in users) or \
                sum(len(u.split()) for u in users) > MAX_WORDS or sum(len(MARKER.findall(u)) for u in users) > MAX_MARKERS:
            continue
        turns = {norm(u) for u in users if len(norm(u)) >= 40}
        if turns & seen:
            continue
        marked = any(MARKER.search(u) for u in users)
        if red and marked and shard in REDACTED:
            redacted.append((shard, h, users))
        elif not red and not marked and shard in PLAIN:
            plain.append((shard, h, users))
        else:
            continue
        seen |= turns
    return redacted, plain


class Filler:
    """Made-up details for Presidio's markers, from one generator."""
    def __init__(self, rng):
        from faker import Faker
        self.rng, self.f = rng, Faker("en_US")
        self.f.seed_instance(rng.randrange(1 << 30))

    def value(self, kind, people):
        f, r = self.f, self.rng
        if kind == "PERSON":
            if people and r.random() < 0.3:
                return r.choice(people)
            v = r.choices([f.name(), f.first_name(), f.last_name()], [6, 3, 1])[0]
            people.append(v)
            return v
        if kind == "EMAIL_ADDRESS":
            return f.email()
        if kind == "PHONE_NUMBER":
            return f.phone_number()
        if kind == "CREDIT_CARD":
            return f.credit_card_number()
        return f.word()


def fill(text, values):
    """The turn with each marker replaced by its value in turn, and the values' spans."""
    out, spans, pos = "", [], 0
    for m, v in zip(MARKER.finditer(text), values):
        out += text[pos:m.start()]
        spans.append([len(out), len(out) + len(v), LABEL.get(m.group(1), "outside")])
        out += v
        pos = m.end()
    return out + text[pos:], spans


def draw(paths):
    if not paths:
        sys.exit("--exclude needs at least the second locked test's chats, and every other set the draw must miss")
    if DRAW.exists():
        sys.exit(f"{DRAW} exists: the draw is made once")
    hashes, texts = excluded(paths)
    redacted, plain = candidates(hashes, texts)
    print(f"excluded {len(hashes)} conversation hashes and {len(texts)} texts; {len(redacted)} redacted and "
          f"{len(plain)} plain candidates", file=sys.stderr)
    if len(redacted) < N or len(plain) < N:
        sys.exit("too few candidates")
    rng = random.Random(SEED)
    picked = [(c, True) for c in rng.sample(redacted, N)] + [(c, False) for c in rng.sample(plain, N)]
    filler = Filler(rng)
    manifest, rows = [], []
    for (shard, h, users), red in picked:
        people, turns, msgs, spans = [], [], [], []
        for u in users:
            values = [filler.value(m.group(1), people) for m in MARKER.finditer(u)]
            text, sp = fill(u, values)
            turns.append([values, sha(text)])
            msgs.append(text)
            spans.append(sp)
        manifest.append({"shard": shard, "hash": h, "redacted": red, "turns": turns})
        rows.append({"id": h, "redacted": red, "messages": msgs, "spans": spans})
    DRAW.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"seed": SEED, "shards": sorted(SHARDS), "exclude": [Path(p).name for p in paths],
               "conversations": manifest}, open(DRAW, "w"), indent=0)
    write(rows)
    print(f"{DRAW}: {len(manifest)} conversations, {sum(len(c['turns']) for c in manifest)} user turns", file=sys.stderr)


def build():
    m = json.load(open(DRAW))
    want = {(c["shard"], c["hash"]) for c in m["conversations"]}
    users = {(s, h): u for s, h, _, u in conversations() if (s, h) in want}
    rows = []
    for c in m["conversations"]:
        msgs, spans = [], []
        for u, (values, digest) in zip(users[(c["shard"], c["hash"])], c["turns"]):
            text, sp = fill(u, values)
            if sha(text) != digest:
                raise ValueError(f"conversation {c['hash']}: a turn isn't as it was drawn")
            msgs.append(text)
            spans.append(sp)
        rows.append({"id": c["hash"], "redacted": c["redacted"], "messages": msgs, "spans": spans})
    write(rows)


def write(rows):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{OUT}: {len(rows)} conversations", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("fetch", "draw", "build"))
    ap.add_argument("--exclude", nargs="*", default=[])
    a = ap.parse_args()
    if a.step == "fetch":
        import urllib.request
        DATA.mkdir(parents=True, exist_ok=True)
        for name, url in SHARDS.items():
            if not (DATA / name).exists():
                print("fetching", name, file=sys.stderr, flush=True)
                urllib.request.urlretrieve(url, DATA / name)
    elif a.step == "draw":
        draw(a.exclude)
    else:
        build()


if __name__ == "__main__":
    main()
