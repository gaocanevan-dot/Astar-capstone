# Running the single-agent framework

## Prerequisites

- Python 3.10+
- OpenAI API key (any project tier with `gpt-4o-mini` access — `.env` can pin a different model via `OPENAI_MODEL`)
- Git
- Optional: Foundry, Slither (not needed for single-agent variant)

## One-time setup

```bash
git clone <this repo>
cd agent

# Windows (use forward slashes in paths)
python -m venv venv
venv/Scripts/python.exe -m pip install -U pip
venv/Scripts/python.exe -m pip install -e .

# Linux/WSL
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -e .

# Configure API key
cp .env.example .env
# Edit .env to set OPENAI_API_KEY=sk-...
# Optionally set OPENAI_MODEL (default falls back to gpt-4o-mini if unset)
```

## Run the single-agent evaluation

### Full run (42 cases, ~14 min, ~42 LLM calls)

```bash
# Windows
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_single_agent.py

# Linux/WSL
PYTHONIOENCODING=utf-8 python scripts/run_single_agent.py
```

Outputs:
- `data/evaluation/single_agent_predictions.json` — per-case predictions + tokens + fingerprints
- `data/evaluation/single_agent_summary.md` — aggregate Recall + per-case table

### Smoke (5 cases)

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_single_agent.py --limit 5
```

### Dry-run (no LLM cost, verifies schema only)

```bash
venv/Scripts/python.exe scripts/run_single_agent.py --dry-run
```

## Run unit tests

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m pytest tests/unit/ -v
```

Expected: 23 passed in under 1 second (no network required).

## Rebuild the evaluation dataset from source JSONs

Normally the eval_set is pre-built and hash-locked. To rebuild:

```bash
venv/Scripts/python.exe scripts/build_eval_set.py --validate
```

Re-running this will regenerate `bad_cases.json` and `eval_set.json` from
`vulnerabilities.json` + `vulnerabilities_pre.json` (deduped to 42 unique IDs).

## Reproducibility caveats

- **LLM determinism is best-effort.** OpenAI's `seed` parameter is a hint,
  not a guarantee. Each prediction record stores the `system_fingerprint`
  observed at call time; two runs with the same seed may differ if the model
  rolled a new fingerprint between calls. Report the fingerprint in paper
  tables as a footnote.
- **Reasoning-family models (gpt-5, o1/o3/o4) ignore `temperature` + `seed`.**
  The adapter detects these and omits the parameters silently.
- **42 cases is the current dataset baseline.** See `docs/DATASET.md` (future)
  for harvesting plans to 150.

## Expected wall-clock

- Smoke (5 cases, ~3 LLM calls after 2 skip): ~60 seconds
- Full (42 cases, ~40 LLM calls): ~14 minutes
- Unit tests: <1 second

## Files this variant produces

```
data/evaluation/single_agent_predictions.json
data/evaluation/single_agent_summary.md
data/evaluation/single_agent_run_full.log  (only if tee'd from CLI)
```

To reset a run, delete those three files and re-invoke.
