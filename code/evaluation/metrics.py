"""evaluation/metrics.py — Per-field scoring utilities for sample_claims.csv."""


def exact_match(pred: str, gold: str) -> int:
    return int(str(pred).strip().lower() == str(gold).strip().lower())


def jaccard(pred_str: str, gold_str: str) -> float:
    """Set-overlap Jaccard for semicolon-separated multi-value fields."""
    pred_set = {x.strip().lower() for x in str(pred_str).split(";") if x.strip() and x.strip().lower() != "none"}
    gold_set = {x.strip().lower() for x in str(gold_str).split(";") if x.strip() and x.strip().lower() != "none"}
    if not pred_set and not gold_set:
        return 1.0  # both "none" → perfect match
    if not pred_set or not gold_set:
        return 0.0
    return len(pred_set & gold_set) / len(pred_set | gold_set)


EXACT_MATCH_FIELDS = [
    "claim_status",
    "issue_type",
    "object_part",
    "severity",
    "evidence_standard_met",
    "valid_image",
]

JACCARD_FIELDS = [
    "risk_flags",
    "supporting_image_ids",
]


def score_predictions(predictions: list[dict], gold_rows: list[dict]) -> dict:
    """
    Compare predictions to gold rows from sample_claims.csv.

    Returns a summary dict with per-field accuracy / jaccard scores,
    plus a confusion matrix for claim_status.
    """
    assert len(predictions) == len(gold_rows), "Row count mismatch"

    field_scores: dict[str, list] = {f: [] for f in EXACT_MATCH_FIELDS + JACCARD_FIELDS}
    confusion = {}  # {(gold, pred): count}

    for pred, gold in zip(predictions, gold_rows):
        for f in EXACT_MATCH_FIELDS:
            field_scores[f].append(exact_match(pred.get(f, ""), gold.get(f, "")))
        for f in JACCARD_FIELDS:
            field_scores[f].append(jaccard(pred.get(f, ""), gold.get(f, "")))

        g_status = str(gold.get("claim_status", "")).strip().lower()
        p_status = str(pred.get("claim_status", "")).strip().lower()
        key = (g_status, p_status)
        confusion[key] = confusion.get(key, 0) + 1

    summary = {}
    for f, scores in field_scores.items():
        summary[f] = sum(scores) / len(scores) if scores else 0.0

    summary["confusion_claim_status"] = confusion
    return summary


def print_report(summary: dict, strategy_name: str = "") -> None:
    label = f" [{strategy_name}]" if strategy_name else ""
    print(f"\n{'='*60}")
    print(f"Evaluation Report{label}")
    print(f"{'='*60}")
    for f in EXACT_MATCH_FIELDS:
        print(f"  {f:<30} accuracy = {summary.get(f, 0):.3f}")
    for f in JACCARD_FIELDS:
        print(f"  {f:<30} jaccard  = {summary.get(f, 0):.3f}")

    print("\n  claim_status confusion matrix (gold → pred):")
    statuses = ["supported", "contradicted", "not_enough_information"]
    header = f"  {'':>25}" + "".join(f"{p[:6]:>8}" for p in statuses)
    print(header)
    for g in statuses:
        row_vals = "".join(
            f"{summary['confusion_claim_status'].get((g, p), 0):>8}"
            for p in statuses
        )
        print(f"  {'gold_'+g[:20]:>25}{row_vals}")
    print()
