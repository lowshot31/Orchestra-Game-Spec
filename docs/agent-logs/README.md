# Agent Session Logs

이 폴더는 평가자가 에이전트 세션 로그 제출 방식을 이해할 수 있도록 남긴 안내 문서입니다.

## 원본 로그를 public repo에 직접 올리지 않는 이유

Codex 세션 로그(JSONL)는 개발 과정의 중요한 증거이지만, 다음 정보가 섞일 수 있습니다.

- 시스템 프롬프트와 도구 호출 내역
- 로컬 파일 경로와 사용자 환경 정보
- API token, Discord token, GitHub token 같은 민감정보가 포함된 출력
- 외부 제출에 불필요한 잡담 또는 개인 작업 맥락

따라서 원본 로그는 public GitHub repo에 그대로 커밋하지 않고, 제출 시에는 아래 둘 중 하나를 권장합니다.

## 제출 권장 방식

| 방식 | 설명 |
| :--- | :--- |
| 화면 녹화 | README대로 실행되는 모습, agent message log, 최종 산출물을 보여주는 방식 |
| Sanitized JSONL | 민감정보와 잡담을 제거하고 프로젝트 관련 이벤트만 남긴 세션 로그 |

JSONL을 제출한다면 파일명은 아래처럼 두면 평가자가 이해하기 쉽습니다.

```text
codex-agent-session-history.sanitized.jsonl
codex-agent-session-audit.sanitized.jsonl
```

## 로컬 원본 위치

Codex Desktop/CLI의 로컬 원본 세션 로그는 일반적으로 아래 위치에 있습니다.

```text
%USERPROFILE%\.codex\sessions
%USERPROFILE%\.codex\session_index.jsonl
```

이 프로젝트의 제출 설명 문서는 `docs/design/skill-and-subagent-usage.md`를 참고하면 됩니다.
