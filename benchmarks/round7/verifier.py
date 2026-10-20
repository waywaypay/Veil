"""A second, different detector over what the span model left visible: a 4-bit Qwen3-4B (Apache-2.0) run with llama.cpp.
It reads the text with the model's finds already replaced (NAME_X, ...), lists any private detail still visible, copied as
written; each one is found in the original text (exactly, or with only spacing/punctuation between its letters and digits,
as in boxed forms) and hidden too.  The verifier only adds.  The prompt was written once, before scoring, and not tuned on
the dev slices.

python verifier.py <model>@<threshold> <slice> ...     (results cached in llm/verify_cache.jsonl)"""
import json
import os
import re
import sys
import time

sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import round4 as R  # noqa: E402
import round7 as R7  # noqa: E402
from breakdown import cached  # noqa: E402

T = R.T
HERE = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/llm"
CACHE = f"{HERE}/verify_cache.jsonl"
CHUNK = 5000

PROMPT = """You check redacted text for private details that were missed. Some details were already replaced with placeholders such as NAME_X, ADDRESS_X, PHONE_X, SSN_X, ID_X, ACCOUNT_X, EMAIL_X. Look at what is still visible.

List every private detail about a person that is still visible:
- names of people (first, middle, last names, nicknames)
- street addresses (with house number or PO box), and postcodes with them
- email addresses, phone and fax numbers, usernames and handles
- social security numbers, tax IDs and employer identification numbers (EIN), national ID, passport and driver licence numbers
- bank account, routing, IBAN, SWIFT, credit card numbers
- dates of birth
- employee IDs, customer IDs, control numbers, member or policy numbers

Do NOT list: company or organisation names, job titles, money amounts, ordinary dates, cities or countries on their own, form box labels, or the placeholders.

Copy each detail exactly as it appears in the text. Reply with JSON only, in this form:
{"items": [{"text": "...", "type": "name|address|email|phone|id|account|date of birth|username"}]}
If nothing is missed, reply {"items": []}.

Text:
<<<
%s
>>>"""

KIND = {"name": "NAME", "address": "ADDRESS", "email": "EMAIL", "phone": "PHONE", "id": "ID", "account": "ACCOUNT",
        "date of birth": "DOB", "username": "USERNAME"}

_llm = None


def llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama
        _llm = Llama(model_path=f"{HERE}/Qwen3-4B-Q4_K_M.gguf", n_ctx=8192, n_threads=4, verbose=False)
    return _llm


def ask(masked):
    out = llm().create_chat_completion(
        messages=[{"role": "user", "content": PROMPT % masked + "\n/no_think"}],
        temperature=0, max_tokens=700)
    raw = out["choices"][0]["message"]["content"]
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        items = json.loads(m.group(0))["items"] if m else []
    except (json.JSONDecodeError, KeyError, TypeError):
        items = []
    return [(str(i.get("text", "")), str(i.get("type", ""))) for i in items if isinstance(i, dict)], raw


def locate(text, value):
    """Every place `value` occurs in `text`: exactly, else letters/digits in order with only spacing or punctuation
    (brackets, dashes, dots) between them."""
    value = value.strip()
    if len(re.sub(r"\W", "", value)) < 3 or re.fullmatch(r"[A-Z]+_X", value):
        return []
    spans = [(m.start(), m.end()) for m in re.finditer(re.escape(value), text)]
    if spans:
        return spans
    chars = re.sub(r"[^0-9A-Za-z]", "", value)
    pat = r"[^0-9A-Za-z\n]{0,4}".join(re.escape(c) for c in chars)
    return [(m.start(), m.end()) for m in re.finditer(pat, text, re.I)] if chars else []


def load_cache():
    have = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line)
            have[r["k"]] = r["items"]
    return have


def verify(text, found, th, have):
    """The extra spans the verifier adds for `text` (cached by the masked text it was shown)."""
    masked = T.alone(text, found, th)
    k = T.key(masked)
    if k not in have:
        items = []
        for i in range(0, len(masked), CHUNK):
            got, _ = ask(masked[i:i + CHUNK])
            items += got
        have[k] = items
        with open(CACHE, "a") as f:
            f.write(json.dumps({"k": k, "items": items}) + "\n")
    extra = []
    for value, typ in have[k]:
        for s, e in locate(text, value):
            extra.append((s, e, KIND.get(typ.lower(), "ID"), 1.0))
    return extra


def main(spec, names):
    model, _, th = spec.partition("@")
    th = float(th)
    spans = cached(model)
    sets = R7.dev_sets()
    have = load_cache()
    res = {}
    for name in names:
        rows = sets[name]
        ins = [t for t, _ in rows]
        t0 = time.time()
        extra = [verify(t, spans[T.key(t)], th, have) for t in ins]
        alone = T.score(rows, ins, [T.alone(t, spans[T.key(t)], th) for t in ins])
        both = T.score(rows, ins, [T.alone(t, spans[T.key(t)] + x, th) for t, x in zip(ins, extra)])
        res[name] = {"model": [alone["found"], alone["over"], alone["by"]], "model+verifier": [both["found"], both["over"], both["by"]],
                     "seconds": time.time() - t0, "docs": len(rows), "chars": sum(map(len, ins))}
        print(f"{name}: model {alone['found']:.1%}/{alone['over']:.2%}  model+verifier {both['found']:.1%}/{both['over']:.2%}"
              f"  ({len(rows)} docs, {time.time() - t0:.0f} s)", flush=True)
    out = f"{HERE}/verify_results.json"
    old = json.load(open(out)) if os.path.exists(out) else {}
    old.setdefault(spec.split("/")[-1], {}).update(res)
    json.dump(old, open(out, "w"), indent=1)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    main(sys.argv[1], sys.argv[2:])
