# Orchestra Model Provider Integration Guide

## Purpose

This guide explains how Orchestra currently connects to real models, where that logic lives, and how to extend it safely.

Use this document if you need to:

- understand the current provider flow
- change default model assignments
- override providers per role
- add a new provider adapter
- debug why a real-model run is failing

## Current Architecture

The real-model path is already implemented.

High-level flow:

`orchestra/cli.py or orchestra/discord_bot.py -> orchestra/workflow.py -> orchestra/config.py -> orchestra/adapters.py`

Responsibilities:

- `orchestra/cli.py`
  - receives local demo input from terminal arguments or stdin
  - loads environment values
  - starts the design/review/finalize workflow
- `orchestra/discord_bot.py`
  - receives Discord slash commands and thread messages
  - loads environment values
  - starts the design/review/finalize workflow
- `orchestra/workflow.py`
  - creates agent adapters for each role
  - runs the multi-step collaboration
  - writes artifacts such as Markdown, JSON, and message logs
- `orchestra/config.py`
  - reads `AGENT_MODE`
  - selects default provider/model combinations for each role
  - applies role-level overrides from environment variables
- `orchestra/adapters.py`
  - builds prompts
  - dispatches requests to the selected provider
  - returns model text back into the workflow

## Role and Provider Model

Current roles:

- `creative_designer`
- `technical_reviewer`
- `product_ceo`
- `spec_writer`

Each role resolves to an `AgentConfig` with:

- `id`
- `role`
- `provider`
- `model`

That config is later passed into `create_adapter(...)` in `orchestra/adapters.py`.

## Mode Resolution

`orchestra/config.py` supports three top-level modes:

- `mock`
- `ollama`
- `api`

### `mock`

Every role uses the `MockAgentAdapter`.

### `ollama`

Every role defaults to provider `ollama`, with model defaults currently set to:

- Designer -> `qwen2.5-coder:7b-instruct`
- Reviewer -> `qwen2.5-coder:7b-instruct`
- CEO -> `qwen3:8b`
- Spec Writer -> `qwen2.5-coder:7b-instruct`

### `api`

The current repository uses a mixed-provider default:

- Designer -> `anthropic / claude-sonnet-4.6`
- Reviewer -> `google / gemini-3.1-pro`
- CEO -> `anthropic / claude-opus-4.7`
- Spec Writer -> `openai / gpt-5.4-mini`

Important:

`AGENT_MODE=api` does not force every role to use the same provider. It only selects the default mapping table. The actual adapter still follows each role's resolved `provider`.

## Environment Variable Override Rules

`_agent_from_defaults(...)` in `orchestra/config.py` applies overrides like this:

- provider from `<PREFIX>_PROVIDER`
- model from `<PREFIX>_MODEL`

Supported prefixes:

- `DESIGNER`
- `REVIEWER`
- `CEO`
- `SPEC_WRITER`

Examples:

- `DESIGNER_PROVIDER=anthropic`
- `DESIGNER_MODEL=claude-opus-4.7`
- `REVIEWER_PROVIDER=google`
- `REVIEWER_MODEL=gemini-3.1-pro`

This means you can:

- keep the top-level mode as `api` and still use all-OpenAI
- keep the top-level mode as `api` and mix Ollama with OpenAI or Google
- keep the top-level mode as `ollama` and override one role to `openai`

## Adapter Selection

`create_adapter(...)` in `orchestra/adapters.py` selects the implementation by `config.provider`.

Current supported providers:

- `mock`
- `ollama`
- `openai`
- `anthropic`
- `google`

Mappings:

- `mock` -> `MockAgentAdapter`
- `ollama` -> `OllamaAgentAdapter`
- `openai` -> `OpenAIAgentAdapter`
- `anthropic` -> `AnthropicAgentAdapter`
- `google` -> `GoogleAgentAdapter`

## Provider Implementation Notes

### Ollama

Class:

- `OllamaAgentAdapter`

Current behavior:

- reads `OLLAMA_BASE_URL`, default `http://localhost:11434`
- sends `POST /api/generate`
- sends `model`, `prompt`, and `stream=false`
- returns `response` text from the JSON payload

Operational implication:

- model names must already exist locally via `ollama pull`
- the current implementation is synchronous and non-streaming

### OpenAI

Class:

- `OpenAIAgentAdapter`

Current behavior:

- requires `OPENAI_API_KEY`
- imports `OpenAI` from the `openai` package
- uses `client.chat.completions.create(...)`
- sends a single user message containing the built prompt

Operational implication:

- this is a simple request path and does not yet expose temperature, max tokens, retries, or response format options

### Google

Class:

- `GoogleAgentAdapter`

Current behavior:

- requires `GOOGLE_API_KEY`
- imports `google.generativeai`
- constructs `genai.GenerativeModel(self.config.model)`
- calls `generate_content(...)`

Operational implication:

- this path is also single-shot and does not yet expose safety settings, generation config, or retries

## Prompt Construction

All non-mock providers share the same prompt builder:

- `AgentAdapter.build_prompt(...)`
- `_build_prompt(...)` in `orchestra/adapters.py`

The prompt includes:

- role rules from `orchestra/rules/`
- preset instructions from `orchestra/presets.py`
- optional `PROJECT_INSTRUCTIONS`
- the current task name
- the original user idea
- prior context
- optional human intervention

This is useful because provider swapping does not require rewriting prompt composition.

## How To Change Default Models

If you want to permanently change defaults for a mode, edit:

- `orchestra/config.py`

Most likely touchpoint:

- `_defaults_for_mode(mode: str)`

Use this when:

- the team has settled on better baseline models
- you want a cheaper API default
- you want all API-mode roles to default to one provider

## How To Add a New Provider

To add a new provider cleanly:

1. Add a new adapter class in `orchestra/adapters.py`.
2. Reuse `self.build_prompt(...)` so prompt formatting stays consistent.
3. Add a new branch in `create_adapter(...)`.
4. Set the provider string in `orchestra/config.py` defaults or role overrides.
5. Add or update tests in `tests/`.
6. Update `README.md` and the quick-start guide if the provider becomes a supported path.

Example shape:

```python
class AnthropicAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        api_key = self.env.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Anthropic agents.")
        ...
        return text.strip()
```

Then register:

```python
if config.provider == "anthropic":
    return AnthropicAgentAdapter(config, env)
```

## Recommended Tests for Provider Work

If provider logic changes, verify at least these areas:

- mode parsing in `orchestra/config.py`
- provider/model override resolution per role
- unsupported provider failure path
- adapter selection behavior
- workflow message metadata includes `provider`, `model`, and `agent_config_id`

Good test targets:

- `tests/test_orchestra_core.py`

## Known Limitations

The current implementation is good for MVP demos, but there are a few important limits.

### 1. `api` mode is a label, not a single-provider mode

Today it means "use the API default table," not "everything uses one API vendor."

This is flexible, but it can confuse operators if the documentation is too short.

### 2. Per-provider runtime controls are minimal

There is no first-class configuration yet for:

- temperature
- token limits
- retries
- timeout per provider
- structured response settings

### 3. Error handling is basic

The current code returns helpful top-level failures, but it does not yet include:

- automatic retries
- rate-limit backoff
- provider-specific logging details
- partial fallback to another provider

### 4. Dependency expectations are implicit

The code assumes the right package is installed and the environment variable exists. This is fine for an MVP, but a setup preflight would reduce friction.

## Recommended Next Improvements

If the team wants smoother production-like usage, these are the most useful next steps.

### 1. Add a provider preflight check

Before a run starts, validate:

- required API keys exist for selected providers
- Ollama endpoint is reachable when any role uses `ollama`
- configured model names are non-empty

Best insertion point:

- before `run_design_review(...)` starts real generation

### 2. Separate mode naming from provider composition

Possible future direction:

- keep `AGENT_MODE` for broad presets like `demo`, `local`, `cloud`
- move actual provider composition fully to role-level config

This would better match how the code already behaves internally.

### 3. Add provider settings per role

Possible future environment variables:

- `DESIGNER_TEMPERATURE`
- `REVIEWER_TIMEOUT_SECONDS`
- `SPEC_WRITER_MAX_TOKENS`

### 4. Add a unified config dump for debugging

At run start, print or persist the resolved role matrix:

- role
- provider
- model

This would make support and demo debugging much easier.

## Practical Operating Advice

For this repository's current maturity:

- use `mock` when the demo must never fail
- use `ollama` when local execution matters more than output quality
- use `api` when you want stronger outputs and are comfortable with external dependencies
- use role-level overrides instead of editing code for one-off experiments

## Source Map

Primary files:

- `orchestra/cli.py`
- `orchestra/discord_bot.py`
- `orchestra/config.py`
- `orchestra/adapters.py`
- `orchestra/workflow.py`
- `requirements.txt`

Reference docs:

- `README.md`
- `docs/guides/ollama-quickstart.md`
