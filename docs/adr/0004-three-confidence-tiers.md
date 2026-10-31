# ADR 0004: Three confidence tiers, set from dev

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

The confidence score starts at 0.95 and loses points for signs of trouble, such as a missing receipt
or fields with no evidence box. On the dev split, those raw values didn't mean what they said:

| Raw score | Claims | Correct |
|---|---:|---:|
| 0.95 | 116 | 115 |
| 0.70 to 0.85 | 47 | 40 |
| 0.60 or lower | 5 | 0 |

## Decision

Map the raw score to the rate seen on dev, smoothed as (correct + 1) / (claims + 2): 0.98, 0.84 and
0.15. Anything below 0.9 that would otherwise be ready for approval is labelled "Check closely before
approving" in the console. Fraud reviews and document requests keep their own routes.

I used tiers rather than a fitted curve because 168 claims can't support anything finer, and the
middle of the raw scale wasn't ordered: 0.80 did better than 0.85. Five claims is a thin basis for the
bottom tier, so that number is rough.

The mapping was set on dev only. `test` and `test-heldout` show whether it holds.

## Result

Calibration error on `test` was 0.043, so the tiers meant about what they claimed overall. The top
tier did worse than it claimed, though: 104 of 110 correct (94.5%, not 98%), including two wrong
payouts and four underpaid honest claims. STP@99 fell from 74.7% on dev to 2.5% on `test`. On the
held-out split calibration error was 0.153. Good average calibration isn't enough to skip review.

## Consequences

Scores are coarse, but a reviewer can trust what each tier means. A person still approves every
payout, so routing decides how closely a claim gets read, not whether it gets read.
