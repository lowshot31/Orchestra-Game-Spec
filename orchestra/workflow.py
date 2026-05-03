from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from .adapters import create_adapter
from .config import load_agent_configs
from .discord import build_workspace_from_env, create_discord_transport, export_collaboration_to_discord
from .models import AgentConfig, AgentMessage, CollaborationResult, DesignReviewStage
from .pipeline import build_execution_plan
from .presets import normalize_preset


def resolve_artifact_dir(
    artifact_dir: Path | str,
    env: Mapping[str, str] | None = None,
) -> Path:
    base_path = Path(artifact_dir)
    source = dict(os.environ if env is None else env)
    cli_run_name = source.get("CLI_RUN", "").strip()
    if cli_run_name:
        return base_path / "playable" / cli_run_name
    run_name = source.get("DISCORD_RUN", "").strip()
    if source.get("DISCORD_PROJECT") and run_name:
        return base_path / "playable" / run_name
    return base_path


def run_collaboration(
    idea: str,
    intervention: str = "",
    env: Mapping[str, str] | None = None,
    artifact_dir: Path | str = "artifacts",
) -> CollaborationResult:
    stage = run_design_review(idea, env=env, artifact_dir=artifact_dir)
    return finalize_collaboration(stage, intervention=intervention)


def run_design_review(
    idea: str,
    env: Mapping[str, str] | None = None,
    artifact_dir: Path | str = "artifacts",
) -> DesignReviewStage:
    source = dict(os.environ if env is None else env)
    configs = load_agent_configs(source)
    agents = configs.by_id
    artifact_path = resolve_artifact_dir(artifact_dir, source)
    artifact_path.mkdir(parents=True, exist_ok=True)

    messages: list[AgentMessage] = []

    user_config = AgentConfig("human_operator", "human", "human", "operator")
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=1,
            sender="human_operator",
            receiver="creative_designer",
            message_type="user_request",
            config=user_config,
            content=idea,
        )
    )

    designer = create_adapter(agents["creative_designer"], source)
    reviewer = create_adapter(agents["technical_reviewer"], source)
    ceo = create_adapter(agents["product_ceo"], source)

    draft = designer.generate("draft", idea)
    round_1_path = artifact_path / "round_1_design.md"
    round_1_path.write_text(draft, encoding="utf-8")
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=1,
            sender="creative_designer",
            receiver="technical_reviewer",
            message_type="draft",
            config=agents["creative_designer"],
            content=draft,
            artifact=round_1_path,
        )
    )

    review = reviewer.generate("review", idea, context=draft)
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=1,
            sender="technical_reviewer",
            receiver="creative_designer",
            message_type="review",
            config=agents["technical_reviewer"],
            content=review,
        )
    )

    # --- Negotiation: Designer responds to Reviewer's critique ---
    rebuttal_context = "\n\n".join([draft, review])
    rebuttal = designer.generate("rebuttal", idea, context=rebuttal_context)
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=1,
            sender="creative_designer",
            receiver="technical_reviewer",
            message_type="rebuttal",
            config=agents["creative_designer"],
            content=rebuttal,
        )
    )

    ceo_context = "\n\n".join([draft, review, rebuttal])
    ceo_review = ceo.generate("ceo_review", idea, context=ceo_context)
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=1,
            sender="product_ceo",
            receiver="creative_designer",
            message_type="ceo_review",
            config=agents["product_ceo"],
            content=ceo_review,
        )
    )

    return DesignReviewStage(
        idea=idea,
        env=source,
        artifact_dir=artifact_path,
        messages=messages,
        draft=draft,
        review=review,
        ceo_review=ceo_review,
        risk_level=_parse_risk_level(ceo_review),
    )


def _parse_risk_level(ceo_review: str) -> str:
    """CEO 리뷰 텍스트에서 RISK: LOW/MEDIUM/HIGH를 파싱한다."""
    for line in reversed(ceo_review.splitlines()):
        upper = line.strip().upper()
        if "RISK:" in upper or "RISK :" in upper:
            if "HIGH" in upper:
                return "HIGH"
            if "MEDIUM" in upper:
                return "MEDIUM"
            if "LOW" in upper:
                return "LOW"
    # 파싱 실패 시 안전하게 HIGH
    return "HIGH"


def finalize_collaboration(
    stage: DesignReviewStage,
    intervention: str = "",
) -> CollaborationResult:
    source = stage.env
    configs = load_agent_configs(source)
    agents = configs.by_id
    artifact_path = stage.artifact_dir
    messages = list(stage.messages)
    draft = stage.draft
    review = stage.review
    ceo_review = stage.ceo_review
    idea = stage.idea

    if intervention:
        messages.append(
            _message(
                index=len(messages) + 1,
                round_number=2,
                sender="human_operator",
                receiver="creative_designer",
                message_type="intervention",
                config=AgentConfig("human_operator", "human", "human", "operator"),
                content=intervention,
            )
        )

    designer = create_adapter(agents["creative_designer"], source)
    writer = create_adapter(agents["spec_writer"], source)
    revision_context = "\n\n".join([draft, review, ceo_review])
    revision = designer.generate(
        "revision", idea, context=revision_context, intervention=intervention
    )
    round_2_path = artifact_path / "round_2_revision.md"
    round_2_path.write_text(revision, encoding="utf-8")
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=2,
            sender="creative_designer",
            receiver="spec_writer",
            message_type="revision",
            config=agents["creative_designer"],
            content=revision,
            artifact=round_2_path,
        )
    )

    final_context = "\n\n".join([draft, review, ceo_review, revision])
    final_spec = writer.generate(
        "final_spec", idea, context=final_context, intervention=intervention
    )
    final_spec_path = artifact_path / "final_game_spec.md"
    final_spec_path.write_text(final_spec, encoding="utf-8")
    messages.append(
        _message(
            index=len(messages) + 1,
            round_number=2,
            sender="spec_writer",
            receiver="human_operator",
            message_type="final_spec",
            config=agents["spec_writer"],
            content=final_spec,
            artifact=final_spec_path,
        )
    )

    completed_steps = {"draft", "review", "ceo_review", "revision", "final_spec"}
    skipped_steps: set[str] = set()
    if intervention:
        completed_steps.add("intervention")
    else:
        skipped_steps.add("intervention")

    progress = build_execution_plan(
        configs,
        source.get("AGENT_PRESET"),
        completed_steps=completed_steps,
        skipped_steps=skipped_steps,
    )
    progress_path = artifact_path / "run_progress.json"
    progress_path.write_text(
        json.dumps(progress.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    schema_path = artifact_path / "game_schema.json"
    schema_path.write_text(
        json.dumps(
            _build_schema(
                idea,
                intervention,
                configs.mode,
                source.get("AGENT_PRESET"),
                source.get("PROJECT_INSTRUCTIONS", ""),
                progress.to_dict(),
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    message_log_path = artifact_path / "message_log.json"
    message_log_path.write_text(
        json.dumps([message.to_dict() for message in messages], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    discord_sync_path = None
    if source.get("DISCORD_PROJECT"):
        transport = create_discord_transport(source.get("DISCORD_SYNC_MODE", "mock"), source)
        discord_sync_path = export_collaboration_to_discord(
            CollaborationResult(
                messages=messages,
                final_spec_path=final_spec_path,
                schema_path=schema_path,
                progress_path=progress_path,
            ),
            workspace=build_workspace_from_env(source),
            transport=transport,
            artifact_dir=artifact_path,
            preset=source.get("AGENT_PRESET", "balanced"),
        )

    return CollaborationResult(
        messages=messages,
        final_spec_path=final_spec_path,
        schema_path=schema_path,
        progress_path=progress_path,
        discord_sync_path=discord_sync_path,
    )


def _message(
    index: int,
    round_number: int,
    sender: str,
    receiver: str,
    message_type: str,
    config: AgentConfig,
    content: str,
    artifact: Path | None = None,
) -> AgentMessage:
    artifact_payload = None
    if artifact is not None:
        artifact_payload = {"format": artifact.suffix.lstrip("."), "path": str(artifact)}
    return AgentMessage(
        id=f"msg_{index:04d}",
        round=round_number,
        sender=sender,
        receiver=receiver,
        type=message_type,
        agent_config_id=config.config_id,
        provider=config.provider,
        model=config.model,
        content=content,
        artifact=artifact_payload,
    )


def _build_schema(
    idea: str,
    intervention: str,
    mode: str,
    preset: str | None = None,
    project_instructions: str = "",
    pipeline_progress: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "title": "Orchestra Generated Casual Game Spec",
        "source_idea": idea,
        "agent_mode": mode,
        "agent_preset": normalize_preset(preset),
        "project_instructions": project_instructions,
        "pipeline_progress": pipeline_progress or {},
        "session_target": "short",
        "human_intervention": intervention,
        "core_loop": ["merge_items", "complete_goal", "grant_reward", "advance_stage"],
        "excluded_scope": ["live_ops", "complex_economy", "social_features"],
        "artifacts": [
            "round_1_design.md",
            "round_2_revision.md",
            "final_game_spec.md",
            "game_schema.json",
            "message_log.json",
            "run_progress.json",
        ],
    }
