"""claim_verifier_user_template.py — builds the user-turn message content list
for the multimodal LLM call (text + images).
"""

from schema import (
    ISSUE_TYPE_VALUES,
    OBJECT_PART_VALUES_BY_OBJECT,
    RISK_FLAG_VALUES,
    SEVERITY_VALUES,
    CLAIM_STATUS_VALUES,
)


def build_user_message_parts(context: dict) -> list[dict]:
    """
    Build a list of content parts for the user turn:
      [{"type": "text", "text": ...}, {"type": "image", ...}, ...]

    Each part is a dict; the LLM client is responsible for translating to the
    provider's wire format.
    """
    claim_object = context["claim_object"]
    object_parts = sorted(OBJECT_PART_VALUES_BY_OBJECT.get(claim_object, {"unknown"}))
    issue_types = sorted(ISSUE_TYPE_VALUES)
    risk_flags = sorted(RISK_FLAG_VALUES)
    severities = sorted(SEVERITY_VALUES)
    statuses = sorted(CLAIM_STATUS_VALUES)

    history = context["user_history_row"]
    if history:
        history_text = (
            f"Past claims: {history.get('past_claim_count', 'N/A')} total "
            f"({history.get('accept_claim', 0)} accepted, "
            f"{history.get('manual_review_claim', 0)} manual review, "
            f"{history.get('rejected_claim', 0)} rejected). "
            f"Last 90 days: {history.get('last_90_days_claim_count', 'N/A')} claims. "
            f"History flags: {history.get('history_flags', 'none')}. "
            f"Summary: {history.get('history_summary', 'No history available.')}."
        )
    else:
        history_text = "No user history available."

    evidence_rules_text = "\n".join(
        f"- [{r['requirement_id']}] ({r['applies_to']}): {r['minimum_image_evidence']}"
        for r in context["evidence_rules"]
    )

    image_ids_in_set = context["image_ids"]

    text_prompt = f"""## CLAIM DETAILS

**Claim object:** {claim_object}
**User claim transcript:**
{context["user_claim"]}

## USER HISTORY (risk context only — never overrides visual evidence)
{history_text}

## MINIMUM EVIDENCE REQUIREMENTS (for {claim_object})
{evidence_rules_text}

## ALLOWED VALUES (use ONLY these — do not invent new values)

claim_status: {", ".join(statuses)}
issue_type: {", ".join(issue_types)}
object_part (for {claim_object}): {", ".join(object_parts)}
severity: {", ".join(severities)}
risk_flags (semicolon-separate multiple): {", ".join(risk_flags)}

supporting_image_ids: use semicolon-separated IDs from this set: {", ".join(image_ids_in_set)}; or "none"

## SUBMITTED IMAGES
The images below are labelled with their image_id. Inspect each carefully.
"""

    parts: list[dict] = [{"type": "text", "text": text_prompt}]

    for img in context["images"]:
        if img["b64"] is not None:
            parts.append({
                "type": "text",
                "text": f"\n[Image: {img['image_id']}]",
            })
            parts.append({
                "type": "image",
                "image_id": img["image_id"],
                "b64": img["b64"],
                "media_type": img["media_type"],
            })
        else:
            parts.append({
                "type": "text",
                "text": f"\n[Image: {img['image_id']} — FILE MISSING OR UNREADABLE]",
            })

    parts.append({
        "type": "text",
        "text": "\nProduce ONLY the JSON verdict. No explanation before or after the JSON.",
    })

    return parts
