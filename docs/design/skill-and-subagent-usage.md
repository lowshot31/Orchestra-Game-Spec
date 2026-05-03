# Skill & Subagent Usage

## 한눈에 보기

Orchestra는 두 층의 멀티에이전트 활용을 보여준다.

| 구분 | 무엇을 의미하나 | 어디서 확인하나 |
| :--- | :--- | :--- |
| 개발 과정의 에이전트 활용 | Codex가 스킬과 서브에이전트를 사용해 설계, 리뷰, 구현 방향을 정리한 과정 | 이 문서, Codex 세션 로그 |
| 제품 실행 중의 에이전트 협업 | Orchestra 안에서 Designer, Reviewer, CEO, Writer가 메시지를 주고받는 runtime workflow | `artifacts/cli/playable/<run-name>/message_log.json` |

이 문서는 평가자가 "개발 과정에서 어떤 스킬과 서브에이전트를 사용했는지" 빠르게 이해할 수 있도록 정리한 안내 문서다.

원본 근거는 Codex 로컬 세션 로그다.

```text
%USERPROFILE%\.codex\sessions
%USERPROFILE%\.codex\session_index.jsonl
```

## 평가자가 보면 좋은 포인트

- Codex 본체만 사용한 것이 아니라, 특정 검토와 설계 작업을 서브에이전트에게 위임했다.
- Superpowers와 gstack 계열 스킬을 사용해 제품 방향, 구현 계획, 코드 리뷰, 운영 문서를 정리했다.
- 서브에이전트는 단순 보조가 아니라, UX 리뷰, Discord 구조 검토, command routing 검토, dynamic agent 구조 검토처럼 역할이 분리된 작업을 맡았다.
- 최종 제품 안에서도 별도의 runtime agent들이 메시지를 주고받는다.

## 사용한 스킬

### Superpowers

`Superpowers`는 개발 과정에서 가장 명확하게 확인되는 스킬 계열이다.

| 스킬 | 사용 목적 |
| :--- | :--- |
| `superpowers:brainstorming` | 과제 방향, Discord 제품 방향, 구현 범위 정리 |
| `superpowers:using-superpowers` | 스킬 사용 흐름 확인 |
| `superpowers:writing-plans` | 구현 계획 작성 |
| `superpowers:receiving-code-review` | 코드 리뷰 피드백 검토 후 반영 |

대표 사용 장면:

- 초기 과제 제안서를 검토할 때 `superpowers:brainstorming`을 명시적으로 사용했다.
- Discord 방향을 잡을 때 brainstorming 방식으로 범위와 리스크를 나눴다.
- 리뷰 피드백을 반영할 때 `receiving-code-review` 지침을 확인하고, 실제 코드와 문서 상태를 검증한 뒤 수정했다.

### GStack

`gstack`는 Codex에 설치된 스킬 팩으로, 창업자/제품/엔지니어링 운영 관점의 문서와 의사결정 흐름을 만드는 데 사용되었다.

| 스킬 또는 관점 | 사용 목적 |
| :--- | :--- |
| `gstack-office-hours` | 아이디어와 제품 방향 압박 질문 |
| `gstack-plan-ceo-review` | CEO 관점의 범위 판단 |
| `gstack-plan-eng-review` | 구현 구조와 리스크 검토 |
| `gstack-plan-design-review` | UX/디자인 방향 검토 |
| `gstack-plan-devex-review` | 개발자 경험 검토 |
| `gstack-review` | 코드/문서 리뷰 관점 정리 |

관련 산출물:

- `docs/operations/founder-ai-operating-guide.md`
- `docs/operations/codex-request-catalog.md`
- `docs/operations/weekly-operating-template.md`

참고:

스킬 사용은 항상 "실행 로그 한 줄"처럼 남지 않는다. 일부는 세션 중 언급, 일부는 도구 호출, 일부는 최종 문서에 반영된 형태로 남는다.

## 사용한 서브에이전트

아래 표는 확인 가능한 Codex 서브에이전트 작업을 평가자가 읽기 쉬운 단위로 묶은 것이다.

### 1. 초기 제안서와 MVP 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Review docs consistency` | README, 제안서, 구현 내용 사이의 불일치 검토 | 문서와 코드가 어긋나는 지점 발견 |
| `Review multi-agent workflow` | 멀티에이전트 workflow와 Human-in-the-loop 구조 검토 | 사용자 개입, API 의존성, 테스트 부족 리스크 지적 |

### 2. 동적 에이전트와 pipeline 구조 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Support dynamic agent pipeline` | 고정 3-agent pipeline을 설정 가능한 구조로 바꾸는 방법 검토 | ordered pipeline, step metadata, generic workflow 제안 |
| `Review dynamic agents risks` | agent 추가/삭제 기능의 위험 검토 | 임의 graph보다 validated preset부터 가는 접근 추천 |

### 3. 제품 범위, UX, DevEx 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Review Orchestra v1 scope` | v1 제품 범위와 핵심 wedge 검토 | "설정 가능한 agent tool"보다 "게임 아이디어를 spec으로 만드는 제품"에 집중하라고 제안 |
| `Review Orchestra UX` | 사용자 화면과 정보 구조 검토 | Run 중심 UX, Workspace/Settings 분리 방향 제안 |
| `Review DevEx platform design` | 개발자 경험과 runtime 확장성 검토 | 선언적 runtime과 제한된 설정 구조 제안 |

### 4. Discord 제품 방향 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Review Discord bot UX` | Discord 첫 사용 경험과 onboarding 검토 | command-first가 아니라 action-first 경험 필요성 지적 |
| `Review game pivot plan` | 단순 오케스트레이터에서 실제 게임 생성 흐름으로 pivot 검토 | playable prototype 생성이 제출 설득력을 높인다고 판단 |
| `Review creator product pivot` | creator-first 제품 방향 검토 | Discord에서 "첫 게임 만들기"를 중심 흐름으로 제안 |
| `Review orchestra command flow` | `/orchestra`, `/tutti`, help/start/status 구조 검토 | primary flow와 admin flow를 분리하는 router 제안 |
| `Review Discord readiness` | Discord 제출 준비도 검토 | 현재 구현의 강점과 부족한 onboarding 지점 점검 |
| `Review Discord onboarding UX` | 초대 후 첫 메시지와 버튼 UX 검토 | `Start Demo`, `Configure Workspace`, `Agent Settings` 같은 CTA 제안 |
| `Review Discord implementation` | Discord bot 구현 리스크 검토 | interaction timeout, defer/followup 처리 등 실제 Discord API 리스크 지적 |

### 5. Discord 메시지와 thread UX 검토

이 그룹은 세션 이름이 명확하지 않은 일부 서브에이전트까지 포함한다. 다만 `subagent_notification` 요약 내용에서 역할이 확인된다.

| 역할 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| Discord readability reviewer | run thread 메시지 가독성 검토 | 역할별 메시지와 완료 메시지를 더 구분해야 한다고 제안 |
| Discord hierarchy reviewer | Discord category/channel/thread 구조 검토 | 너무 많은 곳에 run이 분산되는 문제 지적 |
| Human intervention placement reviewer | 사람 개입 위치 검토 | 승인/수정은 run thread 안에 있어야 한다고 제안 |
| Discord message taxonomy reviewer | 메시지 형식 분류 검토 | card-like block 구조 추천 |
| Discord message formatting reviewer | 역할별 메시지, 승인, 핸드오프 포맷 검토 | 같은 run 안에서 읽는 방식이 일관되어야 한다고 제안 |

### 6. Command routing 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Clarify /tutti command routing` | `/tutti revise`를 어떤 경로로 처리할지 검토 | slash command만 action으로 보고 thread plain text는 chat으로 남기자고 제안 |
| `Clarify command and chat handling` | legacy prefix, slash command, thread chat 분리 검토 | real slash command와 일반 대화의 책임 분리 계약 제안 |

### 7. Agent rules와 협업 규칙 검토

| 서브에이전트 | 맡긴 일 | 결과 |
| :--- | :--- | :--- |
| `Review collaboration rules` | `orchestra/rules/*.md` 규칙 검토 | 역할별 규칙이 더 명확한 협업 계약을 가져야 한다고 제안 |
| `Extract subagent patterns` | Superpowers subagent 패턴 분석 | Orchestra 역할 규칙에 재사용 가능한 delegation 패턴 정리 |

## 제품 안에서 실행되는 runtime agents

Codex 개발 과정의 서브에이전트와 별개로, Orchestra 제품 자체도 runtime agent를 가진다.

| Runtime agent | 역할 |
| :--- | :--- |
| `human_operator` | 사용자 요청과 개입 |
| `creative_designer` | 게임 컨셉 초안 작성 |
| `technical_reviewer` | 기술 검토와 범위 조정 |
| `product_ceo` | 시장성, 훅, 위험도 판단 |
| `spec_writer` | 최종 명세 작성 |

CLI 또는 Discord로 실행하면 이 agent들의 메시지가 `message_log.json`에 저장된다.

예시:

```text
artifacts/cli/playable/<run-name>/message_log.json
artifacts/discord/playable/<run-name>/message_log.json
```

## 추천 확인 순서

평가자가 빠르게 확인하려면 아래 순서가 좋다.

1. 이 문서에서 어떤 스킬과 서브에이전트가 쓰였는지 본다.
2. `docs/operations/`의 개발/운영 문서가 실제 결과물로 남아 있는지 확인한다.
3. CLI를 실행해 runtime agent 메시지 로그를 만든다.
4. 생성된 `message_log.json`에서 Orchestra 내부 agent들이 서로 메시지를 주고받는지 확인한다.

대표 CLI 실행:

```powershell
python -m orchestra.cli --idea "한 손으로 하는 30초 리듬 게임" --intervention "모바일에서 바로 이해되게 단순하게" --run-name review-demo
```

생성되는 로그:

```text
artifacts/cli/playable/review-demo/message_log.json
```

## 최종 해석

이 프로젝트에서 "멀티에이전트"는 두 번 사용된다.

- 개발 과정에서는 Codex가 스킬과 서브에이전트를 사용해 설계, 리뷰, 구현 방향을 잡았다.
- 제품 실행 과정에서는 Orchestra runtime agents가 실제로 메시지를 주고받으며 게임 기획 산출물을 만든다.

따라서 이 문서는 "AI 코딩 에이전트를 활용해 개발했다"는 증거를 설명하고, 실행 산출물의 `message_log.json`은 "제품 안에서 에이전트들이 협업한다"는 증거를 보여준다.

