"""main.py — Orchestrator: reads claims.csv, calls the verifier for each row,
writes output.csv in the exact required column order.

Usage:
    python code/main.py [--input dataset/claims.csv] [--output output.csv]

Env vars required:
    GEMINI_API_KEY  — your Google AI Studio / Vertex API key
    GEMINI_MODEL    — (optional) defaults to gemini-2.5-flash
"""

import argparse
import csv
import sys
import time
from pathlib import Path

# Allow imports from the code/ directory regardless of cwd.
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from data_loader import load_csv_as_dicts, load_user_history, load_evidence_requirements, build_context
from prompts.claim_verifier_user_template import build_user_message_parts
from llm_client import call_verifier
from validator import validate_and_clamp, fallback_row
from schema import OUTPUT_COLUMNS

REPO_ROOT = Path(__file__).parent.parent


def process_row(row: dict, user_history: dict, evidence_rows: list[dict]) -> dict:
    """Full pipeline for one claims.csv row. Always returns a valid output dict."""
    context = build_context(row, user_history, evidence_rows)

    # If no images loaded at all, shortcut to fallback.
    if not context["has_valid_images"]:
        print(f"  [main] No valid images for {context['user_id']} — using fallback.")
        out = fallback_row()
        out["evidence_standard_met_reason"] = "No usable images could be loaded."
        return {**_passthrough(row), **out}

    parts = build_user_message_parts(context)

    try:
        raw = call_verifier(context, parts)
    except RuntimeError as e:
        print(f"  [main] call_verifier failed: {e}. Using fallback.")
        return {**_passthrough(row), **fallback_row()}

    validated = validate_and_clamp(raw, context)
    return {**_passthrough(row), **validated}


def _passthrough(row: dict) -> dict:
    return {
        "user_id": row["user_id"],
        "image_paths": row["image_paths"],
        "user_claim": row["user_claim"],
        "claim_object": row["claim_object"],
    }


def run(input_path: Path, output_path: Path) -> None:
    print(f"[main] Loading reference data...")
    user_history = load_user_history(REPO_ROOT / "dataset" / "user_history.csv")
    evidence_rows = load_evidence_requirements(REPO_ROOT / "dataset" / "evidence_requirements.csv")

    rows = load_csv_as_dicts(input_path)
    print(f"[main] Processing {len(rows)} rows from {input_path.name}...")

    results = []
    for i, row in enumerate(rows, 1):
        user_id = row.get("user_id", f"row_{i}")
        print(f"[main] [{i}/{len(rows)}] {user_id} ({row.get('claim_object','?')})...")
        t0 = time.time()
        result = process_row(row, user_history, evidence_rows)
        elapsed = time.time() - t0
        print(f"  => {result.get('claim_status','?')} | {result.get('issue_type','?')} | {result.get('severity','?')} ({elapsed:.1f}s)")
        results.append(result)

    # Write output.csv in exact column order.
    print(f"[main] Writing {output_path}...")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"[main] Done. {len(results)} rows written to {output_path}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-modal damage claim verifier")
    parser.add_argument("--input", default=str(REPO_ROOT / "dataset" / "claims.csv"))
    parser.add_argument("--output", default=str(REPO_ROOT / "output.csv"))
    args = parser.parse_args()

    run(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
