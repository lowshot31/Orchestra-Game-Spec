# Submission Guide

이 문서는 평가자가 GitHub repo, 실행 방법, 에이전트 활용 증거를 빠르게 확인할 수 있도록 정리한 제출 안내서입니다.

## 제출물 대응표

| 제출 요구사항 | 이 프로젝트에서의 위치 | 확인 방법 |
| :--- | :--- | :--- |
| 작동하는 코드 | https://github.com/lowshot31/Orchestra-Game-Spec | README의 Quick Start 또는 아래 CLI 데모 실행 |
| 개발 과정에서 에이전트에 활용한 `.md` 파일 | `docs/design/skill-and-subagent-usage.md`, `docs/operations/`, `Multi_Agent_Game_Design_Proposal.md`, `DESIGN.md` | 각 문서에서 설계, 운영, 스킬/서브에이전트 활용 내역 확인 |
| 에이전트 세션 로그(JSONL) 또는 화면 녹화 | 화면 녹화 제출 권장. JSONL을 제출할 경우 민감정보 제거 후 별도 첨부 | 공개 repo에는 원본 로그를 커밋하지 않음. 이유는 `docs/agent-logs/README.md` 참고 |

## 가장 빠른 실행 확인

API 키나 Discord token 없이 `mock` 모드로 바로 실행할 수 있습니다.

```powershell
python -m orchestra.cli --idea "한 손으로 하는 30초 리듬 게임" --intervention "모바일에서 바로 이해되게 단순하게" --run-name review-demo
```

실행 후 아래 파일이 생성되면 정상입니다.

```text
artifacts/cli/playable/review-demo/final_game_spec.md
artifacts/cli/playable/review-demo/game_schema.json
artifacts/cli/playable/review-demo/message_log.json
artifacts/cli/playable/review-demo/run_progress.json
artifacts/cli/playable/review-demo/game/index.html
```

특히 `message_log.json`은 제품 내부 runtime agents가 서로 메시지를 주고받았다는 증거입니다.

## 테스트 확인

```powershell
python -m unittest discover -s tests
```

현재 테스트는 CLI 저장 구조, Discord 저장 구조, Human-in-the-loop, GitHub PR 연동 모듈, 프로토타입 생성 흐름을 포함합니다.

## 시연 영상 추천 흐름

영상은 3-5분 정도면 충분합니다.

1. GitHub repo와 README를 보여준다.
2. `SUBMISSION.md`를 열어 제출 요구사항 대응표를 보여준다.
3. `python -m unittest discover -s tests`로 테스트 통과를 보여준다.
4. 위 CLI 명령으로 `review-demo` run을 실행한다.
5. `artifacts/cli/playable/review-demo/message_log.json`을 열어 agent 메시지 로그를 보여준다.
6. `artifacts/cli/playable/review-demo/final_game_spec.md`와 `game/index.html`을 열어 최종 산출물을 보여준다.
7. 시간이 남으면 Discord 봇 문서(`Tutti_Discord_Guide.md`)와 `/tutti` 흐름을 설명한다.

## 평가자가 보면 좋은 포인트

- README 명령만으로 기본 데모가 동작한다.
- 외부 API 키 없이도 `mock` mode로 멀티에이전트 메시지 흐름을 확인할 수 있다.
- CLI와 Discord 모두 `artifacts/.../playable/<run-name>/` 구조로 결과물을 저장한다.
- 개발 과정의 스킬과 서브에이전트 사용 내역은 `docs/design/skill-and-subagent-usage.md`에 사람이 읽기 쉬운 형태로 정리되어 있다.
- 원본 Codex JSONL 로그는 민감정보 가능성이 있어 public repo가 아니라 별도 제출 또는 화면 녹화로 대체하는 구성이 안전하다.
