# Orchestra (Tutti) — Multi-Agent Game Design Toolkit

> 여러 AI 에이전트가 **메시지를 주고받으며** 게임을 기획하고, 사용자가 실시간으로 **개입(Human-in-the-loop)**하거나 **관찰**할 수 있는 멀티 에이전트 협업 도구입니다.
> 기획 완료 시 **GitHub PR로 개발팀에 자동 핸드오프**합니다.

---

## 평가자 빠른 확인

| 항목 | 위치 |
|:---|:---|
| GitHub repo | https://github.com/lowshot31/Orchestra-Game-Spec |
| 제출 안내 | [SUBMISSION.md](SUBMISSION.md) |
| 에이전트 스킬/서브에이전트 사용 내역 | [docs/design/skill-and-subagent-usage.md](docs/design/skill-and-subagent-usage.md) |
| Discord 사용 설명서 | [Tutti_Discord_Guide.md](Tutti_Discord_Guide.md) |

API 키 없이 바로 확인하려면 아래 명령을 실행하면 됩니다.

```bash
python -m orchestra.cli --idea "한 손으로 하는 30초 리듬 게임" --intervention "모바일에서 바로 이해되게 단순하게" --run-name review-demo
```

결과는 `artifacts/cli/playable/review-demo/`에 저장되며, `message_log.json`에서 에이전트 간 메시지 교환을 확인할 수 있습니다.

---

## 에이전트 파이프라인

```
[사용자] ──아이디어──▶ [Designer] ──초안──▶ [Reviewer]
                                              │
                          ◀──리뷰 피드백──────┘
                              │
                     [CEO] ──전략 리뷰 + Risk 판단
                              │
                     ┌────────┼────────┐
                   LOW     MEDIUM     HIGH
                (자동승인) (15초대기) (버튼 대기)
                     └────────┼────────┘
                              │
                  [사용자 개입] ──수정 지시──▶ [Designer]
                              │
                     [Spec Writer] ──최종 명세
                              │
                     [Prototype Generator] ──HTML/JS 게임
                              │
                     [GitHub PR] ──브랜치 + 커밋 + PR 자동 생성
```

**4명의 AI 에이전트:**
- 🎨 **Creative Designer** — 게임 컨셉 초안 작성
- 🛠️ **Technical Reviewer** — 기술 검토 및 범위 조정
- 💼 **Product CEO** — 시장 관점 리뷰, 위험도(Risk) 평가
- ✍️ **Spec Writer** — 최종 명세서 작성

---

## 빠른 시작 (Quick Start)

### 1. 설치

**Python 3.11 이상이 필요합니다.**

```bash
git clone https://github.com/lowshot31/Orchestra-Game-Spec.git
cd Orchestra-Game-Spec
```

**가상환경 생성 및 활성화:**

```bash
# Windows (PowerShell)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

**의존성 설치:**

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env   # Windows: Copy-Item .env.example .env
```

`.env` 파일을 열어 필요한 값을 입력합니다:

| 변수 | 필수 | 설명 |
|:---|:---:|:---|
| `DISCORD_BOT_TOKEN` | Discord 봇 전용 | Discord Developer Portal에서 발급 |
| `AGENT_MODE` | ✅ | `mock` / `ollama` / `api` |
| `OLLAMA_BASE_URL` | Ollama 전용 | 기본값: `http://localhost:11434` |
| `DESIGNER_MODEL` | 선택 | Ollama 모델명 (예: `qwen2.5-coder:7b-instruct`) |
| `REVIEWER_MODEL` | 선택 | Ollama 모델명 |
| `CEO_MODEL` | 선택 | Ollama 모델명 (예: `qwen3:8b`) |
| `SPEC_WRITER_MODEL` | 선택 | Ollama 모델명 |
| `OPENAI_API_KEY` | API 모드 전용 | `sk-...` |
| `GOOGLE_API_KEY` | API 모드 전용 | `AIza...` |
| `GITHUB_GAME_REPO` | GitHub PR 전용 | `owner/repo-name` |
| `GITHUB_TOKEN` | GitHub PR 전용 | `ghp_...` (repo 권한 필요) |

> CLI 데모(`AGENT_MODE=mock`)는 `DISCORD_BOT_TOKEN` 없이도 실행됩니다.

### 3. CLI 데모 (가장 빠름 — 설정 불필요)

```bash
python -m orchestra.cli
```

mock 모드로 즉시 실행됩니다. 4명의 에이전트가 메시지를 교환하는 과정을 터미널에서 확인할 수 있습니다.

**옵션:**

```bash
# 아이디어 지정
python -m orchestra.cli --idea "한 손으로 플레이하는 1분 리듬 게임"

# 사용자 개입 포함
python -m orchestra.cli --idea "병합 퍼즐 게임" --intervention "라이브옵스 요소는 제외"

# 프리셋 변경 (fast_draft, balanced, deep_review)
python -m orchestra.cli --preset deep_review

# 저장 폴더 이름 지정
python -m orchestra.cli --idea "우주 공룡 게임" --run-name space-dino

# GitHub PR 연동 (기획 완료 시 자동으로 PR 생성)
python -m orchestra.cli --idea "우주 공룡 게임" \
  --github-repo "owner/repo-name" \
  --github-token "ghp_..."
```

실행 결과:
- `artifacts/cli/playable/<run-name>/round_1_design.md` — 1차 기획안
- `artifacts/cli/playable/<run-name>/round_2_revision.md` — 수정 기획안
- `artifacts/cli/playable/<run-name>/final_game_spec.md` — 최종 명세서
- `artifacts/cli/playable/<run-name>/game_schema.json` — 구조화 명세
- `artifacts/cli/playable/<run-name>/message_log.json` — 에이전트 메시지 로그
- `artifacts/cli/playable/<run-name>/run_progress.json` — 진행 상태
- `artifacts/cli/playable/<run-name>/game/index.html` — 브라우저에서 플레이 가능한 프로토타입

### 3. Discord 봇 (Tutti) — 추천!

디스코드 서버에서 비개발 직군(기획자, PM)도 함께 사용할 수 있습니다.

```bash
cp .env.example .env
# .env 파일을 열어 DISCORD_BOT_TOKEN을 설정하세요
python -m orchestra.discord_bot
```

**슬래시 커맨드:**

| 명령어 | 설명 |
|:---|:---|
| `/tutti start name:... idea:...` | 게임 기획 run 시작 |
| `/tutti revise "지시사항"` | 마지막 run 수정 |
| `/tutti status` | 현재 상태 확인 |
| `/tutti settings` | 에이전트/서버/GitHub 설정 |
| `/tutti apikey` | API 키 및 GitHub 토큰 설정 (DM) |
| `/tutti github` | GitHub PR 연동 설정 가이드 |
| `/tutti learn "규칙"` | 에이전트에게 규칙 학습 |
| `/tutti rules` | 학습된 규칙 목록 |
| `/tutti forget` | 학습된 규칙 삭제 |
| `/tutti help` | 도움말 |
| `/tutti menu` | 온보딩 메뉴 패널 |

**쓰레드 대화:** 생성된 `run-*` 쓰레드에서 `@디자이너`, `@리뷰어`, `@ceo`, `@라이터`로 에이전트를 호출하여 브레인스토밍할 수 있습니다.

> 📖 상세 사용법: [Tutti_Discord_Guide.md](Tutti_Discord_Guide.md)

---

## 에이전트 모드

### Mock 모드 (기본값)
외부 API 없이 즉시 동작합니다. 에이전트 간 메시지 교환과 협업 구조를 확인하는 데 사용합니다.

```bash
python -m orchestra.cli
```

### Ollama 모드
로컬 LLM 서버를 연결하여 실제 AI가 게임을 기획합니다.

```bash
python -m orchestra.cli --mode ollama
```

`.env` 설정:
```
AGENT_MODE=ollama
OLLAMA_BASE_URL=http://localhost:11434
DESIGNER_MODEL=qwen2.5-coder:7b-instruct
REVIEWER_MODEL=qwen2.5-coder:7b-instruct
CEO_MODEL=qwen3:8b
SPEC_WRITER_MODEL=qwen2.5-coder:7b-instruct
```

### API 모드
OpenAI, Google Gemini 등 클라우드 API를 사용합니다.

```bash
python -m orchestra.cli --mode api
```

`.env` 설정:
```
AGENT_MODE=api
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AI...
```

---

## 프로젝트 구조

```
orchestra/
├── cli.py              # CLI 엔트리포인트
├── discord_bot.py      # Discord 봇 (Tutti) - 슬래시 커맨드, UI, HitL
├── discord.py          # Discord 어댑터 및 워크스페이스
├── workflow.py         # 멀티 에이전트 워크플로우 오케스트레이션
├── adapters.py         # LLM 프로바이더 어댑터 (Mock, Ollama, OpenAI, Google)
├── config.py           # 에이전트 설정 로더
├── models.py           # 데이터 모델
├── pipeline.py         # 실행 계획 빌더
├── prototype.py        # 플레이 가능한 HTML 게임 생성기
├── github_pr.py        # GitHub PR 자동 생성 (urllib, 외부 의존성 0)
├── knowledge.py        # 영구 지식 베이스 (Global/Project 규칙)
├── presets.py          # 실행 프리셋 (fast_draft, balanced, deep_review)
├── input_parser.py     # 사용자 입력 파서
├── run_view.py         # 실행 상태 포맷터
└── rules/              # 에이전트별 프롬프트 규칙
    ├── shared.md
    ├── designer.md
    ├── reviewer.md
    ├── ceo.md
    └── spec_writer.md

docs/
├── design/         # 설계 및 아키텍처 문서
├── guides/         # 실행 가이드 (Ollama, API 연동)
├── operations/     # AI 활용 운영 문서와 요청 카탈로그
└── agent-logs/     # 세션 로그 제출 안내 (원본 JSONL은 민감정보 제거 후 별도 제출)
```

---

## AI 코딩 에이전트 활용 기록

이 프로젝트는 **AI 코딩 에이전트를 활용하여 개발**되었습니다.

| 도구 | 활용 범위 |
|:---|:---|
| **OpenAI Codex** | 초기 아키텍처 설계, 모듈 구현, 코드 리뷰 |
| **Gemini CLI (Antigravity)** | P0/P1 고도화, GitHub PR 연동, 문서 작성, 디버깅 |

세션 로그 원본은 토큰/로컬 경로 등 민감정보가 포함될 수 있어 public repo에는 그대로 커밋하지 않습니다. 제출 시에는 화면 녹화 또는 민감정보를 제거한 JSONL을 별도 첨부하는 방식을 권장합니다.
세션 로그 제출 안내: [docs/agent-logs/README.md](docs/agent-logs/README.md)
에이전트 활용 안내 문서: [docs/design/skill-and-subagent-usage.md](docs/design/skill-and-subagent-usage.md)

---

## 테스트

```bash
python -m unittest discover -s tests
```

## 기술 스택

- **Python 3.11+**
- **discord.py 2.3+** — Discord 봇 및 슬래시 커맨드
- **Ollama** — 로컬 LLM 추론 (선택)
- **OpenAI / Google Gemini** — 클라우드 LLM (선택)
- **GitHub REST API** — PR 자동 생성 (stdlib `urllib`, 외부 의존성 0)

## 문서

- [DESIGN.md](DESIGN.md) — 시스템 설계 문서
- [Tutti_Discord_Guide.md](Tutti_Discord_Guide.md) — 디스코드 봇 사용 설명서
- [Multi_Agent_Game_Design_Proposal.md](Multi_Agent_Game_Design_Proposal.md) — 초기 기술 제안서

## 라이선스

MIT

---

## 📝 프로젝트 완성 후 발견한 것

> 이 프로젝트를 완성하고 나서 알게 되었습니다.

**[openai-oauth](https://github.com/EvanZhouDev/openai-oauth)**를 사용하면 ChatGPT Plus/Pro 구독자가 별도의 API 키 없이 OAuth 인증만으로 OpenAI 모델을 사용할 수 있습니다.

현재 Tutti는 사용자가 직접 API 키를 발급받아 입력해야 하지만, 이 라이브러리를 적용하면:

- ✅ API 키 발급 없이 ChatGPT 구독만으로 바로 사용
- ✅ `/tutti apikey` 설정 단계 제거 → 온보딩 마찰 0
- ✅ B2C 구독 서비스 모델로 전환 가능

현재 구조(`adapters.py`의 Provider 패턴)는 신규 프로바이더를 쉽게 추가할 수 있도록 설계되어 있어, 향후 `OpenAIOAuthAdapter`를 추가하는 방향으로 확장할 수 있습니다.
