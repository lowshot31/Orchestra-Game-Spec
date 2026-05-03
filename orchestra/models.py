from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    id: str
    role: str
    provider: str
    model: str

    @property
    def config_id(self) -> str:
        safe_model = (
            self.model.replace(":", "_")
            .replace(".", "_")
            .replace("/", "_")
            .replace("-", "_")
        )
        return f"{self.id}_{self.provider}_{safe_model}"


@dataclass(frozen=True)
class AgentConfigSet:
    mode: str
    agents: tuple[AgentConfig, ...]

    @property
    def by_id(self) -> dict[str, AgentConfig]:
        return {agent.id: agent for agent in self.agents}


@dataclass
class AgentMessage:
    id: str
    round: int
    sender: str
    receiver: str
    type: str
    agent_config_id: str
    provider: str
    model: str
    content: str
    artifact: dict[str, str] | None = None
    status: str = "created"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "round": self.round,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.type,
            "agent_config_id": self.agent_config_id,
            "provider": self.provider,
            "model": self.model,
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at,
        }
        if self.artifact:
            data["artifact"] = self.artifact
        return data


@dataclass
class CollaborationResult:
    messages: list[AgentMessage]
    final_spec_path: Path
    schema_path: Path
    progress_path: Path | None = None
    discord_sync_path: Path | None = None
    playable_dir: Path | None = None


@dataclass
class DesignReviewStage:
    idea: str
    env: dict[str, str]
    artifact_dir: Path
    messages: list[AgentMessage]
    draft: str
    review: str
    ceo_review: str
    risk_level: str = "HIGH"  # LOW, MEDIUM, HIGH — 기본값은 안전하게 HIGH


@dataclass(frozen=True)
class PipelineStep:
    id: str
    title: str
    agent_id: str
    task: str
    status: str
    progress_percent: int
    schedule_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "agent_id": self.agent_id,
            "task": self.task,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "schedule_label": self.schedule_label,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    preset: str
    steps: tuple[PipelineStep, ...]

    @property
    def overall_percent(self) -> int:
        if not self.steps:
            return 0
        completed = [step.progress_percent for step in self.steps if step.status in {"completed", "skipped"}]
        return max(completed, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "overall_percent": self.overall_percent,
            "steps": [step.to_dict() for step in self.steps],
        }
