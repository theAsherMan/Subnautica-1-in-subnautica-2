#!/usr/bin/env bash
# Bug-report collector for the F1 key (SN2BugShot). Run under the Monitor tool (persistent / long timeout): one stdout line per event.
# Usage: bash src/tools/bugshot_watch.sh [--once]      (paths from local.config)
# Lines: WATCHING ..., GAME started/exited, BUGSHOT <id> [late] map= ue= sn1= depth= hit= shot= dir=
# Read-only toward the game (no input, no kill, no saves); removes only its own report json files from the Mods folder.
. "$(dirname "$0")/sn2_env.sh"
exec python -u "$(dirname "$0")/bugshot_watch.py" "$@"
