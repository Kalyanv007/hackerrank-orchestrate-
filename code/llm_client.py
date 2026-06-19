"""llm_client.py — Thin wrapper for the Google Gemini multimodal API.

Sends one system prompt + one user message (text + images) and returns
the parsed JSON dict. Retries once on malformed JSON and handles rate
limits with exponential backoff.
"""

import json
import os
import re
import time
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # seconds; doubled each retry
REQUEST_TIMEOUT = 120  # seconds per call

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "claim_verifier_system_prompt.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _configure_client() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY env var is not set.")
    genai.configure(api_key=api_key)


def _build_gemini_contents(parts: list[dict]) -> list:
    """Convert our internal parts list to Gemini SDK content format."""
    import google.generativeai.types as gtypes
    contents = []
    for p in parts:
        if p["type"] == "text":
            contents.append(p["text"])
        elif p["type"] == "image":
            import base64
            raw = base64.b64decode(p["b64"])
            contents.append({
                "mime_type": p["media_type"],
                "data": raw,
            })
    return contents


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a text response."""
    # Strip markdown fences if present
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No valid JSON found in response:\n{text[:500]}")


_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


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
    _configure_client()
    system_prompt = _get_system_prompt()

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_prompt,
        safety_settings=_SAFETY_SETTINGS,
    )

    gemini_contents = _build_gemini_contents(parts)
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(
                gemini_contents,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
                request_options={"timeout": REQUEST_TIMEOUT},
            )
            raw_text = response.text
            result = _extract_json(raw_text)
            return result

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [llm_client] JSON parse error (attempt {attempt+1}): {e}")
            # On JSON error, retry with a repair instruction appended
            gemini_contents = _build_gemini_contents(parts) + [
                "Your previous response was not valid JSON. Return ONLY the JSON object, no other text."
            ]

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if any(x in err_str for x in ("429", "resource_exhausted", "rate")):
                wait = BACKOFF_BASE ** attempt
                print(f"  [llm_client] Rate limit hit (attempt {attempt+1}), sleeping {wait}s...")
                time.sleep(wait)
            else:
                print(f"  [llm_client] Error (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE)

    raise RuntimeError(
        f"call_verifier failed after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
