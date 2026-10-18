# Judging marked spans: is this a private person's detail?

You get a JSON file of items, each `{"text": ..., "spans": [[start, end], ...]}`: a tweet, a forum post or a piece of
a press release, and stretches of it that a dataset's labels or a redaction tool marked. For each span, read it in
context (`text[start:end]`, Python offsets) and give one verdict.

## Tweets and posts (`social_*.json`)

* `personal:<label>`: a private person's detail, which a redactor should hide. Labels: `name`, `username`,
  `email address`, `phone number`, `street address`, `date of birth`, `account number`, `credit card number`,
  `customer id`, `employee id`, `tax id`, `ssn`, `passport number`, `driver license number`, `iban`.
  * A private person: the poster's friends, family, classmates, colleagues, a local shopkeeper, a person the poster
    talks to or about who isn't known to the public.
  * An `@handle` of a private person's account is `personal:username` (cover the whole handle, `@` included).
* `public`: a public figure (politician, celebrity, athlete, musician, actor, author, journalist or presenter in
  their work, a CEO in the news, a historical figure), someone named in a news report as its subject, a fictional
  character, a band, a brand's, a media outlet's or an organisation's account or handle, a fan account named after
  a celebrity (`@BiebersFairies`).
* `ordinary`: not a person's detail at all: a word, a place, a company, a product, an event, a hashtag topic, a
  span that is only part of a word or a mangled piece.
* `unsure`: you can't tell from the text whether the person is private or public. Use it sparingly: most handles in
  a casual tweet reply (`@daxx_d24 lol same`) are private people; a full name in a news-style headline is public.

If a span covers more or less than the detail (`@ BBCNews` vs `BBCNews`, `Mr Smith` vs `Smith`), judge what it
mostly is: the verdict applies to the detail it overlaps.

## Press releases (`buster_judge.json`)

The spans are what a model marked outside the companies the dataset labels. Verdicts:

* `person`: any person's name or detail (an executive, a lawyer, a spokesperson, a contact), public or not.
* `business`: a company's or office's contact detail: its street address, phone, fax, email, website.
* `ordinary`: anything else: a company or fund name the dataset missed, a product, a place, a date, an amount, a
  ticker, a term.

## Output

Write a JSON file mapping each item's index (as a string) to a list of verdicts, one per span, in order:
`{"0": ["public", "personal:username"], "1": ["ordinary"], ...}`. Every item and every span gets a verdict. Check
with Python that the file parses and that the counts match, and report the verdict counts.

## Test sets (`social_test_b*.json`, `enron_test_b*.json`)

The spans are everything any redaction system hid in a text, with the dataset's persons and handles. Tweets and
posts (`social_test`) take the tweets' verdicts above. Emails (`enron_test`, from Enron's mailboxes, 2000–2001) take
the same verdicts with one more:

* `personal:<label>`: a private person's detail. Enron's employees and the people they write to are private people:
  their names, their work and personal email addresses (`first.last@enron.com`), direct lines, mobiles, home
  addresses.
* `public`: a public figure (a politician, a regulator or official acting publicly, a celebrity, Enron's chairman
  or CEO in the news), a fictional character.
* `business`: a company's or office's own contact detail or address (a switchboard, a fax line, `1400 Smith Street`,
  a shared mailbox, a conference room), or a company's name that merely contains a surname.
* `ordinary`: anything else: a word, a place alone, a company, a date, an amount, a deal or contract number.
* `unsure`: you can't tell.

Write verdicts the same way, one list per item, one verdict per span, in order.


## Chats (`locked_chats_b*.json`)

Messages people sent to an AI assistant (WildChat). The spans are words a redaction system hid; details the dataset
already knows about (made-up names, emails and phones written in where its de-identifier took something out) are not
among them. Same verdicts as tweets and posts: `personal:<label>` for a private person's detail (the user, their
family, friends, colleagues, a landlord, a teacher; their contact details and numbers; a username in a pasted path),
`public` for a public figure, an author cited in a reference list or a fictional character (including characters in
a story or role-play the user is writing), `ordinary` for anything else (words, places, companies, products, code
identifiers, placeholder names like John Doe), `business` for an organisation's own contact details, `unsure` when you
can't tell.

## Locked sets

Files named `locked_*` are the final test. Judge every span on its own merits; you are not told which system hid it.
