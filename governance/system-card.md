# System card: OpenAdjuster

This maps a portfolio project to the MAS AI risk management guidelines as an exercise. It is not legal
or compliance advice, and no insurer uses this system.

## Inventory

| | |
|---|---|
| Purpose | Recommend a decision on outpatient reimbursement claims. A person approves every payout. |
| Owner | Mohamed Mahdi |
| Models | `bonsai-2:4b` through Ollama, Apple Vision OCR |
| Data | Synthetic ClaimDocBench packets only |
| Where it runs | On the laptop. No claim data leaves the machine. |
| Risk tier | High if deployed: it affects payments to people, and errors can be unfair or costly. |

## What can go wrong

| Risk | Control | How it is tested |
|---|---|---|
| Paying a forged claim | Seven code checks; any failure goes to fraud review | Fraud recall per type on ClaimDocBench |
| Denying an honest claim | No automatic denial; every outcome is reviewed, with evidence shown | False-alarm rate, reason code F1 |
| Instructions hidden in a document | Document text is data only; code decides; no payment tool exists | Paired injection packets, attack success rate |
| Unfair treatment | Results split by language, name origin, country and capture quality | Fairness slices in each report |
| Overconfidence | Confidence tiers set on dev, checked on test | Calibration error, coverage curve |
| Silent change in behaviour | Case records store model, prompt, policy and pipeline fingerprints | `openadjuster replay` |
| A rushed fix that weakens fraud checks | Regression tests; ADR 0002 rule | CI, benchmark rerun |

## MAS expectations

| Expectation | What exists here | Gap |
|---|---|---|
| AI inventory | This card | |
| Risk materiality | The table above | No independent review |
| Data governance | Synthetic data, local processing | Retention rules for real data aren't defined |
| Testing | ClaimDocBench, including a held-out split with unseen templates | Synthetic only |
| Human oversight | Mandatory approval, override with a logged reason | Not tested with claims staff |
| Monitoring | Audit log of reviews | No live drift or override alerts |
| Cybersecurity | Injection tests | No wider penetration test |
| Change management | Fingerprints, replay, CI | CI only runs once the repo is public |
| Third-party AI | Open-weight model run locally | Model license review is manual |

Malaysia: BNM's 2025 discussion paper is non-binding. The same controls would apply.
