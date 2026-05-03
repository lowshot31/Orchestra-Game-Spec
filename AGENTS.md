# AGENTS.md

Karpathy-inspired working guidelines for coding agents in this repository.

Source: adapted from `forrestchang/andrej-karpathy-skills` for Codex-style agent workflows.

## 1. Think Before Coding

Do not assume. Do not hide confusion. Surface tradeoffs.

- State assumptions explicitly when they matter.
- If multiple interpretations are plausible, do not silently pick one.
- If a simpler path exists, say so.
- If something is genuinely unclear or risky, pause and ask instead of guessing.

## 2. Simplicity First

Write the minimum code that solves the requested problem.

- Do not add features that were not requested.
- Do not introduce abstractions for single-use code.
- Do not add configurability or flexibility without a real need.
- Do not add defensive handling for impossible scenarios.
- If a solution feels bloated, simplify it.

Rule of thumb: if a strong senior engineer would call it overengineered, it probably is.

## 3. Surgical Changes

Touch only what the request requires.

- Do not refactor adjacent code unless it is necessary for the task.
- Do not rewrite comments, formatting, or structure just because you prefer a different style.
- Match existing local patterns unless there is a good reason not to.
- If you notice unrelated problems, mention them separately instead of folding them into the same change.

Clean up only the mess your change creates:

- Remove imports, variables, or functions that become unused because of your edit.
- Leave pre-existing dead code alone unless the user asks for cleanup.

Every changed line should trace back to the user request.

## 4. Goal-Driven Execution

Define success criteria and verify them.

- Turn bug fixes into reproductions plus verification.
- Turn feature work into concrete checks, tests, or observable outcomes.
- For multi-step work, keep a short plan and verify each step.

Example:

1. Reproduce or define the target behavior.
2. Make the smallest change that satisfies it.
3. Run the relevant verification.

Strong success criteria are better than vague instructions like "make it work."

## 5. Codex Notes

- Respect existing user changes. Do not revert unrelated work.
- Prefer minimal diffs over broad rewrites.
- Verify before claiming completion whenever practical.
- For trivial edits, use judgment and avoid unnecessary ceremony.
