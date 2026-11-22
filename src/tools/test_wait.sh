#!/usr/bin/env bash
# Wait for an autotest run to end OR for a check period to elapse, then print a SHORT status (never extends the timeout, never stops anything).
# Usage: bash src/tools/test_wait.sh [--run <dir>|latest] [--for <s>]     --for defaults to the run's check period (run_info.txt check_s), else 60.
# Run it with run_in_background or Monitor to be woken. Exit 0 = run finished, 1 = still running, 2 = no such run.
. "$(dirname "$0")/sn2_env.sh"
. "$(dirname "$0")/autotest_lib.sh"
RUNARG=latest; FOR=""
while [ $# -gt 0 ]; do
  case "$1" in --run) RUNARG="$2"; shift 2;; --for) FOR="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac
done
[ "$RUNARG" = latest ] && RUNARG="$(latest_run)"
[ -n "$RUNARG" ] && [ -d "$RUNARG" ] || { echo "no run folder ($RUNARG)"; exit 2; }
OUT="$RUNARG"
info() { grep "^$1=" "$OUT/run_info.txt" 2>/dev/null | head -1 | cut -d= -f2-; }
CHECK="$(info check_s)"; TO="$(info timeout_s)"; START="$(info start_epoch)"
[ -z "$FOR" ] && FOR="${CHECK:-60}"
T_END=$(( $(date +%s) + FOR ))
while [ ! -f "$OUT/result.txt" ] && [ "$(date +%s)" -lt "$T_END" ]; do sleep 2; done
if [ -f "$OUT/result.txt" ]; then V="$(cat "$OUT/result.txt")"; else V=running; fi
if [ -n "$START" ]; then EL=$(( $(date +%s) - START )); else EL="?"; fi
[ -f "$OUT/result.txt" ] && { RT="$(grep -m1 '^run time:' "$OUT/summary.txt" 2>/dev/null | sed 's/run time: //; s/ s$//')"; [ -n "$RT" ] && EL="$RT"; }
echo "run: $OUT"
echo "verdict: $V   elapsed: ${EL}s of timeout ${TO:-unknown}s   check period: ${CHECK:-none}"
echo "phase: $(cur_phase "$OUT")"
echo "shots: $(ls "$OUT/shots"/*.png 2>/dev/null | wc -l)   newest: $(ls -t "$OUT/shots"/*.png 2>/dev/null | head -1 | xargs -r basename)"
echo "-- driver.log (last 8) --"
tail -8 "$OUT/driver.log" 2>/dev/null | cut -c1-200
[ "$V" = running ] && exit 1
exit 0
