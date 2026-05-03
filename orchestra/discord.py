from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_agent_configs
from .pipeline import build_execution_plan
from .prototype import generate_playable_prototype
from .run_view import format_progress_board

ROLE_DISPLAY_LABELS = {
    "human_operator": "Human",
    "creative_designer": "Designer",
    "technical_reviewer": "Reviewer",
    "product_ceo": "CEO",
    "spec_writer": "Writer",
}

ROLE_EMOJIS = {
    "human_operator": "👤",
    "creative_designer": "🎨",
    "technical_reviewer": "🛠️",
    "product_ceo": "💼",
    "spec_writer": "📝",
}

MESSAGE_TYPE_LABELS = {
    "user_request": "User Request",
    "draft": "Draft",
    "review": "Review",
    "ceo_review": "CEO Review",
    "intervention": "Intervention",
    "revision": "Revision",
    "final_spec": "Final Spec",
}


@dataclass(frozen=True)
class DiscordCommand:
    group: str
    action: str
    arguments: dict[str, str]


@dataclass
class DiscordBotState:
    extra_agents: list[dict[str, str]] = field(default_factory=list)
    skill_overrides: dict[str, str] = field(default_factory=dict)
    agent_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    last_run: dict[str, str] | None = None
    server_config: dict[str, str] = field(default_factory=dict)
    api_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class DiscordCommandResult:
    message: str
    workspace: ProjectWorkspace | None = None
    collaboration_result: Any | None = None


@dataclass(frozen=True)
class ProjectWorkspace:
    project_name: str
    category_name: str
    brief_channel_name: str
    runs_channel_name: str
    handoff_channel_name: str
    team_channel_name: str
    run_thread_name: str

    def to_dict(self) -> dict[str, str]:
        return {
            "project": self.project_name,
            "category": self.category_name,
            "brief_channel": self.brief_channel_name,
            "runs_channel": self.runs_channel_name,
            "handoff_channel": self.handoff_channel_name,
            "team_channel": self.team_channel_name,
            "run_thread": self.run_thread_name,
        }


@dataclass(frozen=True)
class DiscordDelivery:
    channel: str
    thread: str
    content: str
    kind: str = "message"

    def to_dict(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "thread": self.thread,
            "kind": self.kind,
            "content": self.content,
        }


class DiscordTransport:
    name = "base"

    def send_message(self, channel_name: str, thread_name: str, content: str) -> DiscordDelivery:
        raise NotImplementedError


@dataclass
class MockDiscordTransport(DiscordTransport):
    deliveries: list[DiscordDelivery] = field(default_factory=list)
    name = "mock"

    def send_message(self, channel_name: str, thread_name: str, content: str) -> DiscordDelivery:
        delivery = DiscordDelivery(
            channel=channel_name,
            thread=thread_name,
            content=content,
        )
        self.deliveries.append(delivery)
        return delivery


class BotDiscordTransport(DiscordTransport):
    name = "bot"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("DISCORD_BOT_TOKEN", "").strip()

    def send_message(self, channel_name: str, thread_name: str, content: str) -> DiscordDelivery:
        if not self.token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required for bot transport.")
        raise NotImplementedError(
            "Bot transport is intentionally left as a wiring seam for post-submission Discord integration."
        )


class ApiConnector:
    name = "base"

    def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockApiConnector(ApiConnector):
    name = "mock"

    def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "mocked",
            "action": action,
            "payload": payload,
        }


def parse_discord_command(content: str) -> DiscordCommand:
    stripped = content.strip()
    if not stripped.startswith("/orchestra "):
        raise ValueError("Discord commands must start with /orchestra")

    tokens = shlex.split(stripped)
    if len(tokens) < 2:
        raise ValueError("Discord commands must include a command.")

    group = tokens[1].strip().lower()
    if group in {"help", "status"}:
        return DiscordCommand(group=group, action="default", arguments={})
    if group == "start":
        idea = " ".join(tokens[2:]).strip()
        if idea.startswith("idea="):
            idea = idea.split("=", 1)[1].strip()
        return DiscordCommand(
            group=group,
            action="default",
            arguments={"idea": idea} if idea else {},
        )
    if group == "revise":
        instruction = " ".join(tokens[2:]).strip()
        if instruction.startswith("instruction="):
            instruction = instruction.split("=", 1)[1].strip()
        return DiscordCommand(
            group=group,
            action="default",
            arguments={"instruction": instruction} if instruction else {},
        )

    if len(tokens) < 3:
        raise ValueError("Discord commands must include a group and action.")

    action_token = tokens[2].strip()
    if "=" in action_token:
        action = "default"
        argument_tokens = tokens[2:]
    else:
        action = action_token.lower()
        argument_tokens = tokens[3:]
    arguments: dict[str, str] = {}
    for token in argument_tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        arguments[key.strip().lower()] = value.strip()
    return DiscordCommand(group=group, action=action, arguments=arguments)


def build_workspace_from_env(env: dict[str, str] | os._Environ[str]) -> ProjectWorkspace:
    project_name = env.get("DISCORD_PROJECT", "orchestra-demo")
    run_name = env.get("DISCORD_RUN", "latest")
    return ProjectWorkspace(
        project_name=project_name,
        category_name=f"project-{_slugify(project_name)}",
        brief_channel_name="proj-brief",
        runs_channel_name="proj-runs",
        handoff_channel_name="proj-handoffs",
        team_channel_name="proj-team",
        run_thread_name=f"run-{_slugify(run_name)}",
    )


def create_discord_transport(mode: str, env: dict[str, str] | os._Environ[str] | None = None) -> DiscordTransport:
    normalized = (mode or "mock").strip().lower()
    if normalized == "bot":
        token = None if env is None else env.get("DISCORD_BOT_TOKEN")
        return BotDiscordTransport(token=token)
    return MockDiscordTransport()


def export_collaboration_to_discord(
    result: Any,
    workspace: ProjectWorkspace,
    transport: DiscordTransport,
    artifact_dir: Path | str,
    preset: str = "balanced",
) -> Path:
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)

    _send_workspace_overview(transport, workspace, preset, result)
    _send_sprint_summary(transport, workspace, result)
    _send_task_handoff(transport, workspace, result)
    _send_run_thread_messages(transport, workspace, result)

    payload = {
        "transport": transport.name,
        "workspace": workspace.to_dict(),
        "deliveries": [
            delivery.to_dict()
            for delivery in getattr(transport, "deliveries", [])
        ],
    }
    output_path = artifact_path / "discord_sync.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def execute_discord_command(
    command: DiscordCommand,
    state: DiscordBotState,
    base_env: dict[str, str] | os._Environ[str] | None = None,
    artifact_dir: Path | str = "artifacts",
) -> DiscordCommandResult:
    source = dict(os.environ if base_env is None else base_env)

    if command.group == "help":
        return DiscordCommandResult(message=build_help_message(source, state))

    if command.group == "status":
        return DiscordCommandResult(message=build_status_message(state, source))

    if command.group == "revise":
        from .workflow import run_collaboration

        if not state.last_run:
            raise ValueError('revise requires a previous run. Try: /tutti start "작은 게임 아이디어"')
        instruction = command.arguments.get("instruction", "").strip()
        if not instruction:
            raise ValueError('revise requires an instruction. Try: /tutti revise "속도를 낮춰줘"')
        env = _build_revise_env(state, source)
        workspace = build_workspace_from_env(env)
        idea = state.last_run["idea"]
        result = run_collaboration(
            idea,
            intervention=instruction,
            env=env,
            artifact_dir=artifact_dir,
        )
        run_artifact_dir = result.final_spec_path.parent
        playable_dir = generate_playable_prototype(
            idea=idea,
            final_spec=result.final_spec_path.read_text(encoding="utf-8"),
            artifact_dir=run_artifact_dir,
            run_name=env["DISCORD_RUN"],
            env=env,
        )
        result.playable_dir = playable_dir
        state.last_run = {
            "idea": idea,
            "project": env["DISCORD_PROJECT"],
            "feature": env["DISCORD_FEATURE"],
            "sprint": env["DISCORD_SPRINT"],
            "task": env["DISCORD_TASK"],
            "run_name": env["DISCORD_RUN"],
            "run_thread": workspace.run_thread_name,
            "mode": env.get("AGENT_MODE", "mock"),
            "provider": load_agent_configs(env).by_id["creative_designer"].provider,
            "model": load_agent_configs(env).by_id["creative_designer"].model,
            "final_spec_path": str(result.final_spec_path),
            "schema_path": str(result.schema_path),
            "playable_dir": str(playable_dir),
            "intervention": instruction,
        }
        return DiscordCommandResult(
            message=(
                "Revision completed.\n"
                f"- Run: `{workspace.run_thread_name}`\n"
                f"- Instruction: {instruction}\n"
                f"- Updated output: `{format_display_path(result.final_spec_path)}`\n"
                f"- Playable: `{format_display_path(playable_dir / 'index.html')}`"
            ),
            workspace=workspace,
            collaboration_result=result,
        )

    if command.group == "start":
        from .workflow import run_collaboration

        env = _build_start_env(command, state, source)
        workspace = build_workspace_from_env(env)
        idea = command.arguments.get("idea", "").strip()
        if not idea:
            raise ValueError('start requires an idea. Try: /tutti start "작은 게임 아이디어"')
        result = run_collaboration(
            idea,
            intervention=command.arguments.get("intervention", "").strip(),
            env=env,
            artifact_dir=artifact_dir,
        )
        run_artifact_dir = result.final_spec_path.parent
        playable_dir = generate_playable_prototype(
            idea=idea,
            final_spec=result.final_spec_path.read_text(encoding="utf-8"),
            artifact_dir=run_artifact_dir,
            run_name=env["DISCORD_RUN"],
            env=env,
        )
        result.playable_dir = playable_dir
        state.last_run = {
            "idea": idea,
            "project": env["DISCORD_PROJECT"],
            "feature": env["DISCORD_FEATURE"],
            "sprint": env["DISCORD_SPRINT"],
            "task": env["DISCORD_TASK"],
            "run_name": env["DISCORD_RUN"],
            "run_thread": workspace.run_thread_name,
            "mode": env.get("AGENT_MODE", "mock"),
            "provider": load_agent_configs(env).by_id["creative_designer"].provider,
            "model": load_agent_configs(env).by_id["creative_designer"].model,
            "final_spec_path": str(result.final_spec_path),
            "schema_path": str(result.schema_path),
            "playable_dir": str(playable_dir),
            "intervention": "",
        }
        return DiscordCommandResult(
            message=(
                "Playable prototype request accepted.\n"
                f"- Run: `{workspace.run_thread_name}`\n"
                f"- Idea: {idea}\n"
                f"- Current output: `{format_display_path(result.final_spec_path)}`\n"
                f"- Playable: `{format_display_path(playable_dir / 'index.html')}`"
            ),
            workspace=workspace,
            collaboration_result=result,
        )

    if command.group == "agent" and command.action == "add":
        agent_record = {
            "role": command.arguments.get("role", "assistant"),
            "provider": command.arguments.get("provider", "mock"),
            "model": command.arguments.get("model", "assistant"),
        }
        state.extra_agents.append(agent_record)
        return DiscordCommandResult(
            message=(
                "Agent registered for future Discord runs: "
                f"`{agent_record['role']}` via `{agent_record['provider']}/{agent_record['model']}`."
            )
        )

    if command.group == "agent" and command.action in {"list", "show"}:
        return DiscordCommandResult(message=build_agent_settings_message(state, source))

    if command.group == "agent" and command.action == "config":
        role = command.arguments.get("role", "").strip()
        provider = command.arguments.get("provider", "").strip()
        model = command.arguments.get("model", "").strip()
        if not role or not provider or not model:
            raise ValueError("agent config requires role, provider, and model.")
        state.agent_overrides[role] = {"provider": provider, "model": model}
        return DiscordCommandResult(
            message=f"Agent config updated for `{role}`: `{provider}/{model}`"
        )

    if command.group == "skill" and command.action == "override":
        role = command.arguments.get("role", "shared")
        instruction = command.arguments.get("instruction", "").strip()
        if not instruction:
            raise ValueError("skill override requires an instruction=... argument.")
        state.skill_overrides[role] = instruction
        return DiscordCommandResult(
            message=f"Skill override saved for `{role}`: {instruction}"
        )

    if command.group == "run" and command.action == "create":
        from .workflow import run_collaboration

        env = _build_run_env(command, state, source)
        workspace = build_workspace_from_env(env)
        idea = command.arguments.get("idea", "").strip()
        if not idea:
            raise ValueError("run create requires idea=\"...\".")
        result = run_collaboration(
            idea,
            intervention=command.arguments.get("intervention", "").strip(),
            env=env,
            artifact_dir=artifact_dir,
        )
        run_artifact_dir = result.final_spec_path.parent
        playable_dir = generate_playable_prototype(
            idea=idea,
            final_spec=result.final_spec_path.read_text(encoding="utf-8"),
            artifact_dir=run_artifact_dir,
            run_name=env["DISCORD_RUN"],
            env=env,
        )
        result.playable_dir = playable_dir
        state.last_run = {
            "idea": idea,
            "project": env["DISCORD_PROJECT"],
            "feature": env["DISCORD_FEATURE"],
            "sprint": env["DISCORD_SPRINT"],
            "task": env["DISCORD_TASK"],
            "run_name": env["DISCORD_RUN"],
            "run_thread": workspace.run_thread_name,
            "mode": env.get("AGENT_MODE", "mock"),
            "provider": load_agent_configs(env).by_id["creative_designer"].provider,
            "model": load_agent_configs(env).by_id["creative_designer"].model,
            "final_spec_path": str(result.final_spec_path),
            "schema_path": str(result.schema_path),
            "playable_dir": str(playable_dir),
            "intervention": "",
        }
        return DiscordCommandResult(
            message=(
                "Run completed for "
                f"`{workspace.run_thread_name}`. Final spec saved to `{format_display_path(result.final_spec_path)}`.\n"
                f"- Playable: `{format_display_path(playable_dir / 'index.html')}`"
            ),
            workspace=workspace,
            collaboration_result=result,
        )

    if command.group == "run" and command.action == "review":
        run_name = command.arguments.get("run", "latest")
        return DiscordCommandResult(
            message=f"Review command received for run `{_slugify(run_name)}`. Use the latest posted run thread for artifacts."
        )

    if command.group == "handoff":
        project_name = command.arguments.get("project", source.get("DISCORD_PROJECT", "orchestra-demo"))
        feature_name = command.arguments.get("feature", source.get("DISCORD_FEATURE", "design-handoff"))
        sprint_name = command.arguments.get("sprint", source.get("DISCORD_SPRINT", "sprint-01"))
        return DiscordCommandResult(
            message=(
                "Handoff queued for "
                f"`project-{_slugify(project_name)}` / `feature-{_slugify(feature_name)}` / `{_slugify(sprint_name)}`."
            )
        )

    raise ValueError(f"Unsupported Discord command: {command.group} {command.action}")


def build_onboarding_message(mode: str = "mock", model: str = "mock") -> str:
    return (
        "# Tutti Home\n\n"
        "```text\n"
        "이 채널은 시작용 홈입니다.\n"
        "- 새 run 시작\n"
        "- 상태 확인\n"
        "- 설정 변경\n\n"
        "실제 진행은 생성된 run thread 안에서 이어집니다.\n"
        "```"
        "\n\n"
        "Start here:\n"
        '- `/tutti start "작은 게임 아이디어"`\n\n'
        "Quick actions:\n"
        "- `/tutti help`\n"
        "- `/tutti status`\n"
        "- `/tutti settings`\n\n"
        "Runtime:\n"
        f"- Mode: `{mode}`\n"
        f"- Model: `{model}`"
    )


def build_help_message(source: dict[str, str], state: DiscordBotState) -> str:
    mode = source.get("AGENT_MODE", "mock")
    model = source.get("DESIGNER_MODEL", "mock")
    advanced_count = len(state.extra_agents) + len(state.skill_overrides) + len(state.agent_overrides)
    return (
        "# Tutti Help\n\n"
        "```text\n"
        "일반 채널에서는 run을 시작만 하세요.\n"
        "실제 토론, 승인, 수정, 결과 확인은 run thread에서 진행합니다.\n"
        "```"
        "\n\n"
        "Create a new run:\n\n"
        ' `/tutti start "작은 게임 아이디어"`\n\n'
        "Home channel commands:\n"
        "- `/tutti help`\n"
        "- `/tutti start \"3분 리듬 퍼즐\"`\n"
        "- `/tutti status`\n"
        "- `/tutti revise \"속도를 낮추고 튜토리얼을 추가해\"`\n"
        "- `/tutti settings`\n\n"
        "Advanced:\n"
        "- `!orchestra` prefix commands remain available for compatibility\n\n"
        "Runtime:\n"
        f"- Mode: `{mode}`\n"
        f"- Primary model: `{model}`\n"
        f"- Advanced overlays active: `{advanced_count}`"
    )


def build_status_message(state: DiscordBotState, source: dict[str, str]) -> str:
    if not state.last_run:
        return (
            "# Orchestra Status\n\n"
            "No run has finished in this bot session yet.\n\n"
            'Start with: `/tutti start "작은 게임 아이디어"`'
        )
    intervention_line = ""
    if state.last_run.get("intervention"):
        intervention_line = f"\n- Last intervention: {state.last_run['intervention']}"
    return (
        "# Orchestra Status\n\n"
        "Last run:\n"
        f"- Run: `{state.last_run['run_thread']}`\n"
        f"- Idea: {state.last_run['idea']}\n"
        f"- Mode: `{state.last_run['mode']}`\n"
        f"- Model: `{state.last_run['provider']}/{state.last_run['model']}`\n"
        f"- Final spec: `{format_display_path(state.last_run['final_spec_path'])}`\n"
        f"- Schema: `{format_display_path(state.last_run['schema_path'])}`\n"
        f"- Playable: `{format_display_path(state.last_run.get('playable_dir', 'not generated'))}`"
        f"{intervention_line}\n\n"
        f"{build_agent_settings_message(state, source)}"
    )


def build_agent_settings_message(state: DiscordBotState, source: dict[str, str]) -> str:
    configs = load_agent_configs(_env_with_agent_overrides(source, state))
    lines = ["# Agent Settings", ""]
    for agent in configs.agents:
        lines.append(f"- `{agent.id}` -> `{agent.provider}/{agent.model}`")
    if state.skill_overrides:
        lines.append("")
        lines.append("Instruction overrides:")
        for role, instruction in state.skill_overrides.items():
            lines.append(f"- `{role}`: {instruction}")
    return "\n".join(lines)


def _build_run_env(
    command: DiscordCommand,
    state: DiscordBotState,
    source: dict[str, str],
) -> dict[str, str]:
    env = dict(source)
    env["DISCORD_PROJECT"] = command.arguments.get("project", source.get("DISCORD_PROJECT", "orchestra-demo"))
    env["DISCORD_FEATURE"] = command.arguments.get("feature", source.get("DISCORD_FEATURE", "design-handoff"))
    env["DISCORD_SPRINT"] = command.arguments.get("sprint", source.get("DISCORD_SPRINT", "sprint-01"))
    env["DISCORD_TASK"] = command.arguments.get("task", source.get("DISCORD_TASK", "agent-run"))
    env["DISCORD_RUN"] = command.arguments.get("run", source.get("DISCORD_RUN", "latest"))
    env["AGENT_PRESET"] = command.arguments.get("preset", source.get("AGENT_PRESET", "balanced"))
    env["DISCORD_SYNC_MODE"] = source.get("DISCORD_SYNC_MODE", "mock")
    env["PROJECT_INSTRUCTIONS"] = _compose_project_instructions(
        source.get("PROJECT_INSTRUCTIONS", ""),
        state,
    )
    return _env_with_agent_overrides(env, state)


def _build_start_env(
    command: DiscordCommand,
    state: DiscordBotState,
    source: dict[str, str],
) -> dict[str, str]:
    idea = command.arguments.get("idea", "orchestra-game")
    run_name = command.arguments.get("run", _slugify(idea) or "latest")
    env = dict(source)
    env["DISCORD_PROJECT"] = command.arguments.get("project", source.get("DISCORD_PROJECT", "first-game"))
    env["DISCORD_FEATURE"] = command.arguments.get("feature", source.get("DISCORD_FEATURE", "playable-prototype"))
    env["DISCORD_SPRINT"] = command.arguments.get("sprint", source.get("DISCORD_SPRINT", "sprint-1"))
    env["DISCORD_TASK"] = command.arguments.get("task", source.get("DISCORD_TASK", "make-game"))
    env["DISCORD_RUN"] = run_name
    env["AGENT_PRESET"] = command.arguments.get("preset", source.get("AGENT_PRESET", "balanced"))
    env["DISCORD_SYNC_MODE"] = source.get("DISCORD_SYNC_MODE", "mock")
    env["PROJECT_INSTRUCTIONS"] = _compose_project_instructions(
        source.get("PROJECT_INSTRUCTIONS", "Generate a small playable HTML/JS prototype after the design run."),
        state,
    )
    return _env_with_agent_overrides(env, state)


def _build_revise_env(state: DiscordBotState, source: dict[str, str]) -> dict[str, str]:
    env = dict(source)
    env["DISCORD_PROJECT"] = state.last_run.get("project", source.get("DISCORD_PROJECT", "first-game")) if state.last_run else source.get("DISCORD_PROJECT", "first-game")
    env["DISCORD_FEATURE"] = state.last_run.get("feature", source.get("DISCORD_FEATURE", "playable-prototype")) if state.last_run else source.get("DISCORD_FEATURE", "playable-prototype")
    env["DISCORD_SPRINT"] = state.last_run.get("sprint", source.get("DISCORD_SPRINT", "sprint-1")) if state.last_run else source.get("DISCORD_SPRINT", "sprint-1")
    env["DISCORD_TASK"] = state.last_run.get("task", source.get("DISCORD_TASK", "make-game")) if state.last_run else source.get("DISCORD_TASK", "make-game")
    env["DISCORD_RUN"] = state.last_run.get("run_name", source.get("DISCORD_RUN", "latest")) if state.last_run else source.get("DISCORD_RUN", "latest")
    env["AGENT_PRESET"] = source.get("AGENT_PRESET", "balanced")
    env["DISCORD_SYNC_MODE"] = source.get("DISCORD_SYNC_MODE", "mock")
    env["PROJECT_INSTRUCTIONS"] = _compose_project_instructions(
        source.get("PROJECT_INSTRUCTIONS", "Revise the existing game and preserve the strongest core loop."),
        state,
    )
    return _env_with_agent_overrides(env, state)


def _compose_project_instructions(base: str, state: DiscordBotState) -> str:
    sections: list[str] = []
    if base.strip():
        sections.append(base.strip())
    if state.extra_agents:
        sections.append(
            "추가 등록 에이전트:\n"
            + "\n".join(
                f"- {agent['role']}: {agent['provider']}/{agent['model']}"
                for agent in state.extra_agents
            )
        )
    if state.skill_overrides:
        label_map = {
            "technical_reviewer": "기술 리드 역할 오버라이드",
            "game_designer": "디자이너 역할 오버라이드",
            "product_ceo": "CEO 역할 오버라이드",
            "spec_writer": "스펙 라이터 역할 오버라이드",
        }
        sections.append(
            "역할별 오버라이드:\n"
            + "\n".join(
                f"- {label_map.get(role, role)}: {instruction}"
                for role, instruction in state.skill_overrides.items()
            )
        )
    return "\n\n".join(section for section in sections if section).strip()


def _env_with_agent_overrides(env: dict[str, str], state: DiscordBotState) -> dict[str, str]:
    enriched = dict(env)
    prefix_map = {
        "creative_designer": "DESIGNER",
        "technical_reviewer": "REVIEWER",
        "product_ceo": "CEO",
        "spec_writer": "SPEC_WRITER",
    }
    for role, config in state.agent_overrides.items():
        prefix = prefix_map.get(role)
        if not prefix:
            continue
        if config.get("provider"):
            enriched[f"{prefix}_PROVIDER"] = config["provider"]
        if config.get("model"):
            enriched[f"{prefix}_MODEL"] = config["model"]
    return enriched


def _send_workspace_overview(
    transport: DiscordTransport,
    workspace: ProjectWorkspace,
    preset: str,
    result: Any,
) -> None:
    transport.send_message(
        channel_name=workspace.runs_channel_name,
        thread_name=workspace.run_thread_name,
        content=format_run_opened_message(workspace, preset, result),
    )


def _send_sprint_summary(
    transport: DiscordTransport,
    workspace: ProjectWorkspace,
    result: Any,
) -> None:
    transport.send_message(
        channel_name=workspace.runs_channel_name,
        thread_name=workspace.run_thread_name,
        content=_build_final_progress_board(result),
    )


def _send_task_handoff(
    transport: DiscordTransport,
    workspace: ProjectWorkspace,
    result: Any,
) -> None:
    transport.send_message(
        channel_name=workspace.handoff_channel_name,
        thread_name=workspace.run_thread_name,
        content=format_handoff_message(result),
    )


def _send_run_thread_messages(
    transport: DiscordTransport,
    workspace: ProjectWorkspace,
    result: Any,
) -> None:
    for message in result.messages:
        transport.send_message(
            channel_name=workspace.runs_channel_name,
            thread_name=workspace.run_thread_name,
            content=format_agent_timeline_message(message),
        )


def _build_final_progress_board(result: Any) -> str:
    if getattr(result, "progress_path", None):
        try:
            progress_data = json.loads(Path(result.progress_path).read_text(encoding="utf-8"))
            env = {
                "AGENT_MODE": "mock",
                "AGENT_PRESET": str(progress_data.get("preset", "balanced")),
            }
            configs = load_agent_configs(env)
            completed_steps = {
                step["task"]
                for step in progress_data.get("steps", [])
                if step.get("status") == "completed"
            }
            skipped_steps = {
                step["task"]
                for step in progress_data.get("steps", [])
                if step.get("status") == "skipped"
            }
            plan = build_execution_plan(
                configs,
                str(progress_data.get("preset", "balanced")),
                completed_steps=completed_steps,
                skipped_steps=skipped_steps,
            )
            return format_progress_board(plan, "Run board: complete")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return "Run board: complete\n\nProgress artifact unavailable."


async def publish_collaboration_live(
    result: Any,
    workspace: ProjectWorkspace,
    publisher: Any,
    preset: str = "balanced",
) -> None:
    await publisher.send_message(
        channel_name=workspace.runs_channel_name,
        thread_name=workspace.run_thread_name,
        content=format_run_opened_message(workspace, preset, result),
    )
    await publisher.send_message(
        channel_name=workspace.runs_channel_name,
        thread_name=workspace.run_thread_name,
        content=_build_final_progress_board(result),
    )
    await publisher.send_message(
        channel_name=workspace.handoff_channel_name,
        thread_name=workspace.run_thread_name,
        content=format_handoff_message(result),
    )
    for message in result.messages:
        await publisher.send_message(
            channel_name=workspace.runs_channel_name,
            thread_name=workspace.run_thread_name,
            content=format_agent_timeline_message(message),
        )


def _slugify(value: str) -> str:
    characters: list[str] = []
    previous_dash = False
    for char in value.strip().lower():
        if char.isalnum():
            characters.append(char)
            previous_dash = False
            continue
        if not previous_dash:
            characters.append("-")
            previous_dash = True
    normalized = "".join(characters).strip("-")
    # 디스코드 쓰레드명은 최대 100자 제한이 있으므로 안전하게 50자로 자름
    if len(normalized) > 50:
        normalized = normalized[:50].strip("-")
    return normalized or "untitled"


def format_display_path(path_like: Any) -> str:
    if not path_like:
        return "not generated"
    path = Path(path_like)
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def format_run_opened_message(
    workspace: ProjectWorkspace,
    preset: str,
    result: Any,
) -> str:
    playable_path = getattr(result, "playable_dir", None)
    return (
        "# Tutti Run Started\n\n"
        "Summary:\n"
        f"- Project: `{workspace.project_name}`\n"
        f"- Run: `{workspace.run_thread_name}`\n"
        f"- Preset: `{preset}`\n"
        "- Stage: `Design Review`\n\n"
        "What to do here:\n"
        "- Read the agent discussion below\n"
        "- Approve to generate final spec + prototype\n"
        "- Revise to inject human feedback\n\n"
        "Artifacts so far:\n"
        f"- Current spec: `{format_display_path(result.final_spec_path)}`\n"
        f"- Prototype: `{format_display_path(playable_path / 'index.html') if playable_path else 'pending'}`"
    )


def format_agent_timeline_message(message: Any) -> str:
    sender = getattr(message, "sender", "agent")
    receiver = getattr(message, "receiver", "thread")
    message_type = getattr(message, "type", "note")
    provider = getattr(message, "provider", "unknown")
    model = getattr(message, "model", "unknown")
    content = getattr(message, "content", "")
    sender_label = ROLE_DISPLAY_LABELS.get(sender, sender)
    receiver_label = ROLE_DISPLAY_LABELS.get(receiver, receiver)
    emoji = ROLE_EMOJIS.get(sender, "🤖")
    stage_label = MESSAGE_TYPE_LABELS.get(message_type, str(message_type).replace("_", " ").title())
    # 에이전트 내용을 코드블록으로 감싸서 디스코드에서 시각적으로 분리
    content_block = f"```md\n{content.strip()}\n```" if content.strip() else ""
    return (
        f"## {emoji} {sender_label}\n"
        f"Stage: `{stage_label}` · Route: `{sender_label} → {receiver_label}` · Model: `{provider}/{model}`\n\n"
        f"{content_block}"
    )


def format_approval_needed_message(stage: Any | None = None) -> str:
    summary_lines = _extract_summary_lines(stage) if stage is not None else []
    summary_block = ""
    if summary_lines:
        summary_block = (
            "Current direction:\n"
            + "\n".join(f"- {line}" for line in summary_lines)
            + "\n\n"
        )
    return (
        "## Approval Needed\n\n"
        "Checkpoint:\n"
        "- Status: `1차 기획 및 리뷰 완료`\n"
        "- Reviewed by: `Designer`, `Reviewer`, `CEO`\n\n"
        f"{summary_block}"
        "Choose next step:\n"
        "- Approve: final spec + prototype 생성\n"
        "- Revise: 피드백 반영 후 다시 진행"
    )


def format_run_complete_message(final_spec_path: Path | str, playable_index_path: Path | str) -> str:
    return (
        "# 🎉 기획 완료 (Run Complete)\n\n"
        "상태:\n"
        "- 최종 명세서 및 프로토타입 생성 완료\n\n"
        "산출물:\n"
        f"- 📄 기획서: `{format_display_path(final_spec_path)}`\n"
        f"- 🎮 플레이: `{format_display_path(playable_index_path)}`\n\n"
        "다음 권장 단계:\n"
        "- 프로토타입을 열어서 직접 플레이 감각을 테스트해보세요.\n"
        "- 수정이 필요하다면 `/tutti revise` 명령어를 사용하세요."
    )


def format_handoff_message(result: Any) -> str:
    prototype_path = getattr(result, "playable_dir", None)
    return (
        "# 📤 개발팀 전달 준비 (Handoff to Task Planning)\n\n"
        "준비 완료:\n"
        "- 최종 기획 명세서\n"
        "- 플레이 가능한 프로토타입\n\n"
        "산출물:\n"
        f"- 📄 명세서: `{format_display_path(result.final_spec_path)}`\n"
        f"- 💾 데이터 스키마: `{format_display_path(result.schema_path)}`\n"
        f"- 🎮 프로토타입: `{format_display_path(prototype_path / 'index.html') if prototype_path else '생성 대기중'}`\n\n"
        "다음 할 일:\n"
        "- 스프린트 태스크(Task) 단위로 쪼개기\n"
        "- 프로토타입 품질 검토"
    )


def _extract_summary_lines(stage: Any | None, limit: int = 3) -> list[str]:
    if stage is None:
        return []
    candidates: list[str] = []
    for attr in ("draft", "review", "ceo_review"):
        text = getattr(stage, attr, "") or ""
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped.startswith("- "):
                continue
            cleaned = stripped[2:].strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
            if len(candidates) >= limit:
                return candidates
    return candidates
