# The locked tests: what happened along the way

* L06 (correspondence): its agent listed the file names in locked/ after writing its documents; it opened none.
* L03 (healthcare): its agent listed the file names in locked/ when creating its folder; it opened none, and read
  nothing under docgen/ but RULES.md.
* No agent writing a locked document was given, or reported opening, any training or earlier test document.
* L01 (US tax and payroll): its agent listed the file names in locked/ when creating its folder; it opened none.
* Near-duplicates: for each locked document, the share of its 8-word runs found in its closest training document
  (the 720 agent-written training documents): median 0%, 95th percentile 5.7%, highest 35%. The four over 20% are
  US tax forms (W-9, K-1, W-4, 1099) whose shared runs are the IRS's own form text; no personal detail lies in a shared
  run.

## Second labeller and second reviewers (18 October 2026)

* The two second labellers of the 30 relabel documents opened only `docgen/RULES.md`, their input file and their own
  work files (checked in their transcripts: no read, listing or script touched `locked/L*.jsonl`). Their spans
  agreed with the first labels on 650 of 653 exactly and 652 overlapping; the differences were a hospital's EIN
  (left as company data), a bare street name, "Sophie B (Ōtautahi)" as a username or a name, and a phone span with
  or without "Ext. 312".
* The three second reviewers of a random fifth of the judged items worked in `judge4_second/`, a copy of the rules
  and their items only, with the first verdicts kept out of the folder; their transcripts show no path outside it.
* Both kinds of second opinion come from the same model under the same written rules as the first, so their
  agreement measures how consistently the rules are applied, not how far people would agree.
* Second-review agreement (random fifth of the items, before the final model's spans were pooled): chats 376 spans,
  98.7% (kappa 0.981), private or not 98.9%; Enron 335 spans, 99.7% (kappa 0.990), private or not 100%; tweets 263
  spans, 96.2% (kappa 0.942), private or not 98.1%. The tweets' differences are mostly handles one reviewer took for
  a public figure's (journalists, an MP, an academic) and the other for a private person's.
* Conflicting verdicts on overlapping spans of one text, after the earlier rounds' spans were judged: 7 private-person
  spans in tweets and 1 in Enron sit wholly inside a span judged public (a private handle inside a run of handles
  judged by its public ones; "Skilling" inside "Mr. Skilling"). Scoring counts such words as a private person's, the
  stricter reading. Spans of Jeff Skilling and Ken Lay in internal mail were judged public by some reviewers and
  private by others; the rules' "in the news" leaves it open.
* Before any locked score: the scorer scored only tweets and Enron a second time with the smallest spans, though the
  protocol says every judged set; chats were added to it (a judged span holding a smaller private detail, a filled-in
  one or a judged one, is set aside and the details inside it are scored). Found while a reviewer reported long
  Arabic spans judged a name because a name sat inside them.
* The second-review sample of the spans the earlier rounds added was drawn from those new items only (a fifth of
  each set's new items), not from the earlier items left unsampled.
* Second-review agreement over both samples (a fifth of the first items and a fifth of those the earlier rounds
  added): chats 887 spans, 98.2% (kappa 0.974), private or not 98.5%; Enron 673 spans, 96.7% (kappa 0.929), private
  or not 97.8% (15 of the 22 differences are one marketing email's tracking number, judged ordinary first and a
  customer ID second); tweets 429 spans, 97.0% (kappa 0.953), private or not 98.8%. The second reviewers' transcripts
  show no path outside judge4_second/.
* The chosen model (round 6, segment 3 at 0.4) was frozen at 09:02 UTC and its hash committed before scoring. Its
  spans not yet judged (25 in tweets, 30 in Enron, 82 in chats) were judged blind, and a fifth of them again. Final
  second-review agreement: chats 900 spans, 98.2% (kappa 0.974), private or not 98.6%; Enron 680, 96.6% (kappa
  0.927), private or not 97.8%; tweets 434, 97.0% (kappa 0.953), private or not 98.8%.
* Near-duplicates between training text (every chunk of the mixes for rounds 2 to 6) and the locked tweets, emails
  and chats, as the share of a text's 8-word runs found in training: tweets median 0%, 95th percentile 0%, highest
  75% (one, the stock "I posted a new photo to Facebook" plus a link); Enron median 0%, 95th percentile 0.6%,
  highest 7.2%; chats median 0%, 95th percentile 0.3%, highest 20% (a user's own stock prompt wording).
* Hidden runs no verdict covers, at the scored thresholds: none for veil alone or any model alone on tweets and
  Enron, none for any model alone on chats; veil alone 15 on chats (a conversation's redactor hides a name in later
  turns it learned earlier, which the pool, turn by turn, didn't), veil with a model 7 to 27 on Enron and 10 to 32
  on chats (every spelling of an added name). Each counts as another word hidden. The scorer's own printed count
  overstated these, leaving out spans judged ordinary; the scores themselves don't depend on it.
