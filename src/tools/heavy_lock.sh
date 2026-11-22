#!/usr/bin/env bash
# One-at-a-time lock for the RAM-heavy jobs (game, modkit editor, cook, SN1 builder), shared by parallel Claude sessions on this PC.
# Usage:
#   bash src/tools/heavy_lock.sh acquire <what> [--wait SECONDS] [--note TEXT]
#        what = game | editor | cook | build | ...  (free text, shown to other sessions). Exit 0 = this session holds the lock.
#        --wait 0 (default) tries once; --wait N polls every SN2_LOCK_POLL s (15) for up to N s. Long waits: run with run_in_background.
#        Re-acquiring a lock you already hold refreshes it (resets the idle timer) and adds <what>.
#   bash src/tools/heavy_lock.sh release [--force]   give the lock back (--force: even if another session holds it - ask the user first)
#   bash src/tools/heavy_lock.sh check               exit 0 if this session holds the lock, 1 otherwise (prints nothing)
#   bash src/tools/heavy_lock.sh status              holder, running heavy processes, verdict
# Owner identity: SN2_LOCK_OWNER if set, else "claude-pid-<CLAUDE_PID>" (each Claude session is its own claude.exe; in-process subagents share it).
# The lock is free when: nobody holds it; OR the holder's claude.exe is gone; OR no heavy process has run for SN2_LOCK_IDLE s (60) since the
# holder last acquired. Free + a heavy process running that nobody owns (orphan, or started by hand) = busy, except that `acquire editor`
# may adopt an already-open editor. Heavy processes = image-name prefixes in SN2_HEAVY_PROCS. History: <Workspace>/locks/history.log.
. "$(dirname "$0")/sn2_env.sh"
LOCKS="${SN2_LOCK_DIR:-$SN2_WORKSPACE/locks}"
INFO="$LOCKS/heavy.info"
GUARD="$LOCKS/.guard"
IDLE="${SN2_LOCK_IDLE:-60}"
POLL="${SN2_LOCK_POLL:-15}"
PROCS="${SN2_HEAVY_PROCS:-Subnautica2-Win64 UnrealEditor AutomationTool UnrealBuildTool ShaderCompileWorker sn1build}"
ADOPTABLE_FOR_EDITOR="UnrealEditor ShaderCompileWorker"
ME="${SN2_LOCK_OWNER:-${CLAUDE_PID:+claude-pid-$CLAUDE_PID}}"
ME="${ME:-manual}"
ME_PID="${CLAUDE_PID:-}"
[ -n "${SN2_LOCK_OWNER:-}" ] && ME_PID="${SN2_LOCK_OWNER_PID:-}"
mkdir -p "$LOCKS"

now() { date +%s; }
log() { printf '%s %s owner=%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$ME" "${2:-}" >> "$LOCKS/history.log"; }

# short critical section around every read-modify-write of heavy.info (mkdir is atomic); a guard older than 60 s is from a killed caller
guard_on() {
  local t0; t0=$(now)
  until mkdir "$GUARD" 2>/dev/null; do
    if [ -d "$GUARD" ] && [ $(( $(now) - $(stat -c %Y "$GUARD" 2>/dev/null || now) )) -gt 60 ]; then rmdir "$GUARD" 2>/dev/null; continue; fi
    [ $(( $(now) - t0 )) -gt 90 ] && { echo "heavy_lock: could not get $GUARD" >&2; exit 9; }
    sleep 0.3
  done
}
guard_off() { rmdir "$GUARD" 2>/dev/null; }

# heavy.info is plain key=value lines (also read by src/modkit/tools/ue_run.py)
declare -A L
read_info() { L=(); [ -f "$INFO" ] || return 1; while IFS='=' read -r k v; do [ -n "$k" ] && L[$k]="${v%$'\r'}"; done < "$INFO"; return 0; }
write_info() { local tmp="$INFO.tmp.$$"; { for k in owner owner_pid what note since seen; do printf '%s=%s\n' "$k" "${L[$k]:-}"; done; } > "$tmp" && mv -f "$tmp" "$INFO"; }

heavy_running() {  # prints the running heavy image names, one per line
  local re; re=$(echo "$PROCS" | tr ' ' '|')
  tasklist //FO CSV //NH 2>/dev/null | cut -d, -f1 | tr -d '"' | grep -iE "^($re)" | sort -u
}
pid_alive() { [ -n "$1" ] && tasklist //FI "PID eq $1" //FO CSV //NH 2>/dev/null | grep -q "\"$1\""; }

# sets STALE_WHY to the reason the current holder no longer counts, or empty if the holder is valid; updates 'seen' while heavy processes run
evaluate() {
  STALE_WHY=""
  RUNNING="$(heavy_running)"
  if [ -n "$RUNNING" ]; then L[seen]=$(now); write_info; fi
  if [ -n "${L[owner_pid]:-}" ] && ! pid_alive "${L[owner_pid]}"; then STALE_WHY="holder session gone (pid ${L[owner_pid]})"; return; fi
  local last=${L[since]:-0}; [ "${L[seen]:-0}" -gt "$last" ] && last=${L[seen]}
  if [ -z "$RUNNING" ] && [ $(( $(now) - last )) -gt "$IDLE" ]; then STALE_WHY="idle $(( $(now) - last )) s > ${IDLE} s, no heavy process running"; fi
}

describe() { echo "holder=${L[owner]} what=${L[what]} since=$(date -d "@${L[since]}" '+%H:%M:%S' 2>/dev/null)${L[note]:+ note=${L[note]}}"; }

# one attempt; exit status 0 = held by me; sets MSG
try_acquire() {
  local what="$1" note="$2"
  guard_on
  if read_info; then
    if [ "${L[owner]}" = "$ME" ]; then
      case ",${L[what]}," in *",$what,"*) ;; *) L[what]="${L[what]},$what" ;; esac
      L[since]=$(now); L[owner_pid]="$ME_PID"; [ -n "$note" ] && L[note]="$note"
      write_info; guard_off; MSG="held (refreshed): $(describe)"; return 0
    fi
    evaluate
    if [ -z "$STALE_WHY" ]; then guard_off; MSG="BUSY: $(describe); running: $(echo $RUNNING)"; return 1; fi
    log TAKEOVER "from=${L[owner]} reason=$STALE_WHY"
    echo "heavy_lock: taking over from ${L[owner]} ($STALE_WHY)"
    rm -f "$INFO"
  fi
  RUNNING="$(heavy_running)"
  if [ -n "$RUNNING" ]; then
    local foreign; foreign=$(echo "$RUNNING" | grep -viE "^($(echo "$ADOPTABLE_FOR_EDITOR" | tr ' ' '|'))" || true)
    if [ "$what" != editor ] || [ -n "$foreign" ]; then
      guard_off; MSG="BUSY: no holder, but heavy processes run that no session owns: $(echo $RUNNING) - the previous owner should close them; if none exists, ask the user"; return 1
    fi
    echo "heavy_lock: adopting the already-open editor"
  fi
  L=([owner]="$ME" [owner_pid]="$ME_PID" [what]="$what" [note]="$note" [since]=$(now) [seen]=0)
  write_info; guard_off; log ACQUIRE "what=$what${note:+ note=$note}"
  MSG="acquired: $(describe)"; return 0
}

cmd="${1:-status}"; shift || true
case "$cmd" in
  acquire)
    WHAT="${1:?what (game|editor|cook|build)}"; shift
    WAIT=0; NOTE=""
    while [ $# -gt 0 ]; do case "$1" in --wait) WAIT="$2"; shift 2 ;; --note) NOTE="$2"; shift 2 ;; *) echo "unknown arg $1"; exit 2 ;; esac; done
    T0=$(now); LASTMSG=""
    while :; do
      if try_acquire "$WHAT" "$NOTE"; then echo "heavy_lock: $MSG"; exit 0; fi
      [ "$MSG" != "$LASTMSG" ] && { echo "heavy_lock: $MSG"; LASTMSG="$MSG"; }
      [ $(( $(now) - T0 )) -ge "$WAIT" ] && { echo "heavy_lock: NOT ACQUIRED after $(( $(now) - T0 )) s"; exit 1; }
      sleep "$POLL"
    done ;;
  release)
    guard_on
    if read_info; then
      if [ "${L[owner]}" = "$ME" ] || [ "${1:-}" = --force ]; then
        rm -f "$INFO"; log RELEASE "from=${L[owner]}${1:+ $1}"; guard_off
        R="$(heavy_running)"; echo "heavy_lock: released"
        [ -n "$R" ] && echo "heavy_lock: WARNING still running: $(echo $R) - close what you started; other sessions wait while it runs"
        exit 0
      fi
      guard_off; echo "heavy_lock: not yours ($(describe)); use --force only if the user says so"; exit 1
    fi
    guard_off; echo "heavy_lock: not held"; exit 0 ;;
  check)
    read_info && [ "${L[owner]}" = "$ME" ] ;;
  status)
    guard_on
    if read_info; then
      evaluate; guard_off
      echo "$(describe) owner_pid=${L[owner_pid]:-none}${L[owner]:+$([ "${L[owner]}" = "$ME" ] && echo ' (this session)')}"
      [ -n "$STALE_WHY" ] && echo "verdict: FREE - stale: $STALE_WHY" || echo "verdict: HELD"
    else
      guard_off; RUNNING="$(heavy_running)"; echo "no holder"
      [ -n "$RUNNING" ] && echo "verdict: BUSY - unowned heavy processes running" || echo "verdict: FREE"
    fi
    echo "heavy processes running: $(echo ${RUNNING:-none})"
    echo "you are: $ME" ;;
  *) sed -n 2,16p "$0"; exit 2 ;;
esac
