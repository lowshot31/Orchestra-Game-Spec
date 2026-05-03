# Discord Hybrid V1 Implementation Plan - 2026-05-02

Goal: prove a Discord-first collaboration direction by exporting Orchestra runs into channel and thread shaped payloads without depending on live account linking.

## Tasks

1. Define Discord command parsing
- Parse `/orchestra` commands into `group`, `action`, and `key=value` arguments.
- Cover run creation, agent management, and skill override commands with tests.

2. Define workspace naming and structure
- Build a project workspace model from environment variables.
- Normalize names into Discord-safe category, channel, and thread identifiers.

3. Add transport seams
- Implement `MockDiscordTransport` for artifact generation.
- Add `BotDiscordTransport` as a future live seam that fails clearly without a token.

4. Export workflow results
- Convert final workflow artifacts into Discord-shaped deliveries.
- Persist the result to `discord_sync.json`.
- Wire optional export into the existing workflow using environment variables.

5. Update submission docs
- Document Discord mock demo setup.
- Publish the command contract in README and ops docs.

## Verification

- Run the Python unittest suite.
- Confirm Discord-specific tests cover command parsing, workspace naming, mock export, and bot seam behavior.
