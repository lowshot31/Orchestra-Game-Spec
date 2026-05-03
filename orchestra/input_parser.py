from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunInput:
    idea: str
    intervention: str = ""
    preset: str = ""
    project_instructions: str = ""


def parse_user_message(content: str) -> tuple[str, str]:
    run_input = parse_run_message(content)
    return run_input.idea, run_input.intervention


def parse_run_message(content: str) -> RunInput:
    idea_lines: list[str] = []
    intervention_lines: list[str] = []
    instruction_lines: list[str] = []
    preset = ""
    in_intervention = False
    in_instructions = False

    for line in content.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("preset:"):
            preset = stripped.split(":", 1)[1].strip()
            in_intervention = False
            in_instructions = False
            continue
        if stripped.startswith("프리셋:"):
            preset = stripped.split(":", 1)[1].strip()
            in_intervention = False
            in_instructions = False
            continue
        if lower.startswith("instructions:") or lower.startswith("instruction:"):
            in_instructions = True
            in_intervention = False
            instruction_lines.append(stripped.split(":", 1)[1].strip())
            continue
        if stripped.startswith("안내:") or stripped.startswith("지시문:"):
            in_instructions = True
            in_intervention = False
            instruction_lines.append(stripped.split(":", 1)[1].strip())
            continue
        if lower.startswith("intervention:"):
            in_intervention = True
            in_instructions = False
            intervention_lines.append(stripped.split(":", 1)[1].strip())
            continue
        if stripped.startswith("개입:"):
            in_intervention = True
            in_instructions = False
            intervention_lines.append(stripped.split(":", 1)[1].strip())
            continue
        if in_intervention:
            intervention_lines.append(stripped)
        elif in_instructions:
            instruction_lines.append(stripped)
        else:
            idea_lines.append(line)

    idea = "\n".join(idea_lines).strip()
    intervention = "\n".join(intervention_lines).strip()
    project_instructions = "\n".join(instruction_lines).strip()
    if not idea:
        idea = content.strip()
    return RunInput(
        idea=idea,
        intervention=intervention,
        preset=preset,
        project_instructions=project_instructions,
    )
