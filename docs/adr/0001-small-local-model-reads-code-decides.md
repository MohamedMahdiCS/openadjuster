# ADR 0001: A small local model reads; code decides

- **Status:** Accepted
- **Date:** 2026-10-29

## Context

OpenAdjuster has to run on a laptop with no paid APIs, and the total model download had to stay
small. I smoke-tested the single-prompt approach (policy, records and documents in one prompt; the
model returns the decision) on the 25-packet `smoke` subset of ClaimDocBench `dev`:

| Model (Ollama) | Input | Decision + amount correct | Fraud caught | Fields read correctly | p50 latency |
|---|---|---:|---:|---:|---:|
| `bonsai-2:4b` (1.6 GB) | page images | 16% | 0% | 94% | 23 s |
| `bonsai-2:4b` | OCR text | 0% | 0% | 91% | 24 s |
| `bonsai-2:2b` (0.9 GB) | page images | 0% | 0% | 63% | 10 s |
| `bonsai-2:2b` | OCR text | 0% | 0% | 66% | 8 s |

The 4B model reads documents well but can't be trusted to apply the policy or spot fraud: it
approved almost everything. `lfm3-vl:2b` was a candidate but needs a newer Ollama than Homebrew ships.

## Decision

- **Reading:** Apple Vision OCR (on-device, no download) for text and boxes, run in English-first
  and Chinese-first orders, keeping the Chinese pass only when it finds Chinese text.
- **Receipt items and totals:** parsed with code (straighten the page using the TOTAL row, pair
  prices with descriptions in order). 91% of dev receipts parse exactly; the rest are OCR misreads.
- **Header fields** (clinic, patient, dates, receipt number, claim form answers): `bonsai-2:4b`
  copies them from numbered OCR rows and says which row it used, which gives evidence boxes.
- **Item categories** (is this a vitamin? a cosmetic?): `bonsai-2:4b`, one call per receipt.
- **Everything else is code:** registry lookups, cross-document fraud checks, and the policy
  rules engine shared with ClaimDocBench.

## Consequences

- The model never does arithmetic or remembers the policy, so a 4B model is enough.
- Most errors are now OCR errors, which can be measured and handled (re-reading a cropped line,
  lowering confidence) instead of hoping a bigger model fixes them.
- Using the same rules engine as the benchmark is deliberate: a real insurer would also have one
  policy implementation. The benchmark's difficulty is reading and checking the documents, which
  OpenAdjuster has to do from pixels.
