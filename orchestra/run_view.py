from __future__ import annotations

from .models import ExecutionPlan, PipelineStep


STATUS_LABELS = {
    "pending": "Pending",
    "completed": "Completed",
    "skipped": "Skipped",
    "unavailable": "Unavailable",
}


def format_run_composer(mode: str, preset: str) -> str:
    return (
        "# Start a design run\n\n"
        f"Mode: `{mode}`  \n"
        f"Default preset: `{preset}`\n\n"
        "Describe a game idea to begin. You can optionally add:\n\n"
        "```text\n"
        "preset: fast_draft | balanced | deep_review\n"
        "instructions: your project direction, constraints, or review style\n"
        "intervention: optional note for the revision step\n"
        "```\n\n"
        "Preset guide: `fast_draft` for quick shape, `balanced` for normal runs, "
        "`deep_review` for stricter pressure-testing."
    )


def format_progress_board(plan: ExecutionPlan, title: str = "Run board") -> str:
    rows = [
        f"## {title}",
        "",
        f"Preset: `{plan.preset}`  ",
        f"Overall progress: `{plan.overall_percent}%`",
        "",
        "| Step | Owner | Status | Schedule | Progress |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows.extend(_format_step_row(step) for step in plan.steps)
    return "\n".join(rows)


def _format_step_row(step: PipelineStep) -> str:
    return (
        f"| {step.title} | `{step.agent_id}` | {STATUS_LABELS.get(step.status, step.status)} "
        f"| {step.schedule_label} | {_progress_bar(step.progress_percent)} `{step.progress_percent}%` |"
    )


def _progress_bar(percent: int) -> str:
    filled = max(0, min(10, round(percent / 10)))
    return "[" + ("#" * filled) + ("-" * (10 - filled)) + "]"
