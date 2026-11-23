#!/usr/bin/env bash
# Shared helpers for autotest.sh / autotest_retry.sh / autotest_stop.sh / test_wait.sh. Source after sn2_env.sh.
# Exit codes used by the refusals (all happen BEFORE the heavy lock is taken and before anything launches):
#   8 = --timeout missing/invalid   9 = raising a timeout after a TIMEOUT needs --timeout-reason
#   10 = two consecutive TIMEOUT verdicts on the plan (needs --after-fix)   6 = Steam not running and did not become ready within SN2_STEAM_WAIT (default 90 s) after ensure_steam started it
TIMEOUTS_TSV="${SN2_TIMEOUTS_TSV:-$SN2_WORKSPACE/autotest/timeouts.tsv}"

steam_running() {   # SN2_FAKE_NO_STEAM=1 simulates "not running" for offline tests
  [ "${SN2_FAKE_NO_STEAM:-0}" = 1 ] && return 1
  tasklist 2>/dev/null | grep -qi "^steam.exe"
}
steam_logged_in() {   # HKCU\Software\Valve\Steam\ActiveProcess ActiveUser non-zero = a user is logged in
  [ "${SN2_FAKE_NO_STEAM:-0}" = 1 ] && return 1
  local u; u=$(reg query 'HKCU\Software\Valve\Steam\ActiveProcess' //v ActiveUser 2>/dev/null | tr -d '\r' | sed -n 's/^ *ActiveUser *REG_DWORD *//p')
  [ -n "$u" ] && [ "$u" != 0x0 ]
}
# ensure_steam [timeout_s=90]: make sure the Steam client is running and logged in. Starts it minimized (steam.exe -silent, path from the
# registry SteamExe value) if needed and waits up to timeout_s for ActiveUser != 0. Returns 0 ok, 6 = Steam did not become ready (no fallback to the
# visible desktop). Logs whether Steam was started or already running. Test hooks: SN2_FAKE_NO_STEAM=1 (never executes steam.exe; waits out the timeout).
ensure_steam() {
  local to="${1:-90}" t0 exe
  if steam_running && steam_logged_in; then echo "ensure_steam: Steam already running (logged in)"; return 0; fi
  if steam_running; then echo "ensure_steam: Steam running, waiting for login"
  elif [ "${SN2_FAKE_NO_STEAM:-0}" = 1 ]; then echo "ensure_steam: [fake] Steam not running, NOT starting it (test mode)"
  else
    exe=$(reg query 'HKCU\Software\Valve\Steam' //v SteamExe 2>/dev/null | tr -d '\r' | sed -n 's/^ *SteamExe *REG_SZ *//p')
    exe=$(cygpath -u "$exe" 2>/dev/null)
    if [ -z "$exe" ] || [ ! -f "$exe" ]; then echo "REFUSED: Steam is not running and its exe was not found (registry HKCU\Software\Valve\Steam SteamExe)."; return 6; fi
    echo "ensure_steam: Steam was not running, starting it minimized (steam.exe -silent)"
    "$exe" -silent >/dev/null 2>&1 &
  fi
  t0=$(date +%s)
  while [ $(( $(date +%s) - t0 )) -lt "$to" ]; do
    if steam_running && steam_logged_in; then echo "ensure_steam: Steam ready after $(( $(date +%s) - t0 )) s"; return 0; fi
    sleep 2
  done
  echo "REFUSED: Steam did not become ready (running + logged in) within ${to} s. Hidden-desktop runs never fall back to the visible desktop."; return 6
}

# precheck <plan> <timeout|""> <reason> <after_fix> <hidden 0|1>   -> exits (not returns) with the refusal code
autotest_precheck() {
  local plan="$1" to="$2" reason="$3" fix="$4" hidden="$5"
  case "$to" in ''|*[!0-9]*|0) echo "REFUSED: every test needs --timeout <seconds> (whole run, launch to game exit); no default exists. See research/01_runbook.md 'Test timeouts'."; exit 8;; esac
  if [ -f "$TIMEOUTS_TSV" ]; then
    # last two rows of this plan: columns datetime, plan, timeout_s, verdict, ...
    local rows last_v last_t prev_v
    rows=$(awk -F'\t' -v p="$plan" '$0 !~ /^#/ && $2==p {print $3 "\t" $4}' "$TIMEOUTS_TSV" | tail -2)
    last_t=$(echo "$rows" | tail -1 | cut -f1); last_v=$(echo "$rows" | tail -1 | cut -f2)
    prev_v=$(echo "$rows" | head -1 | cut -f2)
    if [ "$last_v" = TIMEOUT ] && [ "$(echo "$rows" | wc -l)" -ge 2 ] && [ "$prev_v" = TIMEOUT ]; then
      if [ -z "$fix" ]; then echo "REFUSED: two consecutive timeouts on plan $plan: treat as broken, investigate and report. Override only with --after-fix \"<what was changed>\"."; exit 10; fi
    fi
    if [ "$last_v" = TIMEOUT ] && [ "$to" -gt "${last_t:-0}" ] && [ -z "$reason" ]; then
      echo "REFUSED: last run of plan $plan ended TIMEOUT at ${last_t}s; raising to ${to}s needs --timeout-reason \"<why the previous estimate was wrong>\" (find the long phase in that run's driver.log first)."; exit 9
    fi
  fi
  ensure_steam "${SN2_STEAM_WAIT:-90}" || exit 6
}

# phase reached by the driver: last 'step ...' / 'waypoint ...' / FAIL / RESULT line of driver.log (single line, trimmed)
cur_phase() {
  local log="$1/driver.log"
  [ -f "$log" ] || { echo "no_driver_log"; return; }
  grep -E '\] [0-9:]+ (step |waypoint |FAIL|CLEAN QUIT|lobby|menu)|RESULT ' "$log" | tail -1 | sed 's/^\[driver\] //' | cut -c1-120 | tr '\t\r' '  '
}

# tsv_row <plan> <timeout_s> <verdict> <phase> <runtime_s> <folder> <reason>
tsv_row() {
  mkdir -p "$(dirname "$TIMEOUTS_TSV")"
  [ -f "$TIMEOUTS_TSV" ] || printf '#datetime\tplan\ttimeout_s\tverdict\tphase_at_end\trun_time_s\trun_folder\treason\n' > "$TIMEOUTS_TSV"
  local reason; reason=$(printf '%s' "$7" | tr '\t\r\n' '   ')
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" "$3" "$4" "$5" "$6" "$reason" >> "$TIMEOUTS_TSV"
}

# newest run folder (named <ts>_<plan>)
latest_run() { ls -d "$SN2_WORKSPACE/autotest/"[0-9]*_[0-9]*_* 2>/dev/null | sort | tail -1; }

kill_holder() {   # only the hidden-desktop holder python process
  powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'hidden_desktop\.py launch' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1
  return 0
}

# stop_game <run dir> <reason>: clean quit through the command channel (driver 'quit': main_quit click, WM_CLOSE fallback), wait up to 20 s,
# then force-kill the game through the FORCED_KILL path (logged in forced_kill.txt with a windows/stall artefact), then end the holder.
stop_game() {
  local out="$1" why="$2" tools="$SN2_REPO/src/tools" i
  if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then
    [ -f "$out/hidden.flag" ] && export SN2_HIDDEN_DESKTOP=1
    [ -f "$out/run_dir.txt" ] && export SN2_RUN_DIR="$(cat "$out/run_dir.txt")"
    export SN2_AUTOTEST_OUT="$(cygpath -w "$out")"
    echo "$(date +%H:%M:%S) stop_game: clean quit requested ($why)" >> "$out/stop.log"
    timeout 30 python "$tools/autotest_driver.py" quit >> "$out/stop.log" 2>&1
    for i in $(seq 1 20); do tasklist 2>/dev/null | grep -qi "Subnautica2-Win64" || break; sleep 1; done
    if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then
      echo "FORCED_KILL $why (still running 20 s after the clean quit request)" >> "$out/forced_kill.txt"
      python "$tools/autotest_driver.py" windows forced_kill "$(cygpath -w "$out")" >> "$out/forced_kill_windows.log" 2>&1
      taskkill //IM Subnautica2-Win64-Shipping.exe //F >/dev/null 2>&1
    else
      echo "$(date +%H:%M:%S) stop_game: game exited cleanly" >> "$out/stop.log"
    fi
  fi
  [ -f "$out/hidden.flag" ] && { sleep 1; kill_holder; }
  return 0
}

# ---------------------------------------------------------------- test-world cleanup (user rule 2026-11-22: every test deletes the world it created)
# Saves folder; SN2_SAVEGAMES_DIR overrides it FOR OFFLINE TESTS ONLY (never point it at fake files in the real folder).
slot_dir() { echo "${SN2_SAVEGAMES_DIR:-$SN2_SAVES_DIR}"; }
game_running() {   # SN2_FAKE_GAME_RUNNING=1 simulates a running game (offline tests)
  [ "${SN2_FAKE_GAME_RUNNING:-0}" = 1 ] && return 0
  tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"
}
# file creation time (epoch): birth time where stat supports it (%W > 0), else mtime
slot_ctime() { local w; w=$(stat -c %W "$1" 2>/dev/null); if [ -n "$w" ] && [ "$w" -gt 0 ] 2>/dev/null; then echo "$w"; else stat -c %Y "$1"; fi; }
# record_slots_pre <run dir> <start epoch>: slots_pre.txt = "# start_epoch=<n>" then "<name>\t<mtime epoch>\t<size>" per savegame_*.sav / savegame_*_*.bak
record_slots_pre() {
  local out="$1" t0="$2" d f; d="$(slot_dir)"
  { echo "# start_epoch=$t0 savedir=$d"
    for f in "$d"/savegame_*.sav "$d"/savegame_*_*.bak; do
      [ -f "$f" ] && printf '%s\t%s\t%s\n' "$(basename "$f")" "$(stat -c %Y "$f")" "$(stat -c %s "$f")"
    done
  } > "$out/slots_pre.txt"
}
# cleanup_test_slots <run dir> [keep 0|1]: run AFTER the game process has exited. Deletes only savegame_N.sav + savegame_N_*.bak of slots N that had no file in
# slots_pre.txt AND whose files were created after the run start. Deletes NOTHING (logs SLOT_CLEANUP_SKIPPED <reason>) if the game is running, slots_pre.txt is
# missing, an existing slot was modified/gained a file, or a "new" slot predates the run start. Never touches non-slot files. Logs to <run>/deleted_slots.txt
# and appends the line to <run>/slot_cleanup.txt (autotest.sh copies it into summary.txt). Idempotent per run folder (marker .slot_cleanup_done).
cleanup_test_slots() {
  local out="$1" keep="${2:-0}" d pre t0 f b n rsn="" new=() pre_slots line
  [ -f "$out/.slot_cleanup_done" ] && return 0
  : > "$out/.slot_cleanup_done"
  d="$(slot_dir)"; pre="$out/slots_pre.txt"
  say() { echo "$1"; echo "$1" >> "$out/deleted_slots.txt"; echo "$1" >> "$out/slot_cleanup.txt"; }
  if [ "$keep" = 1 ]; then say "SLOT_CLEANUP_SKIPPED --keep-world given (plan-approved)"; return 0; fi
  if [ ! -f "$pre" ]; then say "SLOT_CLEANUP_SKIPPED no slots_pre.txt"; return 0; fi
  if game_running; then say "SLOT_CLEANUP_SKIPPED game still running"; return 0; fi
  t0=$(sed -n 's/^# start_epoch=\([0-9]*\).*/\1/p' "$pre" | head -1)
  [ -z "$t0" ] && { say "SLOT_CLEANUP_SKIPPED no start_epoch in slots_pre.txt"; return 0; }
  # slots known before the run
  pre_slots=" $(grep -v '^#' "$pre" | cut -f1 | sed -n 's/^savegame_\([0-9]*\)\(_[0-9]*\.bak\|\.sav\)$/\1/p' | sort -u | tr '\n' ' ')"
  # ambiguity checks: a pre-existing file changed, or a pre-existing slot gained a file
  while IFS=$'\t' read -r b m s; do
    case "$b" in '#'*|'') continue;; esac
    if [ ! -f "$d/$b" ]; then continue; fi
    if [ "$(stat -c %Y "$d/$b")" != "$m" ] || [ "$(stat -c %s "$d/$b")" != "$s" ]; then rsn="pre-existing file $b was modified during the run"; break; fi
  done < "$pre"
  if [ -z "$rsn" ]; then
    for f in "$d"/savegame_*.sav "$d"/savegame_*_*.bak; do
      [ -f "$f" ] || continue; b=$(basename "$f")
      n=$(echo "$b" | sed -n 's/^savegame_\([0-9]*\)\(_[0-9]*\.bak\|\.sav\)$/\1/p'); [ -z "$n" ] && continue
      if grep -q "^$b	" "$pre"; then continue; fi
      case "$pre_slots" in *" $n "*) rsn="pre-existing slot $n gained a new file $b"; break;; esac
      if [ "$(slot_ctime "$f")" -lt "$t0" ]; then rsn="file $b is not in slots_pre.txt but predates the run start"; break; fi
      case " ${new[*]:-} " in *" $n "*) ;; *) new+=("$n");; esac
    done
  fi
  if [ -n "$rsn" ]; then say "SLOT_CLEANUP_SKIPPED $rsn"; return 0; fi
  if [ ${#new[@]} -eq 0 ]; then say "SLOT_CLEANUP none (no new slot created)"; return 0; fi
  for n in "${new[@]}"; do
    for f in "$d/savegame_${n:?}.sav" "$d"/savegame_"${n:?}"_*.bak; do
      [ -f "$f" ] || continue
      case "$(basename "$f")" in savegame_[0-9]*.sav|savegame_[0-9]*_[0-9]*.bak) ;; *) continue;; esac
      rm -- "${f:?}" && echo "$(date '+%Y-%m-%d %H:%M:%S') deleted $f" >> "$out/deleted_slots.txt"
    done
  done
  say "SLOT_CLEANUP deleted new slot(s): ${new[*]} (details in deleted_slots.txt)"
  return 0
}
