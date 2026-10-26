# The third locked test: conversations (round 10)

The clean readout of round 10 (`../PROTOCOL.md`, "Round 10"): conversations people send an AI assistant, built before
any round 10 training data and kept from everyone who makes that data, judged blind, and scored once, after round 10's
model is chosen. PII-TRACE's test half is read beside it, but round 10's data was aimed at PII-TRACE's formats, so it
is the kinder test. This one says whether the gains hold on conversations nobody aimed at.

## What it holds

* **150 written conversations** by ten new agents, 15 each, one theme each (`WRITERS.md`): `health`, `housing`,
  `family`, `work`, `money`, `accounts`, `shopping`, `code`, `writing`, `other`. Each agent gets `WRITERS.md`,
  `../docgen/RULES.md`, a theme, a count, a locale mix and a path (`locked3/W01.jsonl` to `W10.jsonl`), and nothing
  else: not PII-TRACE, not `round7/chatgen.py` or its output, not round 10's source B brief or chats, not another
  writer's file. None of them writes any round 10 training data.
* **300 WildChat conversations** from WildChat-1M's shards 8 and 9, drawn once by `../../locked3_draw.py`, English
  only, as every earlier locked chat set was. A candidate has 1 to 20 user turns, none empty, and at most 3,000 words
  of user text. It is left out if its conversation hash is in the second locked test's chats or any other set's
  manifest, or if a user turn of 40 characters or more repeats a text in them or in an earlier candidate. 150 are
  drawn from the conversations WildChat marks `redacted` that hold one of Presidio's markers in a user turn, and 150
  from those it found nothing in, with `random.Random(103)`. Each marker is filled with a made-up detail (a name, an
  email, a phone or a card number), which counts as a detail as a writer's mark does. `draw.json` here holds the draw
  without WildChat's text, so it can be rebuilt and checked. Only user turns are read and scored.

## Order of work

1. Write this folder's two briefs, and the draw's seed and rule, before any round 10 training data exists. Done
   when this file is merged.
2. Draw the WildChat conversations and have the ten agents write theirs. Validate every file (the checks in
   `WRITERS.md`), and check by 8-word runs that no written conversation copies another, an earlier locked set or any
   training data. Record the files' SHA-256 in `INTEGRITY_LOG.md`.
3. Only then hand out round 10's source B brief and generate source A's data.
4. Nobody reads the files' contents again until round 10's model is chosen and frozen, its weights' hash written in
   `../PROTOCOL.md`.

## Judging, after the choice and before any score

Judged blind, to `../wider_rules.md` (the "Chats" section and its labels, with round 10's two):

* **Systems run**, each one message at a time and over the whole conversation: veil alone (GENERIC, one Redactor a
  conversation); round 7's model and round 10's chosen model, alone and through `TaggedRedactor`'s redactor; and
  PII-Tracer, alone.
* **The written conversations**: the writers' marks are the details. Every run of words a system hides that no mark
  covers is judged, so a missed mark the writer left out isn't counted against a system.
* **The WildChat conversations**: the details put in Presidio's markers are details, and every other run of words
  any system hides is judged. A detail Presidio missed that no system hides isn't counted as missed; this is how the
  earlier locked tests read real chats, and it is reported as a limit.
* The runs to judge are pooled, shuffled and shown with their message, without the system that hid them. A second
  reviewer judges a random fifth again; agreement is reported as raw agreement and Cohen's kappa. A second labeller
  marks 15 of the written conversations from scratch, and the models are scored on both labellings of those 15.

## Scoring, once

* **Found**: a private person's detail counts as found when every word of it is hidden. **Other words hidden**: of
  the words no detail covers, the share hidden (public names and placeholders count here, so hiding them is a
  mistake; `business` and `unsure` spans count neither way).
* Reported for each system, one message at a time and whole conversation, on the written and WildChat conversations
  apart and together, by label, and for details mentioned more than once (every mention hidden).
* 95% intervals from 2,000 bootstrap resamples over conversations, seed 0; differences between systems paired. A
  difference whose interval holds zero is a tie.
* Reported whichever way it falls, beside PII-TRACE's test half and the second locked test.
