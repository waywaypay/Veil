# Round 7 training data: integrity notes (working log)

Kept while the data is made; the repo's `benchmarks/judged/INTEGRITY.md` is written from it when round 7 is done.

## Order of events

* 18 Oct 2026: the second locked test's text was drawn and its documents commissioned (locked2/INTEGRITY_LOG.md)
  before any round 7 data existed.
* 19-20 Oct: round 7 data commissioned: ten agent-written waves aimed at round 6's misses (w1_t01-t10, 40 documents
  each), a forms wave (w2_f01-f10, 40 each; added after the user asked for tax, school and other forms), TweetNER7's
  test tweets judged (judge7/tweetner_b0-b19), WildChat-4.8M shards 40-48 chats judged (judge7/wc_b0-b7), 300 real
  Enron emails labelled by hand (r7_enron/batch_00-14). None of these sources overlaps a locked test: TweetNER7
  positions and WildChat shards differ, Enron excludes both tests' ids and the second test's mailboxes.
* Every agent was told to read only `docgen/RULES.md` (and, for Enron, `r7_enron/LABEL.md`) plus its own input, and
  to keep working files in its own folder. Each finished agent's transcript is checked for paths outside those.

## Validation of each output (R.unmark round-trip, labels in the known set; judge files: one verdict per span, keys
## 0..n-1, verdicts in the allowed set; Enron: stripping the markup gives back the input exactly, ids in order)

| output | result | transcript paths |
|---|---|---|
| w1_t01 (names in every casing) | 40 docs, 1,565 spans, clean | rules + own folder only |
| w1_t02 (emails) | 40 docs, 784 spans, clean | rules + own folder only |
| w1_t05 (international addresses) | 40 docs, 419 spans, clean | rules + own folder only |
| w1_t07 (social posts and handles) | 40 docs, 617 spans, clean | rules + own folder only |
| w1_t06 (business vs personal) | 40 docs, 433 spans, clean; writer cut off once by a rate limit, resumed | rules + own folder only |
| w1_t08 (AI chats) | 40 docs, 374 spans, clean | rules + own folder only |
| w2_f08 (employment and onboarding forms) | 40 docs, 511 spans, clean; Opus/medium | rules + own folder only |
| w1_t10 (technical data) | 40 docs, 541 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f02 (US tax forms) | 40 docs, 356 spans, clean; Opus/medium (restarted); company EINs left unmarked, individuals' marked | rules + own folder only |
| w1_t04 (statements and securities) | 40 docs, 270 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f07 (housing and utilities forms) | 40 docs, 528 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f05 (government service forms) | 40 docs, 516 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f03 (school and university forms) | 40 docs, 598 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f06 (insurance applications and claims) | 40 docs, 628 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f10 (web-form submissions and exports) | 40 docs, 464 spans, clean; Opus/medium | rules + own folder only |
| w2_f04 (childcare, clubs, community forms) | 40 docs, 816 spans, clean; Opus/medium (restarted) | rules + own folder only |
| w2_f09 (healthcare intake and records) | 40 docs, 484 spans, clean; Opus/medium | rules + own folder only |
| w2_f01 (tax forms outside the US) | 40 docs, 453 spans, clean; Opus/medium (restarted); all 20 waves done | rules + own folder only |
| tweetner_b0 | 246 verdicts, clean | rules + own folder only |
| tweetner_b1 | 233, clean | same |
| tweetner_b2 | 251, clean | same |
| tweetner_b3 | 260, clean | same |
| tweetner_b4 | 256 (1 unsure), clean | same |
| tweetner_b5 | 232, clean | same |
| tweetner_b6 | 250 (1 unsure), clean | same |
| tweetner_b9 | 240 (2 unsure), clean | same |
| tweetner_b10 | 256 (3 unsure), clean | same |
| tweetner_b11 | 255, clean | same |
| tweetner_b13 | 230 (1 unsure), clean | same |
| tweetner_b14 | 238 (1 unsure), clean | same |
| tweetner_b15 | 233, clean (its judge was stopped after writing the file; validated here) | same |
| tweetner_b19 | 202 (1 unsure), clean; Opus/medium | same |
| tweetner_b16 | 221 (2 unsure), clean; Opus/medium | same |
| tweetner_b17 | 233 (1 unsure), clean; Opus/medium | same |
| tweetner_b18 | 258 (3 unsure), clean; Opus/medium; tweet judging complete | same |
| tweetner_b12 | 223 (1 unsure), clean; judge noted an unlabelled phone number in one tweet's text | same |
| wc_b0 | 807, clean | same |
| wc_b1 | 780, clean | same |
| wc_b2 | 1,016, clean | same |
| wc_b3 | 1,206, clean | same |
| wc_b4 | 883 (2 unsure), clean | same |
| wc_b5 | 575, clean | same |
| wc_b6 | 539 (2 unsure), clean | same |
| wc_b7 | 318, clean; chat judging complete, dl7/r7_chat_docs.json built | same |
| Enron batch 00 | 20 emails, 270 spans, round-trip exact | LABEL.md, rules + own folder |
| Enron batch 01 | 20 emails, 325 spans, exact | same |
| Enron batch 02 | 20 emails, 324 spans, exact | same |
| w1_t03 (OCR'd and scanned copies) | 40 docs, 266 spans, clean | rules + own folder only |
| w1_t09 (dates of birth among other dates) | 40 docs, 679 spans, clean; writer made a local venv in its own folder for calendar conversions | rules + own folder only |
| tweetner_b7 | 234 (6 unsure), clean | same |
| tweetner_b8 | 240 (2 unsure), clean | same |
| Enron batch 03 | 20 emails, 321 spans, exact; personal fax lines left unmarked (LABEL.md), as batch 01 did | same |
| Enron batch 04 | 20 emails, 333 spans, exact | same |
| Enron batch 06 | 20 emails, 272 spans, exact | same |
| Enron batch 07 | 20 emails, 340 spans, exact | same |
| Enron batch 08 | 20 emails, 220 spans, exact | same |
| Enron batch 09 | 20 emails, 405 spans, exact; Opus/medium; Enron labelling complete (300 emails) | same |
| Enron batch 10 | 20 emails, 297 spans, exact; Opus/medium | same |
| Enron batch 11 | 20 emails, 255 spans, exact; Opus/medium | same |
| Enron batch 12 | 20 emails, 287 spans, exact; Opus/medium | same |
| Enron batch 13 | 20 emails, 271 spans, exact; Opus/medium | same |
| Enron batch 14 | 20 emails, 190 spans, exact; Opus/medium | same |
| Enron batch 05 | 20 emails, 249 spans, exact; one all-employee memo with zero spans | same |

## Judging conventions the judges reported (training data; recorded so the labels' meaning is known)

* Tweets: school and youth athletes, village-club officials, local coaches, people thanked in a tweet ->
  `personal:name`; pro and junior-league athletes, musicians and authors presented in their work, people named as the
  subject of a news report -> `public`. Deities: "Jesus" public, bare "God"/"Lord"/"Allah" ordinary. Hashtags that
  are a public figure's name -> public; topic hashtags -> ordinary. Handle-like strings without @ for private people
  -> `personal:username`.
* Chats (WildChat-4.8M shards 40-48 are dominated by Russian job adverts): job titles, benefits, places, products ->
  ordinary; recruiters' own phones, personal emails and Telegram handles -> personal; job-board channels -> public;
  company hotlines and merchant ids -> business. One judge (wc_b1, item 78) labelled the passwords in a pasted
  credential dump `personal:username` for want of a password label; the leaked emails there are `personal:email
  address`. A pasted AT&T account PIN -> `personal:account number`; a card's last four -> `personal:ssn` (nearest
  label). Names a summarising model made up for a recruiter contact (wc_b2 items 37, 38, 87) -> `personal:name`.
* Enron: journalists' bylines with their phone and email left unmarked (public, per LABEL.md); a wire-service
  staffer's From line marked; line-wrapped Lotus names marked as one span including the newline; truncated
  header addresses marked as the whole truncated token; the "x" of an extension inside the phone span.

## Rate limit

The weekly limit on the agents' default model stopped about seventeen agents on 19-20 October; each was resumed
after the reset with its saved work, or relaunched. Files from resumed agents are validated like the others.

* From 20 October (user's instruction): agents launched after this point run on Opus at medium effort.

## Data complete (20 Oct, 02:14 UTC)

All sources done and validated: 20 agent waves (800 documents), 20 tweet batches (TweetNER7: 7,929 tweets kept, 38
dropped because veil's rules found a phone, email or card number the corpus doesn't tag, unsure items dropped),
8 chat batches (813 training turns), 15 Enron batches (300 emails, 4,228 spans). The tweet builder originally shared one
veil Redactor across all tweets, which slowed as its mapping grew; it now makes a fresh one per tweet (same output).

Training mix (`round7.py build`, 18,919 chunks): documents (round 7 agents) 2,038 chunks / 18,006 labels; documents
(rounds 4 and 6) 1,067 / 8,606; augmented copies 2,086 / 17,609; lists 736 / 27,948; tweets 5,000 of 6,341 / 3,147;
chats 1,260 / 923; Enron 632 / 6,920; forms (fresh) 1,500 / 11,340; tax forms (fresh) 600 / 1,425; round 6 replayed
4,000 of 11,212 / 17,267. Segment 1 (r7_1) started from ft/r6_3 at offset 0.

## Employer EINs (20 Oct, user's decision)

The user decided employer EINs are hidden (marked `tax id`), as the writing rules and veil already say. Both locked
tests already mark every EIN. In training, 30 EIN-shaped numbers next to an EIN, employer, TIN or tax-ID label had been
left unmarked as the organisation's own detail (w1_t04, w1_t06, w2_f02, w2_f05, w2_f06, w2_f08, w2_f10, g07, fam02);
they were marked `tax id` by script, originals kept in ein_relabel_orig/. Takes effect from segment 3's mix.

## W-2 sets (20 Oct)

Commissioned on Opus/medium after the user set a >99.5% target for W-2s: locked W-2 test w2test/T1-T4 (75 each) and
training W-2s w2train/A1-A2 (50 each), all told to read only docgen/RULES.md and w2_spec.txt. w2gen.py written by
hand (not by agents) from the spec, without looking at any agent's W-2s. PROTOCOL.md amended before any W-2 test
text existed.

## W-2 and tax-form sets, validated (20 Oct)

All 14 agents (Opus/medium) finished; every file passed the round-trip and label checks and every transcript shows
only the rules, the spec and the agent's own folder.

| set | docs | spans |
|---|---|---|
| w2test T1 (PDF extraction, payroll prints) | 75 | 1,071 |
| w2test T2 (OCR, photos, carbons, corrections) | 75 | 783 |
| w2test T3 (boxes, JSON/HTML, CSV, EFW2, W-2c) | 75 | 1,286 |
| w2test T4 (emails, chats, tickets, household) | 75 | 882 |
| taxtest K1 | 50 | 493 |
| taxtest W9W4 | 50 | 480 |
| taxtest F1099 | 50 | 730 |
| taxtest F1040 | 50 | 823 |
| taxtest F1095 | 50 | 868 |
| taxtest F1098 | 50 | 591 |
| w2train A1, A2 | 100 | 1,067 |
| taxtrain B1, B2 | 100 | 1,309 |

Limitation to report: most locked-test writers built their documents with their own generator scripts or templates
(T1-T4, K1, F1095, F1040, part of F1099); each is independent of w2gen.py/usgen.py, but wording within a rendering
repeats more than in hand-written documents. Labelling calls the writers reported: SSA/RRB claim numbers as `ssn`;
investor and shareholder numbers as `customer id`; an estate's decedent as a private person; Form 8879 self-select
PINs left unmarked (only the IP PIN is marked, per the spec).

## W-2s from the real IRS form (20 Oct, afternoon)

After segment 3 improved the generated W-2 dev slices (88.5 to 98.5%) but not the held-out agent-written W-2s (88.1 to
84.7%), a third source was added: w2real.py fills the IRS's own fillable Form W-2 PDF (irs.gov/pub/irs-pdf/fw2.pdf, six
fillable pages of two copies each) with made-up people and employers (Faker, several locales for names), and extracts
text as real tools do: pdftotext (layout, raw, reading order), pypdf, and Tesseract OCR of the rendered page at
110-250 dpi with skew, blur, noise, fading and JPEG damage. Labels are the values put into the fields, found again in the
text (every occurrence, one per copy, whole tokens; fuzzy for OCR); a document with a value that can't be found, or
that matches more often than the copies, is dropped (kept: 82% of PDF-extracted, 45% of OCR). Shards: trainA, trainB
(600 each, seeds 51, 52) and dev (150, seed 53). Not used for the locked W-2 test, whose writers are independent.
