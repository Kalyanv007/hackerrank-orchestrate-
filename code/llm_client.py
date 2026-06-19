"""llm_client.py — Thin wrapper for OpenRouter (OpenAI-compatible API).

Uses the `openai` SDK with OpenRouter's base URL so any model available
on OpenRouter can be used by changing OPENROUTER_MODEL.

Env vars:
    OPENROUTER_API_KEY  — your OpenRouter API key (required)
    OPENROUTER_MODEL    — model slug (default: google/gemini-2.5-flash)
"""

import base64
import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
MAX_RETRIES = 4
BACKOFF_BASE = 5.0  # seconds
REQUEST_TIMEOUT = 120

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "claim_verifier_system_prompt.md"
_SYSTEM_PROMPT: str | None = None
_CLIENT: OpenAI | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY env var is not set.")
        _CLIENT = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=REQUEST_TIMEOUT,
        )
    return _CLIENT


def _build_openai_messages(system_prompt: str, parts: list[dict]) -> list[dict]:
    """Convert internal parts list to OpenAI vision message format."""
    user_content = []
    for p in parts:
        if p["type"] == "text":
            user_content.append({"type": "text", "text": p["text"]})
        elif p["type"] == "image" and p.get("b64"):
            data_url = f"data:{p['media_type']};base64,{p['b64']}"
            user_content.append({
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "high"},
            })
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


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
    Send a multimodal claim verification request via OpenRouter.

    Returns:
        Parsed JSON dict with the 10 output fields.
    Raises:
        RuntimeError after all retries are exhausted.
    """
    client = _get_client()
    system_prompt = _get_system_prompt()
    messages = _build_openai_messages(system_prompt, parts)
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.0,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content or ""
            result = _extract_json(raw_text)
            return result

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  [llm_client] JSON parse error (attempt {attempt+1}): {e}")
            # Append fix instruction to messages and retry
            messages = _build_openai_messages(system_prompt, parts) + [{
                "role": "user",
                "content": "Your previous response was not valid JSON. Return ONLY the JSON object, no other text.",
            }]

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if any(x in err_str for x in ("429", "rate", "quota", "too many")):
                wait = BACKOFF_BASE * (2 ** attempt)
                # Try to parse a Retry-After value from the error
                m = re.search(r"retry.after[^\d]*(\d+)", str(e), re.IGNORECASE)
                if m:
                    wait = max(float(m.group(1)) + 2, wait)
                print(f"  [llm_client] Rate limit (attempt {attempt+1}), sleeping {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"  [llm_client] Error (attempt {attempt+1}): {type(e).__name__}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE)

    raise RuntimeError(
        f"call_verifier failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    )
