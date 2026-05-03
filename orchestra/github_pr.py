"""GitHub PR 자동 생성 모듈.

Tutti 파이프라인 완료 후, 산출물(기획서 + 스키마 + 프로토타입)을
별도 GitHub 레포에 자동으로 브랜치 → 커밋 → PR 생성.

외부 의존성 없이 urllib만 사용.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import urllib.parse

LOGGER = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


@dataclass
class PRResult:
    """PR 생성 결과."""
    pr_url: str
    branch_name: str
    files_pushed: list[str] = field(default_factory=list)


def _gh_request(
    method: str,
    path: str,
    token: str,
    body: dict | None = None,
) -> dict:
    """GitHub REST API 호출 (urllib 기반)."""
    # 한글 등 비-ASCII 문자가 포함된 경로 처리
    path = urllib.parse.quote(path, safe="/?&=")
    url = f"{GITHUB_API}{path}" if path.startswith("/") else path
    data = json.dumps(body).encode("utf-8") if body else None

    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code != 404:
            LOGGER.error("GitHub API error %s %s: %s — %s", method, path, exc.code, error_body)
        raise RuntimeError(f"GitHub API {exc.code}: {error_body}") from exc


def _get_default_branch_sha(token: str, repo: str) -> tuple[str, str]:
    """기본 브랜치(main/master)의 최신 SHA를 가져옴."""
    repo_info = _gh_request("GET", f"/repos/{repo}", token)
    default_branch = repo_info.get("default_branch", "main")
    ref = _gh_request("GET", f"/repos/{repo}/git/ref/heads/{default_branch}", token)
    sha = ref["object"]["sha"]
    return default_branch, sha


def _create_branch(token: str, repo: str, branch_name: str, base_sha: str) -> None:
    """새 브랜치 생성."""
    try:
        _gh_request("POST", f"/repos/{repo}/git/refs", token, body={
            "ref": f"refs/heads/{branch_name}",
            "sha": base_sha,
        })
        LOGGER.info("Branch created: %s", branch_name)
    except RuntimeError as exc:
        if "422" in str(exc) and "Reference already exists" in str(exc):
            LOGGER.warning("Branch %s already exists, reusing.", branch_name)
        else:
            raise


def _upload_file(
    token: str,
    repo: str,
    branch: str,
    repo_path: str,
    content: bytes,
    commit_message: str,
) -> None:
    """파일 하나를 브랜치에 커밋."""
    encoded = base64.b64encode(content).decode("ascii")

    # 기존 파일이 있으면 SHA를 가져와야 업데이트 가능
    sha = None
    try:
        existing = _gh_request("GET", f"/repos/{repo}/contents/{repo_path}?ref={branch}", token)
        sha = existing.get("sha")
    except RuntimeError:
        pass  # 파일이 없으면 새로 생성

    body: dict = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    _gh_request("PUT", f"/repos/{repo}/contents/{repo_path}", token, body=body)


def _create_pull_request(
    token: str,
    repo: str,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> str:
    """PR 생성 후 URL 반환."""
    result = _gh_request("POST", f"/repos/{repo}/pulls", token, body={
        "title": title,
        "body": body,
        "head": branch,
        "base": base_branch,
    })
    return result["html_url"]


def _build_pr_body(
    run_name: str,
    idea: str,
    risk_level: str,
    files: list[str],
) -> str:
    """PR 본문 Markdown 자동 생성."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    file_table = "\n".join(f"| `{f}` |" for f in files)

    return f"""## 🎮 게임 기획 핸드오프: {run_name}

### 📋 기획 요약
- **아이디어:** {idea}
- **생성일:** {date_str}
- **위험도:** {risk_level}

### 📦 산출물
| 파일 |
|:---|
{file_table}

### 🎯 개발팀 다음 단계
1. 이 PR을 리뷰하여 기획의 기술적 실현 가능성을 검토하세요.
2. `prototype/index.html`을 로컬에서 열어 게임 감각을 테스트하세요.
3. 승인 후 실제 엔진(Unity/React 등)으로 프로덕션 코드를 작성하세요.

---
*이 PR은 [Tutti](https://github.com) 멀티 에이전트 봇에 의해 자동 생성되었습니다.*
"""


def _build_readme(run_name: str, idea: str, risk_level: str) -> str:
    """산출물 디렉토리의 README.md 자동 생성."""
    return f"""# 🎮 {run_name}

> {idea}

## 산출물
- `final_game_spec.md` — 최종 게임 기획서
- `game_schema.json` — 게임 메타데이터
- `prototype/` — 브라우저에서 플레이 가능한 프로토타입

## 프로토타입 실행
```bash
# prototype/ 폴더 안의 index.html을 브라우저에서 열기
open prototype/index.html
```

## 정보
- **위험도:** {risk_level}
- **생성:** Tutti 멀티 에이전트 봇
"""


def create_game_pr(
    token: str,
    repo: str,
    run_name: str,
    spec_path: Path,
    schema_path: Path,
    prototype_dir: Path,
    idea: str,
    risk_level: str = "MEDIUM",
) -> PRResult:
    """산출물을 GitHub에 푸시하고 PR을 생성.

    Args:
        token: GitHub Personal Access Token
        repo: "owner/repo-name" 형식
        run_name: 런 이름 (예: "1to50-game")
        spec_path: final_game_spec.md 경로
        schema_path: game_schema.json 경로
        prototype_dir: 프로토타입 디렉토리 (index.html, style.css, game.js 포함)
        idea: 원본 게임 아이디어
        risk_level: CEO 위험도 평가 결과

    Returns:
        PRResult with PR URL, branch name, and pushed files list
    """
    branch_name = f"game/{run_name}"
    base_dir = f"games/{run_name}"

    # 1. 기본 브랜치의 최신 SHA 가져오기
    default_branch, base_sha = _get_default_branch_sha(token, repo)
    LOGGER.info("Base branch: %s (SHA: %s)", default_branch, base_sha[:8])

    # 2. 새 브랜치 생성
    _create_branch(token, repo, branch_name, base_sha)

    # 3. 파일 수집 및 업로드
    files_pushed: list[str] = []

    # README.md 자동 생성
    readme_content = _build_readme(run_name, idea, risk_level)
    readme_path = f"{base_dir}/README.md"
    _upload_file(token, repo, branch_name, readme_path, readme_content.encode("utf-8"),
                 f"docs: {run_name} README 추가")
    files_pushed.append(readme_path)

    # 기획서
    if spec_path.exists():
        _upload_file(token, repo, branch_name, f"{base_dir}/final_game_spec.md",
                     spec_path.read_bytes(),
                     f"docs: {run_name} 최종 기획서 추가")
        files_pushed.append(f"{base_dir}/final_game_spec.md")

    # 스키마
    if schema_path.exists():
        _upload_file(token, repo, branch_name, f"{base_dir}/game_schema.json",
                     schema_path.read_bytes(),
                     f"docs: {run_name} 게임 스키마 추가")
        files_pushed.append(f"{base_dir}/game_schema.json")

    # 프로토타입 파일들
    if prototype_dir.exists():
        for file in sorted(prototype_dir.rglob("*")):
            if file.is_file():
                relative = file.relative_to(prototype_dir)
                repo_file_path = f"{base_dir}/prototype/{relative.as_posix()}"
                _upload_file(token, repo, branch_name, repo_file_path,
                             file.read_bytes(),
                             f"feat: {run_name} 프로토타입 {relative.name} 추가")
                files_pushed.append(repo_file_path)

    LOGGER.info("Pushed %d files to %s", len(files_pushed), branch_name)

    # 4. PR 생성
    pr_body = _build_pr_body(run_name, idea, risk_level, files_pushed)
    pr_url = _create_pull_request(
        token, repo, branch_name, default_branch,
        title=f"🎮 게임 기획: {run_name}",
        body=pr_body,
    )
    LOGGER.info("PR created: %s", pr_url)

    return PRResult(pr_url=pr_url, branch_name=branch_name, files_pushed=files_pushed)
