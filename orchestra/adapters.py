from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from .models import AgentConfig
from .presets import normalize_preset, preset_instructions


class AgentAdapter:
    def __init__(self, config: AgentConfig, env: Mapping[str, str] | None = None) -> None:
        self.config = config
        self.env = os.environ if env is None else env

    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        raise NotImplementedError

    def build_prompt(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        return _build_prompt(
            self.config.role,
            task,
            idea,
            context,
            intervention,
            preset=self.env.get("AGENT_PRESET"),
            project_instructions=self.env.get("PROJECT_INSTRUCTIONS", ""),
            learned_rules=self.env.get("LEARNED_RULES", ""),
        )


class MockAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        preset = normalize_preset(self.env.get("AGENT_PRESET"))
        project_instructions = self.env.get("PROJECT_INSTRUCTIONS", "").strip()
        steering_notes = _mock_steering_notes(preset, project_instructions)

        if task == "draft":
            return (
                f"# 1차 게임 기획안\n\n"
                f"- 핵심 아이디어: {idea}\n"
                f"{steering_notes}"
                "- 장르: 3분 내 종료되는 캐주얼 병합 퍼즐\n"
                "- 메인 루프: 아이템 병합 -> 목표 달성 -> 보상 획득 -> 다음 스테이지 진입\n"
                "- 보상 구조: 짧은 세션 보상, 연속 성공 보너스, 일일 목표 보상\n"
                "- 초기 콘텐츠: 20개 스테이지, 5개 아이템 계열, 3개 장애물 패턴\n"
            )

        if task == "review":
            return (
                "# 기술 검토\n\n"
                f"{steering_notes}"
                "- 데이터 모델은 stage, item, mission, reward로 분리하는 편이 안전합니다.\n"
                "- 3분 세션 목표를 지키려면 스테이지 목표 수와 병합 깊이를 제한해야 합니다.\n"
                "- 라이브옵스 요소는 MVP 범위 밖으로 두고, 기본 스테이지 반복 검증부터 진행하는 편이 좋습니다.\n"
                "- 엣지 케이스: 더 이상 병합할 수 없는 상태, 보상 중복 지급, 목표 달성 직후 앱 종료.\n"
            )

        if task == "ceo_review":
            return (
                "# CEO 리뷰\n\n"
                f"{steering_notes}"
                "- 첫 10초 안에 이해되는 훅이 필요합니다.\n"
                "- 한 손 조작과 1분 세션 약속을 더 전면에 드러내야 합니다.\n"
                "- 지금 아이디어가 너무 넓어지면 데모 가치가 떨어지니 한 개의 주력 재미에 집중하세요.\n"
                "- 결과물은 팀이 바로 플레이해볼 수 있는 작은 프로토타입으로 이어져야 합니다.\n\n"
                "RISK: MEDIUM"
            )

        if task == "revision":
            direction = intervention or "Reviewer의 범위 축소 제안을 반영"
            return (
                "# 수정 기획안\n\n"
                f"- 반영된 사용자 개입: {direction}\n"
                f"{steering_notes}"
                "- 세션 목표: 90~150초 안에 한 판이 끝나는 짧은 구조\n"
                "- MVP 범위: 기본 병합 퍼즐, 스테이지 목표, 단순 보상만 포함\n"
                "- 제외 범위: 라이브옵스 요소는 제외, 복잡한 경제 시스템은 후순위\n"
                "- 구현 우선순위: 보드 상태 검증 -> 병합 규칙 -> 목표 판정 -> 보상 지급\n"
            )

        if task == "final_spec":
            return (
                "# 최종 게임 명세\n\n"
                f"## 입력 아이디어\n{idea}\n\n"
                f"## 사용자 개입\n{intervention or '없음'}\n\n"
                f"## 실행 프리셋\n{preset}\n\n"
                f"{_mock_project_section(project_instructions)}"
                "## 핵심 플레이\n"
                "플레이어는 제한된 보드에서 동일 아이템을 병합해 스테이지 목표를 달성합니다.\n\n"
                "## MVP 범위\n"
                "- 90~150초 세션\n"
                "- 병합 규칙과 목표 판정\n"
                "- 스테이지 완료 보상\n"
                "- Markdown/JSON 명세 저장\n\n"
                "## 제외 범위\n"
                "- 라이브옵스 요소는 제외\n"
                "- 복잡한 재화 경제와 소셜 기능은 제외\n"
            )

        if task == "chat":
            role_label = {
                "game_designer": "게임 디자이너",
                "technical_reviewer": "기술 리뷰어",
                "product_ceo": "프로덕트 CEO",
                "spec_writer": "스펙 라이터",
            }.get(self.config.role, self.config.role)
            return (
                f"[{role_label} 응답]\n\n"
                f"질문을 확인했습니다: {idea[:100]}\n\n"
                f"{steering_notes}"
                "현재 기획 맥락을 기반으로 답변드리겠습니다.\n"
                "더 구체적인 질문이 있으시면 말씀해주세요."
            )

        return context


class OllamaAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        base_url = self.env.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        prompt = self.build_prompt(task, idea, context, intervention)
        payload = json.dumps(
            {"model": self.config.model, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("response", "").strip()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                "Ollama request failed. Check that Ollama is running and the model is pulled."
            ) from exc


class OpenAIAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        api_key = self.env.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI agents.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai to use API mode.") from exc

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "user",
                    "content": self.build_prompt(task, idea, context, intervention),
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()


class AnthropicAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        api_key = self.env.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Anthropic agents.")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install anthropic to use Anthropic agents.") from exc

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.config.model,
            max_tokens=1200,
            messages=[
                {
                    "role": "user",
                    "content": self.build_prompt(task, idea, context, intervention),
                }
            ],
        )
        parts = []
        for block in response.content:
            text = getattr(block, "text", "")
            if text:
                parts.append(text)
        return "\n".join(parts).strip()


class GoogleAgentAdapter(AgentAdapter):
    def generate(self, task: str, idea: str, context: str = "", intervention: str = "") -> str:
        api_key = self.env.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Google agents.")
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError("Install google-generativeai to use API mode.") from exc

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.config.model)
        response = model.generate_content(self.build_prompt(task, idea, context, intervention))
        return (response.text or "").strip()


def create_adapter(config: AgentConfig, env: Mapping[str, str] | None = None) -> AgentAdapter:
    if config.provider == "mock":
        return MockAgentAdapter(config, env)
    if config.provider == "ollama":
        return OllamaAgentAdapter(config, env)
    if config.provider == "openai":
        return OpenAIAgentAdapter(config, env)
    if config.provider == "anthropic":
        return AnthropicAgentAdapter(config, env)
    if config.provider == "google":
        return GoogleAgentAdapter(config, env)
    raise ValueError(f"Unsupported provider: {config.provider}")


def _build_prompt(
    role: str,
    task: str,
    idea: str,
    context: str = "",
    intervention: str = "",
    preset: str = "",
    project_instructions: str = "",
    learned_rules: str = "",
) -> str:
    rules = _load_prompt_rules(role)
    normalized_preset = normalize_preset(preset)
    project_section = (
        f"Project instructions:\n{project_instructions.strip()}\n\n"
        if project_instructions.strip()
        else ""
    )
    learned_section = (
        f"{learned_rules.strip()}\n\n"
        if learned_rules.strip()
        else ""
    )
    return (
        "You are participating in a multi-agent game design workflow.\n"
        f"{rules}\n\n"
        f"{preset_instructions(normalized_preset)}\n\n"
        f"{project_section}"
        f"{learned_section}"
        f"Role: {role}\n"
        f"Task: {task}\n"
        f"User game idea: {idea}\n"
        f"Prior context:\n{context}\n"
        f"Human intervention:\n{intervention or 'None'}\n\n"
        "Write concise Korean output suitable for a casual mobile game production team."
    )


def _load_prompt_rules(role: str) -> str:
    rules_dir = Path(__file__).resolve().parent / "rules"
    shared_rules = (rules_dir / "shared.md").read_text(encoding="utf-8").strip()
    role_file = _role_rules_path(role, rules_dir)
    role_rules = role_file.read_text(encoding="utf-8").strip()
    return "\n\n".join([shared_rules, role_rules]).strip()


def _role_rules_path(role: str, rules_dir: Path) -> Path:
    role_to_file = {
        "game_designer": "designer.md",
        "technical_reviewer": "reviewer.md",
        "product_ceo": "ceo.md",
        "spec_writer": "spec_writer.md",
    }
    filename = role_to_file.get(role)
    if not filename:
        raise ValueError(f"Unsupported role rules file for role: {role}")
    return rules_dir / filename


def _mock_steering_notes(preset: str, project_instructions: str) -> str:
    lines: list[str] = []
    if preset != "balanced":
        lines.append(f"- 실행 프리셋 반영: {preset}")
    if project_instructions:
        lines.append(f"- 프로젝트 지시문 반영: {project_instructions}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _mock_project_section(project_instructions: str) -> str:
    if not project_instructions:
        return "## 프로젝트 지시문\n없음\n\n"
    return f"## 프로젝트 지시문\n{project_instructions}\n\n"
