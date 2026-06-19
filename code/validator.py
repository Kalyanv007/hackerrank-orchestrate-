"""validator.py — Clamps LLM output to allowed vocabularies and enforces
deterministic consistency rules. Never crashes; always returns a valid row.
"""

from schema import (
    CLAIM_STATUS_VALUES,
    ISSUE_TYPE_VALUES,
    OBJECT_PART_VALUES_BY_OBJECT,
    RISK_FLAG_VALUES,
    SEVERITY_VALUES,
    SAFE_FALLBACK,
)


def _clamp_enum(value: str, allowed: set[str], fallback: str = "unknown") -> str:
    v = str(value).strip().lower()
    return v if v in allowed else fallback


def _clamp_bool_str(value: str) -> str:
    v = str(value).strip().lower()
    if v in ("true", "1", "yes"):
        return "true"
    if v in ("false", "0", "no"):
        return "false"
    return "false"


def _clamp_risk_flags(value: str) -> str:
    if not value or str(value).strip().lower() in ("", "none"):
        return "none"
    flags = [f.strip().lower() for f in str(value).split(";") if f.strip()]
    valid = [f for f in flags if f in RISK_FLAG_VALUES]
    return ";".join(valid) if valid else "none"


def _clamp_supporting_ids(value: str, valid_ids: list[str]) -> str:
    if not value or str(value).strip().lower() in ("", "none"):
        return "none"
    ids = [i.strip() for i in str(value).split(";") if i.strip()]
    valid = [i for i in ids if i in valid_ids]
    return ";".join(valid) if valid else "none"


def validate_and_clamp(raw: dict, context: dict) -> dict:
    """
    Takes the raw LLM JSON output and returns a dict with all 10 output fields
    guaranteed to use valid vocabulary values and satisfy consistency rules.

    Consistency rules (deterministic overrides):
      1. evidence_standard_met=false  => claim_status=not_enough_information
      2. claim_status=not_enough_information => severity=unknown
      3. valid_image=false => supporting_image_ids should be "none" (warn if not)
    """
    claim_object = context.get("claim_object", "car")
    image_ids = context.get("image_ids", [])
    object_part_allowed = OBJECT_PART_VALUES_BY_OBJECT.get(claim_object, {"unknown"})

    try:
        evidence_standard_met = _clamp_bool_str(raw.get("evidence_standard_met", "false"))
        evidence_standard_met_reason = str(raw.get("evidence_standard_met_reason", "")).strip() or "No reason provided."
        risk_flags = _clamp_risk_flags(raw.get("risk_flags", "none"))
        issue_type = _clamp_enum(raw.get("issue_type", "unknown"), ISSUE_TYPE_VALUES)
        object_part = _clamp_enum(raw.get("object_part", "unknown"), object_part_allowed)
        claim_status = _clamp_enum(raw.get("claim_status", "not_enough_information"), CLAIM_STATUS_VALUES, "not_enough_information")
        claim_status_justification = str(raw.get("claim_status_justification", "")).strip() or "No justification provided."
        supporting_image_ids = _clamp_supporting_ids(raw.get("supporting_image_ids", "none"), image_ids)
        valid_image = _clamp_bool_str(raw.get("valid_image", "false"))
        severity = _clamp_enum(raw.get("severity", "unknown"), SEVERITY_VALUES)

        # --- Consistency rule 1 ---
        if evidence_standard_met == "false":
            claim_status = "not_enough_information"

        # --- Consistency rule 2 ---
        if claim_status == "not_enough_information":
            severity = "unknown"

        # --- Consistency rule 3 ---
        if valid_image == "false" and supporting_image_ids != "none":
            print(f"  [validator] Warning: valid_image=false but supporting_image_ids={supporting_image_ids}; clearing.")
            supporting_image_ids = "none"

        return {
            "evidence_standard_met": evidence_standard_met,
            "evidence_standard_met_reason": evidence_standard_met_reason,
            "risk_flags": risk_flags,
            "issue_type": issue_type,
            "object_part": object_part,
            "claim_status": claim_status,
            "claim_status_justification": claim_status_justification,
            "supporting_image_ids": supporting_image_ids,
            "valid_image": valid_image,
            "severity": severity,
        }

    except Exception as e:
        print(f"  [validator] Unexpected error during clamping: {e}. Using SAFE_FALLBACK.")
        return dict(SAFE_FALLBACK)


def fallback_row() -> dict:
    """Return the safe fallback output dict."""
    return dict(SAFE_FALLBACK)
