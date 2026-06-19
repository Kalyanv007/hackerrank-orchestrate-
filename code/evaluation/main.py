"""evaluation/main.py — Runs the full pipeline against sample_claims.csv
with two configurations and reports metrics.

Usage:
    python code/evaluation/main.py

Outputs:
    code/evaluation/eval_predictions_A.csv  — Strategy A predictions
    code/evaluation/eval_predictions_B.csv  — Strategy B predictions
    code/evaluation/evaluation_report.md    — Final report
"""

import csv
import os
import sys
import time
from pathlib import Path

# Allow imports from code/ directory
CODE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CODE_DIR))

from dotenv import load_dotenv
load_dotenv(CODE_DIR / ".env")

from data_loader import load_csv_as_dicts, load_user_history, load_evidence_requirements, build_context
from prompts.claim_verifier_user_template import build_user_message_parts
from llm_client import call_verifier
from validator import validate_and_clamp, fallback_row
from schema import OUTPUT_COLUMNS
from metrics import score_predictions, print_report

REPO_ROOT = CODE_DIR.parent
SAMPLE_CSV = REPO_ROOT / "dataset" / "sample_claims.csv"
EVAL_DIR = Path(__file__).parent

# Gold columns present in sample_claims.csv (not in claims.csv)
GOLD_COLUMNS = [
    "evidence_standard_met", "evidence_standard_met_reason", "risk_flags",
    "issue_type", "object_part", "claim_status", "claim_status_justification",
    "supporting_image_ids", "valid_image", "severity",
]


def _passthrough(row: dict) -> dict:
    return {
        "user_id": row["user_id"],
        "image_paths": row["image_paths"],
        "user_claim": row["user_claim"],
        "claim_object": row["claim_object"],
    }


def run_pipeline(rows, user_history, evidence_rows, strategy: str) -> tuple[list[dict], dict]:
    """
    Run the pipeline for a given strategy.
    strategy: "A" (full prompt) or "B" (no evidence-rule injection, as ablation)
    Returns (predictions, operational_stats)
    """
    predictions = []
    stats = {"calls": 0, "total_images": 0, "total_latency": 0.0, "errors": 0}

    for i, row in enumerate(rows, 1):
        context = build_context(row, user_history, evidence_rows)

        if strategy == "B":
            # Ablation: remove evidence_rules from context to test their impact
            context = dict(context)
            context["evidence_rules"] = []

        print(f"  [{strategy}] [{i}/{len(rows)}] {context['user_id']}...")
        stats["total_images"] += len(context["images"])

        if not context["has_valid_images"]:
            out = fallback_row()
            out["evidence_standard_met_reason"] = "No usable images."
            predictions.append({**_passthrough(row), **out})
            continue

        parts = build_user_message_parts(context)

        t0 = time.time()
        try:
            raw = call_verifier(context, parts)
            stats["calls"] += 1
        except RuntimeError as e:
            print(f"    Error: {e}")
            stats["errors"] += 1
            predictions.append({**_passthrough(row), **fallback_row()})
            continue
        finally:
            stats["total_latency"] += time.time() - t0

        validated = validate_and_clamp(raw, context)
        predictions.append({**_passthrough(row), **validated})

    return predictions, stats


def save_predictions(predictions: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(predictions)


def write_evaluation_report(
    summary_A: dict,
    summary_B: dict,
    stats_A: dict,
    stats_B: dict,
    n_rows: int,
) -> None:
    report_path = EVAL_DIR / "evaluation_report.md"
    lines = []
    lines.append("# Evaluation Report\n")
    lines.append(f"Evaluated on `dataset/sample_claims.csv` ({n_rows} rows with gold labels).\n")

    lines.append("## Strategy Descriptions\n")
    lines.append("- **Strategy A (Full):** Full prompt with evidence-rule injection, anti-injection instruction, stock-photo check, and user-history risk integration.\n")
    lines.append("- **Strategy B (Ablation):** Same prompt but with evidence-requirement rules removed from the user message, to measure their contribution.\n")

    lines.append("\n## Per-Field Accuracy\n")
    lines.append("| Field | Strategy A | Strategy B |\n|---|---|---|")
    from metrics import EXACT_MATCH_FIELDS, JACCARD_FIELDS
    for f in EXACT_MATCH_FIELDS:
        lines.append(f"| {f} (accuracy) | {summary_A.get(f, 0):.3f} | {summary_B.get(f, 0):.3f} |")
    for f in JACCARD_FIELDS:
        lines.append(f"| {f} (Jaccard) | {summary_A.get(f, 0):.3f} | {summary_B.get(f, 0):.3f} |")
    lines.append("")

    lines.append("## claim_status Confusion Matrix — Strategy A\n")
    statuses = ["supported", "contradicted", "not_enough_information"]
    conf = summary_A.get("confusion_claim_status", {})
    lines.append("| gold \\ pred | supported | contradicted | not_enough_information |")
    lines.append("|---|---|---|---|")
    for g in statuses:
        row_str = " | ".join(str(conf.get((g, p), 0)) for p in statuses)
        lines.append(f"| {g} | {row_str} |")
    lines.append("")

    lines.append("## Final Strategy Decision\n")
    # Simple aggregate: average of exact-match fields
    avg_A = sum(summary_A.get(f, 0) for f in EXACT_MATCH_FIELDS) / len(EXACT_MATCH_FIELDS)
    avg_B = sum(summary_B.get(f, 0) for f in EXACT_MATCH_FIELDS) / len(EXACT_MATCH_FIELDS)
    winner = "A" if avg_A >= avg_B else "B"
    lines.append(f"Strategy **{winner}** was selected for generating `output.csv` (avg exact-match accuracy: A={avg_A:.3f}, B={avg_B:.3f}).\n")

    lines.append("## Operational Analysis\n")
    n_sample = n_rows
    n_test = 44
    lines.append(f"| Metric | Sample ({n_sample} rows) | Test est. ({n_test} rows) |")
    lines.append("|---|---|---|")
    lines.append(f"| LLM calls (Strategy A) | {stats_A['calls']} | ~{n_test} |")
    lines.append(f"| Images processed | {stats_A['total_images']} | ~82 |")
    lines.append(f"| Errors / fallbacks | {stats_A['errors']} | — |")
    avg_lat = stats_A['total_latency'] / max(stats_A['calls'], 1)
    lines.append(f"| Avg latency/call | {avg_lat:.1f}s | ~{avg_lat:.1f}s |")
    total_lat = n_test * avg_lat
    lines.append(f"| Est. total runtime (test) | — | ~{total_lat/60:.1f} min |")
    lines.append("")
    lines.append("**Token usage (approximate):**")
    lines.append("- Input: ~1,500 text tokens + ~2,000 image tokens per call (1–2 images × ~1,000 tokens each).")
    lines.append(f"- For {n_test} test rows: ~{n_test * 3500:,} input tokens total.")
    lines.append("- Output: ~300 tokens per call (JSON object).")
    lines.append(f"- Total output tokens: ~{n_test * 300:,}.")
    lines.append("")
    lines.append("**Cost estimate (gemini-2.5-flash pricing, June 2026):**")
    lines.append("- Input: $0.075/1M tokens → $0.075 × 3500 × 44 / 1,000,000 ≈ $0.012")
    lines.append("- Output: $0.30/1M tokens → $0.30 × 300 × 44 / 1,000,000 ≈ $0.004")
    lines.append("- Image tokens at ~$0.001/image × 82 images ≈ $0.082")
    lines.append("- **Total estimated cost: < $0.10 for the full test set.**")
    lines.append("")
    lines.append("**Rate limits / batching / retry strategy:**")
    lines.append("- Sequential processing (one row at a time) — 44 rows is small enough.")
    lines.append("- Exponential backoff (2s, 4s, 8s) on 429/rate-limit errors.")
    lines.append("- One automatic retry on malformed JSON before falling back.")
    lines.append("- No caching implemented (44 rows; not needed). Would add disk-cache keyed by SHA-256(image bytes + claim text + claim_object) if the dataset were larger.")
    lines.append("- Concurrency: not parallelized. Could add ThreadPoolExecutor(4) for a ~4× speedup if needed.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[eval] Report written to {report_path}")


def main():
    print("[eval] Loading data...")
    user_history = load_user_history(REPO_ROOT / "dataset" / "user_history.csv")
    evidence_rows = load_evidence_requirements(REPO_ROOT / "dataset" / "evidence_requirements.csv")
    sample_rows = load_csv_as_dicts(SAMPLE_CSV)
    n_rows = len(sample_rows)
    print(f"[eval] {n_rows} sample rows loaded.")

    print("\n[eval] === Strategy A: Full prompt ===")
    preds_A, stats_A = run_pipeline(sample_rows, user_history, evidence_rows, "A")
    save_predictions(preds_A, EVAL_DIR / "eval_predictions_A.csv")

    print("\n[eval] === Strategy B: Ablation (no evidence rules) ===")
    preds_B, stats_B = run_pipeline(sample_rows, user_history, evidence_rows, "B")
    save_predictions(preds_B, EVAL_DIR / "eval_predictions_B.csv")

    print("\n[eval] Scoring...")
    # Gold values come from the sample_claims.csv columns
    gold_rows = [{k: r[k] for k in GOLD_COLUMNS if k in r} for r in sample_rows]

    summary_A = score_predictions(preds_A, gold_rows)
    summary_B = score_predictions(preds_B, gold_rows)

    print_report(summary_A, "Strategy A — Full")
    print_report(summary_B, "Strategy B — Ablation")

    write_evaluation_report(summary_A, summary_B, stats_A, stats_B, n_rows)
    print("[eval] Complete.")


if __name__ == "__main__":
    main()
