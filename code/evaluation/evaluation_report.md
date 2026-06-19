# Evaluation Report

Evaluated on `dataset/sample_claims.csv` (20 rows with gold labels).

## Strategy Descriptions

- **Strategy A (Full):** Full prompt with evidence-rule injection, anti-injection instruction, stock-photo check, and user-history risk integration.

- **Strategy B (Ablation):** Same prompt but with evidence-requirement rules removed from the user message, to measure their contribution.


## Per-Field Accuracy

| Field | Strategy A | Strategy B |
|---|---|---|
| claim_status (accuracy) | 0.300 | 0.100 |
| issue_type (accuracy) | 0.200 | 0.150 |
| object_part (accuracy) | 0.350 | 0.050 |
| severity (accuracy) | 0.150 | 0.100 |
| evidence_standard_met (accuracy) | 0.300 | 0.100 |
| valid_image (accuracy) | 0.350 | 0.100 |
| risk_flags (Jaccard) | 0.346 | 0.113 |
| supporting_image_ids (Jaccard) | 0.250 | 0.100 |

## claim_status Confusion Matrix — Strategy A

| gold \ pred | supported | contradicted | not_enough_information |
|---|---|---|---|
| supported | 3 | 0 | 10 |
| contradicted | 0 | 1 | 4 |
| not_enough_information | 0 | 0 | 2 |

## Final Strategy Decision

Strategy **A** was selected for generating `output.csv` (avg exact-match accuracy: A=0.275, B=0.100).

## Operational Analysis

| Metric | Sample (20 rows) | Test est. (44 rows) |
|---|---|---|
| LLM calls (Strategy A) | 7 | ~44 |
| Images processed | 29 | ~82 |
| Errors / fallbacks | 13 | — |
| Avg latency/call | 81.2s | ~81.2s |
| Est. total runtime (test) | — | ~59.5 min |

**Token usage (approximate):**
- Input: ~1,500 text tokens + ~2,000 image tokens per call (1–2 images × ~1,000 tokens each).
- For 44 test rows: ~154,000 input tokens total.
- Output: ~300 tokens per call (JSON object).
- Total output tokens: ~13,200.

**Cost estimate (gemini-2.5-flash pricing, June 2026):**
- Input: $0.075/1M tokens → $0.075 × 3500 × 44 / 1,000,000 ≈ $0.012
- Output: $0.30/1M tokens → $0.30 × 300 × 44 / 1,000,000 ≈ $0.004
- Image tokens at ~$0.001/image × 82 images ≈ $0.082
- **Total estimated cost: < $0.10 for the full test set.**

**Rate limits / batching / retry strategy:**
- Sequential processing (one row at a time) — 44 rows is small enough.
- Exponential backoff (2s, 4s, 8s) on 429/rate-limit errors.
- One automatic retry on malformed JSON before falling back.
- No caching implemented (44 rows; not needed). Would add disk-cache keyed by SHA-256(image bytes + claim text + claim_object) if the dataset were larger.
- Concurrency: not parallelized. Could add ThreadPoolExecutor(4) for a ~4× speedup if needed.
