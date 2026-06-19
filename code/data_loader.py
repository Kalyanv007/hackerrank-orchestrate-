"""data_loader.py — Loads CSVs, joins user history, pre-filters evidence rules,
and decodes images with content-sniffing (not trusting the .jpg extension).
"""

import base64
import io
import csv
from pathlib import Path

# PIL/Pillow is used to sniff actual codec and normalize to JPEG bytes.
try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# Root of the repo — image paths in the CSVs are relative to /dataset/
REPO_ROOT = Path(__file__).parent.parent


def load_csv_as_dicts(path: str | Path) -> list[dict]:
    """Read a CSV and return a list of row-dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_user_history(path: str | Path) -> dict[str, dict]:
    """Return user_history keyed by user_id."""
    rows = load_csv_as_dicts(path)
    return {r["user_id"]: r for r in rows}


def load_evidence_requirements(path: str | Path) -> list[dict]:
    """Return all evidence requirement rows."""
    return load_csv_as_dicts(path)


def filter_evidence_rules(evidence_rows: list[dict], claim_object: str) -> list[dict]:
    """Return rules that apply to this claim_object (includes 'all' rules)."""
    return [r for r in evidence_rows if r["claim_object"] in (claim_object, "all")]


def _encode_image(image_path: Path) -> tuple[str, str] | None:
    """
    Load an image from disk, sniff its actual format, normalize to JPEG bytes,
    and return (base64_string, media_type).
    Returns None if the file is missing or unreadable.
    """
    if not image_path.exists():
        return None

    raw = image_path.read_bytes()

    if _PIL_AVAILABLE:
        try:
            img = PILImage.open(io.BytesIO(raw))
            img.load()  # force decode
            buf = io.BytesIO()
            # Normalize everything to JPEG to keep the API call uniform.
            rgb = img.convert("RGB")
            rgb.save(buf, format="JPEG", quality=90)
            jpeg_bytes = buf.getvalue()
            return base64.b64encode(jpeg_bytes).decode("ascii"), "image/jpeg"
        except Exception:
            pass

    # Fallback: sniff magic bytes for MIME, send raw.
    if raw[:4] == b"\x89PNG":
        mime = "image/png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    return base64.b64encode(raw).decode("ascii"), mime


def build_context(
    row: dict,
    user_history: dict[str, dict],
    evidence_rows: list[dict],
) -> dict:
    """
    Build a complete context dict for one claims.csv row.

    Returns:
        {
          user_id, image_paths_raw, user_claim, claim_object,
          user_history_row,          # dict or {} if not found
          evidence_rules,            # list[dict] filtered for claim_object
          images,                    # list[{image_id, b64, media_type, path}]
          image_ids,                 # list of img_N strings (for validator)
          has_valid_images,          # False if ALL images failed to load
        }
    """
    user_id = row["user_id"]
    claim_object = row["claim_object"].strip().lower()
    user_claim = row["user_claim"]
    image_paths_raw = row["image_paths"]

    history = user_history.get(user_id, {})
    evidence_rules = filter_evidence_rules(evidence_rows, claim_object)

    image_paths = [p.strip() for p in image_paths_raw.split(";") if p.strip()]
    images = []
    for img_path_rel in image_paths:
        # image_paths in CSV are relative to dataset/ directory
        img_file = REPO_ROOT / "dataset" / img_path_rel
        image_id = Path(img_path_rel).stem  # e.g. "img_1"
        result = _encode_image(img_file)
        if result is not None:
            b64, mime = result
            images.append({
                "image_id": image_id,
                "b64": b64,
                "media_type": mime,
                "path": str(img_file),
            })
        else:
            # Missing/corrupt image — record it so the validator can flag it.
            images.append({
                "image_id": image_id,
                "b64": None,
                "media_type": None,
                "path": str(img_file),
            })

    image_ids = [img["image_id"] for img in images]
    has_valid_images = any(img["b64"] is not None for img in images)

    return {
        "user_id": user_id,
        "image_paths_raw": image_paths_raw,
        "user_claim": user_claim,
        "claim_object": claim_object,
        "user_history_row": history,
        "evidence_rules": evidence_rules,
        "images": images,
        "image_ids": image_ids,
        "has_valid_images": has_valid_images,
    }
