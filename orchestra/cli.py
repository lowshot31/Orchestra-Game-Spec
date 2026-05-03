"""Orchestra CLI — 터미널에서 멀티 에이전트 협업 데모를 실행합니다.

사용법:
    python -m orchestra.cli                         # mock 모드 (기본)
    python -m orchestra.cli --idea "1분 리듬 게임"   # 아이디어 지정
    python -m orchestra.cli --mode ollama            # Ollama 모드
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .workflow import run_design_review, finalize_collaboration
from .prototype import generate_playable_prototype


def _safe_run_name(value: str) -> str:
    normalized = re.sub(r"\s+", "-", value.strip().lower())
    normalized = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "latest"


def _print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def _print_agent(role: str, provider: str, model: str, content: str) -> None:
    print(f"+-- {role} [{provider}/{model}]")
    for line in content.strip().splitlines():
        print(f"|  {line}")
    print("+" + "-" * 50)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestra 멀티 에이전트 게임 기획 CLI")
    parser.add_argument("--idea", default="3분 안에 끝나는 병합 퍼즐 게임", help="게임 아이디어")
    parser.add_argument("--mode", default="mock", choices=["mock", "ollama", "api"], help="에이전트 모드")
    parser.add_argument("--intervention", default="", help="사용자 개입 지시")
    parser.add_argument("--preset", default="balanced", help="프리셋 (fast_draft, balanced, deep_review)")
    parser.add_argument("--output", default="artifacts/cli", help="결과물 저장 경로")
    parser.add_argument("--run-name", default="", help="결과물 run 폴더 이름 (기본: idea 기반 자동 생성)")
    parser.add_argument("--github-repo", default="", help="GitHub 레포 (owner/repo)")
    parser.add_argument("--github-token", default="", help="GitHub PAT")
    args = parser.parse_args()

    run_name = _safe_run_name(args.run_name or args.idea)
    env = {
        "AGENT_MODE": args.mode,
        "AGENT_PRESET": args.preset,
        "CLI_RUN": run_name,
    }

    artifact_dir = Path(args.output)

    # Load knowledge for CLI
    from .knowledge import load_all_rules
    knowledge = load_all_rules(Path(args.output).parent, "")
    learned_text = knowledge.format_for_prompt()
    if learned_text:
        env["LEARNED_RULES"] = learned_text

    _print_header("Orchestra Multi-Agent Game Design")
    print(f"  Mode:         {args.mode}")
    print(f"  Preset:       {args.preset}")
    print(f"  Idea:         {args.idea}")
    print(f"  Intervention: {args.intervention or '(none)'}")
    print(f"  Knowledge:    {len(knowledge.rules)} rules loaded")
    print(f"  Run:          {run_name}")
    print(f"  Output:       {artifact_dir / 'playable' / run_name}")
    print()

    # Round 1: Design Review
    _print_header("Round 1 - Design Review")

    stage = run_design_review(args.idea, env=env, artifact_dir=artifact_dir)

    for msg in stage.messages:
        _print_agent(msg.sender, msg.provider, msg.model, msg.content)
        
    print(f"[Risk] CEO Risk Assessment: {stage.risk_level}")

    # User intervention checkpoint
    intervention = args.intervention
    if not intervention and sys.stdin.isatty():
        print("-" * 60)
        print("에이전트 리뷰를 확인했습니다.")
        print("개입하려면 지시를 입력하세요 (Enter로 스킵):")
        try:
            user_input = input("> ").strip()
        except EOFError:
            user_input = ""
        if user_input:
            intervention = user_input

    # Round 2: Finalize
    _print_header("Round 2 - Revision & Final Spec")

    result = finalize_collaboration(stage, intervention=intervention)

    for msg in result.messages:
        if msg.round == 2:
            _print_agent(msg.sender, msg.provider, msg.model, msg.content)

    # Prototype
    _print_header("Playable Prototype")

    playable_dir = generate_playable_prototype(
        args.idea, result.messages[-1].content, result.final_spec_path.parent, "game", env,
    )
    print(f"  생성 완료: {playable_dir}")
    print(f"  브라우저에서 열기: {playable_dir / 'index.html'}")

    # GitHub PR
    if args.github_repo and args.github_token:
        _print_header("GitHub Auto PR")
        repo_val = args.github_repo.strip()
        if "github.com/" in repo_val:
            repo_val = repo_val.split("github.com/")[-1]
        if repo_val.endswith(".git"):
            repo_val = repo_val[:-4]
        repo_val = repo_val.strip("/")
        
        from .github_pr import create_game_pr
        try:
            pr_result = create_game_pr(
                token=args.github_token,
                repo=repo_val,
                run_name=run_name,
                spec_path=result.final_spec_path,
                schema_path=result.schema_path,
                prototype_dir=playable_dir,
                idea=args.idea,
                risk_level=stage.risk_level,
            )
            print(f"[OK] PR Created: {pr_result.pr_url}")
            print(f"   Branch: {pr_result.branch_name}")
            print(f"   Pushed: {len(pr_result.files_pushed)} files")
        except Exception as e:
            print(f"[ERROR] GitHub PR Failed: {e}")

    # Summary
    _print_header("Results")
    print(f"  Final spec:   {result.final_spec_path}")
    print(f"  Schema:       {result.schema_path}")
    print(f"  Prototype:    {playable_dir / 'index.html'}")
    print(f"  Messages:     {len(result.messages)}개 에이전트 메시지")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
