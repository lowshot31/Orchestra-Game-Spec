# Orchestra Ollama / API Quick Start

## Purpose

This guide is for someone who wants Orchestra to stop using mock outputs and start using real models with the current codebase.

Use this document when you want:

- local model execution with Ollama
- external model execution with OpenAI and Google APIs
- quick troubleshooting when a run fails before or during generation

## What already exists

The current repository already includes provider adapters for:

- `mock`
- `ollama`
- `openai`
- `google`

The runtime switch is controlled by `AGENT_MODE`.

No new integration code is required for a basic real-model run.

## Mode Summary

| Mode   | Value    | Main use                                           |
| :----- | :------- | :------------------------------------------------- |
| Mock   | `mock`   | Demo path without external dependencies            |
| Ollama | `ollama` | Local model execution through Ollama               |
| API    | `api`    | External model execution through OpenAI and Google |

## Before You Start

Make sure these are ready:

- Python virtual environment created and activated
- `pip install -r requirements.txt` completed
- CLI or Discord bot runs in the same terminal session

Base startup:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Quick Start: Ollama

### 1. Install and run Ollama

Make sure the Ollama app or server is running locally.

Quick health check:

```powershell
ollama list
```

If this command fails, start Ollama first.

### 2. Pull the models you want to use

Example:

```powershell
ollama pull qwen2.5-coder:7b-instruct
ollama pull qwen3:8b
```

These names match the current defaults in `orchestra/config.py`.

### 3. Start Orchestra in Ollama mode

```powershell
$env:AGENT_MODE="ollama"
$env:DESIGNER_MODEL="qwen2.5-coder:7b-instruct"
$env:REVIEWER_MODEL="qwen2.5-coder:7b-instruct"
$env:CEO_MODEL="qwen3:8b"
$env:SPEC_WRITER_MODEL="qwen2.5-coder:7b-instruct"
python -m orchestra.cli --mode ollama
```

### 4. Optional: custom Ollama endpoint

If Ollama is not running on the default local address:

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434"
```

## Quick Start: API Mode

### 1. Install dependencies

`requirements.txt` already includes:

- `openai`
- `google-generativeai`

If needed, refresh them:

```powershell
pip install -r requirements.txt
```

### 2. Set API keys

```powershell
$env:AGENT_MODE="api"
$env:OPENAI_API_KEY="your-openai-api-key"
$env:GOOGLE_API_KEY="your-google-api-key"
```

### 3. Start Orchestra

```powershell
python -m orchestra.cli --mode api
```

### 4. Understand the default API routing

In `api` mode, the current defaults are:

- Designer -> `anthropic / claude-sonnet-4`
- Reviewer -> `google / gemini-3.1-pro`
- CEO -> `anthropic / claude-opus-4.7`
- Spec Writer -> `openai / gpt-5.5`

This is defined in `orchestra/config.py`.

## Role Override Examples

You can override provider and model per role without changing code.

### All OpenAI example

```powershell
$env:AGENT_MODE="api"
$env:OPENAI_API_KEY="your-openai-api-key"
$env:DESIGNER_PROVIDER="openai"
$env:DESIGNER_MODEL="gpt-5.5"
$env:REVIEWER_PROVIDER="openai"
$env:REVIEWER_MODEL="gpt-5.4"
$env:CEO_PROVIDER="openai"
$env:CEO_MODEL="gpt-5.4"
$env:SPEC_WRITER_PROVIDER="openai"
$env:SPEC_WRITER_MODEL="gpt-5.4"
python -m orchestra.cli --mode api
```

Note:

- the current code still treats this as `AGENT_MODE=api`
- provider selection actually follows the role-specific `*_PROVIDER` values
- if no role uses `google`, `GOOGLE_API_KEY` does not need to be set

### Mixed Ollama + API example

```powershell
$env:AGENT_MODE="api"
$env:OPENAI_API_KEY="your-openai-api-key"
$env:GOOGLE_API_KEY="your-google-api-key"
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"
$env:DESIGNER_PROVIDER="anthropic"
$env:DESIGNER_MODEL="claude-opus-4.7"
$env:REVIEWER_PROVIDER="google"
$env:REVIEWER_MODEL="gemini-3.1-pro"
$env:CEO_PROVIDER="openai"
$env:CEO_MODEL="gpt-5.4"
$env:SPEC_WRITER_PROVIDER="openai"
$env:SPEC_WRITER_MODEL="gpt-5.4"
python -m orchestra.cli --mode api
```

This works because adapter creation follows the per-role provider value, not only the top-level mode.

## Environment Variable Reference

Top-level:

- `AGENT_MODE`
- `AGENT_PRESET`
- `PROJECT_INSTRUCTIONS`
- `OLLAMA_BASE_URL`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`

Role-specific:

- `DESIGNER_PROVIDER`
- `DESIGNER_MODEL`
- `REVIEWER_PROVIDER`
- `REVIEWER_MODEL`
- `CEO_PROVIDER`
- `CEO_MODEL`
- `SPEC_WRITER_PROVIDER`
- `SPEC_WRITER_MODEL`

## Recommended First Real Run

If you want the least setup pain:

1. Try `ollama` first if you already use Ollama locally.
2. Try `api` next if you want stronger output quality quickly.
3. Keep one role on a cheaper model first, usually `CEO` or `SPEC_WRITER`.

## Troubleshooting

### `Ollama request failed`

Check:

- Ollama is running
- the model was pulled
- `OLLAMA_BASE_URL` is correct

Verification:

```powershell
ollama list
```

### `OPENAI_API_KEY is required for OpenAI agents`

Set the key in the same PowerShell session:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
```

### `GOOGLE_API_KEY is required for Google agents`

Set the key in the same PowerShell session:

```powershell
$env:GOOGLE_API_KEY="your-google-api-key"
```

### `Install openai to use API mode`

Install dependencies again:

```powershell
pip install -r requirements.txt
```

### `Install google-generativeai to use API mode`

Install dependencies again:

```powershell
pip install -r requirements.txt
```

## Where to Look in Code

- `orchestra/cli.py`: local CLI demo entrypoint
- `orchestra/discord_bot.py`: Discord bot entrypoint
- `orchestra/workflow.py`: run orchestration and artifact generation
- `orchestra/config.py`: default role/provider/model mapping
- `orchestra/adapters.py`: actual provider calls

## Practical Recommendation

For demos:

- use `mock` for guaranteed reproducibility
- use `ollama` when internet-independent local runs matter
- use `api` when output quality matters more than cost and setup simplicity
