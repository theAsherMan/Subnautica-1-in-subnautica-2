#!/usr/bin/env bash
# Automated in-game test run: installs SN2AutoTest (observe-only Lua) + SN2Census, arms a plan, launches the game, runs
# src/tools/autotest_driver.py (simulated OS keyboard/mouse + screen capture), waits for DONE/crash/timeout,
# collects screenshots/logs/census into <Workspace>/autotest/<timestamp>_<plan>/ and builds summary.txt + contact sheets.
# Usage: bash src/tools/autotest.sh <plan-name>      (plans: src/mods/SN2AutoTest/plans/<plan-name>.json, menus.json)
# Run it with run_in_background (a run is several minutes). Nobody may touch the PC; the game window must stay in front.
# Exit code 0 only for result DONE with all shots present.
. "$(dirname "$0")/sn2_env.sh"
# input mode: --input engine|os (or env SN2_INPUT). engine (default) = commands via run/cmd.txt to the SN2AutoTest Lua mod
# + PrintWindow capture of the (windowed) game window; no real input. os (--input os, needs --visible) = SendInput + full-screen grabs.
# DESKTOP: hidden desktop is the DEFAULT (game on its own desktop SN2Test, user input cannot reach it; needs the Steam client running).
#   --visible (or SN2_HIDDEN=0) = old behaviour: game on the user's desktop, launched through Steam.
# REQUIRED: --timeout <s> (whole run, launch to game exit). Optional: --check <s> (check period, recorded for test_wait.sh),
#   --timeout-reason "<why>" (needed to raise a timeout after a TIMEOUT), --after-fix "<what>" (needed after two TIMEOUTs in a row),
#   --keep-world (ONLY when the plan says so: keep the world/save slot the run created; default = the new slot is deleted after the game exited, see cleanup_test_slots in autotest_lib.sh),
#   --precheck-only (run the refusal checks and exit 0; used by autotest_retry.sh). Exit codes: see autotest_lib.sh.
ARGS_IN=(); TIMEOUT=""; CHECK=""; T_REASON=""; AFTER_FIX=""; PRECHECK_ONLY=0; KEEP_WORLD=0
SN2_HIDDEN="${SN2_HIDDEN:-1}"
while [ $# -gt 0 ]; do
  case "$1" in
    --input) SN2_INPUT="$2"; shift 2;;
    --visible) SN2_HIDDEN=0; shift;;
    --hidden) SN2_HIDDEN=1; shift;;
    --timeout) TIMEOUT="$2"; shift 2;;
    --check) CHECK="$2"; shift 2;;
    --timeout-reason) T_REASON="$2"; shift 2;;
    --after-fix) AFTER_FIX="$2"; shift 2;;
    --precheck-only) PRECHECK_ONLY=1; shift;;
    --keep-world) KEEP_WORLD=1; shift;;
    *) ARGS_IN+=("$1"); shift;;
  esac
done
set -- "${ARGS_IN[@]}"
PLAN="${1:?plan name}"
export SN2_INPUT="${SN2_INPUT:-engine}" SN2_HIDDEN
case "$SN2_INPUT" in os|engine) ;; *) echo "bad --input $SN2_INPUT (os|engine)"; exit 2;; esac
[ "$SN2_HIDDEN" = 1 ] && [ "$SN2_INPUT" = os ] && { echo "--input os needs --visible (hidden desktop is engine mode only)"; exit 2; }
PLANFILE="$SN2_REPO/src/mods/SN2AutoTest/plans/$PLAN.json"
[ -f "$PLANFILE" ] || { echo "no plan $PLANFILE"; exit 2; }
. "$SN2_REPO/src/tools/autotest_lib.sh"
# refusals: before the lock, before any install/launch (exit 8 no --timeout, 6 no Steam, 9 raise without reason, 10 two timeouts in a row)
autotest_precheck "$PLAN" "$TIMEOUT" "$T_REASON" "$AFTER_FIX" "$SN2_HIDDEN"
[ "$PRECHECK_ONLY" = 1 ] && { echo "precheck ok plan=$PLAN timeout=$TIMEOUT hidden=$SN2_HIDDEN"; exit 0; }
# RAM: hold the heavy lock (src/tools/heavy_lock.sh) for the whole run; waits up to SN2_LOCK_WAIT s (default 3600). Released at exit only if taken here.
HL="$SN2_REPO/src/tools/heavy_lock.sh"
if ! bash "$HL" check; then
  bash "$HL" acquire game --wait "${SN2_LOCK_WAIT:-3600}" --note "autotest $PLAN" || { echo "heavy lock not acquired - abort"; exit 2; }
  HL_TAKEN=1
fi
# EXIT trap: record the script's own exit status (OUT/exit_code.txt), append the timeouts.tsv row (EVERY run end that got as far as creating a run folder),
# release the lock if taken here; the status is preserved
on_exit() {
  rc=$?
  if [ -n "${OUT:-}" ] && [ -d "$OUT" ]; then
    echo "$rc" > "$OUT/exit_code.txt"
    if [ -z "${ROW_DONE:-}" ]; then
      ROW_DONE=1
      tsv_row "$PLAN" "$TIMEOUT" "${RESULT:-ABORTED_rc$rc}" "$(cur_phase "$OUT")" "$(( $(date +%s) - ${T0:-$(date +%s)} ))" "$OUT" "${STOP_WHY:-}${T_REASON:+ timeout-reason: $T_REASON}${AFTER_FIX:+ after-fix: $AFTER_FIX}"
    fi
  fi
  # test-world cleanup also on aborted paths (idempotent; skips when the game still runs)
  [ -n "${OUT:-}" ] && [ -d "$OUT" ] && cleanup_test_slots "$OUT" "$KEEP_WORLD"
  [ -n "${HL_TAKEN:-}" ] && bash "$HL" release >/dev/null 2>&1
  exit $rc
}
trap on_exit EXIT
if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then echo "game is running - abort"; exit 2; fi

TOOLS="$SN2_REPO/src/tools"
MODDIR="$SN2_UE4SS_DIR/Mods/SN2AutoTest"
RUN="$MODDIR/run"
UE4LOG="$SN2_UE4SS_DIR/UE4SS.log"
LOCAL="${LOCALAPPDATA:-$HOME/AppData/Local}/Subnautica2/Saved"
GAMELOG="$LOCAL/Logs/Subnautica2.log"
CRASHDIR="$LOCAL/Crashes"
TS=$(date +%Y%m%d_%H%M%S)
OUT="$SN2_WORKSPACE/autotest/${TS}_$PLAN"
mkdir -p "$OUT/shots" "$OUT/census" "$OUT/crash"
T0=$(date +%s)   # the timeout covers the whole run: from here (before install/launch) to game exit
{ echo "plan=$PLAN"; echo "timeout_s=$TIMEOUT"; echo "check_s=${CHECK:-}"; echo "hidden=$SN2_HIDDEN"; echo "start_epoch=$T0"; echo "timeout_reason=$T_REASON"; echo "after_fix=$AFTER_FIX"; } > "$OUT/run_info.txt"
[ "$SN2_HIDDEN" = 1 ] && : > "$OUT/hidden.flag"
record_slots_pre "$OUT" "$T0"   # slot names + mtimes + run start, for the end-of-run test-world cleanup

if [ "$SN2_INPUT" = engine ]; then METHOD=engine-printwindow; else METHOD=driver-grab; fi
EXPECTED=$(python -c "import json,sys;print(sum(len([t for t in w.get('steps',[]) if 'shot' in t]) if w.get('views')=='script' else 10 if w.get('views')=='abs8ud' else (1 if w.get('views')=='fixed' else (2 if w.get('views') in ('one','down45','vanish') else 8)) for w in json.load(open(sys.argv[1]))['waypoints']))" "$(cygpath -w "$PLANFILE")")
START=$(python -c "import json,sys;print(json.load(open(sys.argv[1])).get('start','new'))" "$(cygpath -w "$PLANFILE")")
echo "plan=$PLAN input=$SN2_INPUT method=$METHOD expected=$EXPECTED out=$OUT"

bash "$TOOLS/backup_saves.sh" || echo "WARNING: backup failed"
bash "$TOOLS/install_mod.sh" SN2AutoTest
bash "$TOOLS/install_mod.sh" SN2Census
# extra mods a plan needs: optional top-level "mods": ["SN2BugShot", ...] in the plan json
for M in $(python -c "import json,sys;print(' '.join(json.load(open(sys.argv[1])).get('mods',[])))" "$(cygpath -w "$PLANFILE")" | tr -d '\r'); do bash "$TOOLS/install_mod.sh" "$M" || exit $?; done
rm -rf "$RUN"; mkdir -p "$RUN"
python "$TOOLS/autotest_driver.py" arm "$(cygpath -w "$PLANFILE")" "$(cygpath -w "$RUN")" || { echo "arm failed"; exit 2; }
rm -f "$UE4LOG" 2>/dev/null

# watchdog marks of the game (research/01 "Start-up hang"): record presence + mtime before launch
{
  for f in running.dat beforelobby.dat; do
    if [ -f "$LOCAL/$f" ]; then echo "$f: present, modified $(date -r "$LOCAL/$f" '+%Y-%m-%d %H:%M:%S')"; else echo "$f: absent"; fi
  done
} > "$OUT/marks_before.txt"
cat "$OUT/marks_before.txt"
# stop only the python driver process (never match by bare command line text: that also hit powershell itself and any wrapper shell whose command line mentions the script)
kill_driver() {
  powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'autotest_driver\.py run' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
  return 0
}
# kill the game only through this helper so a forced kill (which leaves the marks behind = dialog on the next launch) is recorded
force_kill() {
  if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then
    echo "FORCED_KILL $1" >> "$OUT/forced_kill.txt"
    # research/01 rule 2026-11-19: explain the stall before killing (full-desktop screenshot without focusing the game + all game windows)
    python "$TOOLS/autotest_driver.py" windows forced_kill "$(cygpath -w "$OUT")" >> "$OUT/forced_kill_windows.log" 2>&1
    taskkill //IM Subnautica2-Win64-Shipping.exe //F >/dev/null 2>&1
  fi
}
MARK="$OUT/.launchmark"; : > "$MARK"
machine_snap() {   # machine snapshot into $OUT/machine.txt (research/01): RAM, top processes, editor/zen/shader workers/Defender
  { echo "=== machine snapshot: $1 ==="; powershell -NoProfile -Command "Get-Content -Raw '$(cygpath -w "$TOOLS/machine_snapshot.ps1")' | Invoke-Expression" 2>&1 | tr -d '\r'; echo; } >> "$OUT/machine.txt"
}
machine_snap "at launch"
sleep 1
ls "$CRASHDIR" 2>/dev/null | sort > "$OUT/.crashes_before"
ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort > "$OUT/.dmp_before"

export SN2_AUTOTEST_OUT="$(cygpath -w "$OUT")"
export SN2_RUN_DIR="$(cygpath -w "$RUN")"
echo "$SN2_RUN_DIR" > "$OUT/run_dir.txt"
if [ "${SN2_HIDDEN:-0}" = 1 ]; then
  # DEFAULT (research/01 "Hidden desktop"): start the Shipping exe directly on the hidden desktop SN2Test (Steam client must be running, checked in the precheck; no -applaunch)
  export SN2_HIDDEN_DESKTOP=1 SN2_FOCUSGUARD=0
  # the holder process keeps the desktop handle open for the whole run (background; it exits when the game exits)
  python -u "$TOOLS/hidden_desktop.py" launch "$(cygpath -w "$SN2_GAME_DIR/Subnautica2/Binaries/Win64/Subnautica2-Win64-Shipping.exe")" -windowed -ResX=1920 -ResY=1080 -WinX=0 -WinY=0 > "$OUT/hidden_holder.log" 2>&1 &
  HID_UP=0; for i in $(seq 1 30); do sleep 2; tasklist 2>/dev/null | grep -qi "Subnautica2-Win64" && { HID_UP=1; break; }; done
  if [ $HID_UP = 0 ]; then
    echo "LAUNCH FAILED game not running 60 s after hidden launch" | tee -a "$(dirname "$OUT")/hidden_desktop_status.txt"; echo "RUN DONE LAUNCH_FAILED" >> "$(dirname "$OUT")/hidden_desktop_status.txt"; exit 7
  fi
elif [ "$SN2_INPUT" = engine ]; then
  # launched through Steam like Play (launch_game.sh -> steam.exe -applaunch); only DISPLAY args, no start override. Windowed (PrintWindow needs a normal window); flag names UE 5.6: -windowed -ResX -ResY -WinX -WinY
  bash "$TOOLS/launch_game.sh" -windowed -ResX=1920 -ResY=1080 -WinX=0 -WinY=0
else
  bash "$TOOLS/launch_game.sh"
fi
python -u "$TOOLS/autotest_driver.py" run "$(cygpath -w "$PLANFILE")" > "$OUT/driver.log" 2>&1 &
DRV=$!
RESULT=""; SEEN=0; DONE_AT=0
while [ -z "$RESULT" ]; do
  sleep 5
  NOW=$(date +%s); EL=$((NOW - T0))
  RUNNING=0; tasklist 2>/dev/null | grep -qi "Subnautica2-Win64" && RUNNING=1
  [ $RUNNING = 1 ] && SEEN=1
  DRVDONE=0; kill -0 "$DRV" 2>/dev/null || DRVDONE=1
  if [ $DRVDONE = 1 ]; then
    DR=$(grep -o 'RESULT [A-Z_]*' "$OUT/driver.log" | tail -1 | cut -d' ' -f2)
    for i in $(seq 1 12); do
      tasklist 2>/dev/null | grep -qi "Subnautica2-Win64" || break; sleep 5
    done
    force_kill "game still running 60 s after the driver ended (driver result ${DR:-none})"
    RESULT="${DR:-DRIVER_ERROR}"
  elif [ $SEEN = 1 ] && [ $RUNNING = 0 ]; then
    for i in $(seq 1 25); do kill -0 "$DRV" 2>/dev/null || break; sleep 2; done   # up to 50 s: the game exit can take 18 s+ and the driver writes RESULT DONE only after it
    if grep -q 'RESULT DONE' "$OUT/driver.log" 2>/dev/null; then RESULT=DONE; continue; fi
    NEWC=$(ls "$CRASHDIR" 2>/dev/null | sort | comm -13 "$OUT/.crashes_before" - | wc -l)
    NEWD=$(ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort | comm -13 "$OUT/.dmp_before" - | wc -l)
    if [ "$NEWC" -gt 0 ] || [ "$NEWD" -gt 0 ]; then RESULT=CRASH; else RESULT=EXITED; fi
    kill "$DRV" 2>/dev/null; kill_driver
  elif [ $EL -ge "$TIMEOUT" ]; then
    # overall --timeout reached (launch to game exit): verdict TIMEOUT, log the phase, clean quit, 20 s, FORCED_KILL, end holder
    PH="$(cur_phase "$OUT")"; STOP_WHY="TIMEOUT ${TIMEOUT}s reached at phase: $PH"
    echo "TIMEOUT after $EL s (limit ${TIMEOUT} s); phase reached: $PH" | tee -a "$OUT/driver.log"
    kill "$DRV" 2>/dev/null; kill_driver
    stop_game "$OUT" "$STOP_WHY"
    RESULT=TIMEOUT
  elif [ -f "$OUT/stop_request.txt" ]; then
    PH="$(cur_phase "$OUT")"; STOP_WHY="STOPPED by autotest_stop.sh at phase: $PH ($(cat "$OUT/stop_request.txt" | head -1))"
    echo "$STOP_WHY" | tee -a "$OUT/driver.log"
    kill "$DRV" 2>/dev/null; kill_driver
    stop_game "$OUT" "$STOP_WHY"
    RESULT=STOPPED
  elif [ $SEEN = 0 ] && [ $EL -ge 300 ] && [ "$TIMEOUT" -gt 300 ]; then
    RESULT=EXITED   # game never started
  fi
done
[ "$RESULT" != DONE ] && machine_snap "at failure (driver result $RESULT)"
echo "result=$RESULT after $(( $(date +%s) - T0 )) s"
[ "${SN2_HIDDEN:-0}" = 1 ] && { kill_holder; echo "RUN DONE $RESULT" >> "$(dirname "$OUT")/hidden_desktop_status.txt"; }
sleep 3
# test-world cleanup: only after the game process has fully exited (cleanup_test_slots refuses while it runs)
for i in $(seq 1 10); do game_running || break; sleep 2; done
cleanup_test_slots "$OUT" "$KEEP_WORLD"; cat "$OUT/slot_cleanup.txt" 2>/dev/null

# ---------------------------------------------------------------- always: cleanup + collect
rm -f "$RUN"/active_plan*.lua
kill_driver
cp "$RUN/manifest.tsv" "$OUT/manifest.tsv" 2>/dev/null
cp "$UE4LOG" "$OUT/UE4SS.log" 2>/dev/null
cp "$GAMELOG" "$OUT/Subnautica2.log" 2>/dev/null
cp "$PLANFILE" "$OUT/plan.json" 2>/dev/null
for f in "$SN2_UE4SS_DIR/Mods/SN2Census/census_"*.txt; do [ -f "$f" ] && [ "$f" -nt "$MARK" ] && cp "$f" "$OUT/census/"; done
for d in $(ls "$CRASHDIR" 2>/dev/null | sort | comm -13 "$OUT/.crashes_before" -); do cp -r "$CRASHDIR/$d" "$OUT/crash/" 2>/dev/null; done
for f in $(ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort | comm -13 "$OUT/.dmp_before" -); do cp "$f" "$OUT/crash/" 2>/dev/null; done

taskkill //IM CrashReportClient.exe //F >/dev/null 2>&1
# crash classification (research/01): a new dump in the crash folders, or a fatal marker in the game log, makes the verdict CRASH
# whatever the driver said (a crash during a map load leaves the process alive with no window and used to read as FAIL_MENU)
CRASH_WHY=""; RESULT_WAS=""
case "$RESULT" in DONE|STOPPED) ;; *)
  ND=$(ls "$OUT/crash" 2>/dev/null | wc -l)
  [ "$ND" -gt 0 ] && CRASH_WHY="new crash artefact(s) in the crash folders: $(ls "$OUT/crash" | tr '\n' ' ')"
  FL=""; [ "$GAMELOG" -nt "$MARK" ] && FL=$(grep -a -m1 -E 'Spent too much time waiting for FinishDestroy|AbortInsideMemberFunction|Fatal error|LowLevelFatalError' "$OUT/Subnautica2.log" 2>/dev/null | cut -c1-300)
  [ -n "$FL" ] && CRASH_WHY="${CRASH_WHY:+$CRASH_WHY | }game log: $FL"
  if [ -n "$CRASH_WHY" ]; then echo "reclassified $RESULT -> CRASH: $CRASH_WHY"; RESULT_WAS="$RESULT"; RESULT=CRASH; fi ;;
esac
echo "$RESULT" > "$OUT/result.txt"
if [ "$SN2_INPUT" = engine ]; then
  mkdir -p "$SN2_WORKSPACE/reports"
  for f in "$RUN"/widgets_*.txt "$RUN"/inputs.txt; do [ -f "$f" ] && { cp "$f" "$OUT/"; cp "$f" "$SN2_WORKSPACE/reports/"; }; done
fi

FOUND=$(ls "$OUT/shots"/[0-9][0-9]_*_k[0-9].png 2>/dev/null | wc -l)
if [ -f "$OUT/manifest.tsv" ]; then
  python "$TOOLS/autotest_sheets.py" "$OUT" "$PLAN" > "$OUT/sheets.log" 2>&1 || echo "sheets failed, see sheets.log"
fi
{
  echo "plan: $PLAN   start: $START   input: $SN2_INPUT   method: $METHOD"
  echo "result: $RESULT"
  [ -n "$CRASH_WHY" ] && echo "crash reason: $CRASH_WHY (harness/driver verdict was $RESULT_WAS)"
  echo "timeout: ${TIMEOUT} s   check: ${CHECK:-none}   hidden: $SN2_HIDDEN"
  [ -n "$T_REASON" ] && echo "timeout-reason: $T_REASON"
  [ -n "$AFTER_FIX" ] && echo "after-fix: $AFTER_FIX"
  [ -n "${STOP_WHY:-}" ] && echo "stop: $STOP_WHY"
  echo "phase at end: $(cur_phase "$OUT")"
  echo "== phase timestamps (launch/driver: local time; game log: UTC) =="
  echo "launch: $(date -d "@$T0" +%H:%M:%S)"
  grep -ah 'MENU_READY_AT\|FIRST_CLICK_AT' "$OUT/driver.log" 2>/dev/null | while read -r _ k v; do echo "$k: $(date -d "@${v%.*}" +%H:%M:%S 2>/dev/null)"; done
  echo "game log first line: $(grep -a -m1 . "$OUT/Subnautica2.log" 2>/dev/null | cut -c1-60)"
  grep -a -E 'LogLoad: LoadMap:|Took .* to LoadMap|BeginTearingDown|UWorld::CleanupWorld|LogGarbage: Warning: Spent' "$OUT/Subnautica2.log" 2>/dev/null | cut -c1-170 | head -16
  grep -a -E '\[SN2AutoTest\] (WORLD|PAWN possessed)' "$OUT/UE4SS.log" 2>/dev/null | cut -c1-120 | head -8
  [ -f "$OUT/machine.txt" ] && echo "machine snapshots: machine.txt ($(grep -c '^=== machine' "$OUT/machine.txt") taken)"
  cat "$OUT/slot_cleanup.txt" 2>/dev/null
  echo "== watchdog marks before launch =="; cat "$OUT/marks_before.txt"
  grep -h 'DIALOG' "$OUT/driver.log" 2>/dev/null
  grep -h '^\[driver\] \(FG\|FPS\) ' "$OUT/driver.log" 2>/dev/null
  cat "$OUT/forced_kill.txt" 2>/dev/null
  grep -h 'QUIT_FAILED\|RESULT FAIL_\|STALL_ARTEFACTS' "$OUT/driver.log" 2>/dev/null
  for f in "$OUT"/windows_*.txt; do [ -f "$f" ] || continue; R=$(basename "$f" .txt); R=${R#windows_}; echo "== stall artefact '$R': $(basename "$f") + shots/stall_$R.png =="; cat "$f"; done
  echo "run time: $(( $(date +%s) - T0 )) s"
  echo "== deaths / respawns =="; grep -h '\] \(DEATH\|RESPAWN\|DIED_WAYPOINT\|DEATHS\) \|DEATH waypoint\|RESPAWN pos\|DIED_WAYPOINT' "$OUT/driver.log" 2>/dev/null | sort -u
  echo "shots expected: $EXPECTED   found: $FOUND   manifest rows: $( [ -f "$OUT/manifest.tsv" ] && echo $(( $(wc -l < "$OUT/manifest.tsv") - 1 )) || echo 0 )"
  echo; echo "== per shot (lum = mean luminance, diff_prev = mean abs diff to previous shot) =="
  cat "$OUT/shot_stats.txt" 2>/dev/null
  echo; echo "== log lines =="
  grep -hE 'StartNewLocalGame|LoadLocalGame|LoadMap|Took .* to LoadMap|Applying start conditions|LogSN2Lifepod|Error:|Fatal|Accessed None|\[SN2AutoTest\]|\[driver\]' "$OUT/Subnautica2.log" "$OUT/UE4SS.log" "$OUT/driver.log" 2>/dev/null | sort -u | cut -c1-300
  echo; echo "== census sample lines (first / last) =="
  grep -h '^\[SN2Census\] world=' "$OUT/UE4SS.log" 2>/dev/null | sed -n '1p;$p' | cut -c1-600
  if [ "$RESULT" = CRASH ]; then
    echo; echo "== crash info =="
    grep -h 'MENU_READY_AT\|FIRST_CLICK_AT' "$OUT/driver.log" | head -2
    grep -a 'LogGarbage\|LoadMap:\|Took .* to LoadMap\|Fatal error\|Unhandled Exception\|Applying start' "$OUT/Subnautica2.log" | tail -12 | cut -c1-300
    echo "last game log lines:"; tail -8 "$OUT/Subnautica2.log" | cut -c1-250
  fi
  echo; echo "crash folders: $(ls "$OUT/crash" | tr '\n' ' ')"
} > "$OUT/summary.txt"
echo "summary: $OUT/summary.txt"
head -8 "$OUT/summary.txt"
NDIED=$(grep -c "DIED_WAYPOINT" "$OUT/driver.log" 2>/dev/null); [ "$RESULT" = DONE ] && { [ "$FOUND" -ge "$EXPECTED" ] || [ "${NDIED:-0}" -gt 0 ]; } && exit 0
exit 1
