# ADR 0002: The claim form can't clear a failed receipt check

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

v1 raised too many false fraud alarms. Most came from one check: receipt items not adding up to the
total. Usually the cause was an OCR misread on one item, not fraud. So I added a shortcut: if the
items don't add up but the printed total matches the amount on the claim form, accept it.

The false alarms I tested it on went away, so I shipped it. Then, while testing the public demo, one of
the 20 demo cases disagreed with the benchmark. Packet `2bfb1e4beda9` is a planted forgery: its items
sum to 108.97, but the printed total and the claim form both say 179.97. The system would have
recommended a payout.

The shortcut was wrong in principle. Someone who inflates a receipt also writes the inflated amount
on the form. Two documents from the same person agreeing proves nothing.

## Decision

The check compares the printed total only with amounts read from the receipt itself. The claim form
is never evidence that a receipt is genuine. A regression test holds this case in place.

I threw away the 60 predictions made with the shortcut and restarted the dev run from zero.

## Consequences

- Some false alarms come back. They cost a reviewer a minute. A missed forgery costs real money.
- Without the shortcut, dev accuracy is 93.3%, up from 90.7% in v1, with 100% fraud recall and false
  alarms on honest claims down from 10.2% to 6.8% (the other fixes held up).
- Rule for later changes: a fix for false alarms has to name what a forger could do with it.
