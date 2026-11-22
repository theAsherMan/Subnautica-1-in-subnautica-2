#!/usr/bin/env bash
# Ask a running autotest to stop: clean quit first (main_quit through the command channel, WM_CLOSE fallback), then the FORCED_KILL fallback after 20 s,
# verdict STOPPED. Works for hidden runs. Touches only that run's game process and its hidden-desktop holder.
# Usage: bash src/tools/autotest_stop.sh [--run <dir>|latest] [--reason "<text>"]
# Mechanism: writes <run>/stop_request.txt; the run's own autotest.sh loop (polls every 5 s) does the stop and the normal collection. If the run's
# result.txt does not appear within 60 s (autotest.sh itself died) this script does the stop itself with the same helper.
. "$(dirname "$0")/sn2_env.sh"
. "$(dirname "$0")/autotest_lib.sh"
RUNARG=latest; WHY="requested"
while [ $# -gt 0 ]; do
  case "$1" in --run) RUNARG="$2"; shift 2;; --reason) WHY="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac
done
[ "$RUNARG" = latest ] && RUNARG="$(latest_run)"
[ -n "$RUNARG" ] && [ -d "$RUNARG" ] || { echo "no run folder ($RUNARG)"; exit 2; }
OUT="$RUNARG"
[ -f "$OUT/result.txt" ] && { echo "run already finished: $(cat "$OUT/result.txt")"; exit 0; }
echo "$WHY ($(date '+%H:%M:%S'))" > "$OUT/stop_request.txt"
echo "stop requested for $OUT"
for i in $(seq 1 30); do [ -f "$OUT/result.txt" ] && break; sleep 2; done
if [ -f "$OUT/result.txt" ]; then echo "run ended: $(cat "$OUT/result.txt")"; exit 0; fi
echo "autotest.sh did not finish the run within 60 s: stopping the game directly"
stop_game "$OUT" "STOPPED by autotest_stop.sh directly ($WHY)"
echo "STOPPED" > "$OUT/result.txt"
echo "RUN DONE STOPPED" >> "$(dirname "$OUT")/hidden_desktop_status.txt"
exit 0
