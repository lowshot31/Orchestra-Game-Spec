# 기술 제안서: Orchestra - Multi-Agent Game Design Studio

## 1. 프로젝트 개요

**Orchestra**는 여러 AI 코딩 에이전트가 하나의 게임 기획 과제를 두고 서로 메시지를 주고받으며, 사용자가 그 협업 과정을 관찰하고 개입할 수 있는 멀티 에이전트 협업 도구입니다.

베이글코드 모바일 캐주얼팀은 AI 에이전트를 제품 제작의 핵심 도구로 사용합니다. 이 프로젝트는 그 환경을 전제로, 기획자가 게임 아이디어를 입력하면 여러 에이전트가 역할을 나누어 기획안 작성, 기술 검토, 보완, 최종 명세 생성을 수행하는 워크플로우를 구현합니다.

이 도구의 핵심은 단순히 여러 LLM을 호출하는 것이 아니라, **에이전트 간 협업 프로토콜**, **역할과 모델의 분리**, **Human-in-the-loop 개입 흐름**을 제품 제작 과정에 맞게 설계하는 것입니다.

## 2. 과제 요구사항 대응

| 과제 조건 | Orchestra의 대응 방식 |
| :--- | :--- |
| 두 개 이상의 AI 에이전트가 메시지를 주고받아야 함 | Designer, Reviewer, Spec Writer 에이전트가 공통 메시지 프로토콜을 통해 결과물과 피드백을 교환 |
| 사용자가 협업 과정에 개입하거나 관찰 가능해야 함 | Discord UI에서 쓰레드 대화를 관찰하고, [✅ 승인]/[✏️ 수정] 버튼으로 개입. CLI에서도 동일한 파이프라인 실행 가능 |
| 통신 방식, 프로토콜, UI, 언어/프레임워크 자유 | Python 모듈과 Discord 봇(Tutti) + CLI 기반으로 단계형 워크플로우 구현 |
| AI 코딩 에이전트를 사용하여 개발해야 함 | Codex를 중심으로 설계, 구현, 검토, 문서 정리를 진행하고, 필요한 구간에서 다른 AI coding CLI를 보조적으로 활용 |
| README대로 실행했을 때 동작해야 함 | 기본 `mock` 모드로 API 키 없이 실행 가능하며, 선택적으로 `ollama` 또는 `api` 모드 사용 |

## 3. 시스템 설계

### 3.1 에이전트 구성

| 에이전트 | 역할 | 기본 provider/model 예시 | 주요 책임 |
| :--- | :--- | :--- | :--- |
| **Creative Designer** | 게임 기획자 | `mock/designer`, `ollama/llama3.1:8b`, `openai/gpt-4o` | 핵심 재미, 메타 루프, 보상 구조, 레벨/미션 아이디어 생성 |
| **Technical Reviewer** | 기술 검토자 | `mock/reviewer`, `ollama/qwen2.5-coder:7b`, `google/gemini-1.5-pro` | 구현 난이도, 데이터 구조, 밸런싱 리스크, 엣지 케이스 검토 |
| **Spec Writer** | 명세 정리자 | `mock/writer`, `ollama/mistral:7b`, `openai/gpt-4o-mini` | 합의된 내용을 개발 가능한 Markdown/JSON 명세로 정리 |
| **Human Operator** | 사용자 | CLI / Discord | 아이디어 입력, 중간 피드백 삽입, 최종안 승인 |

MVP에서는 최소 조건 충족을 위해 Designer와 Reviewer만으로도 동작하며, Spec Writer는 최종 산출물 품질을 높이기 위한 확장 에이전트로 둡니다. 각 에이전트의 **역할은 고정**되지만, 실행 시점의 **provider/model은 설정으로 교체**할 수 있습니다.

### 3.2 메시지 프로토콜

모든 에이전트 간 통신은 동일한 메시지 스키마를 사용합니다. 메시지는 누가 무엇을 보냈는지뿐 아니라, 어떤 provider/model 설정에서 생성되었는지도 함께 기록합니다.

```json
{
  "id": "msg_0001",
  "round": 1,
  "sender": "creative_designer",
  "receiver": "technical_reviewer",
  "type": "draft",
  "agent_config_id": "designer_ollama_llama31",
  "provider": "ollama",
  "model": "llama3.1:8b",
  "content": "게임 기획안 또는 리뷰 내용",
  "artifact": {
    "format": "markdown",
    "path": "artifacts/round_1_design.md"
  },
  "status": "created",
  "created_at": "2026-05-01T12:00:00+09:00"
}
```

주요 메시지 타입은 다음과 같습니다.

- `user_request`: 사용자의 최초 게임 아이디어 또는 중간 지시
- `draft`: Designer가 작성한 기획 초안
- `review`: Reviewer가 작성한 검토 의견
- `revision`: Designer가 반영한 수정안
- `intervention`: 사용자가 중간에 삽입한 방향 수정
- `final_spec`: 최종 개발 명세

### 3.3 Agent Runtime Configuration

에이전트의 역할과 모델 실행 환경은 별도 설정으로 분리합니다. 이를 통해 OpenClaw의 모델 선택처럼 역할별 모델을 유동적으로 지정할 수 있습니다.

```json
{
  "agent_mode": "ollama",
  "agents": [
    {
      "id": "creative_designer",
      "role": "game_designer",
      "provider": "ollama",
      "model": "llama3.1:8b"
    },
    {
      "id": "technical_reviewer",
      "role": "technical_reviewer",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b"
    },
    {
      "id": "spec_writer",
      "role": "spec_writer",
      "provider": "ollama",
      "model": "mistral:7b"
    }
  ]
}
```

`AGENT_MODE`는 `mock`, `ollama`, `api` 중 하나를 사용합니다. `mock`은 기본 실행 보장을 담당하고, `ollama`는 API 키 없이 로컬 실제 모델 기반 협업을 제공하며, `api`는 OpenAI/Gemini 같은 외부 모델을 사용합니다.

## 4. 협업 워크플로우

1. **Initiate**
   - 사용자가 CLI 또는 Discord `/tutti start` 명령으로 게임 아이디어를 입력합니다.
   - 예: "3분 안에 끝나는 캐주얼 병합 퍼즐 게임을 만들고 싶다."

2. **Drafting**
   - Creative Designer가 1차 게임 기획안을 생성합니다.
   - 산출물: 핵심 플레이, 목표 유저, 메인 루프, 보상 루프, 초기 콘텐츠 구조

3. **Cross Review**
   - Technical Reviewer가 기획안을 검토합니다.
   - 산출물: 구현 리스크, 데이터 모델, 밸런싱 이슈, 범위 축소 제안

4. **Human Intervention**
   - 사용자는 Designer 초안과 Reviewer 검토 메시지를 관찰합니다.
   - 필요하면 "BM은 낮추고 세션 길이를 더 짧게", "라이브옵스 요소는 제외" 같은 지시를 삽입합니다.

5. **Revision**
   - Designer가 Reviewer와 사용자 피드백을 반영해 수정안을 작성합니다.
   - 반복 횟수는 기본 2라운드로 제한해 무한 루프를 방지합니다.

6. **Spec Generation**
   - Spec Writer가 최종 합의안을 개발 명세로 정리합니다.
   - 산출물: `artifacts/final_game_spec.md`, `artifacts/game_schema.json`

## 5. 관찰성과 개입 UI

CLI와 Discord 봇은 에이전트의 내부 사고 과정을 노출하지 않습니다. 대신 제품 제작에 필요한 **관찰 가능한 협업 기록**을 제공합니다.

- 에이전트별 송수신 메시지 로그
- 메시지별 provider/model 정보
- 리뷰 단계 이후 사용자 개입 입력
- 최종 Markdown/JSON 명세 로컬 저장

이 방식은 평가자가 "에이전트들이 실제로 협업하고 있는가"를 확인하기 쉽고, 불필요하게 Chain of Thought를 노출하지 않아 안전합니다.

## 6. 기술 스택

| 영역 | 선택 기술 | 이유 |
| :--- | :--- | :--- |
| Language | Python 3.11+ | AI API, Discord bot, CLI 실행 환경과 호환성 우수 |
| Orchestration | Python workflow modules | 에이전트 상태, 라운드 제어, 리뷰 후 개입 흐름을 단순하게 구현 |
| CLI | `python -m orchestra.cli` | API 키 없이도 README 기준으로 즉시 실행 가능한 기본 데모 제공 |
| Team Surface | Discord bot (`/tutti`) | 팀원이 Discord 채널과 쓰레드에서 기획 run을 시작, 관찰, 개입 가능 |
| Model Provider | Ollama, OpenAI API, Google AI Studio | 로컬 모델과 외부 모델을 모두 지원 |
| Model Adapter Layer | `mock`, `ollama`, `openai`, `google` | 동일한 에이전트 인터페이스로 provider/model을 교체 가능 |
| Demo Mode | Local mock agents | API 키 없이 README 실행만으로 동작 확인 가능 |
| Artifacts | Markdown, JSON | 기획자와 엔지니어가 모두 읽고 재사용하기 쉬움 |

FastAPI나 별도 웹 콘솔은 외부 서비스 연동이 필요할 때의 확장 옵션으로 둔다. 현재 제출 MVP는 CLI와 Discord bot을 중심으로 실행 흐름을 단순화한다.

## 7. 실행 전략

README 기준 기본 실행 흐름은 다음을 목표로 합니다.

**가상환경 생성 및 활성화:**

```bash
# Windows (PowerShell)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

**의존성 설치 및 실행:**

```bash
pip install -r requirements.txt
AGENT_MODE=mock python -m orchestra.cli
```

환경 변수 `AGENT_MODE`에 따라 세 가지 모드로 동작합니다.

```bash
# API 키와 Ollama 없이 실행 가능한 기본 데모 모드
AGENT_MODE=mock python -m orchestra.cli

# API 키 없이 로컬 Ollama 모델로 실행
AGENT_MODE=ollama DESIGNER_MODEL=llama3.1:8b REVIEWER_MODEL=qwen2.5-coder:7b python -m orchestra.cli

# 외부 API 모델 사용
AGENT_MODE=api OPENAI_API_KEY=... GOOGLE_API_KEY=... python -m orchestra.cli

# 팀 협업용 Discord bot 실행
python -m orchestra.discord_bot
```

주요 환경 변수:

- `DISCORD_BOT_TOKEN`: Discord 봇 실행 시 필수
- `AGENT_MODE`: `mock`, `ollama`, `api` 중 하나. 기본값은 `mock`
- `OLLAMA_BASE_URL`: Ollama 서버 주소. 기본값은 `http://localhost:11434`
- `DESIGNER_MODEL` / `REVIEWER_MODEL` / `SPEC_WRITER_MODEL`: 역할별 사용할 모델명
- `OPENAI_API_KEY` / `GOOGLE_API_KEY`: 외부 API 모델 사용 시 필요
- `GITHUB_GAME_REPO` / `GITHUB_TOKEN`: GitHub PR 자동 생성 시 필요

`mock` 모드에서는 정해진 규칙 기반 응답 템플릿을 사용하여 Designer와 Reviewer가 메시지를 교환합니다. 이를 통해 평가자는 별도 API 키나 Ollama 설치 없이도 협업 흐름, 사용자 개입, 최종 산출물 생성을 확인할 수 있습니다.

## 8. 구현 로드맵

1. **Message Protocol**
   - 에이전트 간 공통 메시지 스키마 정의
   - `agent_config_id`, `provider`, `model`을 포함한 메시지 로그 저장 구조 구현

2. **Mock Agent MVP**
   - API 키 없이 동작하는 Designer, Reviewer, Spec Writer 구현
   - 1~2라운드 협업 루프 검증

3. **Staged Workflow**
   - Draft → Review → Intervention Check → Revision → Final Spec 흐름 구성
   - 반복 횟수와 종료 조건 정의

4. **CLI / Discord Interaction**
   - 에이전트별 메시지 표시
   - 메시지별 provider/model 표시
   - 사용자 개입 입력 처리
   - 최종 산출물 표시

5. **Model Adapter Layer**
   - `mock`, `ollama`, `openai`, `google` provider를 같은 인터페이스로 호출
   - 역할별 provider/model 선택을 환경 변수 또는 설정 파일로 주입
   - Ollama 어댑터를 먼저 추가한 뒤 OpenAI/Gemini 어댑터로 확장

6. **README & Verification**
   - macOS/Linux와 Windows PowerShell 실행 방법 작성
   - `mock`, `ollama`, `api` 모드별 샘플 명령 포함
   - 실행 후 생성되는 artifact 경로 명시

## 9. 성공 기준

- README 명령만으로 CLI 데모가 실행된다.
- Discord token을 설정하면 `/tutti` 봇이 실행된다.
- 기본 `mock` 모드는 API 키와 Ollama 없이 실행된다.
- 사용자가 게임 아이디어를 입력하면 최소 두 에이전트가 서로 메시지를 교환한다.
- 사용자가 중간에 개입 메시지를 입력하면 이후 에이전트 응답에 반영된다.
- 최종 결과물이 Markdown 명세와 JSON 스키마로 저장된다.
- 사용자가 역할별 provider/model을 설정할 수 있다.
- 각 메시지 로그에 `provider`와 `model` 정보가 남는다.
- Ollama가 설치된 환경에서는 API 키 없이 실제 로컬 모델 기반 협업을 실행할 수 있다.
- API 키가 있으면 OpenAI/Gemini 모델 기반 협업으로 전환할 수 있다.

## 10. 기대 효과

Orchestra는 AI 에이전트를 단순 코드 작성 보조 도구가 아니라, 게임 제작 과정의 협업 단위로 다룹니다. 기획자는 에이전트를 통해 아이디어를 빠르게 구체화하고, 엔지니어는 에이전트의 역할, 메시지 프로토콜, 모델 어댑터를 확장해 팀의 제작 파이프라인에 맞게 발전시킬 수 있습니다.

또한 Ollama 기반 유동 모델 선택을 지원함으로써, 평가자와 개발자는 외부 API 키 없이도 실제 로컬 LLM을 사용해 에이전트 협업을 확인할 수 있습니다. 이 프로젝트는 과제 조건을 충족하는 동시에, 실제 모바일 캐주얼 게임 팀에서 사용할 수 있는 멀티 에이전트 제작 워크플로우의 작은 원형을 제시합니다.

---

**작성일:** 2026년 5월 1일 (초안) → 5월 3일 업데이트  
**작성자:** 전정배
