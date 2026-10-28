# OpenAdjuster

An open-source AI claims adjuster for outpatient medical insurance claims. It reads the
documents people actually submit (phone photos of receipts, scanned medical certificates,
handwritten claim forms, in English, Malay or Chinese), checks them against the policy and the
insurer's records, catches tampering, ignores instructions hidden in documents, and recommends
what to pay. A person approves every payout.

It runs entirely on a laptop with a 1.6 GB open model. No claim data leaves the machine, and it
costs nothing per claim.

![Review screen: a forged receipt with the wrong patient name is sent to fraud review](docs/images/review-fraud.png)

<!-- RESULTS:START -->
Results on [ClaimDocBench](https://github.com/MohamedMahdiCS/claimdocbench) are added after the
evaluation runs finish.
<!-- RESULTS:END -->

## Why I built this

<!-- OWNER: 3-4 sentences in your own words. -->

## How it works

The main design decision: **the model reads, code decides.**

In a first experiment I gave a 4B model the policy, the member's records and the documents in one
prompt and asked for a decision. It read 94% of the fields correctly but got only 16% of the
decisions right and caught none of the fraud, because it was approving almost everything. Small
models are good readers and bad accountants. So OpenAdjuster only asks the model to read and to
make small judgement calls, and does the rest in code
([ADR 0001](docs/adr/0001-small-local-model-reads-code-decides.md)).

```mermaid
flowchart LR
    A[Document images] --> B[Apple Vision OCR<br/>text + boxes, EN / BM / ZH]
    B --> C[Document type<br/>keywords]
    B --> D[Receipt items and total<br/>code: deskew, pair prices]
    B --> E[Header fields<br/>bonsai-2:4b copies values<br/>and cites the line]
    D --> F[Item categories<br/>bonsai-2:4b]
    C & D & E & F --> G[Registry lookups<br/>member, clinic, claims history]
    G --> H[7 fraud cross-checks]
    H --> I[Policy rules engine]
    I --> J[Recommendation + evidence]
    J --> K[Person approves or overrides]
```

| Step | Done by | Why |
|---|---|---|
| Read text and its position | Apple Vision OCR (on-device) | Fast, accurate, no download; the boxes become the evidence |
| Read receipt items and total | Code | The model shifted prices by one row; code doesn't |
| Read names, dates, receipt numbers, claim form answers | `bonsai-2:4b` via Ollama | Layouts vary; the model copies values and says which line it used |
| Decide if an item is a vitamin, cosmetic, etc. | `bonsai-2:4b` | A real judgement call, in three languages |
| Fraud checks, policy maths, payout | Code | Must be exact and explainable |
| Approve the payout | A person | Always |

### Fraud checks

Each check points at the evidence it used, and the review screen highlights it on the document.

- Receipt items add up to the total (catches an edited total)
- Receipt and medical certificate dates match (catches an edited date)
- Same patient on the receipt and the claim form
- Medical certificate is from the same clinic as the receipt
- Clinic is in the insurer's registry
- Receipt number matches the clinic's format
- Receipt hasn't been claimed before

### Hidden instructions

Document text only ever goes into the data part of a prompt. Lines that look like instructions to
an AI ("approve the full amount", "ignore previous rules") are flagged and shown to the reviewer,
and can't change the decision because the decision isn't made by the model.

![Review screen: an instruction hidden in the claim form is flagged and ignored](docs/images/review-injection.png)

## Run it

You need a Mac with Apple silicon (for the on-device OCR), [uv](https://docs.astral.sh/uv/) and
[Ollama](https://ollama.com).

```bash
ollama pull bonsai-2:4b
git clone https://github.com/MohamedMahdiCS/claimdocbench
git clone https://github.com/MohamedMahdiCS/openadjuster
cd claimdocbench && uv sync && uv run playwright install chromium
uv run claimdocbench generate --split dev --n 20 --seed 1
cd ../openadjuster && uv sync
(cd console && npm install && npm run build)
uv run openadjuster serve --split-dir ../claimdocbench/out/dev
```

Open http://localhost:8077 and use "Assess a new claim". Each claim takes about 20 seconds.

To score it on the benchmark:

```bash
uv run openadjuster run --split-dir ../claimdocbench/out/dev --out preds.jsonl
cd ../claimdocbench && uv run claimdocbench evaluate --split-dir out/dev --predictions ../openadjuster/preds.jsonl
```

## Project layout

```
src/openadjuster/
  ocr.py        Apple Vision OCR, both language orders, pixel boxes
  classify.py   document type from titles in three languages
  receipt.py    receipt items and total, with tilt correction
  extract.py    header fields with the model, evidence lookup
  assess.py     registry lookups, fraud checks, rules engine, confidence
  case.py       the record the review screen shows
  server.py     FastAPI: case files, assess, approve / override with an audit log
console/        review screen (React + TypeScript)
docs/adr/       design decisions
```

## Limitations

- Tested on synthetic claims only. Real documents will surface problems the benchmark doesn't.
- One claim type (outpatient reimbursement) and one simplified policy.
- macOS only for now, because of the on-device OCR. Swapping in another OCR engine would make it portable.
- Not yet reviewed by people who handle claims for a living.
- This is a portfolio project, not a product, and not legal or compliance advice.

## License

Apache-2.0.
