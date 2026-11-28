#!/usr/bin/env bash
# UE4SS on/off A/B for the lobby -> L_SN2World GC-watchdog crash (research/crashes/gc_watchdog_logs_2026-11-23.md, "GC-watchdog analysis", "Consequence for the UE4SS on/off A/B").
# N runs, arms alternate ON, OFF, ON, OFF ... (ON = UE4SS loaded, OFF = <Win64>\dwmapi.dll renamed to dwmapi.dll.gcab_off). Per run:
#   1. cache flush: schtasks /run /tn SN2_FlushStandby (RAMMap64 -Et, admin through the pre-made task), waits until the task is no longer running
#   2. OFF only: rename dwmapi.dll   3. install the Lua mods (as autotest.sh does)   4. launch (visible, OS input), Lua-free driver gc_ab_driver.py:
#   new Survival game on L_SN2World, ~20 s in the world, clean quit   5. after the game exited: OFF only: restore + verify dwmapi.dll
# Why not autotest.sh: its OS-input driver needs UE4SS (lobby = '[SN2AutoTest] WORLD' in UE4SS.log, PAWN possessed, quit step post_log), so the OFF arm would
# end FAIL_LOBBY after 300 s. Both arms therefore use gc_ab_driver.py (game log + screen identity only), so only UE4SS differs. Slot cleanup, timeouts.tsv
# row and the lock rules are reused from autotest_lib.sh. RUNS TAKE OVER THE USER'S MOUSE/KEYBOARD (visible, OS input).
# --vt-prio N: see run_one (SN2Census vtprio.lua sets r.VT.IOPriority_HighPagePri; read-back verdict in vtprio_verdict.txt)
# Usage: bash src/tools/gc_ab_test.sh [--runs N=10] [--timeout S=420] [--stay S=20] [--first-arm ON|OFF] [--dry-run]
#   --dry-run: prints every step, launches/renames/flushes/acquires nothing (read-only checks only).
# Output: <Workspace>\reports\gc_ab_<ts>.tsv (one row per run) + run folders <Workspace>\autotest\<ts>_gc_ab_<ON|OFF>\ (driver.log, Subnautica2.log, ...).
# Run it with run_in_background and a Monitor; total ~25-40 min for 10 runs.
. "$(dirname "$0")/sn2_env.sh"
. "$SN2_REPO/src/tools/autotest_lib.sh"
TOOLS="$SN2_REPO/src/tools"; HL="$TOOLS/heavy_lock.sh"
RUNS=10; TIMEOUT=420; STAY=20; FIRST=ON; DRY=0; ONLY=""; DIAG=""; STACKS=""; PASSES=0; WANT=5
while [ $# -gt 0 ]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2;; --timeout) TIMEOUT="$2"; shift 2;; --stay) STAY="$2"; shift 2;;
    --first-arm) FIRST="$2"; shift 2;; --arm) ONLY="$2"; shift 2;; --want) WANT="$2"; shift 2;; --diag) DIAG=1; shift;; --stacks) DIAG=1; STACKS=1; shift;; --noflush) NOFLUSH=1; shift;; --ioq) DIAG=1; STACKS=1; IOQ=1; shift;; --until-crash) UNTIL_CRASH=1; shift;; --vt-prio) VTPRIO="$2"; shift 2;; --dry-run) DRY=1; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
case "${VTPRIO:-0}" in *[!0-9]*) echo "--vt-prio N (integer 0-5)"; exit 2;; esac
case "$RUNS$TIMEOUT$STAY" in *[!0-9]*) echo "numeric options only"; exit 2;; esac
case "$FIRST" in ON|OFF) ;; *) echo "--first-arm ON|OFF"; exit 2;; esac
case "$ONLY" in ""|ON) ;; *) echo "--arm ON only (UE4SS-ON-only mode)"; exit 2;; esac
# ON-only mode (2026-11-24): every run ON, hard timeout 120 s counted from launch_game.sh returning (fixed on purpose, do not change), screenshots, classification,
# stop at the first CRASH/CHECK or after $WANT consecutive passes (RUNS is the cap). Usage: gc_ab_test.sh --arm ON --runs 20
[ -n "$ONLY" ] && { TIMEOUT=120; FIRST=ON; }
# --diag (2026-11-24, diagnostic runs, use with --arm ON --runs 3): game started with -LogCmds="LogGarbage Verbose" and a -trace attempt, SN2Census diag census
# armed through <Census mod dir>/diag.flag (output dir inside the run folder), purge-window thread timeline written to purge_window.txt.
# Stops after 3 runs, or once there is 1 CRASH plus 1 run with purge >= 10 s (a crash counts for both). Timeout stays 120 s.
[ -n "$DIAG" ] && { [ -z "$ONLY" ] && { echo "--diag needs --arm ON"; exit 2; }; if [ -n "$STACKS" ]; then [ "$RUNS" -gt 8 ] && RUNS=8; else [ "$RUNS" -gt 4 ] && RUNS=4; fi; }
# --stacks (2026-11-25): cap 8 runs. A TIMEOUT that is only slow loading (PASS_TIMEOUT_LOW) does not stop the series (project owner 2026-11-25);
# a CHECK (debug terminal / unidentified screen / no timeout shot) stops it for investigation; stop once a slow purge or crash has >= 100 GameThread samples.
# --until-crash (2026-11-25, with --stacks): a slow purge no longer stops the series; stop only on a CRASH with >= 100 samples (or a CHECK, or the 8-run cap).

BIN="$SN2_GAME_DIR/Subnautica2/Binaries/Win64"; DLL="$BIN/dwmapi.dll"; OFFDLL="$DLL.gcab_off"
MODSTXT="$SN2_UE4SS_DIR/Mods/mods.txt"; UE4LOG="$SN2_UE4SS_DIR/UE4SS.log"
LOCAL="${LOCALAPPDATA:-$HOME/AppData/Local}/Subnautica2/Saved"; GAMELOG="$LOCAL/Logs/Subnautica2.log"; CRASHDIR="$LOCAL/Crashes"
TS=$(date +%Y%m%d_%H%M%S); REPORTS="$SN2_WORKSPACE/reports"; TSV="$REPORTS/gc_ab_$TS.tsv"
HL_TAKEN=""; KA=""; DRV=""; DONE_CLEAN=""; STOP=""
say() { echo "[gc_ab $(date +%H:%M:%S)] $*"; }
act() { if [ "$DRY" = 1 ]; then say "[dry-run] $*"; return 0; fi; "$@"; }
game_up() { tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; }

# ---------------------------------------------------------------- dwmapi.dll restore (the trap calls it too, so UE4SS can never stay off)
restore_dll() {   # prints DWMAPI RESTORED OK | DWMAPI RESTORE FAILED <reason>; returns 0/1
  if [ "$DRY" = 1 ]; then say "[dry-run] restore dwmapi.dll if renamed + verify size/sha256, print DWMAPI RESTORED OK"; return 0; fi
  local why=""
  if [ -f "$OFFDLL" ]; then
    if game_up; then echo "DWMAPI RESTORE FAILED game still running (rename back by hand: mv \"$OFFDLL\" \"$DLL\")"; return 1; fi
    if [ -f "$DLL" ]; then echo "DWMAPI RESTORE FAILED both dwmapi.dll and dwmapi.dll.gcab_off exist"; return 1; fi
    mv "$OFFDLL" "$DLL" || { echo "DWMAPI RESTORE FAILED mv error"; return 1; }
  fi
  [ -f "$DLL" ] || why="dwmapi.dll missing"
  [ -z "$why" ] && [ "$(stat -c %s "$DLL")" != "$SIZE0" ] && why="size $(stat -c %s "$DLL") != $SIZE0"
  [ -z "$why" ] && [ "$(sha256sum "$DLL" | cut -d' ' -f1)" != "$SHA0" ] && why="sha256 differs"
  [ -z "$why" ] && [ -f "$OFFDLL" ] && why="dwmapi.dll.gcab_off still exists"
  if [ -n "$why" ]; then echo "DWMAPI RESTORE FAILED $why"; return 1; fi
  echo "DWMAPI RESTORED OK (size $SIZE0, sha256 $SHA0)"; return 0
}
kill_driver() {
  [ -n "$DRV" ] && kill "$DRV" 2>/dev/null
  powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'gc_ab_driver\.py run' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
  return 0
}
force_kill() {   # $1 = why; logged FORCED_KILL (research/process/README.md rule: windows artefact first)
  if game_up; then
    echo "FORCED_KILL $1" >> "$OUT/forced_kill.txt"
    SN2_INPUT=os python "$TOOLS/autotest_driver.py" windows forced_kill "$(cygpath -w "$OUT")" >> "$OUT/forced_kill_windows.log" 2>&1
    taskkill //IM Subnautica2-Win64-Shipping.exe //F >/dev/null 2>&1
  fi
}
wait_game_gone() {   # $1 = seconds; 0 = gone
  local i; for i in $(seq 1 "$1"); do game_up || return 0; sleep 1; done; game_up && return 1; return 0
}
cleanup() {   # EXIT / INT / TERM, once
  [ -n "$DONE_CLEAN" ] && return; DONE_CLEAN=1
  [ -n "$KA" ] && kill "$KA" 2>/dev/null
  kill_driver
  if [ "$DRY" != 1 ] && game_up; then OUT="${OUT:-$REPORTS}"; mkdir -p "$OUT"; force_kill "gc_ab_test.sh ended/interrupted while the game was running"; wait_game_gone 30; fi
  [ -n "$DIAG" ] && rm -f "$SN2_UE4SS_DIR/Mods/SN2Census/diag.flag"
  rm -f "$SN2_UE4SS_DIR/Mods/SN2Census/vtprio.flag"
  for p in ${TPD:-} ${TPP:-}; do kill "$p" 2>/dev/null; done
  [ -n "${SMP:-}" ] && kill "$SMP" 2>/dev/null   # only after the game is gone (the stack sampler suspends the GameThread briefly)
  restore_dll; RC_DLL=$?
  if [ "$DRY" != 1 ]; then
    echo "== mods.txt (SN2 mods must stay enabled) =="; grep -E "^SN2[A-Za-z]* *:" "$MODSTXT" 2>/dev/null
    for m in SN2Census SN2AutoTest SN2Tadpole SN2BugShot; do grep -q "^$m : 1" "$MODSTXT" 2>/dev/null || echo "WARNING: $m is not '$m : 1' in mods.txt"; done
  fi
  [ -n "$HL_TAKEN" ] && bash "$HL" release >/dev/null 2>&1 && say "heavy lock released"
  say "tsv: $TSV"
  return $RC_DLL
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# ---------------------------------------------------------------- preflight
say "runs=$RUNS timeout=${TIMEOUT}s stay=${STAY}s first-arm=$FIRST dry-run=$DRY"
[ -f "$DLL" ] || { [ -f "$OFFDLL" ] && echo "dwmapi.dll is already renamed (leftover $OFFDLL): rename it back by hand first" || echo "no $DLL"; DONE_CLEAN=1; exit 2; }
[ -f "$OFFDLL" ] && { echo "leftover $OFFDLL exists: resolve by hand first"; DONE_CLEAN=1; exit 2; }
SHA0=$(sha256sum "$DLL" | cut -d' ' -f1); SIZE0=$(stat -c %s "$DLL")
say "dwmapi.dll before the test: size $SIZE0 sha256 $SHA0"
if ! bash "$HL" status | grep -q 'verdict: FREE'; then bash "$HL" status
  if [ "$DRY" = 1 ]; then say "[dry-run] WARNING: heavy lock not free - a real run would abort here"; else echo "heavy lock not free - abort"; DONE_CLEAN=1; exit 4; fi; fi
if game_up; then
  if [ "$DRY" = 1 ]; then say "[dry-run] WARNING: Subnautica2-Win64-Shipping.exe is running - a real run would abort here"; else echo "Subnautica2-Win64-Shipping.exe is running - abort"; DONE_CLEAN=1; exit 2; fi; fi
MSYS_NO_PATHCONV=1 schtasks /query /tn SN2_FlushStandby >/dev/null 2>&1 || { echo "scheduled task SN2_FlushStandby not found (research/process/README.md cold-cache recipe) - abort"; DONE_CLEAN=1; exit 2; }
if [ "$DRY" != 1 ]; then
  bash "$HL" acquire gc_ab --wait 0 --note "gc_ab_test $RUNS runs" || { echo "heavy lock not acquired - abort"; DONE_CLEAN=1; exit 4; }
  HL_TAKEN=1
  # the lock counts as free after SN2_LOCK_IDLE s (10) without a heavy process: refresh it while the game is down between runs
  ( while true; do sleep 4; bash "$HL" acquire gc_ab --wait 0 >/dev/null 2>&1; done ) & KA=$!
  bash "$TOOLS/backup_saves.sh" || echo "WARNING: save backup failed"
  mkdir -p "$REPORTS"
else
  say "[dry-run] heavy_lock acquire gc_ab --wait 0 ; keep-alive refresh every 4 s ; backup_saves.sh"
fi
printf '#run\tarm\tverdict\trun_folder\tflush_ok\tflush_s\tboot_to_lobby_s\tlobby_to_world_s\tpurge_s\tresult\tgc_queue\trun_time_s\tforced_kill\n' > "$([ "$DRY" = 1 ] && echo /dev/null || echo "$TSV")"

# ---------------------------------------------------------------- flush
flush_cache() {   # sets FLUSH_OK (1/0) and FLUSH_S
  FLUSH_OK=0; FLUSH_S=""
  if [ "$DRY" = 1 ]; then say "[dry-run] schtasks /run /tn SN2_FlushStandby ; poll 'schtasks /query ... /v' (Status != Running and Last Run Time changed, Last Result 0), timeout 120 s"; FLUSH_OK="dry"; return 0; fi
  local q="MSYS_NO_PATHCONV=1" t0 last0 st last res
  q_field() { MSYS_NO_PATHCONV=1 schtasks /query /tn SN2_FlushStandby /fo LIST /v 2>/dev/null | tr -d '\r' | sed -n "s/^$1: *//p" | head -1; }
  last0=$(q_field "Last Run Time"); t0=$(date +%s)
  MSYS_NO_PATHCONV=1 schtasks /run /tn SN2_FlushStandby >/dev/null 2>&1 || { say "schtasks /run failed"; return 1; }
  while [ $(( $(date +%s) - t0 )) -lt 120 ]; do
    sleep 1; st=$(q_field "Status"); last=$(q_field "Last Run Time")
    if [ "$st" != "Running" ] && [ "$last" != "$last0" ]; then
      res=$(q_field "Last Result"); FLUSH_S=$(( $(date +%s) - t0 ))
      [ "$res" = "0" ] && FLUSH_OK=1 || say "flush task Last Result=$res"
      return 0
    fi
  done
  say "flush task still running / not started after 120 s"; return 1
}

# ---------------------------------------------------------------- one run
NOFLUSH=${NOFLUSH:-0}
BAD_STREAK=0; TO_STREAK=0; DCRASH=0; DSLOW=0
run_one() {   # $1 index, $2 arm
  local idx="$1" arm="$2" RES="" T0 LAUNCH_T SEEN=0 EL RUNNING DRVDONE i MARKSHOT="" TL=0
  OUT="$SN2_WORKSPACE/autotest/$(date +%Y%m%d_%H%M%S)_gc_ab_${arm}_$idx"
  say "=== run $idx/$RUNS arm=$arm -> $OUT"
  if [ "$DRY" = 1 ]; then
    flush_cache
    [ "$arm" = OFF ] && say "[dry-run] mv dwmapi.dll dwmapi.dll.gcab_off (only after: game not running + lock held)"
    say "[dry-run] install_mod.sh SN2AutoTest ; SN2Census ; rm -rf <AutoTest>/run ; rm UE4SS.log ; record_slots_pre"
    say "[dry-run] launch_game.sh (visible, OS input) ; python gc_ab_driver.py run --launch-epoch <t> --stay $STAY  (log: driver.log)"
    say "[dry-run] monitor every 3 s: driver RESULT / game exit / TIMEOUT ${TIMEOUT}s -> FORCED_KILL ; wait until the exe is gone"
    [ "$arm" = OFF ] && say "[dry-run] restore dwmapi.dll after the exe exited, verify size+sha256+no .gcab_off"
    say "[dry-run] cleanup_test_slots (only the slot this run created) ; copy game log ; gc_purge_stats.py ; row -> $TSV ; timeouts.tsv row"
    return 0
  fi
  mkdir -p "$OUT"
  bash "$HL" acquire gc_ab --wait 0 >/dev/null 2>&1
  game_up && { echo "game running before run $idx - abort"; STOP=1; return 1; }
  if [ "$NOFLUSH" = 1 ]; then FLUSH_OK=0; FLUSH_S=""; say "warm boot: cold flush skipped (--noflush)"; echo "flush=skipped(noflush)" > "$OUT/flush_mode.txt"
  else
  flush_cache
  [ "$FLUSH_OK" = 1 ] || { say "flush failed (ok=$FLUSH_OK): stopping, the cold-cache condition is not met"; echo "flush failed" > "$OUT/flush_failed.txt"; STOP=1; return 1; }
  say "flush ok in ${FLUSH_S}s"; echo "flush=cold" > "$OUT/flush_mode.txt"
  fi
  if [ "$arm" = OFF ]; then
    game_up && { STOP=1; return 1; }
    mv "$DLL" "$OFFDLL" || { say "rename failed"; STOP=1; return 1; }
    say "dwmapi.dll renamed (UE4SS OFF)"
  fi
  bash "$TOOLS/install_mod.sh" SN2AutoTest >/dev/null; bash "$TOOLS/install_mod.sh" SN2Census >/dev/null
  rm -rf "$SN2_UE4SS_DIR/Mods/SN2AutoTest/run"; mkdir -p "$SN2_UE4SS_DIR/Mods/SN2AutoTest/run"; rm -f "$UE4LOG" 2>/dev/null
  T0=$(date +%s); record_slots_pre "$OUT" "$T0"
  ls "$CRASHDIR" 2>/dev/null | sort > "$OUT/.crashes_before"
  { echo "arm=$arm"; echo "index=$idx"; echo "timeout_s=$TIMEOUT"; echo "start_epoch=$T0"; echo "flush_s=$FLUSH_S"; } > "$OUT/run_info.txt"
  LAUNCH_T=$T0
  local XARGS=""
  if [ -n "$DIAG" ]; then
    mkdir -p "$OUT"; { cygpath -m "$OUT"; if [ -n "$STACKS" ]; then echo "nocensus classmap"; else echo nocensus; fi; } > "$SN2_UE4SS_DIR/Mods/SN2Census/diag.flag"
    XARGS="-LogCmds=\"LogGarbage Verbose\" -trace=cpu,frame,log -tracefile=$(cygpath -m "$OUT")/gc.utrace"
    [ -n "$STACKS" ] && XARGS=""   # stacks mode: no ineffective Shipping log/trace args
    say "diag: extra game args: $XARGS ; diag.flag -> $(cat "$SN2_UE4SS_DIR/Mods/SN2Census/diag.flag" | sed 's#.*/autotest/#<Workspace>/autotest/#')"
  fi
  # --vt-prio N (2026-11-26, fix test 1): Shipping compiles out -dpcvars/-ini/-ExecCmds, so SN2Census/vtprio.lua sets the cvar from Lua at mod start;
  # the flag file (value, output dir) is written here and removed again by cleanup()/after the run. Read-back is verified after the run.
  rm -f "$SN2_UE4SS_DIR/Mods/SN2Census/vtprio.flag"
  if [ -n "${VTPRIO:-}" ]; then
    { echo "$VTPRIO"; cygpath -m "$OUT"; } > "$SN2_UE4SS_DIR/Mods/SN2Census/vtprio.flag"; echo "vt_prio=$VTPRIO" >> "$OUT/run_info.txt"
    say "vt-prio: r.VT.IOPriority_HighPagePri=$VTPRIO via SN2Census/vtprio.lua (flag written)"
  fi
  # shellcheck disable=SC2086
  SN2_INPUT=os bash "$TOOLS/launch_game.sh" $XARGS > "$OUT/launch.log" 2>&1 || { say "launch_game.sh failed: $(tail -2 "$OUT/launch.log")"; RES=LAUNCH_FAILED; }
  if [ -z "$RES" ]; then
    TL=$(date +%s)
    export SN2_GCAB_OUT="$(cygpath -w "$OUT")"
    SN2_INPUT=os python -u "$TOOLS/gc_ab_driver.py" run --launch-epoch "$LAUNCH_T" --stay "$STAY" > "$OUT/driver.log" 2>&1 &
    DRV=$!
    if [ -n "$DIAG" ]; then   # read-only per-thread sampler (exits by itself when the game exits or after 150 s)
      if [ -n "${IOQ:-}" ]; then   # --ioq (2026-11-26, H8): read-only IoStore request scanner instead of the stack sampler (src/tools/gc_ioq_scan.py)
        python "$TOOLS/gc_ioq_scan.py" "$(cygpath -w "$OUT")" --log "$(cygpath -w "$GAMELOG")" --full-every 3 --max-seconds 150 > "$OUT/sampler.log" 2>&1 &
      elif [ -n "$STACKS" ]; then   # GameThread stack sampler (suspends the thread < 1 ms per sample, 20 Hz, only in the purge window)
        python "$TOOLS/gc_stack_sampler.py" "$(cygpath -w "$OUT")" --log "$(cygpath -w "$GAMELOG")" --max-seconds 200 > "$OUT/sampler.log" 2>&1 &
      else
        python "$TOOLS/gc_thread_sampler.py" "$(cygpath -w "$OUT")/thread_samples.tsv" --max-seconds 150 > "$OUT/sampler.log" 2>&1 &
      fi
      SMP=$!
      # disk/IO counters, 1 Hz, read-only (H8: IO backlog on the game disk at travel time). typeperf ends by itself after -sc samples.
      MSYS_NO_PATHCONV=1 typeperf "\PhysicalDisk(*)\Current Disk Queue Length" "\PhysicalDisk(*)\% Idle Time" "\PhysicalDisk(*)\Disk Reads/sec" "\PhysicalDisk(*)\Disk Read Bytes/sec" "\PhysicalDisk(*)\Avg. Disk sec/Read" -si 1 -sc 200 -f CSV -y -o "$(cygpath -w "$OUT")\disk_perf.csv" > "$OUT/typeperf_disk.log" 2>&1 &
      TPD=$!
      ( for i in $(seq 1 60); do game_up && break; sleep 1; done   # the process instance must exist when typeperf starts
        MSYS_NO_PATHCONV=1 exec typeperf "\Process(Subnautica2-Win64-Shipping)\IO Read Operations/sec" "\Process(Subnautica2-Win64-Shipping)\IO Read Bytes/sec" -si 1 -sc 200 -f CSV -y -o "$(cygpath -w "$OUT")\proc_io.csv" ) > "$OUT/typeperf_proc.log" 2>&1 &
      TPP=$!
    fi
  fi
  while [ -z "$RES" ]; do
    sleep 3; EL=$(( $(date +%s) - T0 )); [ -n "$ONLY" ] && EL=$(( $(date +%s) - TL ))
    if [ -z "$MARKSHOT" ] && grep -qa 'Spent too much time waiting for FinishDestroy\|Spent more than 20.00s on routing FinishDestroy' "$GAMELOG" 2>/dev/null && [ "$GAMELOG" -nt "$OUT/.crashes_before" ]; then
      MARKSHOT=1; python "$TOOLS/gc_ab_shot.py" "$(cygpath -w "$OUT")/gc_marker_screen.png" >> "$OUT/shots.log" 2>&1; fi
    RUNNING=0; game_up && RUNNING=1; [ $RUNNING = 1 ] && SEEN=1
    DRVDONE=0; kill -0 "$DRV" 2>/dev/null || DRVDONE=1
    if [ $DRVDONE = 1 ]; then
      python "$TOOLS/gc_ab_shot.py" "$(cygpath -w "$OUT")/end_screen.png" >> "$OUT/shots.log" 2>&1
      RES=$(grep -a '^RESULT ' "$OUT/driver.log" | tail -1 | cut -d' ' -f2); RES="${RES:-DRIVER_ERROR}"
      wait_game_gone 45 || force_kill "game still running 45 s after the driver ended (driver result $RES)"
    elif [ $EL -ge "$TIMEOUT" ]; then
      echo "TIMEOUT after $EL s (limit $TIMEOUT s); last driver lines:" >> "$OUT/driver.log"; tail -3 "$OUT/driver.log" >> "$OUT/driver.log"
      python "$TOOLS/gc_ab_shot.py" "$(cygpath -w "$OUT")/timeout_screen.png" >> "$OUT/shots.log" 2>&1
      kill_driver; force_kill "TIMEOUT ${TIMEOUT}s"; RES=TIMEOUT
    elif [ $SEEN = 0 ] && [ $EL -ge 240 ]; then
      kill_driver; RES=NOLAUNCH
    fi
  done
  DRV=""; kill_driver
  [ -n "${SMP:-}" ] && { sleep 1; kill "$SMP" 2>/dev/null; SMP=""; }
  for p in ${TPD:-} ${TPP:-}; do kill "$p" 2>/dev/null; done; TPD=""; TPP=""
  # the next step needs the exe gone
  wait_game_gone 40 || { force_kill "exe still alive 40 s after the run end"; wait_game_gone 20; }
  if game_up; then say "game process cannot be stopped - stopping the whole test"; STOP=1; fi
  [ "$arm" = OFF ] && [ -z "$STOP" ] && { restore_dll || STOP=1; }
  [ -n "$STOP" ] && return 1
  if [ -n "$DIAG" ]; then rm -f "$SN2_UE4SS_DIR/Mods/SN2Census/diag.flag"; fi
  rm -f "$SN2_UE4SS_DIR/Mods/SN2Census/vtprio.flag"
  cleanup_test_slots "$OUT" 0 | sed 's/^/  /'
  [ "$GAMELOG" -nt "$OUT/.crashes_before" ] && cp "$GAMELOG" "$OUT/Subnautica2.log" 2>/dev/null
  [ "$arm" = ON ] && [ -f "$UE4LOG" ] && cp "$UE4LOG" "$OUT/UE4SS.log" 2>/dev/null
  # stats: purge etc. from this run's game log (last lobby -> world row)
  local B="" L="" P="" R="" Q="" ROW GCR
  if [ -f "$OUT/Subnautica2.log" ]; then
    python -I "$TOOLS/gc_purge_stats.py" --tsv "$OUT/gc_stats.tsv" "$OUT/Subnautica2.log" > "$OUT/gc_stats.txt" 2>&1
    ROW=$(grep -v '^#' "$OUT/gc_stats.tsv" 2>/dev/null | tail -1)
    if [ -n "$ROW" ]; then L=$(echo "$ROW" | cut -f6); B=$(echo "$ROW" | cut -f7); P=$(echo "$ROW" | cut -f8); R=$(echo "$ROW" | cut -f9); Q=$(echo "$ROW" | cut -f10); fi
  fi
  GCR=NO_END
  if [ "$R" = OK ]; then GCR=OK; fi
  if [ "$R" = GC_CRASH ] || [ "$RES" = GC_CRASH ] || grep -qa 'Spent too much time waiting for FinishDestroy\|Spent more than 20.00s on routing FinishDestroy' "$OUT/Subnautica2.log" 2>/dev/null; then GCR=GC_CRASH; fi
  echo "$RES" > "$OUT/result.txt"
  local FK=0; [ -f "$OUT/forced_kill.txt" ] && FK=1
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$idx" "$arm" "$RES" "$OUT" "$FLUSH_OK" "$FLUSH_S" "$B" "$L" "$P" "$GCR" "$Q" "$(( $(date +%s) - T0 ))" "$FK" >> "$TSV"
  tsv_row gc_ab "$TIMEOUT" "$RES" "gc_ab arm=$arm result=$GCR" "$(( $(date +%s) - T0 ))" "$OUT" "boot_to_lobby=$B purge=$P"
  say "run $idx arm=$arm verdict=$RES result=$GCR boot->lobby=${B}s lobby->world=${L}s purge=${P}s queue=$Q forced_kill=$FK"
  # classification (ON-only mode): PASS / PASS_TIMEOUT_LOW / CRASH / CHECK (inspect screenshot: DEBUG TERMINAL or other)
  local NEWCR CLS; NEWCR=$(ls "$CRASHDIR" 2>/dev/null | sort | comm -13 "$OUT/.crashes_before" - | tr -s '[:space:]' ' ')
  if [ "$GCR" = GC_CRASH ] || [ -n "$NEWCR" ] || [ "$RES" = GC_CRASH ] || [ "$RES" = EXITED ]; then CLS=CRASH
  elif [ "$RES" = DONE ]; then CLS=PASS
  elif [ "$RES" = TIMEOUT ]; then CLS=PASS_TIMEOUT_LOW
    # 2026-11-25: a timeout is CHECK only if a dialog window (#32770) of the game process is open in the timeout shot's window list; the UE4SS
    # Debugging Tools window overlapping during boot is benign (run 20261125_161952: world loaded, purge 0.2 s, shot = world loading screen).
    local GPID; GPID=$(grep -a "class='UnrealWindow'" "$OUT/timeout_screen.png.windows.txt" 2>/dev/null | head -1 | sed -n 's/.* pid=\([0-9]*\) .*/\1/p')
    [ -n "$GPID" ] && grep -a " pid=$GPID class='#32770'" "$OUT/timeout_screen.png.windows.txt" >/dev/null 2>&1 && CLS=CHECK
  else CLS=CHECK; fi
  [ "$RES" = TIMEOUT ] && [ ! -f "$OUT/timeout_screen.png" ] && CLS=CHECK
  if [ -n "${VTPRIO:-}" ]; then   # read-back verdict: SET_OK line + the last LOADMAP_PRE read-back must equal the wanted value, else setup failure
    local VSET VPRE VTL; VSET=$(grep -a ' SET_OK ' "$OUT/vtprio.txt" 2>/dev/null | head -1)
    VPRE=$(grep -a 'LOADMAP_PRE' "$OUT/vtprio.txt" 2>/dev/null | tail -1)
    # OK = SET_OK seen and no LOADMAP_PRE read-back after it that differs (a run that times out before the travel has no pre-hook line after SET_OK: still OK)
    if [ -n "$VSET" ] && awk -v w="$VTPRIO" 'BEGIN{s=-1} / SET_OK /{if(s<0)s=$1} /LOADMAP_PRE/{ if(s>=0 && $1>=s){ split($0,a,"readback="); split(a[2],c," "); if(c[1]!=w) bad=1 } } END{exit bad}' "$OUT/vtprio.txt"; then VTL="VT_PRIO_OK"; else VTL="VT_PRIO_SETUP_FAIL"; fi
    { echo "$VTL"; echo "set: $VSET"; echo "last pre-hook: $VPRE"; } > "$OUT/vtprio_verdict.txt"; echo "vt_prio_verdict=$VTL" >> "$OUT/run_info.txt"
    say "vt-prio read-back: $VTL | set: $(echo "$VSET" | cut -c1-120) | pre: $(echo "$VPRE" | cut -c1-120)"
    [ "$VTL" != VT_PRIO_OK ] && { CLS="${CLS}+$VTL"; STOP=1; say "run $idx: wanted value not confirmed by read-back: setup failure, stopping the series"; }
  fi
  echo "$CLS" > "$OUT/classification.txt"; say "run $idx classification=$CLS new_crash_dirs='$NEWCR' screenshots: $(ls "$OUT"/*.png 2>/dev/null | xargs -n1 basename 2>/dev/null | tr -s '[:space:]' ' ')"
  if [ -n "$DIAG" ]; then
    [ -f "$OUT/Subnautica2.log" ] && python -I "$TOOLS/gc_window.py" "$OUT/Subnautica2.log" "$OUT/purge_window.txt" 2>&1 | tail -2
    grep -a 'Command Line' "$OUT/Subnautica2.log" 2>/dev/null | head -1 | cut -c1-400 > "$OUT/command_line.txt"
    local UT; UT=$(ls -l "$OUT"/*.utrace 2>/dev/null | awk '{print $5}' | head -1); echo "utrace_bytes=${UT:-none}" >> "$OUT/run_info.txt"
    ls "$OUT"/census_*.txt 2>/dev/null | xargs -n1 basename 2>/dev/null | tr -s '[:space:]' ' ' > "$OUT/census_files.txt"
    say "diag: command line: $(cat "$OUT/command_line.txt" | grep -o 'LogCmds[^ ]* *[A-Za-z]*\|trace[^ ]*' | tr -s '[:space:]' ' ') ; utrace bytes: ${UT:-none} ; census files: $(cat "$OUT/census_files.txt")"
    [ "$CLS" = CRASH ] && DCRASH=$((DCRASH + 1))
    if [ "$CLS" = CRASH ] || awk -v p="${P:-0}" 'BEGIN{exit !(p+0>=10)}'; then DSLOW=$((DSLOW + 1)); fi
    say "diag: crashes=$DCRASH slow(purge>=10s or crash)=$DSLOW"
    local SMPN
    if [ -n "$STACKS" ]; then
      SMPN=$(wc -l < "$OUT/stack_samples.jsonl" 2>/dev/null || echo 0); say "diag: stack samples: $SMPN ; $(tail -1 "$OUT/stack_sampler.log" 2>/dev/null)"
      if [ -n "${IOQ:-}" ]; then
        python -I "$TOOLS/gc_ioq_map.py" "$OUT" > "$OUT/ioq_report_stdout.txt" 2>&1; say "diag: ioq report: $(tail -1 "$OUT/ioq_scan.log" 2>/dev/null)"
        [ "$CLS" = CRASH ] && { say "diag stop condition reached (crash with ioq scan)"; STOP=1; }
        [ "$CLS" = CHECK ] && { say "run $idx classified CHECK: stopping, investigate the screenshots"; STOP=1; }
        return 0
      fi
      python -I "$TOOLS/gc_stack_analyse.py" "$OUT" > "$OUT/stack_analysis.txt" 2>&1; head -3 "$OUT/stack_analysis.txt" | cut -c1-160
      if [ -n "$UNTIL_CRASH" ]; then   # --until-crash: slow passes do not stop the series, only a sampled CRASH
        [ "$CLS" = CRASH ] && [ "${SMPN:-0}" -ge 100 ] && { say "diag stop condition reached (crash with >= 100 stack samples)"; STOP=1; }
      else
        [ "$DSLOW" -ge 1 ] && [ "${SMPN:-0}" -ge 100 ] && { say "diag stop condition reached (slow purge or crash with >= 100 stack samples)"; STOP=1; }
      fi
      [ "$CLS" = CHECK ] && { say "run $idx classified CHECK (not a plain slow load): stopping, investigate the screenshots"; STOP=1; }
      return 0
    fi
    SMPN=$(wc -l < "$OUT/thread_samples.tsv" 2>/dev/null || echo 0); say "diag: thread samples rows: $SMPN"
    python -I "$TOOLS/gc_thread_window.py" "$OUT" > "$OUT/thread_window.txt" 2>&1; tail -3 "$OUT/thread_window.txt" | cut -c1-160
    [ "$DSLOW" -ge 1 ] && [ "${SMPN:-0}" -gt 1000 ] && { say "diag stop condition reached (slow purge or crash with thread samples)"; STOP=1; }
    return 0
  fi
  if [ -n "$ONLY" ]; then
    case "$CLS" in PASS|PASS_TIMEOUT_LOW) PASSES=$((PASSES + 1));; *) PASSES=0; say "first non-pass ($CLS): stopping, investigate"; STOP=1;; esac
    [ $PASSES -ge "$WANT" ] && { say "SUCCESS: $PASSES consecutive passes"; STOP=1; }
    return 0
  fi
  # stop rules: two TIMEOUTs in a row = broken (research/process/README.md timeout rule); two harness failures in a row
  if [ "$RES" = TIMEOUT ]; then TO_STREAK=$((TO_STREAK + 1)); else TO_STREAK=0; fi
  if [ "$RES" != DONE ] && [ "$GCR" != GC_CRASH ]; then BAD_STREAK=$((BAD_STREAK + 1)); else BAD_STREAK=0; fi
  if [ $TO_STREAK -ge 2 ] || [ $BAD_STREAK -ge 2 ]; then say "two consecutive failed runs (timeouts $TO_STREAK, harness failures $BAD_STREAK): stopping, investigate (stall_*.png / windows_*.txt in the run folder first)"; STOP=1; fi
  return 0
}

for i in $(seq 1 "$RUNS"); do
  if [ -n "$ONLY" ]; then ARM=ON; elif [ $(( (i - 1) % 2 )) = 0 ]; then ARM=$FIRST; else [ "$FIRST" = ON ] && ARM=OFF || ARM=ON; fi
  run_one "$i" "$ARM"
  [ -n "$STOP" ] && { say "stopped after run $i"; break; }
done
say "done"
[ "$DRY" = 1 ] || { echo "== summary =="; cut -f1,2,3,5,6,7,8,9,10,11 "$TSV"; }
exit 0
