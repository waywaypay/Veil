# Writing conversations with an AI assistant for a test set

Read `../docgen/RULES.md` first: its labels, what never to mark, and its rule that everyone you write is made up all
apply here. This brief says what to write instead of documents, and how to hand it in. What you write is a test: no
model is trained on it, and it is scored once.

You are writing what people type to an AI assistant in their everyday lives, when what they need help with involves
real people: themselves, their family, their colleagues, the people they deal with. Write what they would actually
send, with the details they'd actually include, no more and no fewer.

## What a conversation is

* Only the user's messages: one to eight of them, in order, each answering an assistant reply you don't write.
* Under 500 words of the user's text in all, most well under 200. Pasted text (an email, a letter, a log, a table,
  a chat transcript, a CV) goes inside the message as it would be pasted.
* Each message is one string, line breaks and all.
* Write as people do: some carefully, many in a hurry, in lower case, with typos, abbreviations, half sentences, and
  in a mix of languages where that's natural.

## Your theme

You're given one theme, a number of conversations, a locale mix and an output path. The themes:

| theme | for example |
|---|---|
| `health` | booking or changing appointments, a letter to a GP or insurer, a carer's notes, a prescription mix-up |
| `housing` | a landlord, a letting agent, neighbours, a deposit dispute, a mortgage, utilities, a move |
| `family` | school letters, childcare, a will or an estate, a wedding or a funeral, an elderly parent's affairs |
| `work` | HR, payroll, a reference, a CV and cover letter, a rota, a grievance, onboarding a colleague |
| `money` | a bank, a card, a loan, a tax return, a refund, a scam they fell for, splitting a bill |
| `accounts` | logins, locked or hacked accounts, two-factor codes, recovery, shared family accounts, smart home devices |
| `shopping` | orders, returns, deliveries, warranties, a complaint, a marketplace sale |
| `code` | debugging, deploying, a CI failure, a database or a cloud console, with config, logs and keys pasted in |
| `writing` | a story, a speech, a social post, a translation, a letter to a friend, about real and fictional people |
| `other` | anything else people ask an assistant: travel, legal, school work, a club, a community group |

## What to put in

Whatever the situation calls for: names (written every way people write them), emails, phone numbers (with
extensions where an office has them), home addresses, dates of birth, account, card, policy, member, patient,
employee and customer numbers, national and tax IDs, passport and licence numbers, usernames, passwords, PINs and
codes, API keys and tokens. People give some details more than once, written differently the second time, correct
themselves, and name someone in full and then by first name only. Let that happen where it would.

Just as much, put in what is not a private person's detail, as it would really come up: public figures, characters in
a story the user is writing, companies and their phone numbers and offices, order, booking, ticket and tracking
numbers, versions and hashes, example and placeholder values (`John Doe`, `sk-...`, `123 Main St` in a template),
dates, times and amounts. Some conversations should have no personal details at all.

Never copy formats, wording or examples from a dataset or a benchmark you know of.

## Locales

About two in three conversations in English, from anywhere English is written; the rest in the locales you're given,
with their own formats for names, phones, addresses and IDs.

## Output

Write a JSON Lines file to the path you're given, one conversation a line:

```json
{"theme": "housing", "locale": "en_IE", "messages": ["...", "..."]}
```

Each message holds its markup, as `RULES.md` says (`⟦label|text⟧`), with every private person's detail marked. Before
you finish, check with Python that:

* every line parses, with `theme`, `locale` and a list of one to eight non-empty `messages`;
* every `⟦` has a matching `⟧`, a `|` between, and one of `RULES.md`'s labels;
* no span is empty or starts or ends with a space, and no value you make up holds `|`, `⟦` or `⟧`;
* the conversations are as many as you were asked for, and no two are alike.

Report how many conversations you wrote, how many details of each label, and how many have none.
