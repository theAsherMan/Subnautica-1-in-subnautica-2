#!/usr/bin/env bash
# Stream the interesting lines of UE4SS.log. Use as the Monitor tool's command (timeout_ms 1800000, re-arm on expiry).
# Usage: bash src/tools/watch_log.sh [extra-regex]   (game path from local.config)
# Default filter: our mods' key actions, results, failures, load banners, Lua errors, crashes.
# Avoid matching per-sweep noise ("region dressing", "after GC") unless you are debugging the clearing loop.
. "$(dirname "$0")/sn2_env.sh"
LOG="$SN2_UE4SS_DIR/UE4SS.log"
EXTRA="${1:-}"
PAT='\[(SN2WorldProbe|SN2IntroProbe)\] (loaded|F[0-9]+|Shift|Ctrl|placed|SUCCESS|generated seafloor|REMOVED|RESTORED|wrote|.*failed)|\[Lua\] .*(rror|xception)|Crash'
[ -n "$EXTRA" ] && PAT="$PAT|$EXTRA"
tail -n 0 -F "$LOG" 2>/dev/null | grep -E --line-buffered "$PAT"
