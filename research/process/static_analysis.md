# Static analysis (investigator conversations)

Pass-1 text: `git show 3449200:research/process/static_analysis.md`.

## Static analysis (built 2026-11-28; investigator only)
A conversation between the investigator and the `static-analyst` agent (`.claude/agents/static-analyst.md`: Opus `claude-opus-5-5`, effort xhigh,
tools Read/Grep/Glob/Bash only) about the installed SN1/SN2 game code. Information, not evidence: its claims stay UNTESTED until a test confirms them.
Not a heavy job, never takes the heavy lock. When to use it and how to talk to it: `.claude/agents/investigator.md` "Static analysis".
- Commands (`src/tools/static_analysis.sh` → `static_analysis.py`): `new --game sn1|sn2|both [--slug S]` (prints `<conv>`), `send <conv> --message-file F`
  (always `run_in_background`; blocks while turns run), `watch <conv> [--from N]` (for Monitor; prints each message, `IDLE` at turn end, `STALLED` after
  20 min without output), `cancel <conv>` (taskkill of that turn's `claude.exe` tree), `end <conv>`, `status <conv>`.
- How it works: each turn is one headless `claude -p --agent static-analyst --model claude-opus-5-5 --effort xhigh --output-format stream-json --verbose
  --allowedTools Read Grep Glob Bash --disallowedTools Edit Write NotebookEdit Agent Task WebFetch WebSearch --add-dir <GameDir> <SN1Dir> <ModkitDir>
  <Workspace> --settings <conv>/hook_settings.json [--resume <session_id>]`, prompt on stdin, cwd = repo, env `SN2_SA_CONV=<conv>`, `CLAUDECODE` removed.
  The CLI is found via `CLAUDE_BIN` (local.config / env), then PATH, then the newest `~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe`
  (not on PATH on this machine). Overrides for tests: `SN2_SA_MODEL`, `SN2_SA_EFFORT` (empty = omit the flag).
- Messages: the analyst tags each text block `PARTIAL` (mid-run, keeps working), `QUESTION` or `ANSWER` (end the turn). Each text block of the stream
  becomes `<conv>/updates/NN_<TAG>.md` + a line in `updates.log` as it arrives.
- Mid-run messages: `send` while a turn runs drops the message into `<conv>/inbox/`; the PostToolUse hook (`src/tools/static_analysis_hook.py post`)
  delivers it as `additionalContext` after the next tool call and moves it to `inbox/delivered/`. `send` while idle claims `running.json` (atomic
  create; stale = dead runner pid) and runs turns until the inbox is empty, so a message that arrives after the analyst's last tool call starts the next
  turn on its own.
- Guard: the PreToolUse hook (`pre`, Bash only) logs every command to `<conv>/commands.log` and refuses any command that has a write operation
  (redirect, tee, cp, mv, rm, mkdir, touch, sed -i, Python file writes, PowerShell item cmdlets, retoc/uaa/lvl/repak) with `sn1_decompiled` after it,
  or any write after a `cd` into it; a plain `ilspycmd ... -o <Workspace>/sn1_decompiled/<Type>` is allowed. Known false positive: a WORKDIR file whose
  name contains `sn1_decompiled`. Each turn also compares `git status --porcelain` before/after and logs `WARNING repo changed during turn` (another
  session can trigger it; check `commands.log`).
- Folder `<Workspace>/static_analysis/<stamp>_<slug>/`: `meta.json` (session id, turns with end tag / seconds / cost, total cost), `running.json` (while a
  turn runs: runner pid, claude pid), `inbox/`, `updates/`, `updates.log`, `turns/turn_NN_in.md` + `.stream.jsonl` + `.stderr.txt`, `commands.log`,
  `work/` (the analyst's WORKDIR, the only place it may write besides ilspycmd output).
- Smoke test **VERIFIED (2026-11-28)** on `claude-haiku-5-5`, conversation `<Workspace>/static_analysis/20261128_141939_smoketest` (5 turns, $0.027):
  a PARTIAL arrived mid-run and the turn went on; a mid-run `send` was delivered after the next tool call and answered in a PARTIAL; `--resume` kept
  context (turn 2 recalled a number from turn 1); `cancel` killed a turn 2 s after its PARTIAL and the next `send` resumed the session; a message queued
  during a tool-less turn started the next turn by itself; the hook refused a write live (`PreToolUse:Bash hook error: Refused: ...`). Settings check
  on Opus ($0.11): init event shows model `claude-opus-5-5`, tools `[Read, Grep, Glob, Bash]`, `per_turn_effort_active: true` (the effort value is not
  echoed). The analyst refused, even when told it was authorized, to attempt a write into `sn1_decompiled` to test the hook: the prompt rule holds.
- A cancelled turn has no cost in `meta.json` (the CLI's `result` event never arrives).
