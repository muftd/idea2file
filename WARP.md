# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Common commands

- Install deps

```bash path=null start=null
pip install -r requirements.txt
```

- Run (offline demo mode)

```bash path=null start=null
python main.py --idea "你的想法一句话"
```

- Run (AI mode via OpenRouter-compatible API)

```bash path=null start=null
# Set your key before running (replace {{OPENAI_API_KEY}})
export OPENAI_API_KEY={{OPENAI_API_KEY}}
# Optional: override base URL if not using the default OpenRouter endpoint
# export OPENAI_BASE_URL=https://openrouter.ai/api/v1
python main.py --idea "你的想法一句话"
```

- Interactive input (no --idea)

```bash path=null start=null
python main.py
```

Notes
- No test suite or linting tools are configured in this repo.

## High-level architecture

Big picture
- CLI app with a single entrypoint: `main.py`.
- Prompts are scaffolded from `prompt_template.txt`, then augmented with the user’s idea.
- Two modes: offline (no API key) returns template-based output; AI mode (with `OPENAI_API_KEY`) calls a Chat Completions API.
- Output is a timestamped Markdown file in the repo root; naming avoids collisions.

Key flows (from `main.py`)
- Input handling: `--idea` arg takes precedence; otherwise prompts via `input()`.
- Template loading: `read_template()` reads `prompt_template.txt` (UTF-8).
- API key discovery: `load_api_key()` checks `OPENAI_API_KEY` only (intentionally isolated for future extension).
- LLM call (optional): `call_openai_api()` uses the `openai` SDK with
  - `api_key=OPENAI_API_KEY`
  - `base_url` from `OPENAI_BASE_URL` or defaults to `https://openrouter.ai/api/v1`
  - `model="openrouter/auto"`
  - Chinese system prompt: “你是知识结构化助手。”
- Fallback logic: if no key or the API call fails, `generate_markdown()` returns merged template content.
- File naming: `build_output_path()`
  - Prefix: `YYYY-MM-DD_HHMM-`
  - Stem from `_sanitize_visible_text()` (first N visible chars, non-alnum stripped; defaults to `idea`).
  - De-dup: appends `-2`, `-3`, … if a name already exists.

Where to change things
- Prompt/template wording: edit `prompt_template.txt`.
- Model/provider or endpoint: see `call_openai_api()` (model) and `OPENAI_BASE_URL` (endpoint).
- File naming rules: `_sanitize_visible_text()` and `build_output_path()`.
- Non-interactive usage: pass `--idea` to `main.py`.

## Important from README
- Quick start: clone → `pip install -r requirements.txt` → `python main.py`.
- Modes: offline demo (no key) vs AI mode (set `OPENAI_API_KEY`).
- Naming: semantic filename derived from idea; conflicts resolved with timestamp/sequence.
- Rationale: API key lookup decoupled from generation flow to allow provider swaps or offline demos.
