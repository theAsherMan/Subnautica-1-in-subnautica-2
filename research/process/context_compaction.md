# Context compaction of the main agent (Claude Code mod)

Pass-1 text: `git show 3449200:research/process/context_compaction.md`.

## Context compaction of the main agent (Claude Code mod, built 2026-11-28)
Mod `context-compactor` in `.claude/mods/context-compactor/` (hooks module `hooks/register.ts`), enabled for this project in `.claude/settings.json`
(`enabledPlugins: context-compactor@sn2-mods`). Main loop only; subagents keep their frontmatter `autoCompactWindow` (implementer 150k, investigator 500k).
- Turn ends normally (not interrupted, not a refusal) with `$.session.usage().context.tokens > 150000` -> `$.session.compact()`.
- Before a main-loop model request (`turn.step`, index > 0) with tokens >= 200000 -> `$.turn.abort` (no interrupt marker), compact, then
  `$.prompt.submit` a "continue the task" prompt. A mod cannot compact mid-turn (`$.session.compact()` rejects while a turn runs), hence the abort.
- `compact()` is retried every 1 s (max 30) until the turn has fully ended. Log lines start `context-compactor:`.
- Thresholds: `MID_TURN_LIMIT` / `END_TURN_LIMIT` at the top of `register.ts`. The engine's own autocompact still applies (per-model `/autocompact`
  = `auto`, the model limit), so the mod's 200k always fires first.
- Status: unit tests PASS 2026-11-28 (`claude plugin test .claude/mods/context-compactor`, 6 tests: turn end >150k / <150k / subagent / interrupted,
  mid-turn 200k abort+compact+continue, subagent mid-turn); `claude plugin validate` passes. Live behaviour in a real session UNTESTED.
- New machine: the marketplace is per user, so run once from the repo root: `claude plugin marketplace add ./.claude/mods`
  (the project setting then enables the mod). The plugin is read in place from the repo folder; edits apply at the next session start.
