#!/usr/bin/env bash
# Run a plan up to 3 times; retry after a CRASH only. FAIL_MENU is retried once ONLY with --retry-menu (opt-in, off by default). Any other FAIL is not retried (no waits or delays are added, see research/process/autotest.md "Automated test runs").
# autotest.sh reclassifies a run as CRASH when a new dump appeared or the game log has a fatal marker, so a crash during a map load is retried as a CRASH.
# Usage: bash src/tools/autotest_retry.sh <plan-name> --timeout <s> [--check <s>] [--retry-menu] [--visible] [--input os|engine] [--timeout-reason ..] [--after-fix ..]  (options are forwarded to autotest.sh; --timeout is per attempt)
# (old usage text follows) bash src/tools/autotest_retry.sh <plan-name>      Prints "RETRY_SUMMARY plan attempts=<n> crashes=<c> final=<result>" at the end.
DIR="$(dirname "$0")"
ARGS_IN=(); PASS=(); RETRY_MENU=0
while [ $# -gt 0 ]; do
  case "$1" in
    --input) export SN2_INPUT="$2"; shift 2;;
    --retry-menu) RETRY_MENU=1; shift;;
    --visible|--hidden|--keep-world) PASS+=("$1"); shift;;
    --timeout|--check|--timeout-reason|--after-fix) PASS+=("$1" "$2"); shift 2;;
    *) ARGS_IN+=("$1"); shift;;
  esac
done
set -- "${ARGS_IN[@]}"
PLAN="${1:?plan name}"   # input mode: --input os|engine (default engine; or env SN2_INPUT), forwarded to autotest.sh
. "$DIR/sn2_env.sh"
# refusals (--timeout missing, no Steam, timeout raise/two-timeouts rules) BEFORE the lock is taken: autotest.sh --precheck-only
bash "$DIR/autotest.sh" "${PASS[@]}" "$PLAN" --precheck-only || exit $?
# RAM: hold the heavy lock (src/tools/heavy_lock.sh) for the whole run; waits up to SN2_LOCK_WAIT s (default 3600). Released at exit only if taken here.
HL="$SN2_REPO/src/tools/heavy_lock.sh"
if ! bash "$HL" check; then
  bash "$HL" acquire game --wait "${SN2_LOCK_WAIT:-3600}" --note "autotest_retry $PLAN" || { echo "heavy lock not acquired - abort"; exit 2; }
  trap 'bash "$HL" release >/dev/null' EXIT
fi
ATT=0; CR=0; MF=0; RES=""
while [ $ATT -lt 3 ]; do
  ATT=$((ATT + 1))
  bash "$DIR/autotest.sh" "${PASS[@]}" "$PLAN"; RC=$?
  . "$DIR/sn2_env.sh"
  LAST=$(ls -d "$SN2_WORKSPACE/autotest/"*_"$PLAN" | tail -1)
  RES=$(cat "$LAST/result.txt"); echo "attempt $ATT: $RES ($LAST)"
  if [ "$RES" = CRASH ]; then CR=$((CR + 1))
  elif [ "$RES" = FAIL_MENU ] && [ "$RETRY_MENU" = 1 ] && [ $MF -lt 1 ]; then MF=$((MF + 1)); echo "FAIL_MENU: harness navigation failure, retrying once (stall artefacts: $LAST/windows_menu.txt, $LAST/shots/stall_menu.png)"
  elif [ "$RES" = FAIL_LUA_LOAD ]; then echo "FAIL_LUA_LOAD: Lua syntax error in an SN2* mod, not retryable (see $LAST/driver.log)"; break
  else break; fi
done
echo "RETRY_SUMMARY plan=$PLAN attempts=$ATT crashes=$CR menu_fail_retries=$MF final=$RES"
[ "$RES" = DONE ]
