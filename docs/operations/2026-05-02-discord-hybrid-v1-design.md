# Discord Hybrid V1 Design - 2026-05-02

## Goal

Make Orchestra legible as a Discord-native AI collaboration tool before implementing risky account linking or live bot provisioning.

## Scope

Included in v1:

- channel plus thread information architecture
- slash-command style contract for runs, agents, and skill overrides
- mock Discord transport that records payloads
- bot transport seam for later live Discord wiring
- optional workflow export to `discord_sync.json`

Excluded in v1:

- OAuth and account mapping
- automatic server or channel creation
- credential storage for third-party APIs
- live slash command registration
- full bidirectional Discord bot behavior

## Information Architecture

- Studio or team: one Discord server
- Project: one category, formatted as `project-<name>`
- Feature coordination: `feature-<name>` channel
- Sprint coordination: `sprint-<number>` or `sprint-<name>` channel
- Task execution: `task-<name>` thread
- Individual run trace: `run-<name>` thread

## Command Contract

Primary command groups:

- `/orchestra run create`
- `/orchestra run review`
- `/orchestra handoff`
- `/orchestra agent add`
- `/orchestra agent list`
- `/orchestra skill override`

The contract is intentionally text-parsed first so the same structure can later back Discord slash commands, web UI actions, or scripted demos.

## Delivery Model

At run completion, Orchestra exports:

- feature-level run overview
- sprint-level progress board
- task-level handoff note
- run-thread message stream containing agent outputs

This keeps the local CLI as the control surface while proving the Discord collaboration story with concrete artifacts.

## API and Extensibility Position

Discord must be able to represent:

- new agents being added
- role rules or skills being overridden
- future tool and API integrations

V1 therefore adds interface seams instead of shipping full integrations:

- `BotDiscordTransport` for future live Discord posting
- `MockApiConnector` and connector abstraction for future external API actions

This makes the submission honest: the demo is mock-first, but the architecture already anticipates real operations work.
