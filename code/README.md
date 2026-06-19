# Multi-Modal Evidence Review — Code

Damage claim verifier using OpenRouter (multi-modal LLMs). Reads `dataset/claims.csv` and
produces `output.csv` with structured verdicts per claim.

## Requirements

- Python 3.10+
- An [OpenRouter](https://openrouter.ai) API key with credits

## Setup

```bash
cd code/
pip install openai pillow python-dotenv
cp .env.example .env
# Edit .env and set your OPENROUTER_API_KEY
```

## Run (produce output.csv)

```bash
python code/main.py
# or with explicit paths:
python code/main.py --input dataset/claims.csv --output output.csv
```

## Run Evaluation (against sample_claims.csv)

```bash
python code/evaluation/main.py
```

This compares **Strategy A** (full prompt with evidence rules) vs **Strategy B** (ablation
without evidence rules) on the 20 labeled sample rows and writes:

- `code/evaluation/eval_predictions_A.csv`
- `code/evaluation/eval_predictions_B.csv`
- `code/evaluation/evaluation_report.md`

## File Map

| File | Purpose |
|---|---|
| `main.py` | Entry point — processes `claims.csv`, writes `output.csv` |
| `schema.py` | All allowed vocabularies and column order (single source of truth) |
| `data_loader.py` | CSV loading, user-history join, image codec sniffing & base64 encoding |
| `llm_client.py` | Gemini API wrapper with retry/backoff |
| `validator.py` | Vocabulary clamping + consistency rule enforcement |
| `prompts/claim_verifier_system_prompt.md` | System prompt (anti-injection, stock-photo detection, evidence rules) |
| `prompts/claim_verifier_user_template.py` | User-turn message builder |
| `evaluation/main.py` | Evaluation harness (two strategies, scoring, report) |
| `evaluation/metrics.py` | Per-field scoring utilities |
| `evaluation/evaluation_report.md` | Generated after running evaluation |

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|
|---|
| `OPENROUTER_API_KEY` | Yes | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | No | `google/gemini-2.5-flash` | Any multimodal model on OpenRouter |

## Notes

- Image files referenced in CSVs may be JPEG, PNG, or WebP despite the `.jpg` extension.
  The loader sniffs the actual codec and normalizes to JPEG before sending to the API.
- The system prompt explicitly instructs the model to ignore any text/instructions found
  *inside* submitted images (defense against prompt-injection via physical sticky notes).
- All secrets must come from env vars — never hardcode an API key.
