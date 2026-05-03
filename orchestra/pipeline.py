from __future__ import annotations

from .models import AgentConfigSet, ExecutionPlan, PipelineStep
from .presets import normalize_preset


STEP_DEFINITIONS = (
    {
        "id": "draft",
        "title": "Designer drafts concept",
        "agent_id": "creative_designer",
        "task": "draft",
        "schedule_label": "Start",
    },
    {
        "id": "review",
        "title": "Reviewer pressure-tests scope",
        "agent_id": "technical_reviewer",
        "task": "review",
        "schedule_label": "After draft",
    },
    {
        "id": "ceo_review",
        "title": "CEO challenges market clarity",
        "agent_id": "product_ceo",
        "task": "ceo_review",
        "schedule_label": "After review",
    },
    {
        "id": "intervention",
        "title": "Human intervention checkpoint",
        "agent_id": "human_operator",
        "task": "intervention",
        "schedule_label": "After CEO review",
    },
    {
        "id": "revision",
        "title": "Designer revises concept",
        "agent_id": "creative_designer",
        "task": "revision",
        "schedule_label": "After checkpoint",
    },
    {
        "id": "final_spec",
        "title": "Spec Writer produces final spec",
        "agent_id": "spec_writer",
        "task": "final_spec",
        "schedule_label": "Finish",
    },
)


def build_execution_plan(
    configs: AgentConfigSet,
    preset: str | None = None,
    completed_steps: set[str] | None = None,
    skipped_steps: set[str] | None = None,
) -> ExecutionPlan:
    completed = completed_steps or set()
    skipped = skipped_steps or set()
    agent_ids = set(configs.by_id) | {"human_operator"}
    total = len(STEP_DEFINITIONS)
    steps = []

    for index, definition in enumerate(STEP_DEFINITIONS, start=1):
        status = "pending"
        if definition["id"] in completed:
            status = "completed"
        if definition["id"] in skipped:
            status = "skipped"
        if definition["agent_id"] not in agent_ids:
            status = "unavailable"

        steps.append(
            PipelineStep(
                id=definition["id"],
                title=definition["title"],
                agent_id=definition["agent_id"],
                task=definition["task"],
                status=status,
                progress_percent=round(index / total * 100),
                schedule_label=definition["schedule_label"],
            )
        )

    return ExecutionPlan(preset=normalize_preset(preset), steps=tuple(steps))


def format_pipeline_preview(plan: ExecutionPlan) -> str:
    lines = []
    for step in plan.steps:
        lines.append(
            f"- [{step.progress_percent:>3}%] {step.title} "
            f"({step.agent_id}, {step.schedule_label}, {step.status})"
        )
    return "\n".join(lines)
