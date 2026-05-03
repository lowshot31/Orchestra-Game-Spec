"""Core workflow & pipeline tests.

Mock 모드에서 전체 파이프라인이 올바르게 동작하는지 검증합니다.
외부 API 호출 없이 실행 가능합니다.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from orchestra.config import load_agent_configs
from orchestra.adapters import create_adapter, MockAgentAdapter
from orchestra.workflow import (
    _parse_risk_level,
    resolve_artifact_dir,
    run_collaboration,
    run_design_review,
    finalize_collaboration,
)


# ---------------------------------------------------------------------------
# 1. Risk Parsing — CEO 리뷰 텍스트에서 RISK 레벨 파싱
# ---------------------------------------------------------------------------

class TestParseRiskLevel:
    """CEO 에이전트의 출력에서 RISK: HIGH/MEDIUM/LOW를 정확히 파싱하는지 검증."""

    def test_parse_low(self):
        assert _parse_risk_level("좋은 기획입니다.\nRISK: LOW") == "LOW"

    def test_parse_medium(self):
        assert _parse_risk_level("약간의 우려.\nRISK: MEDIUM") == "MEDIUM"

    def test_parse_high(self):
        assert _parse_risk_level("너무 큰 범위입니다.\nRISK: HIGH") == "HIGH"

    def test_parse_with_spaces(self):
        """RISK : HIGH 처럼 콜론 앞에 공백이 있어도 파싱되어야 한다."""
        assert _parse_risk_level("검토 결과\nRISK : HIGH") == "HIGH"

    def test_parse_missing_defaults_to_high(self):
        """RISK 라벨이 없으면 안전하게 HIGH로 폴백 (인간 개입 강제)."""
        assert _parse_risk_level("그냥 일반적인 텍스트") == "HIGH"

    def test_parse_case_insensitive(self):
        """소문자 risk: low도 파싱되어야 한다."""
        assert _parse_risk_level("risk: low") == "LOW"


# ---------------------------------------------------------------------------
# 2. Config — 모드별 에이전트 설정 로딩
# ---------------------------------------------------------------------------

class TestLoadAgentConfigs:
    """AGENT_MODE에 따라 올바른 프로바이더/모델이 로딩되는지 검증."""

    def test_mock_mode(self):
        configs = load_agent_configs({"AGENT_MODE": "mock"})
        assert configs.mode == "mock"
        for agent in configs.agents:
            assert agent.provider == "mock"

    def test_api_mode_ceo_gets_best_model(self):
        """API 모드에서 CEO 에이전트가 최고급 모델(claude-opus-4.7)을 사용하는지 검증."""
        configs = load_agent_configs({"AGENT_MODE": "api"})
        ceo = configs.by_id["product_ceo"]
        assert ceo.provider == "anthropic"
        assert ceo.model == "claude-opus-4.7"

    def test_env_override(self):
        """환경변수로 모델을 오버라이드할 수 있는지 검증."""
        configs = load_agent_configs({
            "AGENT_MODE": "mock",
            "DESIGNER_PROVIDER": "openai",
            "DESIGNER_MODEL": "gpt-5.5",
        })
        designer = configs.by_id["creative_designer"]
        assert designer.provider == "openai"
        assert designer.model == "gpt-5.5"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="AGENT_MODE"):
            load_agent_configs({"AGENT_MODE": "invalid"})


# ---------------------------------------------------------------------------
# 3. Adapter Factory — 프로바이더별 어댑터 생성
# ---------------------------------------------------------------------------

class TestAdapterFactory:
    """create_adapter가 프로바이더에 맞는 어댑터 인스턴스를 반환하는지 검증."""

    def test_mock_adapter(self):
        from orchestra.models import AgentConfig
        config = AgentConfig("test", "game_designer", "mock", "designer")
        adapter = create_adapter(config)
        assert isinstance(adapter, MockAgentAdapter)

    def test_unsupported_provider_raises(self):
        from orchestra.models import AgentConfig
        config = AgentConfig("test", "game_designer", "nonexistent", "model")
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_adapter(config)


# ---------------------------------------------------------------------------
# 4. E2E Pipeline — Mock 모드 전체 파이프라인
# ---------------------------------------------------------------------------

class TestMockPipeline:
    """Mock 모드에서 전체 파이프라인이 산출물을 올바르게 생성하는지 검증."""

    def test_full_pipeline_produces_artifacts(self, tmp_path):
        """run_collaboration이 모든 산출물 파일을 생성하는지 검증."""
        env = {"AGENT_MODE": "mock"}
        result = run_collaboration(
            idea="우주선 피하기 게임",
            env=env,
            artifact_dir=tmp_path,
        )
        assert result.final_spec_path.exists()
        assert result.schema_path.exists()
        assert result.progress_path.exists()
        assert len(result.messages) >= 5  # user, draft, review, ceo, revision, spec

    def test_pipeline_with_intervention(self, tmp_path):
        """인간 개입(intervention)이 파이프라인에 반영되는지 검증."""
        env = {"AGENT_MODE": "mock"}
        result = run_collaboration(
            idea="퍼즐 게임",
            intervention="BM을 광고 기반으로 바꿔줘",
            env=env,
            artifact_dir=tmp_path,
        )
        # intervention 메시지가 포함되어야 함
        types = [m.type for m in result.messages]
        assert "intervention" in types

        # final_spec에 intervention 내용이 반영되어야 함
        spec_text = result.final_spec_path.read_text(encoding="utf-8")
        assert "BM을 광고 기반으로 바꿔줘" in spec_text

    def test_design_review_then_finalize(self, tmp_path):
        """2단계 분리 실행: design_review → finalize가 올바르게 동작하는지 검증."""
        env = {"AGENT_MODE": "mock"}
        stage = run_design_review(idea="레이싱 게임", env=env, artifact_dir=tmp_path)
        assert stage.risk_level in {"LOW", "MEDIUM", "HIGH"}
        assert stage.draft
        assert stage.review
        assert stage.ceo_review

        result = finalize_collaboration(stage, intervention="속도를 더 빠르게")
        assert result.final_spec_path.exists()

    def test_schema_contains_idea(self, tmp_path):
        """game_schema.json에 원본 아이디어가 보존되는지 검증."""
        env = {"AGENT_MODE": "mock"}
        result = run_collaboration(
            idea="고양이 점프 게임",
            env=env,
            artifact_dir=tmp_path,
        )
        schema = json.loads(result.schema_path.read_text(encoding="utf-8"))
        assert schema["source_idea"] == "고양이 점프 게임"
        assert schema["agent_mode"] == "mock"


# ---------------------------------------------------------------------------
# 5. Artifact Directory Resolution
# ---------------------------------------------------------------------------

class TestResolveArtifactDir:
    """아티팩트 디렉토리 경로가 환경변수에 따라 올바르게 결정되는지 검증."""

    def test_default_path(self):
        result = resolve_artifact_dir("artifacts", env={})
        assert result == Path("artifacts")

    def test_cli_run_path(self):
        result = resolve_artifact_dir("artifacts", env={"CLI_RUN": "test-game"})
        assert result == Path("artifacts/playable/test-game")

    def test_discord_run_path(self):
        result = resolve_artifact_dir(
            "artifacts",
            env={"DISCORD_PROJECT": "proj", "DISCORD_RUN": "run-1"},
        )
        assert result == Path("artifacts/playable/run-1")
