import json
import os
import shutil
import unittest
import uuid
from io import StringIO
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from orchestra.adapters import _build_prompt
from orchestra import cli as orchestra_cli
from orchestra.cli import _print_agent, _print_header
from orchestra.cli import _safe_run_name
from orchestra.config import load_agent_configs
from orchestra.discord import (
    BotDiscordTransport,
    DiscordBotState,
    MockDiscordTransport,
    build_agent_settings_message,
    build_status_message,
    build_workspace_from_env,
    build_onboarding_message,
    execute_discord_command,
    format_display_path,
    export_collaboration_to_discord,
    parse_discord_command,
)
from orchestra.discord_bot import LiveDiscordPublisher, OrchestraDiscordBot
from orchestra.input_parser import parse_run_message, parse_user_message
from orchestra.pipeline import build_execution_plan, format_pipeline_preview
from orchestra.run_view import format_progress_board, format_run_composer
from orchestra.workflow import finalize_collaboration, resolve_artifact_dir, run_collaboration, run_design_review


class OrchestraCoreTests(unittest.TestCase):
    @contextmanager
    def temporary_directory(self):
        temp_root = Path.cwd() / ".test-artifacts"
        temp_root.mkdir(parents=True, exist_ok=True)
        path = temp_root / uuid.uuid4().hex
        path.mkdir()
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def discord_run_dir(self, temp_dir: Path, run_name: str = "latest") -> Path:
        return Path(temp_dir) / "playable" / run_name

    def test_default_agent_mode_is_mock_with_traceable_models(self):
        configs = load_agent_configs({})

        self.assertEqual(configs.mode, "mock")
        self.assertEqual(configs.by_id["creative_designer"].provider, "mock")
        self.assertEqual(configs.by_id["creative_designer"].model, "designer")
        self.assertEqual(configs.by_id["technical_reviewer"].provider, "mock")
        self.assertEqual(configs.by_id["spec_writer"].provider, "mock")
        self.assertEqual(configs.by_id["product_ceo"].provider, "mock")

    def test_ollama_mode_uses_role_specific_models_from_environment(self):
        configs = load_agent_configs(
            {
                "AGENT_MODE": "ollama",
                "DESIGNER_MODEL": "llama3.1:8b",
                "REVIEWER_MODEL": "qwen2.5-coder:7b",
                "SPEC_WRITER_MODEL": "mistral:7b",
                "CEO_MODEL": "qwen3:8b",
            }
        )

        self.assertEqual(configs.mode, "ollama")
        self.assertEqual(configs.by_id["creative_designer"].provider, "ollama")
        self.assertEqual(configs.by_id["creative_designer"].model, "llama3.1:8b")
        self.assertEqual(configs.by_id["technical_reviewer"].model, "qwen2.5-coder:7b")
        self.assertEqual(configs.by_id["spec_writer"].model, "mistral:7b")
        self.assertEqual(configs.by_id["product_ceo"].model, "qwen3:8b")

    def test_agent_config_supports_per_role_provider_and_model_overrides(self):
        configs = load_agent_configs(
            {
                "AGENT_MODE": "mock",
                "DESIGNER_PROVIDER": "ollama",
                "DESIGNER_MODEL": "qwen2.5-coder:7b-instruct",
                "REVIEWER_PROVIDER": "openai",
                "REVIEWER_MODEL": "gpt-4o-mini",
                "CEO_PROVIDER": "google",
                "CEO_MODEL": "gemini-1.5-pro",
            }
        )

        self.assertEqual(configs.by_id["creative_designer"].provider, "ollama")
        self.assertEqual(configs.by_id["creative_designer"].model, "qwen2.5-coder:7b-instruct")
        self.assertEqual(configs.by_id["technical_reviewer"].provider, "openai")
        self.assertEqual(configs.by_id["technical_reviewer"].model, "gpt-4o-mini")
        self.assertEqual(configs.by_id["product_ceo"].provider, "google")
        self.assertEqual(configs.by_id["product_ceo"].model, "gemini-1.5-pro")

    def test_agent_config_supports_anthropic_provider_overrides(self):
        configs = load_agent_configs(
            {
                "AGENT_MODE": "api",
                "DESIGNER_PROVIDER": "anthropic",
                "DESIGNER_MODEL": "claude-3-5-sonnet-latest",
            }
        )

        self.assertEqual(configs.by_id["creative_designer"].provider, "anthropic")
        self.assertEqual(configs.by_id["creative_designer"].model, "claude-3-5-sonnet-latest")

    def test_mock_collaboration_creates_traceable_messages_and_artifacts(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            result = run_collaboration(
                "3분 안에 끝나는 병합 퍼즐 게임",
                intervention="라이브옵스 요소는 제외하고 세션을 더 짧게",
                env={"AGENT_MODE": "mock", "DISCORD_PROJECT": "orchestra-demo", "DISCORD_RUN": "latest"},
                artifact_dir=Path(temp_dir),
            )

            self.assertGreaterEqual(len(result.messages), 5)
            for message in result.messages:
                self.assertTrue(message.agent_config_id)
                self.assertTrue(message.provider)
                self.assertTrue(message.model)

            final_spec = run_dir / "final_game_spec.md"
            schema = run_dir / "game_schema.json"
            message_log = run_dir / "message_log.json"
            round_1 = run_dir / "round_1_design.md"
            round_2 = run_dir / "round_2_revision.md"
            self.assertTrue(final_spec.exists())
            self.assertTrue(schema.exists())
            self.assertTrue(message_log.exists())
            self.assertTrue(round_1.exists())
            self.assertTrue(round_2.exists())
            self.assertIn("라이브옵스 요소는 제외", final_spec.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(schema.read_text(encoding="utf-8"))["session_target"], "short")
            serialized = json.loads(message_log.read_text(encoding="utf-8"))
            self.assertEqual(
                [message["type"] for message in serialized],
                ["user_request", "draft", "review", "ceo_review", "intervention", "revision", "final_spec"],
            )
            self.assertIn("provider", serialized[1])
            self.assertIn("model", serialized[1])
            self.assertIn("agent_config_id", serialized[1])

    def test_mock_collaboration_without_intervention_skips_intervention_message(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            result = run_collaboration(
                "짧은 퍼즐 게임",
                env={"AGENT_MODE": "mock", "DISCORD_PROJECT": "orchestra-demo", "DISCORD_RUN": "latest"},
                artifact_dir=Path(temp_dir),
            )

            self.assertEqual(
                [message.type for message in result.messages],
                ["user_request", "draft", "review", "ceo_review", "revision", "final_spec"],
            )
            schema = json.loads((run_dir / "game_schema.json").read_text(encoding="utf-8"))
            self.assertEqual(schema["human_intervention"], "")

    def test_staged_workflow_allows_review_before_human_intervention(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            stage = run_design_review(
                "관찰 후 개입 가능한 퍼즐",
                env={"AGENT_MODE": "mock", "DISCORD_PROJECT": "orchestra-demo", "DISCORD_RUN": "latest"},
                artifact_dir=Path(temp_dir),
            )

            self.assertEqual([message.type for message in stage.messages], ["user_request", "draft", "review", "ceo_review"])
            self.assertIn("기술 검토", stage.review)
            self.assertIn("CEO", stage.ceo_review)

            result = finalize_collaboration(
                stage,
                intervention="리뷰를 보고 난 뒤 세션을 더 짧게 조정",
            )

            self.assertEqual(
                [message.type for message in result.messages],
                ["user_request", "draft", "review", "ceo_review", "intervention", "revision", "final_spec"],
            )
            self.assertEqual(result.final_spec_path.parent, run_dir)

    def test_chat_message_parser_splits_idea_and_korean_intervention(self):
        idea, intervention = parse_user_message(
            "3분 안에 끝나는 병합 퍼즐\n개입: 라이브옵스 요소는 제외"
        )

        self.assertEqual(idea, "3분 안에 끝나는 병합 퍼즐")
        self.assertEqual(intervention, "라이브옵스 요소는 제외")

    def test_run_message_parser_extracts_preset_and_project_instructions(self):
        run_input = parse_run_message(
            "3분 안에 끝나는 병합 퍼즐\n"
            "preset: deep_review\n"
            "instructions: 모바일 퍼블리셔 피치처럼 날카롭게 검토\n"
            "개입: 라이브옵스 요소는 제외"
        )

        self.assertEqual(run_input.idea, "3분 안에 끝나는 병합 퍼즐")
        self.assertEqual(run_input.preset, "deep_review")
        self.assertEqual(run_input.project_instructions, "모바일 퍼블리셔 피치처럼 날카롭게 검토")
        self.assertEqual(run_input.intervention, "라이브옵스 요소는 제외")

    def test_prompt_includes_shared_and_role_rules(self):
        prompt = _build_prompt(
            "game_designer",
            "draft",
            "짧은 병합 퍼즐",
            context="이전 초안",
            intervention="없음",
        )

        self.assertIn("Shared Workflow Rules", prompt)
        self.assertIn("Designer Role Rules", prompt)
        self.assertIn("player experience first", prompt)

    def test_prompt_includes_preset_and_project_instructions(self):
        prompt = _build_prompt(
            "technical_reviewer",
            "review",
            "짧은 병합 퍼즐",
            preset="deep_review",
            project_instructions="퍼블리셔 관점에서 범위를 강하게 줄여라",
        )

        self.assertIn("Preset: deep_review", prompt)
        self.assertIn("Stress-test feasibility", prompt)
        self.assertIn("퍼블리셔 관점에서 범위를 강하게 줄여라", prompt)

    def test_collaboration_schema_records_preset_and_project_instructions(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            run_collaboration(
                "짧은 퍼즐 게임",
                env={
                    "AGENT_MODE": "mock",
                    "AGENT_PRESET": "fast_draft",
                    "PROJECT_INSTRUCTIONS": "게임잼 제출용으로 단순하게",
                    "DISCORD_PROJECT": "orchestra-demo",
                    "DISCORD_RUN": "latest",
                },
                artifact_dir=Path(temp_dir),
            )

            schema = json.loads((run_dir / "game_schema.json").read_text(encoding="utf-8"))
            self.assertEqual(schema["agent_preset"], "fast_draft")
            self.assertEqual(schema["project_instructions"], "게임잼 제출용으로 단순하게")

    def test_mock_mode_reflects_preset_and_project_instructions_in_artifacts(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            run_collaboration(
                "짧은 퍼즐 게임",
                env={
                    "AGENT_MODE": "mock",
                    "AGENT_PRESET": "deep_review",
                    "PROJECT_INSTRUCTIONS": "퍼블리셔 피치처럼 범위를 날카롭게 줄여라",
                    "DISCORD_PROJECT": "orchestra-demo",
                    "DISCORD_RUN": "latest",
                },
                artifact_dir=Path(temp_dir),
            )

            draft = (run_dir / "round_1_design.md").read_text(encoding="utf-8")
            final_spec = (run_dir / "final_game_spec.md").read_text(encoding="utf-8")
            self.assertIn("실행 프리셋 반영: deep_review", draft)
            self.assertIn("프로젝트 지시문", final_spec)
            self.assertIn("퍼블리셔 피치처럼 범위를 날카롭게 줄여라", final_spec)

    def test_execution_plan_preview_lists_pipeline_steps_and_progress(self):
        configs = load_agent_configs({"AGENT_MODE": "mock"})
        plan = build_execution_plan(configs, "deep_review")

        self.assertEqual(plan.preset, "deep_review")
        self.assertEqual(
            [step.task for step in plan.steps],
            ["draft", "review", "ceo_review", "intervention", "revision", "final_spec"],
        )
        self.assertEqual(plan.steps[0].progress_percent, 17)
        self.assertIn("Designer drafts concept", format_pipeline_preview(plan))
        self.assertIn("CEO challenges market clarity", format_pipeline_preview(plan))
        self.assertIn("Spec Writer produces final spec", format_pipeline_preview(plan))

    def test_collaboration_writes_progress_board_artifact(self):
        with self.temporary_directory() as temp_dir:
            run_dir = self.discord_run_dir(temp_dir)
            result = run_collaboration(
                "짧은 퍼즐 게임",
                env={"AGENT_MODE": "mock", "AGENT_PRESET": "balanced", "DISCORD_PROJECT": "orchestra-demo", "DISCORD_RUN": "latest"},
                artifact_dir=Path(temp_dir),
            )

            progress_path = run_dir / "run_progress.json"
            self.assertEqual(result.progress_path, progress_path)
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            self.assertEqual(progress["preset"], "balanced")
            self.assertEqual(progress["overall_percent"], 100)
            self.assertEqual(progress["steps"][3]["status"], "skipped")

            schema = json.loads((run_dir / "game_schema.json").read_text(encoding="utf-8"))
            self.assertEqual(schema["pipeline_progress"]["overall_percent"], 100)
            self.assertEqual(schema["pipeline_progress"]["steps"][-1]["status"], "completed")

    def test_run_view_formats_composer_and_monday_style_board(self):
        configs = load_agent_configs({"AGENT_MODE": "mock"})
        plan = build_execution_plan(
            configs,
            "balanced",
            completed_steps={"draft", "review"},
        )

        composer = format_run_composer("mock", "balanced")
        board = format_progress_board(plan, "Run board")

        self.assertIn("Start a design run", composer)
        self.assertIn("fast_draft", composer)
        self.assertIn("| Step | Owner | Status | Schedule | Progress |", board)
        self.assertIn("Reviewer pressure-tests scope", board)
        self.assertIn("Completed", board)
        self.assertIn("Pending", board)

    def test_cli_renderers_use_ascii_safe_characters(self):
        header_buffer = StringIO()
        with mock.patch("sys.stdout", header_buffer):
            _print_header("Round 1 - Design Review")
        self.assertNotIn("—", header_buffer.getvalue())

        agent_buffer = StringIO()
        with mock.patch("sys.stdout", agent_buffer):
            _print_agent("Designer", "mock", "writer", "line one\nline two")
        rendered = agent_buffer.getvalue()
        self.assertIn("+--", rendered)
        self.assertNotIn("┌", rendered)
        self.assertNotIn("│", rendered)

    def test_cli_main_skips_intervention_when_stdin_hits_eof(self):
        output_root = Path.cwd() / ".test-artifacts" / "cli"
        argv = [
            "orchestra.cli",
            "--idea",
            "3분 안에 끝나는 병합 퍼즐 게임",
            "--output",
            str(output_root),
            "--run-name",
            "cli-eof",
        ]
        with mock.patch.object(orchestra_cli.sys, "argv", argv):
            with mock.patch.object(orchestra_cli.sys.stdin, "isatty", return_value=True):
                with mock.patch("builtins.input", side_effect=EOFError):
                    orchestra_cli.main()
        run_dir = output_root / "playable" / "cli-eof"
        self.assertTrue((run_dir / "final_game_spec.md").exists())
        self.assertTrue((run_dir / "game" / "index.html").exists())

    def test_cli_run_outputs_are_nested_like_discord_run_bundle(self):
        with self.temporary_directory() as temp_dir:
            argv = [
                "orchestra.cli",
                "--idea",
                "한 손 리듬 게임!",
                "--intervention",
                "범위는 작게",
                "--output",
                str(Path(temp_dir)),
            ]
            with mock.patch.object(orchestra_cli.sys, "argv", argv):
                orchestra_cli.main()

            run_dir = Path(temp_dir) / "playable" / "한-손-리듬-게임"
            self.assertTrue((run_dir / "final_game_spec.md").exists())
            self.assertTrue((run_dir / "game_schema.json").exists())
            self.assertTrue((run_dir / "message_log.json").exists())
            self.assertTrue((run_dir / "run_progress.json").exists())
            self.assertTrue((run_dir / "game" / "index.html").exists())

    def test_cli_run_name_can_be_overridden(self):
        self.assertEqual(_safe_run_name("Pitch Demo!!"), "pitch-demo")

    def test_parse_discord_command_supports_run_and_agent_management(self):
        run_command = parse_discord_command(
            "/orchestra run create project=orbital feature=core-loop sprint=sprint-1 task=merge-balance "
            "idea=\"3분 퍼즐\" preset=deep_review"
        )
        agent_command = parse_discord_command(
            "/orchestra agent add role=qa_reviewer provider=mock model=critic"
        )
        skill_command = parse_discord_command(
            "/orchestra skill override role=technical_reviewer instruction=\"모바일 라이브 밸런스 리스크를 우선 검토\""
        )
        revise_command = parse_discord_command('/orchestra revise "조작을 더 단순하게"')

        self.assertEqual(run_command.group, "run")
        self.assertEqual(run_command.action, "create")
        self.assertEqual(run_command.arguments["project"], "orbital")
        self.assertEqual(run_command.arguments["preset"], "deep_review")

        self.assertEqual(agent_command.group, "agent")
        self.assertEqual(agent_command.action, "add")
        self.assertEqual(agent_command.arguments["role"], "qa_reviewer")

        self.assertEqual(skill_command.group, "skill")
        self.assertEqual(skill_command.action, "override")
        self.assertIn("모바일 라이브 밸런스", skill_command.arguments["instruction"])
        self.assertEqual(revise_command.group, "revise")
        self.assertEqual(revise_command.arguments["instruction"], "조작을 더 단순하게")

    def test_parse_discord_command_supports_help_start_and_status(self):
        help_command = parse_discord_command("/orchestra help")
        status_command = parse_discord_command("/orchestra status")
        start_command = parse_discord_command('/orchestra start "3분 안에 끝나는 리듬 퍼즐"')

        self.assertEqual(help_command.group, "help")
        self.assertEqual(help_command.action, "default")
        self.assertEqual(status_command.group, "status")
        self.assertEqual(status_command.action, "default")
        self.assertEqual(start_command.group, "start")
        self.assertEqual(start_command.action, "default")
        self.assertEqual(start_command.arguments["idea"], "3분 안에 끝나는 리듬 퍼즐")

    def test_help_and_onboarding_messages_prioritize_start_command(self):
        help_result = execute_discord_command(
            parse_discord_command("/orchestra help"),
            DiscordBotState(),
            base_env={"AGENT_MODE": "ollama", "DESIGNER_MODEL": "qwen2.5-coder:7b-instruct"},
            artifact_dir=Path.cwd() / ".test-artifacts",
        )
        onboarding = build_onboarding_message(
            mode="ollama",
            model="qwen2.5-coder:7b-instruct",
        )

        self.assertIn('/tutti start "작은 게임 아이디어"', help_result.message)
        self.assertIn("Advanced", help_result.message)
        self.assertIn("run thread", help_result.message)
        self.assertIn("/tutti help", onboarding)
        self.assertIn("qwen2.5-coder:7b-instruct", onboarding)
        self.assertIn("실제 진행은 생성된 run thread 안에서 이어집니다.", onboarding)

    def test_agent_settings_message_reflects_overrides(self):
        state = DiscordBotState(
            agent_overrides={
                "creative_designer": {"provider": "ollama", "model": "qwen2.5-coder:7b-instruct"},
                "product_ceo": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        )
        message = build_agent_settings_message(state, {"AGENT_MODE": "mock"})

        self.assertIn("creative_designer", message)
        self.assertIn("product_ceo", message)
        self.assertIn("qwen2.5-coder:7b-instruct", message)

    def test_build_workspace_from_env_uses_channel_and_thread_structure(self):
        workspace = build_workspace_from_env(
            {
                "DISCORD_PROJECT": "Orbital Forge",
                "DISCORD_RUN": "Pitch Demo",
            }
        )

        self.assertEqual(workspace.category_name, "project-orbital-forge")
        self.assertEqual(workspace.brief_channel_name, "proj-brief")
        self.assertEqual(workspace.runs_channel_name, "proj-runs")
        self.assertEqual(workspace.handoff_channel_name, "proj-handoffs")
        self.assertEqual(workspace.team_channel_name, "proj-team")
        self.assertEqual(workspace.run_thread_name, "run-pitch-demo")

    def test_export_collaboration_to_mock_discord_writes_payload_artifact(self):
        with self.temporary_directory() as temp_dir:
            env = {
                "AGENT_MODE": "mock",
                "AGENT_PRESET": "deep_review",
                "DISCORD_PROJECT": "Orbital Forge",
                "DISCORD_FEATURE": "Core Loop",
                "DISCORD_SPRINT": "Sprint 07",
                "DISCORD_TASK": "Merge Balance",
                "DISCORD_RUN": "Pitch Demo",
            }
            stage = run_design_review(
                "3분 안에 끝나는 병합 퍼즐 게임",
                env=env,
                artifact_dir=Path(temp_dir),
            )
            result = finalize_collaboration(stage, intervention="라이브옵스 제외")

            transport = MockDiscordTransport()
            artifact_path = export_collaboration_to_discord(
                result,
                workspace=build_workspace_from_env(env),
                transport=transport,
                artifact_dir=Path(temp_dir),
                preset=env["AGENT_PRESET"],
            )

            self.assertTrue(artifact_path.exists())
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["workspace"]["runs_channel"], "proj-runs")
            self.assertEqual(payload["transport"], "mock")
            self.assertGreaterEqual(len(payload["deliveries"]), 4)
            self.assertTrue(any("Run board: complete" in item["content"] for item in payload["deliveries"]))
            self.assertTrue(any(item["thread"] == "run-pitch-demo" for item in payload["deliveries"]))

    def test_bot_transport_is_present_but_not_wired_without_token(self):
        transport = BotDiscordTransport()

        self.assertEqual(transport.name, "bot")
        with self.assertRaises(RuntimeError):
            transport.send_message(
                channel_name="feature-core-loop",
                thread_name="run-pitch-demo",
                content="hello",
            )

    def test_execute_discord_command_tracks_agents_and_skill_overrides(self):
        state = DiscordBotState()

        add_result = execute_discord_command(
            parse_discord_command("/orchestra agent add role=qa_reviewer provider=mock model=critic"),
            state,
            base_env={"AGENT_MODE": "mock"},
            artifact_dir=Path.cwd() / ".test-artifacts",
        )
        override_result = execute_discord_command(
            parse_discord_command(
                "/orchestra skill override role=technical_reviewer instruction=\"모바일 수익화 리스크를 우선 검토\""
            ),
            state,
            base_env={"AGENT_MODE": "mock"},
            artifact_dir=Path.cwd() / ".test-artifacts",
        )

        self.assertIn("qa_reviewer", add_result.message)
        self.assertIn("technical_reviewer", override_result.message)
        self.assertEqual(state.extra_agents[0]["role"], "qa_reviewer")
        self.assertEqual(
            state.skill_overrides["technical_reviewer"],
            "모바일 수익화 리스크를 우선 검토",
        )

    def test_execute_discord_command_updates_agent_provider_and_model(self):
        state = DiscordBotState()

        config_result = execute_discord_command(
            parse_discord_command(
                "/orchestra agent config role=product_ceo provider=ollama model=qwen3:8b"
            ),
            state,
            base_env={"AGENT_MODE": "mock"},
            artifact_dir=Path.cwd() / ".test-artifacts",
        )
        show_result = execute_discord_command(
            parse_discord_command("/orchestra agent show"),
            state,
            base_env={"AGENT_MODE": "mock"},
            artifact_dir=Path.cwd() / ".test-artifacts",
        )

        self.assertIn("product_ceo", config_result.message)
        self.assertEqual(state.agent_overrides["product_ceo"]["provider"], "ollama")
        self.assertEqual(state.agent_overrides["product_ceo"]["model"], "qwen3:8b")
        self.assertIn("qwen3:8b", show_result.message)

    def test_execute_discord_command_run_create_uses_overrides_in_artifacts(self):
        with self.temporary_directory() as temp_dir:
            state = DiscordBotState(
                skill_overrides={"technical_reviewer": "모바일 수익화 리스크를 우선 검토"}
            )
            result = execute_discord_command(
                parse_discord_command(
                    "/orchestra run create project=orbital feature=core-loop sprint=sprint-1 "
                    "task=merge-balance run=pitch-demo idea=\"3분 병합 퍼즐\" preset=deep_review"
                ),
                state,
                base_env={"AGENT_MODE": "mock", "DISCORD_SYNC_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )

            self.assertIn("run-pitch-demo", result.message)
            self.assertIsNotNone(result.collaboration_result)
            run_dir = self.discord_run_dir(temp_dir, "pitch-demo")
            self.assertTrue((run_dir / "discord_sync.json").exists())
            final_spec = (run_dir / "final_game_spec.md").read_text(encoding="utf-8")
            self.assertIn("기술 리드 역할 오버라이드", final_spec)
            self.assertIn("모바일 수익화 리스크를 우선 검토", final_spec)

    def test_execute_discord_start_runs_with_short_command_and_status(self):
        with self.temporary_directory() as temp_dir:
            state = DiscordBotState()
            start_result = execute_discord_command(
                parse_discord_command('/orchestra start "3분 리듬 퍼즐"'),
                state,
                base_env={"AGENT_MODE": "mock", "DISCORD_SYNC_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )
            status_result = execute_discord_command(
                parse_discord_command("/orchestra status"),
                state,
                base_env={"AGENT_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )

            self.assertIn("Playable prototype request accepted", start_result.message)
            self.assertIn("run-", start_result.message)
            self.assertIsNotNone(start_result.collaboration_result)
            run_dir = self.discord_run_dir(temp_dir, state.last_run["run_name"])
            self.assertTrue((run_dir / "final_game_spec.md").exists())
            self.assertIn("Last run", status_result.message)
            self.assertIn("final_game_spec.md", status_result.message)
            self.assertIn("playable", status_result.message)
            playable_dir = run_dir / "game"
            self.assertTrue((playable_dir / "index.html").exists())
            self.assertTrue((playable_dir / "style.css").exists())
            self.assertTrue((playable_dir / "game.js").exists())

    def test_execute_discord_revise_reuses_last_run_idea(self):
        with self.temporary_directory() as temp_dir:
            state = DiscordBotState()
            execute_discord_command(
                parse_discord_command('/orchestra start "1분 리듬 탭 게임"'),
                state,
                base_env={"AGENT_MODE": "mock", "DISCORD_SYNC_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )
            revise_result = execute_discord_command(
                parse_discord_command('/orchestra revise "속도를 조금 낮추고 튜토리얼을 추가해"'),
                state,
                base_env={"AGENT_MODE": "mock", "DISCORD_SYNC_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )

            self.assertIn("Revision completed", revise_result.message)
            run_dir = self.discord_run_dir(temp_dir, state.last_run["run_name"])
            final_spec = (run_dir / "final_game_spec.md").read_text(encoding="utf-8")
            self.assertIn("튜토리얼", final_spec)
            playable_dir = run_dir / "game"
            self.assertTrue((playable_dir / "index.html").exists())
            html = (playable_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn(state.last_run["idea"], html)

    def test_thread_default_agent_uses_last_agent_message(self):
        bot = OrchestraDiscordBot()
        thread = SimpleNamespace(id=123, name="run-demo")
        context = "[User]: 더 어렵게 가자\n[Agent: Reviewer]: 범위를 줄이는 게 먼저입니다."
        bot.thread_context_cache[bot._thread_cache_key(thread)] = context

        self.assertEqual(bot._fallback_agent_for_thread_context(context), "technical_reviewer")
        self.assertEqual(bot._detect_agent("멘션 없이 이어서 논의해줘", thread), "technical_reviewer")
        self.assertEqual(bot._detect_agent("ceo 관점으로 봐줘", thread), "product_ceo")

    def test_thread_default_agent_falls_back_to_designer_without_agent_history(self):
        bot = OrchestraDiscordBot()
        self.assertEqual(bot._detect_agent("그럼 다음은?", None), "creative_designer")

    def test_build_thread_context_does_not_set_attributes_on_discord_thread(self):
        bot = OrchestraDiscordBot()
        bot._connection.user = SimpleNamespace(id=2)

        class SlottedThread:
            __slots__ = ("id", "name", "_messages")

            def __init__(self) -> None:
                self.id = 456
                self.name = "run-demo"
                self._messages = [
                    SimpleNamespace(author=SimpleNamespace(id=1), content="어떤 노트들은 어떻게 생각해?"),
                    SimpleNamespace(author=bot._connection.user, content="**Writer** `mock/writer`\n\n좋습니다."),
                ]

            def history(self, limit: int, oldest_first: bool):
                async def iterator():
                    for message in self._messages[:limit]:
                        yield message

                return iterator()

        thread = SlottedThread()

        import asyncio
        context = asyncio.run(bot._build_thread_context(thread))

        self.assertIn("[User]: 어떤 노트들은 어떻게 생각해?", context)
        self.assertIn("[Agent: Writer]:", context)
        self.assertEqual(bot.thread_context_cache["456"], context)

    def test_display_path_prefers_relative_when_inside_workspace(self):
        target = Path.cwd() / "artifacts" / "discord" / "final_game_spec.md"
        self.assertEqual(format_display_path(target), r"artifacts\discord\final_game_spec.md")

    def test_resolve_artifact_dir_nests_discord_outputs_under_run_bundle(self):
        base = Path("artifacts") / "discord"
        resolved = resolve_artifact_dir(
            base,
            {"DISCORD_PROJECT": "orchestra-demo", "DISCORD_RUN": "latest"},
        )

        self.assertEqual(resolved, base / "playable" / "latest")

    def test_resolve_artifact_dir_nests_cli_outputs_under_run_bundle(self):
        base = Path("artifacts") / "cli"
        resolved = resolve_artifact_dir(
            base,
            {"CLI_RUN": "pitch-demo"},
        )

        self.assertEqual(resolved, base / "playable" / "pitch-demo")

    def test_status_message_uses_relative_artifact_paths(self):
        state = DiscordBotState(
            last_run={
                "run_thread": "run-demo",
                "idea": "demo",
                "mode": "mock",
                "provider": "mock",
                "model": "designer",
                "final_spec_path": str(Path.cwd() / "artifacts" / "discord" / "final_game_spec.md"),
                "schema_path": str(Path.cwd() / "artifacts" / "discord" / "game_schema.json"),
                "playable_dir": str(Path.cwd() / "artifacts" / "discord" / "playable" / "run-demo" / "game"),
            }
        )
        message = build_status_message(state, {"AGENT_MODE": "mock"})

        self.assertIn(r"artifacts\discord\final_game_spec.md", message)
        self.assertNotIn(str(Path.cwd()), message)

    def test_run_finalize_reports_original_failure_without_unbound_publisher(self):
        bot = OrchestraDiscordBot()
        sent_messages = []

        class DummyPublisher:
            async def send_message(self, channel_name: str, thread_name: str, content: str, view=None) -> None:
                sent_messages.append((channel_name, thread_name, content, view))

        interaction = SimpleNamespace(guild=SimpleNamespace())
        workspace = SimpleNamespace(category_name="project-test", runs_channel_name="proj-runs", handoff_channel_name="proj-handoffs", run_thread_name="run-demo")
        env = {"AGENT_MODE": "mock"}
        stage = SimpleNamespace(idea="idea", messages=[])
        bot.pending_stages["run-demo"] = (stage, workspace, env)

        with mock.patch("orchestra.discord_bot.LiveDiscordPublisher", return_value=DummyPublisher()):
            with mock.patch("orchestra.discord_bot.finalize_collaboration", side_effect=RuntimeError("prototype exploded")):
                import asyncio
                asyncio.run(bot._run_finalize(interaction, "run-demo", ""))

        self.assertEqual(len(sent_messages), 1)
        self.assertIn("prototype exploded", sent_messages[0][2])

    def test_live_discord_publisher_exposes_channel_and_thread_helpers(self):
        publisher = LiveDiscordPublisher(SimpleNamespace(), "project-test")

        self.assertTrue(hasattr(publisher, "_get_or_create_text_channel"))
        self.assertTrue(hasattr(publisher, "_get_or_create_category"))
        self.assertTrue(hasattr(publisher, "_get_or_create_thread"))

    def test_run_start_stores_pending_stage_and_uses_human_labels_in_thread(self):
        bot = OrchestraDiscordBot()
        sent_messages = []

        class DummyPublisher:
            async def send_message(self, channel_name: str, thread_name: str, content: str, view=None) -> None:
                sent_messages.append((channel_name, thread_name, content, view))

        async def defer(*, thinking: bool) -> None:
            self.assertTrue(thinking)

        followup_calls = []

        async def followup_send(content: str, view=None, ephemeral: bool = False) -> None:
            followup_calls.append((content, view, ephemeral))

        interaction = SimpleNamespace(
            guild=SimpleNamespace(id=7),
            response=SimpleNamespace(defer=defer),
            followup=SimpleNamespace(send=followup_send),
        )
        stage = SimpleNamespace(
            draft="- 핵심 아이디어: 3분 퍼즐\n- 장르: 캐주얼 퍼즐",
            review="- 데이터 모델 분리 필요",
            ceo_review="- 첫 10초 훅 강화",
            risk_level="HIGH",
            messages=[
                SimpleNamespace(sender="human_operator", provider="human", model="operator", content="idea"),
                SimpleNamespace(sender="creative_designer", provider="mock", model="designer", content="draft"),
                SimpleNamespace(sender="technical_reviewer", provider="mock", model="reviewer", content="review"),
                SimpleNamespace(sender="product_ceo", provider="mock", model="ceo", content="ceo"),
            ]
        )

        with mock.patch("orchestra.discord_bot.LiveDiscordPublisher", return_value=DummyPublisher()):
            with mock.patch("orchestra.discord_bot.run_design_review", return_value=stage) as run_design:
                import asyncio
                asyncio.run(bot._run_start(interaction, "3분 퍼즐"))

        self.assertIn("run-3분-퍼즐", bot.pending_stages)
        design_env = run_design.call_args.kwargs["env"]
        self.assertEqual(design_env["DISCORD_PROJECT"], "orchestra-demo")
        self.assertEqual(design_env["DISCORD_RUN"], "3분-퍼즐")
        self.assertGreaterEqual(len(sent_messages), 4)
        self.assertIn("Designer", sent_messages[1][2])
        self.assertIn("Stage: `Note`", sent_messages[1][2])
        self.assertIn("Reviewer", sent_messages[2][2])
        self.assertIn("CEO", sent_messages[3][2])
        self.assertIn("Approval Needed", sent_messages[4][2])
        self.assertIn("Current direction", sent_messages[4][2])
        self.assertIsNotNone(sent_messages[4][3])
        self.assertEqual(len(followup_calls), 1)
        self.assertIn("Run created", followup_calls[0][0])
        self.assertTrue(followup_calls[0][2])

    def test_plain_thread_messages_do_not_trigger_agent_chat(self):
        bot = OrchestraDiscordBot()
        message = SimpleNamespace(
            content="/tutti revise 지금 노트들이 제대로 나오고있지않아",
            mentions=[],
        )
        bot._connection.user = SimpleNamespace(id=2)

        self.assertFalse(bot._should_respond_to_thread_message(message))

    def test_explicit_agent_thread_message_triggers_agent_chat(self):
        bot = OrchestraDiscordBot()
        message = SimpleNamespace(
            content="designer: 이 노트들 어떻게 생각해?",
            mentions=[],
        )
        bot._connection.user = SimpleNamespace(id=2)

        self.assertTrue(bot._should_respond_to_thread_message(message))

    def test_bot_mention_in_thread_triggers_agent_chat(self):
        bot = OrchestraDiscordBot()
        user = SimpleNamespace(id=2)
        message = SimpleNamespace(
            content="<@2> 이 노트들 어떻게 생각해?",
            mentions=[user],
        )
        bot._connection.user = user

        self.assertTrue(bot._should_respond_to_thread_message(message))


if __name__ == "__main__":
    unittest.main()
