#!/usr/bin/env bash
# Automated in-game test run: installs SN2AutoTest (observe-only Lua) + SN2Census, arms a plan, launches the game, runs
# src/tools/autotest_driver.py (simulated OS keyboard/mouse + screen capture), waits for DONE/crash/timeout,
# collects screenshots/logs/census into <Workspace>/autotest/<timestamp>_<plan>/ and builds summary.txt + contact sheets.
# Usage: bash src/tools/autotest.sh <plan-name>      (plans: src/mods/SN2AutoTest/plans/<plan-name>.json, menus.json)
# Run it with run_in_background (a run is several minutes). Nobody may touch the PC; the game window must stay in front.
# Exit code 0 only for result DONE with all shots present.
. "$(dirname "$0")/sn2_env.sh"
# input mode: --input engine|os (or env SN2_INPUT). engine (default) = commands via run/cmd.txt to the SN2AutoTest Lua mod
# + PrintWindow capture of the (windowed) game window; no real input, the game window stays unfocused in the background.
# os (opt-in: --input os) = SendInput + full-screen grabs (takes over mouse/keyboard).
ARGS_IN=()
while [ $# -gt 0 ]; do
  case "$1" in --input) SN2_INPUT="$2"; shift 2;; *) ARGS_IN+=("$1"); shift;; esac
done
set -- "${ARGS_IN[@]}"
PLAN="${1:?plan name}"
export SN2_INPUT="${SN2_INPUT:-engine}"
case "$SN2_INPUT" in os|engine) ;; *) echo "bad --input $SN2_INPUT (os|engine)"; exit 2;; esac
PLANFILE="$SN2_REPO/src/mods/SN2AutoTest/plans/$PLAN.json"
[ -f "$PLANFILE" ] || { echo "no plan $PLANFILE"; exit 2; }
# RAM: hold the heavy lock (src/tools/heavy_lock.sh) for the whole run; waits up to SN2_LOCK_WAIT s (default 3600). Released at exit only if taken here.
HL="$SN2_REPO/src/tools/heavy_lock.sh"
if ! bash "$HL" check; then
  bash "$HL" acquire game --wait "${SN2_LOCK_WAIT:-3600}" --note "autotest $PLAN" || { echo "heavy lock not acquired - abort"; exit 2; }
  trap 'bash "$HL" release >/dev/null' EXIT
fi
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

if [ "$SN2_INPUT" = engine ]; then METHOD=engine-printwindow; else METHOD=driver-grab; fi
EXPECTED=$(python -c "import json,sys;print(len(json.load(open(sys.argv[1]))['waypoints'])*8)" "$(cygpath -w "$PLANFILE")")
START=$(python -c "import json,sys;print(json.load(open(sys.argv[1])).get('start','new'))" "$(cygpath -w "$PLANFILE")")
echo "plan=$PLAN input=$SN2_INPUT method=$METHOD expected=$EXPECTED out=$OUT"

bash "$TOOLS/backup_saves.sh" || echo "WARNING: backup failed"
bash "$TOOLS/install_mod.sh" SN2AutoTest
bash "$TOOLS/install_mod.sh" SN2Census
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
sleep 1
ls "$CRASHDIR" 2>/dev/null | sort > "$OUT/.crashes_before"
ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort > "$OUT/.dmp_before"

export SN2_AUTOTEST_OUT="$(cygpath -w "$OUT")"
export SN2_RUN_DIR="$(cygpath -w "$RUN")"
if [ "$SN2_INPUT" = engine ]; then
  # windowed launch (PrintWindow needs a normal window); flag names UE 5.6: -windowed -ResX -ResY -WinX -WinY
  bash "$TOOLS/launch_game.sh" -windowed -ResX=1920 -ResY=1080 -WinX=0 -WinY=0
else
  bash "$TOOLS/launch_game.sh"
fi
python -u "$TOOLS/autotest_driver.py" run "$(cygpath -w "$PLANFILE")" > "$OUT/driver.log" 2>&1 &
DRV=$!
RESULT=""; SEEN=0; T0=$(date +%s); DONE_AT=0
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
    for i in 1 2 3 4 5 6 7 8; do kill -0 "$DRV" 2>/dev/null || break; sleep 2; done   # the quit clicks end the game before the driver returns
    if grep -q 'RESULT DONE' "$OUT/driver.log" 2>/dev/null; then RESULT=DONE; continue; fi
    NEWC=$(ls "$CRASHDIR" 2>/dev/null | sort | comm -13 "$OUT/.crashes_before" - | wc -l)
    NEWD=$(ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort | comm -13 "$OUT/.dmp_before" - | wc -l)
    if [ "$NEWC" -gt 0 ] || [ "$NEWD" -gt 0 ]; then RESULT=CRASH; else RESULT=EXITED; fi
    kill "$DRV" 2>/dev/null; powershell -NoProfile -c "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'autotest_driver' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
  elif [ $EL -ge 900 ]; then
    force_kill "TIMEOUT after 900 s"
    kill "$DRV" 2>/dev/null; powershell -NoProfile -c "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'autotest_driver' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
    RESULT=TIMEOUT
  elif [ $SEEN = 0 ] && [ $EL -ge 180 ]; then
    RESULT=EXITED   # game never started
  fi
done
echo "result=$RESULT after $(( $(date +%s) - T0 )) s"
sleep 3

# ---------------------------------------------------------------- always: cleanup + collect
rm -f "$RUN"/active_plan*.lua
powershell -NoProfile -c "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'autotest_driver' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
cp "$RUN/manifest.tsv" "$OUT/manifest.tsv" 2>/dev/null
cp "$UE4LOG" "$OUT/UE4SS.log" 2>/dev/null
cp "$GAMELOG" "$OUT/Subnautica2.log" 2>/dev/null
cp "$PLANFILE" "$OUT/plan.json" 2>/dev/null
for f in "$RUN"/poddump_*.txt; do [ -f "$f" ] && cp "$f" "$OUT/"; done
for f in "$SN2_UE4SS_DIR/Mods/SN2Census/census_"*.txt; do [ -f "$f" ] && [ "$f" -nt "$MARK" ] && cp "$f" "$OUT/census/"; done
for d in $(ls "$CRASHDIR" 2>/dev/null | sort | comm -13 "$OUT/.crashes_before" -); do cp -r "$CRASHDIR/$d" "$OUT/crash/" 2>/dev/null; done
for f in $(ls "$SN2_UE4SS_DIR"/crash_*.dmp 2>/dev/null | sort | comm -13 "$OUT/.dmp_before" -); do cp "$f" "$OUT/crash/" 2>/dev/null; done

taskkill //IM CrashReportClient.exe //F >/dev/null 2>&1
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
  echo "== watchdog marks before launch =="; cat "$OUT/marks_before.txt"
  grep -h 'DIALOG' "$OUT/driver.log" 2>/dev/null
  grep -h '^\[driver\] \(FG\|FPS\) ' "$OUT/driver.log" 2>/dev/null
  cat "$OUT/forced_kill.txt" 2>/dev/null
  grep -h 'QUIT_FAILED\|RESULT FAIL_\|STALL_ARTEFACTS' "$OUT/driver.log" 2>/dev/null
  for f in "$OUT"/windows_*.txt; do [ -f "$f" ] || continue; R=$(basename "$f" .txt); R=${R#windows_}; echo "== stall artefact '$R': $(basename "$f") + shots/stall_$R.png =="; cat "$f"; done
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
[ "$RESULT" = DONE ] && [ "$FOUND" -ge "$EXPECTED" ] && exit 0
exit 1
