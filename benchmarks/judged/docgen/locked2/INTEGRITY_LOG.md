# The second locked test: integrity notes

* Made on 18-20 October 2026, before any round 7 training data existed (PROTOCOL.md, "Round 7 on"). Its chats
  (WildChat-1M shards 8 and 9), Enron emails (the corpus's third file, mailboxes neither earlier sample used) and
  tweets (positions 1,400-2,099 of the test splits' shuffle) were drawn on 18 October; no text overlaps the first
  locked test or the earlier tests by hash or by text.
* Ten agents wrote the 150 documents (M01-M10), each told to read only `docgen/RULES.md`. Their transcripts show no
  path outside `locked2/` and the rules. Four of them (M01, M05, M08, M10) finished their files but were cut off by
  an API rate limit before reporting; their files were validated here (15 documents each, every span well formed).
* An eleventh writer (M11, forms of many kinds) was added on 18 October, after the protocol was amended and before
  any round 7 model existed; it was cut off by the same limit before writing and resumed on 20 October.
* M11 finished on 20 October: 15 forms, 347 spans, every span well formed; its transcript shows only `docgen/RULES.md`
  and its own folder. The 8-word-run check against the other locked-2 documents, the first locked test's documents and
  round 7's waves found only form boilerplate in common ("I declare that the information I have provided", an Italian
  GDPR consent clause); no copied content.
