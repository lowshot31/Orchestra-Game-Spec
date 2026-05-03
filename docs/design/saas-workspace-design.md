# Discord SaaS Workspace Design

## Goal

Turn Orchestra from a local run console into a Discord-native SaaS workflow where each customer connects their own Discord server, then manages projects, features, sprints, and task execution inside that server.

## Product Direction

Orchestra should treat Discord as the team's collaboration surface, not as the source of truth. The application database remains canonical for identities, workspace settings, projects, work items, run state, and audit history. Discord mirrors that structure into categories, channels, and threads so teams can work where they already communicate.

The product model for v1 is:

- One Orchestra workspace can connect one Discord server.
- One Discord category represents one Orchestra project.
- One Discord text channel represents one feature stream or sprint stream inside a project.
- One Discord thread represents one task, execution run, or focused work conversation.

This preserves stable project information at the category level, keeps active coordination in channels, and isolates task execution in threads without creating excessive top-level channel clutter.

## Information Architecture

The hierarchy for the first Discord-native version is:

`Workspace -> Discord server -> Project category -> Feature or sprint channel -> Task or run thread`

Recommended examples:

- Category: `proj-orchestra-mobile`
- Channel: `feat-discord-oauth`
- Channel: `sprint-07`
- Thread: `task-142-oauth-install-flow`
- Thread: `run-2026-05-02-spec-sync`

Categories should hold the long-lived project structure. Channels should represent active lanes of work that several tasks can belong to over time. Threads should be disposable execution containers that can be archived once the task or run is complete.

## Identity And Permissions

There are two separate integration steps and they must stay separate:

1. User account connection identifies which Orchestra user is acting.
2. Discord bot installation authorizes Orchestra to create categories, channels, and threads inside a specific server.

The app should never require a user to manually create every channel before work can begin. Instead, a workspace admin connects Discord through OAuth, selects a server during bot installation, and configures one default location rule for project creation.

Required v1 permissions:

- Read basic guild metadata
- Create and edit categories
- Create and edit text channels
- Create and archive threads
- Post and edit messages
- Read message history for synchronization checks

The app should not require broad moderation permissions beyond what is necessary for the above.

## Workspace Setup Flow

The recommended v1 setup flow is:

1. Workspace admin signs into Orchestra.
2. Admin chooses `Connect Discord`.
3. Discord OAuth identifies the user and installs the bot into a selected server.
4. Orchestra stores the connected guild id, guild name, installer user id, and token metadata needed for refresh or verification.
5. Orchestra shows a setup screen where the admin confirms naming rules and default behavior for project creation.
6. The first Orchestra project creation automatically creates the matching Discord category.

The app should validate permissions immediately after installation and surface actionable errors such as missing `Manage Channels` or thread creation capability.

## Data Model

The minimum internal entities for the Discord SaaS slice are:

- `Workspace`: Orchestra tenant with one connected Discord server for v1
- `DiscordInstallation`: guild-level connection metadata and permission state
- `ProjectWorkspace`: maps an Orchestra project to a Discord category
- `WorkstreamChannel`: maps a feature or sprint to a Discord text channel
- `TaskThread`: maps a task or execution run to a Discord thread

Suggested relationships:

- One `Workspace` has one `DiscordInstallation` in v1.
- One `ProjectWorkspace` belongs to one `Workspace`.
- One `ProjectWorkspace` has many `WorkstreamChannel` records.
- One `WorkstreamChannel` has many `TaskThread` records.

Each mapping record should keep both the Orchestra id and the Discord id so the system can recreate links, repair drift, or re-sync names later.

## Naming Rules

Names should be deterministic, lowercase, and collision-resistant.

Recommended v1 rules:

- Category: `proj-{project-slug}`
- Feature channel: `feat-{feature-slug}`
- Sprint channel: `sprint-{number}`
- Task thread: `task-{short-id}-{task-slug}`
- Run thread: `run-{date}-{run-slug}`

The formatter should also keep a human title alongside the Discord-safe slug. Discord-safe names should strip unsupported punctuation, compress whitespace to hyphens, and cap length defensively before sending API calls.

## Runtime Behavior

Core behaviors for the first release:

1. Creating an Orchestra project creates a Discord category if one does not already exist.
2. Creating a feature or sprint creates or reuses a text channel under that category.
3. Creating a task or run creates a thread under the selected channel.
4. Orchestra posts status updates, summaries, and links into the thread as the task progresses.
5. Completing a task archives the thread.
6. Completing a feature or sprint can optionally lock or move the channel later, but that should not block v1.

The current CLI flow can continue to execute runs while Discord receives projected updates through an adapter. This keeps the orchestration engine stable while the collaboration surface expands.

## Source Of Truth And Sync Rules

The app database is the source of truth for all objects and states.

Discord is a projected collaboration interface. That means:

- Renaming in the app should update Discord.
- Discord posting failures should not destroy the app record.
- If a Discord resource is deleted manually, Orchestra should mark the mapping as drifted and offer repair.
- Thread archival state should be mirrored back into the app only when it maps to a known task completion rule.

This avoids making Discord message state the only place where work can exist.

## Failure Handling

Expected failure cases:

- Bot installed without sufficient permissions
- User connects account but does not complete bot installation
- Category name already exists with a conflicting mapping
- Channel or thread deleted manually in Discord
- Thread auto-archived while the app still considers task execution active

Required v1 handling:

- Fail setup early with a clear permission report
- Treat Discord ids as optional until installation completes
- Store sync status on every mapped entity
- Offer re-create or re-link actions from the Orchestra side

## Rollout Plan

The safest implementation sequence is:

1. Add internal workspace and Discord mapping models
2. Add naming and validation utilities
3. Add a Discord adapter that formats the intended category, channel, and thread actions
4. Reuse existing execution plan and progress board output for Discord message payloads
5. Keep CLI as the local run initiator until Discord projection is proven reliable

## Out Of Scope For V1

- Multiple Discord servers per workspace
- Full bidirectional task editing from Discord messages
- Generic arbitrary channel mapping rules
- Voice channel automation
- Fine-grained role provisioning and ACL policy builders
- Billing plan logic for multi-server enterprise setups

## Decision Summary

The chosen structure is:

- SaaS product model
- Customer connects their own Discord server
- Categories represent projects
- Channels represent features or sprints
- Threads represent tasks or execution runs
- Orchestra database remains the source of truth
- Discord bot performs creation, projection, and archival actions
