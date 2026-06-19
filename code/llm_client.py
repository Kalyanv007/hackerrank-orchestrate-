"""llm_client.py — Thin wrapper for the Google Gemini multimodal API.

Uses the new `google-genai` SDK (google.genai).
Sends one system prompt + one user message (text + images) and returns
the parsed JSON dict. Retries once on malformed JSON and handles rate
limits with exponential backoff.
"""

import base64
import json
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_RETRIES = 3
BACKOFF_BASE = 5.0  # seconds; doubled each retry
REQUEST_TIMEOUT = 120  # seconds per call

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "claim_verifier_system_prompt.md"
_SYSTEM_PROMPT: str | None = None
_CLIENT: genai.Client | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _get_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY env var is not set.")
        _CLIENT = genai.Client(api_key=api_key)
    return _CLIENT


def _build_contents(parts: list[dict]) -> list:
    """Convert our internal parts list to google-genai SDK Part objects."""
    content_parts = []
    for p in parts:
        if p["type"] == "text":
            content_parts.append(types.Part.from_text(text=p["text"]))
        elif p["type"] == "image" and p.get("b64"):
            raw_bytes = base64.b64decode(p["b64"])
            content_parts.append(
                types.Part.from_bytes(data=raw_bytes, mime_type=p["media_type"])
            )
    return content_parts


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a text response."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No valid JSON found in response:\n{text[:500]}")


def call_verifier(context: dict, parts: list[dict]) -> dict:
    """
    Send a multimodal claim verification request to Gemini.

    Args:
        context: The context dict from build_context (used for logging only).
        parts:   Content parts from build_user_message_parts().

    Returns:
        Parsed JSON dict with the 10 output fields.

    Raises:
        RuntimeError after all retries are exhausted.
    """
    client = _get_client()
    system_prompt = _get_system_prompt()

    content_parts = _build_contents(parts)
    last_error: Exception | None = None

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.0,
        response_mime_type="application/json",
        safety_settings=[
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_NONE",
            ),
        ],
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=content_parts,
                config=config,
            )
            raw_text = response.text
            result = _extract_json(raw_text)
            return result

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [llm_client] JSON parse error (attempt {attempt+1}): {e}")
            # Append a fix instruction and retry
            content_parts = _build_contents(parts) + [
                types.Part.from_text(
                    text="Your previous response was not valid JSON. Return ONLY the JSON object, no other text."
                )
            ]

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if any(x in err_str for x in ("429", "resource_exhausted", "rate", "quota")):
                wait = BACKOFF_BASE * (2 ** attempt)
                print(f"  [llm_client] Rate limit hit (attempt {attempt+1}), sleeping {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"  [llm_client] Error (attempt {attempt+1}): {type(e).__name__}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE)

    raise RuntimeError(
        f"call_verifier failed after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
