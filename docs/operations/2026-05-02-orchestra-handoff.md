# Orchestra Handoff - 2026-05-02

## Current product direction

Orchestra is now moving toward a hybrid collaboration model:

- Discord as the team workspace
- Orchestra as the orchestration engine
- Web UI as a run console, progress board, and settings surface

Recommended information architecture going forward:

- One Discord server per studio/team
- One category per game project
- Forum channels or threads for features, sprints, and tasks

Core hierarchy:

`Studio server -> Project category -> Feature/Sprint/Task threads`

## What is implemented

The current project uses CLI and Discord bot surfaces. The main runnable surfaces are:

- CLI demo via `python -m orchestra.cli`
- Discord bot via `python -m orchestra.discord_bot`
- Generated artifacts under `artifacts/`

Implemented:

- Role rules split into files under `orchestra/rules/`
- Preset system with `fast_draft`, `balanced`, `deep_review`
- Project-wide instruction overlay via `instructions: ...`
- Run input parsing for `preset`, `instructions`, and `intervention`
- Execution plan model in `orchestra/pipeline.py`
- Run composer and progress board formatting in `orchestra/run_view.py`
- Progress artifact output at `artifacts/run_progress.json`
- Pipeline progress snapshot embedded in `game_schema.json`
- Discord slash-command surface under `/tutti`
- Playable HTML prototype generation under `artifacts/**/playable/`

Runtime behavior currently:

- CLI prints the agent timeline and writes Markdown/JSON/HTML artifacts.
- Discord bot starts runs with `/tutti start`, creates run threads, publishes agent messages, and supports approval/revision flow.
- Generated artifacts are the durable record for specs, schemas, progress, message logs, Discord sync, and prototypes.

## Important code locations

- CLI entry flow: `orchestra/cli.py`
- Discord bot entry flow: `orchestra/discord_bot.py`
- Prompt construction and provider adapters: `orchestra/adapters.py`
- Preset definitions: `orchestra/presets.py`
- Input parsing: `orchestra/input_parser.py`
- Execution plan and progress structure: `orchestra/pipeline.py`
- Run board formatting: `orchestra/run_view.py`
- Workflow execution and artifact writing: `orchestra/workflow.py`
- Tests: `tests/test_orchestra_core.py`

## Review result

Review pass today found two practical issues and both are fixed:

1. Mock mode was advertising presets and project instructions without reflecting them in output.
   Fix: mock artifacts now include preset and instruction steering so the default demo path behaves honestly.

2. The completion board was shown before the final agent outputs were rendered.
   Fix: the final progress board now appears after the final result messages.

Residual concerns:

- The workflow is still a fixed 3-agent pipeline under the hood.
- Provider selection is still mode-based and hardcoded in `orchestra/config.py`.
- The current UX is CLI/Discord-driven, not a full web board application yet.
- Temporary `tmp...` directories exist in the repo root from earlier Windows temp-path behavior and can be cleaned later.

## Verification

Fresh verification completed:

```powershell
python -m unittest discover -s tests
```

Result:

- `14` tests passed
- no failing tests

## How to run

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:AGENT_MODE="mock"
python -m orchestra.cli
```

Discord bot:

```powershell
Copy-Item .env.example .env
# Set DISCORD_BOT_TOKEN in .env
python -m orchestra.discord_bot
```

Optional run input example:

```text
3분 안에 끝나는 병합 퍼즐 게임
preset: deep_review
instructions: 모바일 퍼블리셔 피치처럼 범위와 리스크를 날카롭게 검토해줘
개입: 라이브옵스 요소는 제외
```

## Best next step tomorrow

The best next implementation slice is not "more chat polish." It is the first Discord-native team model.

Recommended next slice:

1. Define the Discord project structure contract
2. Define project, feature, sprint, and task entities in code
3. Add a Discord adapter layer that can post run updates into channels or threads
4. Reuse the existing execution plan and progress board for Discord messages
5. Keep CLI as the local demo surface until the Discord flow is proven

## Suggested concrete task order

1. Create a design doc for the Discord hybrid model
2. Define a `ProjectWorkspace` model for:
   - project
   - feature
   - sprint
   - task
3. Add a formatter for Discord channel/thread naming
4. Add a Discord event/output adapter without changing the core workflow
5. Keep provider settings and agent rules in the web console for now

## Latest design decision

The current preferred Discord SaaS structure is now more specific than the earlier thread-only note:

- One Orchestra workspace maps to one customer Discord server in v1
- One project maps to one Discord category
- One feature or sprint maps to one Discord text channel
- One task or execution run maps to one Discord thread

This should replace the looser "forum channels or threads for features, sprints, and tasks" idea for the next implementation slice.

## Product guardrails

Keep these decisions stable unless there is a strong reason to change them:

- Do not create one Discord server per game
- Do not turn v1 into a generic agent builder
- Do not expose too many model/provider controls on the first screen
- Keep the primary story as "design run -> handoff -> sprint/task execution"
