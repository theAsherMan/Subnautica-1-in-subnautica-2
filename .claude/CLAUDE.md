# Additional project rules

## Research notes: no images
Never add images to the `research/` notes: no markdown image links, no copied screenshot files, no `<img>`.
When the tester sends a screenshot, describe in text what it shows (objects visible, map/location, HUD values, anything unexpected),
with the usual status word and date (e.g. **VERIFIED (2026-11-18, tester screenshot)**). Include this rule in briefs for any agent that edits `research/`.

## Delegation and agent roles
|   agent   |   role    |
|---|---|
|   Opus  | is used directly by the user as the main agent.  agent is to do planning work, not implementation or testing.  this work should be delegated|
| Sonnet    |   is used for implementation and testing.  this agent should preform investigative work into why its tests fail, but leave deep break downs to its caller |

Whenever something needs implementing, delegate it to the `implementer` agent (`.claude/agents/implementer.md`, model: sonnet) via the Agent tool with `subagent_type: "implementer"`. The brief must be a concrete plan: goal, files to touch, steps, acceptance criteria, and the no-images rule if it edits `research/`. The agent implements, tests, debugs, and reports back.
