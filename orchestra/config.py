from __future__ import annotations

import os
from collections.abc import Mapping

from .models import AgentConfig, AgentConfigSet


def load_agent_configs(env: Mapping[str, str] | None = None) -> AgentConfigSet:
    source = os.environ if env is None else env
    mode = source.get("AGENT_MODE", "mock").strip().lower() or "mock"
    if mode not in {"mock", "ollama", "api"}:
        raise ValueError("AGENT_MODE must be one of: mock, ollama, api")

    defaults = _defaults_for_mode(mode)
    agents = tuple(_agent_from_defaults(source, *definition) for definition in defaults)
    return AgentConfigSet(mode=mode, agents=agents)


def _defaults_for_mode(mode: str) -> tuple[tuple[str, str, str, str, str], ...]:
    if mode == "ollama":
        return (
            ("creative_designer", "game_designer", "DESIGNER", "ollama", "llama3.1:8b"),
            ("technical_reviewer", "technical_reviewer", "REVIEWER", "ollama", "qwen2.5-coder:7b"),
            ("product_ceo", "product_ceo", "CEO", "ollama", "qwen3:8b"),
            ("spec_writer", "spec_writer", "SPEC_WRITER", "ollama", "mistral:7b"),
        )
    if mode == "api":
        return (
            ("creative_designer", "game_designer", "DESIGNER", "anthropic", "claude-sonnet-4.6"),
            ("technical_reviewer", "technical_reviewer", "REVIEWER", "google", "gemini-3.1-pro"),
            ("product_ceo", "product_ceo", "CEO", "anthropic", "claude-opus-4.7"),
            ("spec_writer", "spec_writer", "SPEC_WRITER", "openai", "gpt-5.4-mini"),
        )
    return (
        ("creative_designer", "game_designer", "DESIGNER", "mock", "designer"),
        ("technical_reviewer", "technical_reviewer", "REVIEWER", "mock", "reviewer"),
        ("product_ceo", "product_ceo", "CEO", "mock", "ceo"),
        ("spec_writer", "spec_writer", "SPEC_WRITER", "mock", "writer"),
    )


def _agent_from_defaults(
    source: Mapping[str, str],
    agent_id: str,
    role: str,
    prefix: str,
    default_provider: str,
    default_model: str,
) -> AgentConfig:
    provider = source.get(f"{prefix}_PROVIDER", default_provider)
    model = source.get(f"{prefix}_MODEL", default_model)
    return AgentConfig(agent_id, role, provider, model)
