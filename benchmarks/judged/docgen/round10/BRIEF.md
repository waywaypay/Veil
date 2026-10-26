# Writing a user's side of chats with an AI assistant (round 10, source B)

Read `../RULES.md` first: its labels, what never to mark, and its rule that everyone you write is made up all apply
here. This brief says what to write instead of documents, and how to hand it in.

You are writing what people type to an AI assistant when they want help with something that involves their own
details, or someone else's: a message to their bank, a form, a support ticket, a broken config. A model will learn
from these to find the personal details in what people send to an assistant, and to leave the rest alone.

## What a conversation is

* Only the user's messages: two to eight of them, in order, each answering an assistant reply you don't write. Let
  them read like it: "ok that's too formal", "they wrote back, here's what they said:", "no, the other account".
* Under 400 words of the user's text in all, most well under 200. A pasted log, email or config may take up most of
  it.
* Each message is one string. Line breaks, pasted emails, tables, code blocks and `.env` files go inside it as they'd
  be pasted.
* People type fast and loosely: lower case, missing punctuation, typos, abbreviations ("acct", "pls", "tmrw"), half
  sentences. Some write carefully. Vary it.

## Your family

You're given one family, a number of conversations, a locale mix and an output path. The families:

| family | what the user wants |
|---|---|
| `support` | help with a support ticket, an account locked or hacked, a recovery or reset, a refund or a complaint |
| `banking` | a message to a bank, insurer, lender or pension provider, a disputed payment, a claim, a change of details |
| `travel` | a booking changed or cancelled, a lost bag, a visa or hotel form, a message to a host |
| `helpdesk` | a work IT problem: VPN, email, a laptop, a shared drive, a password expired, an account for a new starter |
| `developer` | code, logs, stack traces or config pasted to be debugged, keys and connection strings among them |
| `forms` | help filling in a form (school, doctor, council, landlord, employer, tax) with the user's and family's details |
| `nothing` | everyday requests with nothing personal in them, full of things that look personal and aren't |

In every family but `nothing`, about one conversation in six should have no personal detail either, or only a first
name.

## What to put in

Spread the details over the turns, the way people give them when asked. In most conversations, use several of these:

* **Details given again.** The same number or address in a later message, written another way ("AC-3DS5-KQ5L" then
  "ac3ds5kq5l", "+44 7700 900123" then "07700 900123"). Mark every mention.
* **Corrections.** "sorry, wrong one, the new code is 482915". Mark both the old and the new value.
* **Several people.** A partner, a child, a parent, a colleague, an agent who answered the phone ("spoke to Priya
  at the call centre"). People who share a surname. A first name alone later for someone named in full earlier.
* **Phone numbers with extensions,** in every form people write them ("ext 204", "x204", ", extension 204", "#204").
  The extension is part of the span.
* **Codes of letters and digits** that are a person's own: member, policy, patient, customer, loan and account
  numbers. Write them in groups separated by dashes, spaces, slashes or dots, or run together, in upper or lower case.
* **Secrets:** PINs, door and alarm codes, one-time and verification codes, recovery codes, passwords (a word and
  digits, a passphrase, random characters), Wi-Fi passwords, answers to security questions; API keys, tokens and
  private keys in the formats their providers use; a password inside a connection string
  (`postgres://app:⟦password or access code|…⟧@db.internal/prod`).
* **Emails** written plainly and obfuscated ("j dot smith at gmail dot com", "[at]", spaces around the @).

And in every conversation, two or more **look-alikes** that stay unmarked, written in the same shapes as the details
where you can: order, invoice, ticket and case numbers; booking references, reservation codes and confirmation
numbers; tracking numbers; SKUs; versions and build numbers; commit hashes; request and error IDs; IP addresses;
times, dates that aren't a birth date, and amounts; a company's own phone number, email or address; public figures
and fictional characters. In `developer`, put real-looking settings beside the secrets (ports, hosts, log levels,
feature flags, colours) and mark only the secret values.

Never copy formats, wording or examples from a dataset or a benchmark you know of. Write what people really send.

## Locales

Two in three conversations in English, from anywhere English is written (US, UK, Ireland, Canada, Australia, India,
Nigeria, South Africa, Singapore), with that place's formats for phones, addresses, IDs and dates. The rest in the
locales you're given (German, French, Spanish, Dutch, Italian, Portuguese, Polish, Swedish...), written as people
there write, with their formats. People mix languages: an English request around a German letter is fine.

## Output

Write a JSON Lines file to the path you're given, one conversation a line:

```json
{"family": "banking", "locale": "en_GB", "messages": ["hi can you help me write to my bank...", "..."]}
```

Each message holds its markup, as `RULES.md` says (`⟦label|text⟧`). Before you finish, check with Python that:

* every line parses, with `family`, `locale` and a list of two to eight non-empty `messages`;
* every `⟦` has a matching `⟧`, a `|` between, and one of `RULES.md`'s labels, including `password or access code`
  and `api key`;
* no span is empty or starts or ends with a space (and no value you make up holds `|`, `⟦` or `⟧`, which would break
  its markup);
* the conversations are as many as you were asked for, and no two are alike.

Report how many conversations you wrote, how many details of each label, and how many have none.

## For whoever hands this out

Round 10's protocol (`../../PROTOCOL.md`, "Round 10") asks for 300 conversations: `support` 50, `banking` 50,
`travel` 40, `helpdesk` 40, `developer` 40, `forms` 40 and `nothing` 40. Give each agent one family, a count, a
locale mix and a path under `r10/chats/` (`round10.py` reads `r10/chats/*.jsonl`). Give the agents this brief and
`RULES.md` only. They never see PII-TRACE, `chatgen.py` or its output, the locked chat test or its brief, or one
another's conversations. A fifth of the conversations is held out for dev by `round10.py`, by a hash of each
conversation's first message.
