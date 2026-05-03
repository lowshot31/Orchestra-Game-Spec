# Discord SaaS Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first Discord-native workspace slice by introducing project, channel, and thread mapping models plus a dry-run Discord adapter that can project Orchestra structure without changing the core design workflow.

**Architecture:** Keep the current orchestration pipeline intact and add a separate Discord projection layer around it. New dataclasses represent workspace, project, channel, and thread mappings, a naming formatter turns app titles into Discord-safe names, and a projection adapter converts run events into category, channel, thread, and message intents that the UI can later send through a real Discord API client.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, unittest, existing Orchestra modules under `orchestra/`

---

## File Structure

Planned file ownership:

- Modify: `C:\Orchestra-Game-Spec\orchestra\models.py`
- Create: `C:\Orchestra-Game-Spec\orchestra\discord_naming.py`
- Create: `C:\Orchestra-Game-Spec\orchestra\discord_projection.py`
- Modify: `C:\Orchestra-Game-Spec\orchestra\workflow.py`
- Modify: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

Responsibility split:

- `models.py` defines stable application-side entities and mapping records.
- `discord_naming.py` owns deterministic category, channel, and thread naming.
- `discord_projection.py` owns Discord projection intents and formatting.
- `workflow.py` emits projection data without changing the underlying design-review pipeline.
- `test_orchestra_core.py` verifies the new behavior end to end in mock mode.

### Task 1: Add workspace and mapping models

**Files:**
- Modify: `C:\Orchestra-Game-Spec\orchestra\models.py`
- Test: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_workspace_mapping_models_roundtrip_to_dict(self):
        from orchestra.models import (
            DiscordInstallation,
            ProjectWorkspace,
            TaskThread,
            WorkstreamChannel,
            Workspace,
        )

        workspace = Workspace(
            id="ws_001",
            name="Studio Alpha",
            discord_guild_id="guild_123",
        )
        installation = DiscordInstallation(
            workspace_id="ws_001",
            guild_id="guild_123",
            guild_name="Alpha Server",
            installed_by_user_id="user_42",
            permissions_ok=True,
        )
        project = ProjectWorkspace(
            id="proj_001",
            workspace_id="ws_001",
            name="Orchestra Mobile",
            slug="orchestra-mobile",
            discord_category_id="cat_123",
        )
        channel = WorkstreamChannel(
            id="chan_001",
            project_id="proj_001",
            kind="feature",
            name="Discord OAuth",
            slug="discord-oauth",
            discord_channel_id="ch_123",
        )
        thread = TaskThread(
            id="thread_001",
            channel_id="chan_001",
            kind="task",
            name="OAuth Install Flow",
            slug="oauth-install-flow",
            discord_thread_id="th_123",
            archived=False,
        )

        self.assertEqual(workspace.to_dict()["discord_guild_id"], "guild_123")
        self.assertEqual(installation.to_dict()["guild_name"], "Alpha Server")
        self.assertEqual(project.to_dict()["discord_category_id"], "cat_123")
        self.assertEqual(channel.to_dict()["kind"], "feature")
        self.assertFalse(thread.to_dict()["archived"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_workspace_mapping_models_roundtrip_to_dict`

Expected: FAIL with `ImportError` or `NameError` because the new model classes do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    discord_guild_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "discord_guild_id": self.discord_guild_id,
        }


@dataclass(frozen=True)
class DiscordInstallation:
    workspace_id: str
    guild_id: str
    guild_name: str
    installed_by_user_id: str
    permissions_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "installed_by_user_id": self.installed_by_user_id,
            "permissions_ok": self.permissions_ok,
        }


@dataclass(frozen=True)
class ProjectWorkspace:
    id: str
    workspace_id: str
    name: str
    slug: str
    discord_category_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "slug": self.slug,
            "discord_category_id": self.discord_category_id,
        }


@dataclass(frozen=True)
class WorkstreamChannel:
    id: str
    project_id: str
    kind: str
    name: str
    slug: str
    discord_channel_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "name": self.name,
            "slug": self.slug,
            "discord_channel_id": self.discord_channel_id,
        }


@dataclass(frozen=True)
class TaskThread:
    id: str
    channel_id: str
    kind: str
    name: str
    slug: str
    discord_thread_id: str = ""
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "kind": self.kind,
            "name": self.name,
            "slug": self.slug,
            "discord_thread_id": self.discord_thread_id,
            "archived": self.archived,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_workspace_mapping_models_roundtrip_to_dict`

Expected: `OK`

- [ ] **Step 5: Record progress without git**

Run: `git status --short`

Expected: `fatal: not a git repository` in this workspace. Note in the implementation log that commit steps are skipped until the project is initialized as a repository.

### Task 2: Add deterministic Discord naming

**Files:**
- Create: `C:\Orchestra-Game-Spec\orchestra\discord_naming.py`
- Test: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_discord_naming_formats_project_channel_and_thread_names(self):
        from orchestra.discord_naming import (
            format_channel_name,
            format_project_category_name,
            format_thread_name,
        )

        self.assertEqual(
            format_project_category_name("Orchestra Mobile"),
            "proj-orchestra-mobile",
        )
        self.assertEqual(
            format_channel_name("feature", "Discord OAuth"),
            "feat-discord-oauth",
        )
        self.assertEqual(
            format_thread_name("task", "142", "OAuth Install Flow"),
            "task-142-oauth-install-flow",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_discord_naming_formats_project_channel_and_thread_names`

Expected: FAIL with `ModuleNotFoundError: No module named 'orchestra.discord_naming'`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import re


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    compact = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return compact or "untitled"


def format_project_category_name(project_name: str) -> str:
    return f"proj-{_slugify(project_name)}"


def format_channel_name(kind: str, name: str) -> str:
    prefix = "feat" if kind == "feature" else "sprint"
    return f"{prefix}-{_slugify(name)}"


def format_thread_name(kind: str, short_id: str, name: str) -> str:
    return f"{kind}-{_slugify(short_id)}-{_slugify(name)}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_discord_naming_formats_project_channel_and_thread_names`

Expected: `OK`

- [ ] **Step 5: Run the full test file**

Run: `python -m unittest discover -s tests`

Expected: all existing tests plus the new naming test pass.

### Task 3: Add Discord projection intents

**Files:**
- Create: `C:\Orchestra-Game-Spec\orchestra\discord_projection.py`
- Test: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_discord_projection_builds_category_channel_thread_and_message_intents(self):
        from orchestra.discord_projection import build_discord_projection
        from orchestra.models import ProjectWorkspace, TaskThread, WorkstreamChannel, Workspace

        workspace = Workspace(id="ws_001", name="Studio Alpha", discord_guild_id="guild_123")
        project = ProjectWorkspace(id="proj_001", workspace_id="ws_001", name="Orchestra Mobile", slug="orchestra-mobile")
        channel = WorkstreamChannel(id="chan_001", project_id="proj_001", kind="feature", name="Discord OAuth", slug="discord-oauth")
        thread = TaskThread(id="thread_001", channel_id="chan_001", kind="task", name="OAuth Install Flow", slug="oauth-install-flow")

        projection = build_discord_projection(
            workspace=workspace,
            project=project,
            channel=channel,
            thread=thread,
            message_title="Run board",
            message_body="Draft complete",
        )

        self.assertEqual(projection["guild_id"], "guild_123")
        self.assertEqual(projection["category"]["name"], "proj-orchestra-mobile")
        self.assertEqual(projection["channel"]["name"], "feat-discord-oauth")
        self.assertEqual(projection["thread"]["name"], "task-thread-001-oauth-install-flow")
        self.assertIn("Draft complete", projection["message"]["content"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_discord_projection_builds_category_channel_thread_and_message_intents`

Expected: FAIL with `ModuleNotFoundError` because the projection module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from .discord_naming import (
    format_channel_name,
    format_project_category_name,
    format_thread_name,
)
from .models import ProjectWorkspace, TaskThread, WorkstreamChannel, Workspace


def build_discord_projection(
    *,
    workspace: Workspace,
    project: ProjectWorkspace,
    channel: WorkstreamChannel,
    thread: TaskThread,
    message_title: str,
    message_body: str,
) -> dict[str, object]:
    return {
        "guild_id": workspace.discord_guild_id,
        "category": {
            "name": format_project_category_name(project.name),
            "project_id": project.id,
        },
        "channel": {
            "name": format_channel_name(channel.kind, channel.name),
            "channel_id": channel.id,
        },
        "thread": {
            "name": format_thread_name(thread.kind, thread.id, thread.name),
            "thread_id": thread.id,
        },
        "message": {
            "title": message_title,
            "content": f"**{message_title}**\n\n{message_body}",
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_discord_projection_builds_category_channel_thread_and_message_intents`

Expected: `OK`

- [ ] **Step 5: Re-run related tests**

Run: `python -m unittest discover -s tests`

Expected: all tests pass and no regressions in the existing workflow tests.

### Task 4: Emit Discord projection data from the workflow

**Files:**
- Modify: `C:\Orchestra-Game-Spec\orchestra\workflow.py`
- Modify: `C:\Orchestra-Game-Spec\orchestra\models.py`
- Test: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_mock_collaboration_includes_discord_projection_in_schema(self):
        with self.temporary_directory() as temp_dir:
            run_collaboration(
                "짧은 퍼즐 게임",
                env={"AGENT_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )

            schema = json.loads((Path(temp_dir) / "game_schema.json").read_text(encoding="utf-8"))
            projection = schema["discord_projection"]
            self.assertEqual(projection["category"]["name"], "proj-sample-project")
            self.assertEqual(projection["channel"]["name"], "feat-design-run")
            self.assertTrue(projection["thread"]["name"].startswith("task-task-001-"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_mock_collaboration_includes_discord_projection_in_schema`

Expected: FAIL with `KeyError: 'discord_projection'`.

- [ ] **Step 3: Write minimal implementation**

```python
from .discord_projection import build_discord_projection
from .models import ProjectWorkspace, TaskThread, Workspace, WorkstreamChannel


workspace = Workspace(id="ws_default", name="Default Workspace", discord_guild_id="guild_mock")
project = ProjectWorkspace(
    id="proj_default",
    workspace_id=workspace.id,
    name="Sample Project",
    slug="sample-project",
)
channel = WorkstreamChannel(
    id="channel_design_run",
    project_id=project.id,
    kind="feature",
    name="Design Run",
    slug="design-run",
)
thread = TaskThread(
    id="task_001",
    channel_id=channel.id,
    kind="task",
    name=idea,
    slug="design-run-task",
)
discord_projection = build_discord_projection(
    workspace=workspace,
    project=project,
    channel=channel,
    thread=thread,
    message_title="Run board",
    message_body="Projection scaffold ready",
)
```

Also add the projection payload into `_build_schema(...)`:

```python
    "discord_projection": discord_projection,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_mock_collaboration_includes_discord_projection_in_schema`

Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

### Task 5: Surface the projection in the UI and artifacts summary

**Files:**
- Modify: `C:\Orchestra-Game-Spec\orchestra\cli.py`
- Modify: `C:\Orchestra-Game-Spec\orchestra\discord_bot.py`
- Modify: `C:\Orchestra-Game-Spec\tests\test_orchestra_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_schema_artifact_lists_discord_projection(self):
        with self.temporary_directory() as temp_dir:
            run_collaboration(
                "짧은 퍼즐 게임",
                env={"AGENT_MODE": "mock"},
                artifact_dir=Path(temp_dir),
            )

            schema = json.loads((Path(temp_dir) / "game_schema.json").read_text(encoding="utf-8"))
            self.assertIn("discord_projection", schema)
```

- [ ] **Step 2: Run test to verify it fails if Task 4 is not implemented**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_schema_artifact_lists_discord_projection`

Expected: FAIL before Task 4, PASS after Task 4.

- [ ] **Step 3: Update the UI summary**

Update the CLI and Discord completion summaries so they include:

- final spec path
- schema path
- progress path
- message log path
- Discord projection or sync artifact path when present

- [ ] **Step 4: Run the focused and full tests**

Run: `python -m unittest tests.test_orchestra_core.OrchestraCoreTests.test_schema_artifact_lists_discord_projection`

Expected: `OK`

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

- [ ] **Step 5: Manual smoke check**

Run: `$env:AGENT_MODE="mock"; python -m orchestra.cli`

Expected: the final artifact summary mentions the Discord projection embedded in `game_schema.json`.

## Self-Review

Spec coverage check:

- Discord SaaS structure is covered by Task 1 model additions.
- Category, channel, and thread naming is covered by Task 2.
- Projection behavior is covered by Task 3 and Task 4.
- CLI and Discord artifact summaries are covered by Task 5.

Placeholder scan:

- No `TBD`, `TODO`, or vague "handle appropriately" language remains in task steps.

Type consistency:

- `Workspace`, `ProjectWorkspace`, `WorkstreamChannel`, and `TaskThread` names are used consistently across tasks.
- Projection payload keys remain `category`, `channel`, `thread`, and `message` across all tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-02-discord-saas-workspace.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
