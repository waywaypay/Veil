"""Rounds 3 to 5 of the tagger's training (benchmarks/model.md), each from the last round's model, in 500-step segments
as train_tagger.py trains, every choice made on dev sets and each test set scored once.

  round 3   Gretel finance's other languages, Gretel pii-masking-en-v1's training split (chunks with its loosely
            labelled dates of birth and IDs left out), TAB's training split, Privy's API payloads, taxgen.py's
            tax-form snippets, and round 2's mix replayed
  round 4   400 documents of ten families written by Claude agents to judged/docgen/RULES.md (a fifth held out for
            dev), formgen.py's forms in 38 locales, tweets and posts (Broad Twitter Corpus, WNUT-17) with each
            person and handle judged private or public, CORD's receipts and opensporks' résumés with a made-up
            person's details written in, BUSTER's press releases and MAPA's EU court texts as text with nothing
            personal in it, and round 3's mix replayed
  round 5   half of round 4's mix, more of round 3's, round 2's judged chats at full weight, fresh tax-form snippets
            and the judged tweets again

The tests: 150 documents written by other agents who never saw the training ones (judged/docgen/test), 300 fresh
forms, 700 tweets and posts from the two corpora's test splits, and 231 of Enron's emails, every span a system hid
in them judged (judged/wider.json; the rules are judged/wider_rules.md); and veil's own taxpayer-ID stress cases.
Needs faker, besides train_tagger.py's needs.

python train_wider.py fetch
python train_wider.py build <round>                        3, 4 or 5
python train_wider.py train <round> <base> <out dir> <offset>
python train_wider.py dev <model>[@threshold] ...
python train_wider.py test <model>[@threshold] ...
python train_wider.py stress <model>[@threshold] ..."""

import ast
import hashlib
import json
import random
import re
import sys
import zipfile
from pathlib import Path

import formgen
import pandas as pd
import tagger as T
import tagger_sets
import taxgen
import train_tagger as TT

from veil import FINANCE, Redactor

HERE = Path(__file__).parent
MANIFEST = HERE / "judged" / "wider.json"
DOCGEN = HERE / "judged" / "docgen"
HF, RAW = tagger_sets.HF, "https://huggingface.co/datasets"
FILES = {
    "gretel_en_train.parquet": f"{HF}/gretelai/gretel-pii-masking-en-v1/parquet/default/train/0.parquet",
    "gretel_en_val.parquet": f"{HF}/gretelai/gretel-pii-masking-en-v1/parquet/default/validation/0.parquet",
    "tab_train.parquet": f"{HF}/ildpil/text-anonymization-benchmark/parquet/default/train/0.parquet",
    "tab_val.parquet": f"{HF}/ildpil/text-anonymization-benchmark/parquet/default/validation/0.parquet",
    "privy.zip": f"{RAW}/beki/privy/resolve/main/privy-dataset.zip",
    **{f"mapa_{s}.jsonl": f"{RAW}/joelniklaus/mapa/resolve/main/{s}.jsonl" for s in ("train", "validation", "test")},
    **{f"btc_{f}.conll": f"{RAW}/GateNLP/broad_twitter_corpus/resolve/main/{d}/{f}.conll"
       for d, f in (("train", "a"), ("train", "b"), ("train", "e"), ("train", "g"), ("dev", "h"), ("test", "f"))},
    **{f"wnut_{f}": f"https://raw.githubusercontent.com/leondz/emerging_entities_17/master/{f}"
       for f in ("wnut17train.conll", "emerging.dev.conll", "emerging.test.annotated")},
    "cord_train0.parquet": f"{RAW}/naver-clova-ix/cord-v2/resolve/main/data/train-00000-of-00004-b4aaeceff1d90ecb.parquet",
    "cord_val.parquet": f"{RAW}/naver-clova-ix/cord-v2/resolve/main/data/validation-00000-of-00001-cc3c5779fe22e8ca.parquet",
    **{f"buster_fold{i}.parquet": f"{RAW}/expertai/BUSTER/resolve/main/data/FOLD_{i}-00000-of-00001.parquet"
       for i in range(1, 6)},
    "resumes.csv": f"{RAW}/opensporks/resumes/resolve/main/Resume/Resume.csv",
    "enron0.parquet": f"{RAW}/corbt/enron-emails/resolve/main/data/train-00000-of-00003.parquet",
}
MARK = re.compile(r"⟦([^|⟦⟧]+)\|([^⟦⟧]*)⟧")
# the tagger's label names -> the groups found is counted by
GROUP = {"name": "name", "street address": "address", "email address": "email", "phone number": "phone",
         "ssn": "ID number", "tax id": "ID number", "passport number": "ID number", "driver license number": "ID number",
         "account number": "account", "credit card number": "account", "iban": "account", "swift code": "account",
         "date of birth": "date of birth", "customer id": "ID number", "employee id": "ID number", "username": "username"}
EN_V1 = {"first_name": "name", "last_name": "name", "name": "name", "street_address": "street address",
         "address": "street address", "email": "email address", "phone_number": "phone number", "ssn": "ssn",
         "credit_card_number": "credit card number", "bank_routing_number": "account number",
         "account_number": "account number", "user_name": "username", "certificate_license_number": "driver license number",
         "national_id": "tax id", "tax_id": "tax id", "swift_bic": "swift code"}
EN_V1_UNSURE = {"date_of_birth", "customer_id", "employee_id"}   # labelled loosely: chunks with them are left out
PRIVY = {"PER": "name", "US_BANK_NUMBER": "account number", "CREDIT_CARD": "credit card number",
         "US_DRIVER_LICENSE": "driver license number", "US_PASSPORT": "passport number", "US_ITIN": "tax id",
         "EMAIL_ADDRESS": "email address", "PHONE_NUMBER": "phone number"}
TAX_GROUP = {"ssn": "SSN / passport / license", "tax id": "SSN / passport / license", "name": "name",
             "street address": "street address"}
SIZES = {3: {"Gretel, other languages": 2500, "Gretel en-v1": 2500, "TAB": 1500, "Privy": 1000,
             "tax forms (synthetic)": 2500, "round 2, replayed": 2500},
         4: {"documents (agents)": 1800, "forms (synthetic)": 3200, "tweets and posts": 2200, "receipts": 400,
             "résumés": 1400, "press releases": 800, "EU court texts": 700, "round 3, replayed": 3500},
         5: {"round 4, replayed": 6000, "round 3, replayed": 2500, "chats (round 2's, judged)": 1800,
             "tax forms (synthetic, fresh)": 1500, "tweets and posts (judged)": 1000}}
SEEDS = {3: 7, 4: 17, 5: 23}


def fetch():
    tagger_sets.fetch({k: v for k, v in FILES.items()})
    if not (T.DATA / "privy_dev_small.json").exists():
        with zipfile.ZipFile(T.DATA / "privy.zip") as z:
            name = next(n for n in z.namelist() if n.endswith("dev-small.json"))
            (T.DATA / "privy_dev_small.json").write_bytes(z.read(name))


def sha(text):
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def manifest():
    return json.load(open(MANIFEST))


# -- round 3's data -------------------------------------------------------------------------------------------------

def gretel_other_languages():
    d = pd.read_parquet(T.DATA / "gretel_train.parquet")
    d = d[d.language != "English"]
    raw = list(zip(d.generated_text, d.pii_spans))
    random.Random(0).shuffle(raw)
    return raw[:300], raw[300:]   # dev, train


def en_v1(name, n=None):
    """(text, [(start, end, label)], unsure spans) from Gretel en-v1, whose entities come without offsets."""
    d = pd.read_parquet(T.DATA / name)
    out = []
    for text, ents in zip(d.text, d.entities):
        spans, unsure = [], []
        for e in ast.literal_eval(ents):
            pos = 0
            while (i := text.find(e["entity"], pos)) >= 0:
                lab = e["types"][0]
                if lab in EN_V1:
                    spans.append((i, i + len(e["entity"]), EN_V1[lab]))
                elif lab in EN_V1_UNSURE:
                    unsure.append((i, i + len(e["entity"])))
                pos = i + len(e["entity"])
        out.append((text, spans, unsure))
    return out[:n] if n else out


def tab_docs(name):
    d = pd.read_parquet(T.DATA / name).drop_duplicates("doc_id")
    return [(t, [(m["start_offset"], m["end_offset"], "name") for m in ms
                 if m["entity_type"] == "PERSON" and m["identifier_type"] in ("DIRECT", "QUASI")])
            for t, ms in zip(d.text, d.entity_mentions)]


def privy_docs(n):
    d = json.load(open(T.DATA / "privy_dev_small.json"))
    random.Random(3).shuffle(d)
    return [(r["full_text"], [(s["start_position"], s["end_position"], PRIVY[s["entity_type"]]) for s in r["spans"]
                              if s["entity_type"] in PRIVY]) for r in d[:n]]


def round3_parts(split, rng):
    _, other = gretel_other_languages()
    parts = {"Gretel, other languages": TT.examples(TT.gretel_docs(other[:2000]), split)}
    v1_ex = []
    for text, spans, unsure in en_v1("gretel_en_train.parquet", 8000):
        for off, piece in T.chunks(text):
            if any(off <= s < off + len(piece) for s, _ in unsure):
                continue   # a loosely labelled date of birth or ID in it: neither taught nor taught against
            v1_ex += TT.examples([(piece, [(s - off, e - off, lab) for s, e, lab in spans])], split)
    parts["Gretel en-v1"] = v1_ex
    parts["TAB"] = TT.examples(tab_docs("tab_train.parquet"), split)
    parts["Privy"] = TT.examples(privy_docs(1500), split)
    parts["tax forms (synthetic)"] = TT.examples(taxgen.docs(2500, 11), split)
    replay = TT.mixed_examples(split)
    rng.shuffle(replay)
    parts["round 2, replayed"] = replay
    return parts


# -- round 4's data -------------------------------------------------------------------------------------------------

def unmark(t):
    """The text of an agent's document and its spans, from its inline ⟦label|text⟧ markup."""
    out, spans, pos, n = [], [], 0, 0
    for m in MARK.finditer(t):
        out.append(t[pos:m.start()])
        n += m.start() - pos
        lab, txt = m.group(1).strip(), m.group(2)
        if lab not in GROUP:
            raise ValueError(f"unknown label {lab!r}")
        if txt.strip():
            lead = len(txt) - len(txt.lstrip())
            spans.append((n + lead, n + len(txt.rstrip()), lab))
        out.append(txt)
        n += len(txt)
        pos = m.end()
    out.append(t[pos:])
    text = "".join(out)
    if "⟦" in text or "⟧" in text:
        raise ValueError("unbalanced markup")
    return text, spans


def docgen():
    """{"train": [...], "dev": [...]}: a fifth of each family's documents held out for dev, by a hash of the text."""
    out = {"train": [], "dev": []}
    for path in sorted(DOCGEN.glob("fam*.jsonl")):
        for line in open(path):
            if line.strip():
                text, spans = unmark(json.loads(line)["text"])
                out["dev" if int(sha(text)[:8], 16) % 5 == 0 else "train"].append((text, spans))
    return out


NO_SPACE_BEFORE = {",", ".", ":", ";", "!", "?", ")", "]", "}", "%", "’", "'s", "’s", "n't", "'", "»", "”"}
NO_SPACE_AFTER = {"(", "[", "{", "‘", "“", "«", "@", "#", "$", "£", "€"}


def detok(tokens):
    """The text and each token's (start, end)."""
    text, pos = "", []
    for i, t in enumerate(tokens):
        if i and t not in NO_SPACE_BEFORE and tokens[i - 1] not in NO_SPACE_AFTER:
            text += " "
        pos.append((len(text), len(text) + len(t)))
        text += t
    return text, pos


# a court's members and officers, public in its judgments: a name near one of these is unsure
OFFICIAL = re.compile(r"(?i)advocate general|generalanw|avocat général|abogad[oa] general|avvocato generale|"
                      r"advocaat-generaal|advogad[oa]-geral|rzecznik generalny|generaladvokat|julkisasianaja|"
                      r"\b(judge|president|rapporteur|registrar|präsident|richter|juge|président|presidente|giudice|"
                      r"juez|rechter|sędzia|domare|tuomari|dommer)\b")
TITLES = {"mr", "mrs", "ms", "dr", "herr", "frau", "m", "mme", "sr", "sra", "sig", "sig.ra", "dott", "prof", "mr.",
          "mrs.", "ms.", "dr.", "m.", "mme.", "sr.", "sra."}


def mapa_negatives(split):
    """MAPA's EU court texts, 24 languages, cut into runs of sentences: the runs with no person's name in them.  (Its
    persons are mostly the court's members and the parties' agents, public in a judgment, some with a role or a
    date taken for a name; its addresses are towns and countries alone.)"""
    L = lambda x: x if isinstance(x, list) else ast.literal_eval(x)  # noqa: E731
    docs = {}
    for line in open(T.DATA / f"mapa_{split}.jsonl"):
        r = json.loads(line)
        docs.setdefault(r["file_name"], []).append(r)
    out = []
    for sents in docs.values():
        sents.sort(key=lambda r: int(r["sentence_number"]))
        text, names, unsure = "", [], []
        for r in sents:
            toks, cg, fg = L(r["tokens"]), L(r["coarse_grained"]), L(r["fine_grained"])
            t, pos = detok(toks)
            base = len(text) + (1 if text else 0)
            text += ("\n" if text else "") + t
            i = 0
            while i < len(toks):
                if cg[i] != "B-PERSON":
                    i += 1
                    continue
                j = i + 1
                while j < len(toks) and cg[j] == "I-PERSON":
                    j += 1
                fine = {f[2:] for f in fg[i:j] if f != "O"}
                k = i
                while k < j and (fg[k][2:] in ("TITLE", "ROLE") or toks[k].lower() in TITLES):
                    k += 1
                s, e = base + pos[i][0], base + pos[j - 1][1]
                if OFFICIAL.search(text[max(0, s - 40):e]) or "ROLE" in fine or fine & {"DAY", "MONTH", "YEAR"} or \
                        not fine & {"FAMILY NAME", "INITIAL NAME"}:
                    unsure.append((s, e))
                elif k < j:
                    names.append((base + pos[k][0], e))
                i = j
        for off, piece in T.chunks(text):
            end = off + len(piece)
            if not any(off < e and s < end for s, e in unsure) and not any(s >= off and e <= end for s, e in names):
                out.append((piece, []))
    return out


def cord(split):
    """CORD's receipts, rebuilt a line at a time, sometimes with a cashier's first name, a card, a loyalty number,
    a customer or an email written in."""
    import pyarrow.parquet as pq
    name = {"train": "cord_train0.parquet", "dev": "cord_val.parquet"}[split]
    gts = pq.read_table(T.DATA / name, columns=["ground_truth"]).column(0).to_pylist()
    r = random.Random(41 if split == "train" else 42)
    out = []
    for g in gts:
        groups = {}
        for ln in json.loads(g)["valid_line"]:
            groups.setdefault(ln["group_id"], []).append(ln)
        rows = []
        for lns in groups.values():
            y = min(w["quad"]["y1"] for ln in lns for w in ln["words"])
            words = sorted((w for ln in lns for w in ln["words"]), key=lambda w: w["quad"]["x1"])
            rows.append((y, " ".join(w["text"] for w in words)))
        d = formgen.Doc()
        p = formgen.Person(r, formgen.pick(r))
        store = r.choice(["TOKO SINAR JAYA", "Kopi Kenangan", "CAFE 21", "Bakery & Co", "RESTO PADANG SEDERHANA",
                          "Mini Market 88", "Tesco Express", "Carrefour City", "SPAR"])
        d.add(f"{store}\n{r.choice(['Jl. Sudirman No. 12', 'Store #4471', 'Branch 03', ''])}\n")
        if r.random() < 0.4:
            d.add(r.choice(["Cashier: ", "Kasir: ", "Served by ", "Operator "])).add(p.first, "name").add("\n")
        d.add(f"{formgen.other_date(r)} {r.randint(7, 22):02d}:{r.randint(0, 59):02d}  #{r.randint(1000, 99999)}\n")
        for _, t in sorted(rows):
            d.add(t + "\n")
        if r.random() < 0.35:
            q = formgen.Person(r, p.loc)
            k = r.randrange(4)
            if k == 0:
                d.add(r.choice(["CARD ", "VISA ", "Debit "])).add(q.card(), "credit card number").add("\n")
            elif k == 1:
                d.add(r.choice(["Member: ", "Loyalty no. ", "Club card "])).add(q.customer_id(), "customer id").add("\n")
            elif k == 2:
                d.add("Customer: ").add(q.name(), "name").add("  Tel ").add(q.phone(), "phone number").add("\n")
            else:
                d.add("Receipt sent to ").add(q.email(), "email address").add("\n")
        d.add(r.choice(["THANK YOU", "Terima kasih", "Please come again", ""]) + "\n")
        out.append((d.text(), d.labels))
    return out


def resumes(seed, n=None):
    """opensporks' anonymised résumés ("Company Name", "City , State") with made-up companies and towns, a made-up
    person's contact block at the top and sometimes referees at the end.  Seed 2 is the dev tenth, 1 the rest."""
    c = pd.read_csv(T.DATA / "resumes.csv")
    r = random.Random(seed)
    idx = list(range(len(c)))
    r.shuffle(idx)
    idx = idx[:len(idx) // 10] if seed == 2 else idx[len(idx) // 10:]
    out = []
    for i in idx[:n]:
        body = re.sub(r"[ \t]{3,}", "\n", str(c.Resume_str[i])).strip()
        p = formgen.Person(r, r.choice(["en_US"] * 6 + ["en_GB", "en_IN", "en_CA", "en_AU", "en_PH"]))
        body = re.sub(r"Company Name", lambda _: p.f.company(), body)
        body = re.sub(r"City\s*,\s*State", lambda _: f"{p.f.city()}, {r.choice(['CA', 'TX', 'NY', 'FL', 'IL', 'OH', 'GA', 'WA'])}", body)
        d = formgen.Doc()
        d.add(p.name(r.choice(["full", "caps", "middle"])), "name").add("\n")
        bits = []
        if r.random() < 0.5:
            bits.append(("address", p.address(one_line=True)))
        bits += [("phone", p.phone()), ("email", p.email())]
        if r.random() < 0.5:
            bits.append(("username", p.username()))
        sep = r.choice([" | ", " • ", "\n", " · ", "  "])
        for j, (k, v) in enumerate(bits):
            d.add(sep if j else "")
            if k == "username":
                d.add(r.choice(["linkedin.com/in/", "github.com/", "LinkedIn: "])).add(v, "username")
            else:
                d.add(v, {"address": "street address", "phone": "phone number", "email": "email address"}[k])
        d.add("\n\n" + body + "\n")
        if r.random() < 0.3:
            d.add("\nReferences\n")
            for _ in range(r.randint(1, 2)):
                q = formgen.Person(r, p.loc)
                d.add(q.name("full"), "name").add(f", {q.f.job()}, {q.f.company()}\n").add(q.phone(), "phone number")
                d.add(" | ").add(q.email(), "email address").add("\n")
        out.append((d.text(), d.labels))
    return out


SOCIAL = {"train": ["btc_a.conll", "btc_b.conll", "btc_e.conll", "btc_g.conll", "wnut_wnut17train.conll"],
          "dev": ["btc_h.conll", "wnut_emerging.dev.conll"], "test": ["btc_f.conll", "wnut_emerging.test.annotated"]}


def social(split):
    """The tweets and posts of a split, shuffled as they were judged."""
    out = []
    for name in SOCIAL[split]:
        doc = []
        for line in list(open(T.DATA / name, encoding="utf-8")) + [""]:
            line = line.rstrip("\n")
            if not line.strip():
                if doc:
                    out.append(detok(doc)[0])
                doc = []
                continue
            doc.append((line.split("\t") if "\t" in line else line.split())[0])
    random.Random(5 if split != "test" else 9).shuffle(out)
    return out[:700] if split == "test" else out


def judged(key):
    """{text hash: [(start, end, verdict)]} for a judged set in the manifest."""
    out = {}
    for h, spans, verdicts in manifest()[key]:
        out.setdefault(h, []).extend((s, e, v) for (s, e), v in zip(spans, verdicts))
    return out


def tweets(split):
    """(text, details, public names) the judged tweets and posts of the training or dev split: their private
    people's details labelled, public figures and everything else left.  A post with an unsure verdict is left out."""
    v = judged(f"tweets_{split}")
    out = []
    for text in social(split):
        h = sha(text)
        if h not in v or any(x == "unsure" for *_, x in v[h]):
            continue
        spans = sorted((s, e, x.split(":", 1)[1].strip()) for s, e, x in v[h]
                       if x.startswith("personal:") and x.split(":", 1)[1].strip() in GROUP)
        kept = []
        for s, e, lab in spans:   # overlapping spans of one detail: the longest
            if kept and s < kept[-1][1]:
                if e - s > kept[-1][1] - kept[-1][0]:
                    kept[-1] = (s, e, lab)
                continue
            kept.append((s, e, lab))
        out.append((text, kept, [(s, e) for s, e, x in v[h] if x == "public"]))
    return out


def press_releases():
    """BUSTER's press-release chunks (3,000 drawn) where round 3's model marked nothing outside the companies BUSTER
    labels, and those with one or two marks outside them that were all judged ordinary (a company missed, a place,
    a ticker)."""
    b = pd.concat([pd.read_parquet(T.DATA / f"buster_fold{i}.parquet") for i in range(1, 6)])
    pieces = [p for t in b.text for _, p in T.chunks(t)]
    random.Random(8).shuffle(pieces)
    by_hash = {sha(p): p for p in pieces[:3000]}
    m = manifest()
    negatives = set(m["buster_negatives"])
    return [(p, []) for p in pieces[:3000] if sha(p) in negatives] + \
        [(by_hash[h], []) for h, _, vs in m["buster_judged"] if all(v == "ordinary" for v in vs)]


def round4_parts(split, rng):
    cv = []
    for text, spans in resumes(1):
        ex = TT.examples([(text, spans)], split)
        cv += ex[:1] + rng.sample(ex[1:], min(1, len(ex) - 1))   # the contact block, and one more page
    return {"documents (agents)": TT.examples(docgen()["train"], split) * 3,
            "forms (synthetic)": TT.examples(formgen.docs(3200, 21), split),
            "tweets and posts": TT.examples([(t, s) for t, s, _ in tweets("train")], split),
            "receipts": TT.examples(cord("train"), split),
            "résumés": cv,
            "press releases": TT.examples(press_releases(), split),
            "EU court texts": TT.examples(mapa_negatives("train"), split),
            "round 3, replayed": json.load(open(T.DATA / "round3_examples.json"))}


def round5_parts(split, rng):
    return {"round 4, replayed": json.load(open(T.DATA / "round4_examples.json")),
            "round 3, replayed": json.load(open(T.DATA / "round3_examples.json")),
            "chats (round 2's, judged)": TT.examples(TT.chat_docs("train"), split),
            "tax forms (synthetic, fresh)": TT.examples(taxgen.docs(1500, 12), split),
            "tweets and posts (judged)": TT.examples([(t, s) for t, s, _ in tweets("train")], split)}


def build(n):
    from gliner import GLiNER
    split = GLiNER.from_pretrained("knowledgator/gliner-pii-edge-v1.0").data_processor.words_splitter
    rng = random.Random(SEEDS[n])
    parts = {3: round3_parts, 4: round4_parts, 5: round5_parts}[n](split, rng)
    data = []
    for k, ex in parts.items():
        rng.shuffle(ex)
        data += ex[:SIZES[n][k]]
        print(f"{k}: {min(len(ex), SIZES[n][k])} of {len(ex)} chunks, {sum(len(x['ner']) for x in ex[:SIZES[n][k]])} labels")
    rng.shuffle(data)
    json.dump(data, open(T.DATA / f"round{n}_examples.json", "w"))
    print(f"{len(data)} chunks in all")


def train(n, base, out, offset):
    TT.train(base, out, lambda splitter: (json.load(open(T.DATA / f"round{n}_examples.json")) * 2)[int(offset):int(offset) + 4000],
             500)


# -- choosing -------------------------------------------------------------------------------------------------------

def rows(docs):
    return [(t, [(s, e, GROUP[lab]) for s, e, lab in spans]) for t, spans in docs]


def judged_rows(texts, key):
    """A judged set's texts with their verdicts: a private person's detail is scored, a public name counts against a
    system that hides it, a business's contact detail and an unsure span count neither way, and an ordinary word
    hidden is a mistake like any unlabelled one."""
    v = judged(key)
    out = []
    for text in texts:
        sp = []
        for s, e, x in v.get(sha(text), []):
            if x.startswith("personal:"):
                sp.append((s, e, GROUP.get(x.split(":", 1)[1].strip(), "ID number")))
            elif x in ("public", "business", "unsure"):
                sp.append((s, e, "ordinary" if x == "public" else "outside"))
        out.append((text, sp))
    return out


def dev_sets():
    g = tagger_sets.gretel_rows(TT.gretel_split()[0])
    n = [(t, [(s["start"], s["end"], tagger_sets._group(s["label"])) for s in spans]) for t, spans in TT.nemo_split()[0]]
    o = tagger_sets.gretel_rows(gretel_other_languages()[0])
    v = [(t, [(s, e, "name" if lab == "name" else "other") for s, e, lab in spans] + [(s, e, "outside") for s, e in unsure])
         for t, spans, unsure in en_v1("gretel_en_val.parquet", 300)]
    d = pd.read_parquet(T.DATA / "tab_val.parquet").drop_duplicates("doc_id")
    tv = []
    for t, ms in zip(d.text, d.entity_mentions):
        sp = []
        for m in ms:
            masked = m["identifier_type"] in ("DIRECT", "QUASI")
            sp.append((m["start_offset"], m["end_offset"], "name" if m["entity_type"] == "PERSON" and masked else
                       "outside" if masked or m["entity_type"] == "PERSON" else "ordinary"))
        tv.append((t, sp))
    x = [(t, [(s, e, TAX_GROUP[lab]) for s, e, lab in labels]) for t, labels in taxgen.docs(300, 99)]
    return {"Gretel": g, "Nemotron": n, "Gretel, other languages": o, "Gretel en-v1": v, "TAB": tv, "tax forms": x,
            "documents (agents)": rows(docgen()["dev"]), "forms (synthetic)": rows(formgen.docs(300, 98)),
            "tweets and posts": [(t, [(s, e, GROUP[lab]) for s, e, lab in sp] + [(s, e, "ordinary") for s, e in pub])
                                 for t, sp, pub in tweets("dev")],
            "receipts": rows(cord("dev")), "résumés": rows(resumes(2, 100))}


def dev(models):
    sets = dev_sets()
    convs = json.load(open(T.DATA / "chats_dev.json"))
    texts = [t for rs in sets.values() for t, _ in rs] + [t["text"] for c in convs for t in c["turns"]]
    base = {k: T.score(rs, [t for t, _ in rs], [Redactor(FINANCE).redact_text(t) for t, _ in rs]) for k, rs in sets.items()}
    print("veil:  " + "  ".join(f"{k} {r['found']:.1%}/{r['over']:.2%}" for k, r in base.items()), flush=True)
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        cells = {k: T.score(rs, [t for t, _ in rs], [T.alone(t, found[T.key(t)], th) for t, _ in rs]) for k, rs in sets.items()}
        c = TT.chat_dev(found, th)
        print(f"{spec.split('/')[-1]}:  " + "  ".join(f"{k} {r['found']:.1%}/{r['over']:.2%}" for k, r in cells.items()) +
              f"  chats {c['alone']['found']:.1%}/{c['alone']['ordinary']:.2%}+{c['alone']['public']:.2%}", flush=True)


# -- the tests, each scored once ------------------------------------------------------------------------------------

def enron():
    """The 231 test emails, in the order they were judged: headers and the first 1,800 characters of the body."""
    e = pd.read_parquet(T.DATA / "enron0.parquet").set_index("message_id")
    out = []
    for mid in manifest()["enron_ids"]:
        m = e.loc[mid]
        to, cc = ", ".join(x for x in m.to if x)[:200], ", ".join(x for x in m.cc if x)[:200]
        out.append(f"From: {m['from']}\nTo: {to}\n" + (f"Cc: {cc}\n" if cc else "") +
                   f"Subject: {m.subject}\n\n{m.body.strip()[:1800]}")
    return out


def test_sets():
    held = [unmark(json.loads(line)["text"]) for path in sorted((DOCGEN / "test").glob("t*.jsonl"))
            for line in open(path) if line.strip()]
    return {"documents, held out (agents)": rows(held), "forms, held out (synthetic)": rows(formgen.docs(300, 97)),
            "tweets and posts (BTC, WNUT-17 tests)": judged_rows(social("test"), "tweets_test"),
            "Enron emails": judged_rows(enron(), "enron_test")}


def test(models):
    sets = test_sets()
    texts = [t for rs in sets.values() for t, _ in rs]
    cols = {"veil": {k: T.score(rs, [t for t, _ in rs], [Redactor(FINANCE).redact_text(t) for t, _ in rs])
                     for k, rs in sets.items()}}
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, texts)
        name = spec.split("/")[-1]
        cols[name] = {k: T.score(rs, [t for t, _ in rs], [T.alone(t, found[T.key(t)], th) for t, _ in rs])
                      for k, rs in sets.items()}
        cols[f"veil + {name}"] = {k: T.score(rs, [t for t, _ in rs], [T.with_veil(t, found[T.key(t)], T.GATES["checked"], th)
                                                                     for t, _ in rs]) for k, rs in sets.items()}
    print("test set".ljust(40) + "".join(c[:22].ljust(24) for c in cols))
    for k in sets:
        print(k.ljust(40) + "".join(f"{cols[c][k]['found']:6.1%} / {cols[c][k]['over']:5.2%}".ljust(24) for c in cols))
    print("details:", {k: cols["veil"][k]["details"] for k in sets})


def stress(models):
    """veil's own taxpayer-ID stress cases (tests/test_taxpayer_ids_stress.py), the tagger alone."""
    sys.path.insert(0, str(HERE.parent / "tests"))
    import test_taxpayer_ids_stress as ST
    specs = json.load(open(ST.SPECIMENS))
    pages = [p for s in specs for p in s["data"]["pages"]]
    tin = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{2}-\d{7}\b")
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, pages + list(ST.LEAKED_ONCE) + list(ST.NOT_TAXPAYER_IDS))
        alone = lambda t: T.alone(t, found[T.key(t)], th)  # noqa: E731
        missed = tot = 0
        for s in specs:
            outs = [alone(p) for p in s["data"]["pages"]]
            for t in {m for p in s["data"]["pages"] for m in tin.findall(p)}:
                tot += 1
                missed += any(ST.leaked(re.sub(r"\D", "", t), o) for o in outs)
        leaks = [c for c in ST.LEAKED_ONCE if ST.leaked(ST.SSN, alone(c)) or ST.leaked(ST.EIN, alone(c))]
        wrong = [p for p in ST.NOT_TAXPAYER_IDS if alone(p) != p and Redactor(FINANCE).redact_text(p) == p]
        print(f"{spec.split('/')[-1]}: K-1 specimens leak {missed} of {tot}; formats that once leaked: {len(leaks)} of "
              f"{len(ST.LEAKED_ONCE)} leak; form text hidden that veil leaves: {len(wrong)}", flush=True)


if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    {"fetch": fetch, "build": lambda: build(int(a[0])), "train": lambda: train(int(a[0]), *a[1:]),
     "dev": lambda: dev(a), "test": lambda: test(a), "stress": lambda: stress(a)}[cmd]()
