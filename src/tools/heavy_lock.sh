#!/usr/bin/env bash
# One-at-a-time lock for the RAM-heavy jobs (game, modkit editor, cook, SN1 builder), shared by parallel Claude sessions on this PC.
# Usage:
#   bash src/tools/heavy_lock.sh acquire <what> [--wait SECONDS] [--note TEXT]
#        what = game | editor | cook | build | ...  (free text, shown to other sessions). Exit 0 = this session holds the lock.
#        --wait 0 (default) tries once; --wait N polls every SN2_LOCK_POLL s (15) for up to N s and queues FIFO behind earlier waiters.
#        Long waits: run with run_in_background. Re-acquiring a lock you already hold renews it (resets the lease) and adds <what>.
#   bash src/tools/heavy_lock.sh release [--force]   give the lock back (--force: even if another session holds it - ask the user first)
#   bash src/tools/heavy_lock.sh check               exit 0 if this session holds the lock, 1 otherwise (prints nothing; also renews)
#   bash src/tools/heavy_lock.sh renew               holder only: reset the lease (exit 1 if not held by you)
#   bash src/tools/heavy_lock.sh hold [--every S] [--max S]
#        holder only, foreground heartbeat (run it with run_in_background): renews every S s (20) for up to --max s (3600) while you
#        still hold the lock and your claude.exe lives. Use it across long non-heavy-process jobs (Python extractors) or long gaps.
#   bash src/tools/heavy_lock.sh status              holder, running heavy processes, verdict, queue
# Owner identity: SN2_LOCK_OWNER if set, else "claude-pid-<CLAUDE_PID>" (each Claude session is its own claude.exe; in-process subagents share it).
# Lease: the lock is free when: nobody holds it; OR the holder's owner_pid process is gone (immediate); OR no heavy process has run and
# nothing renewed the lock (acquire/check/renew/hold) for SN2_LOCK_IDLE s (600) = a holder that forgot to release. A holder whose heavy
# process is running is never idle. Free + a heavy process running that nobody owns (orphan, hand-started) = busy, except that
# `acquire editor` may adopt an already-open editor. Fair order: waiters (--wait N>0) queue FIFO in <locks>/queue; while a live waiter
# is queued, nobody else (not even the releasing holder) can take a free lock. History: <Workspace>/locks/history.log.
# The whole script is one function called on the last line, so replacing the file (write temp + mv) never breaks a running copy.
heavy_lock_main() {
. "$(dirname "$0")/sn2_env.sh"
local LOCKS="${SN2_LOCK_DIR:-$SN2_WORKSPACE/locks}"
local INFO="$LOCKS/heavy.info" GUARD="$LOCKS/.guard" QDIR="$LOCKS/queue"
local IDLE="${SN2_LOCK_IDLE:-600}"
local POLL="${SN2_LOCK_POLL:-15}"
local QTTL="${SN2_LOCK_QTTL:-$(( POLL * 4 > 60 ? POLL * 4 : 60 ))}"   # a queued waiter that has not polled for this long is dead
local PROCS="${SN2_HEAVY_PROCS:-Subnautica2-Win64 UnrealEditor AutomationTool UnrealBuildTool UnrealPak ShaderCompileWorker sn1build Subnautica.exe}"
# UAT (cook_install's BuildCookRun) runs as "dotnet.exe AutomationTool.dll", so its image name never matches AutomationTool: dotnet processes
# count as heavy only when their command line names one of these.
local DOTNET_HEAVY="${SN2_HEAVY_DOTNET:-AutomationTool UnrealBuildTool}"
local ADOPTABLE_FOR_EDITOR="${SN2_ADOPT_EDITOR:-UnrealEditor ShaderCompileWorker}"
local ME="${SN2_LOCK_OWNER:-${CLAUDE_PID:+claude-pid-$CLAUDE_PID}}"
ME="${ME:-manual}"
local ME_PID="${CLAUDE_PID:-}"
[ -n "${SN2_LOCK_OWNER:-}" ] && ME_PID="${SN2_LOCK_OWNER_PID:-}"
mkdir -p "$LOCKS" "$QDIR"

local STALE_WHY="" RUNNING="" MSG=""
declare -gA L
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

# heavy.info is plain key=value lines (also read by src/modkit/tools/ue_run.py). Keys: owner owner_pid what note since seen renewed.
# 'seen' doubles as the last-activity stamp that older copies of this script understand, so renew writes both seen and renewed.
read_info() { L=(); [ -f "$INFO" ] || return 1; while IFS='=' read -r k v; do [ -n "$k" ] && L[$k]="${v%$'\r'}"; done < "$INFO"; return 0; }
write_info() { local tmp="$INFO.tmp.$$"; { for k in owner owner_pid what note since seen renewed; do printf '%s=%s\n' "$k" "${L[$k]:-}"; done; } > "$tmp" && mv -f "$tmp" "$INFO"; }

heavy_running() {  # prints the running heavy image names, one per line
  local re images; re=$(echo "$PROCS" | tr ' ' '|')
  images="$(tasklist //FO CSV //NH 2>/dev/null | cut -d, -f1 | tr -d '"')"
  echo "$images" | grep -iE "^($re)" | sort -u
  if echo "$images" | grep -qix 'dotnet.exe'; then
    local dre; dre=$(echo "$DOTNET_HEAVY" | tr ' ' '|')
    { wmic process where "name='dotnet.exe'" get CommandLine 2>/dev/null \
      || powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='dotnet.exe'\" | ForEach-Object CommandLine" 2>/dev/null; } \
      | grep -oiE "($dre)" | sort -u | sed 's/^/dotnet:/'
  fi
}
pid_alive() { [ -n "$1" ] && tasklist //FI "PID eq $1" //FO CSV //NH 2>/dev/null | grep -q "\"$1\""; }

# --- FIFO queue of waiting sessions: one file per owner, name = <epoch-ns>.<sanitised owner>, content = owner, mtime = last poll ---
qfile_of_me() { local f; for f in "$QDIR"/*."$(printf '%s' "$ME" | tr -c 'A-Za-z0-9_-' '_')"; do [ -f "$f" ] && { echo "$f"; return; }; done; }
q_join() {  # register (keeps position) or refresh my queue entry
  local f; f="$(qfile_of_me)"
  if [ -z "$f" ]; then f="$QDIR/$(date +%s%N).$(printf '%s' "$ME" | tr -c 'A-Za-z0-9_-' '_')"; fi
  printf '%s\n' "$ME" > "$f"
}
q_leave() { local f; f="$(qfile_of_me)"; [ -n "$f" ] && rm -f "$f"; return 0; }
q_head() {  # owner of the first live queue entry (prunes dead ones), empty if none
  local f
  for f in "$QDIR"/*; do
    [ -f "$f" ] || continue
    if [ $(( $(now) - $(stat -c %Y "$f" 2>/dev/null || now) )) -gt "$QTTL" ]; then rm -f "$f"; continue; fi
    head -n1 "$f" | tr -d '\r'; return
  done
}

# sets STALE_WHY to the reason the current holder no longer counts, or empty if the holder is valid; updates 'seen' while heavy processes run
evaluate() {
  STALE_WHY=""
  RUNNING="$(heavy_running)"
  if [ -n "$RUNNING" ]; then L[seen]=$(now); write_info; fi
  if [ -n "${L[owner_pid]:-}" ] && ! pid_alive "${L[owner_pid]}"; then STALE_WHY="holder session gone (pid ${L[owner_pid]})"; return; fi
  local last=${L[since]:-0}
  [ "${L[seen]:-0}" -gt "$last" ] && last=${L[seen]}
  [ "${L[renewed]:-0}" -gt "$last" ] && last=${L[renewed]}
  if [ -z "$RUNNING" ] && [ $(( $(now) - last )) -gt "$IDLE" ]; then STALE_WHY="lease expired: no heavy process and no renewal for $(( $(now) - last )) s > ${IDLE} s"; fi
}

describe() { echo "holder=${L[owner]} what=${L[what]} since=$(date -d "@${L[since]}" '+%H:%M:%S' 2>/dev/null)${L[note]:+ note=${L[note]}}"; }

# one attempt; exit status 0 = held by me; sets MSG. $3 = 1 when I am a --wait caller (queued).
try_acquire() {
  local what="$1" note="$2" queued="${3:-0}" qh
  guard_on
  [ "$queued" = 1 ] && q_join
  if read_info; then
    if [ "${L[owner]}" = "$ME" ]; then
      case ",${L[what]}," in *",$what,"*) ;; *) L[what]="${L[what]},$what" ;; esac
      L[since]=$(now); L[renewed]=$(now); L[owner_pid]="$ME_PID"; [ -n "$note" ] && L[note]="$note"
      write_info; guard_off; q_leave; MSG="held (renewed): $(describe)"; return 0
    fi
    evaluate
    if [ -z "$STALE_WHY" ]; then guard_off; MSG="BUSY: $(describe); running: $(echo $RUNNING)"; return 1; fi
    qh="$(q_head)"
    if [ -n "$qh" ] && [ "$qh" != "$ME" ]; then guard_off; MSG="BUSY: holder ${L[owner]} is stale ($STALE_WHY) but $qh is queued first"; return 1; fi
    log TAKEOVER "from=${L[owner]} reason=$STALE_WHY"
    echo "heavy_lock: taking over from ${L[owner]} ($STALE_WHY)"
    rm -f "$INFO"
  else
    qh="$(q_head)"
    if [ -n "$qh" ] && [ "$qh" != "$ME" ]; then guard_off; MSG="BUSY: free, but $qh is queued first"; return 1; fi
  fi
  RUNNING="$(heavy_running)"
  if [ -n "$RUNNING" ]; then
    local foreign; foreign=$(echo "$RUNNING" | grep -viE "^($(echo "$ADOPTABLE_FOR_EDITOR" | tr ' ' '|'))" || true)
    if [ "$what" != editor ] || [ -n "$foreign" ]; then
      guard_off; MSG="BUSY: no holder, but heavy processes run that no session owns: $(echo $RUNNING) - the previous owner should close them; if none exists, ask the user"; return 1
    fi
    echo "heavy_lock: adopting the already-open editor"
  fi
  L=([owner]="$ME" [owner_pid]="$ME_PID" [what]="$what" [note]="$note" [since]=$(now) [seen]=0 [renewed]=$(now))
  write_info; guard_off; q_leave; log ACQUIRE "what=$what${note:+ note=$note}"
  MSG="acquired: $(describe)"; return 0
}

# holder-only lease reset; exit 0 if I hold the lock
renew_me() {
  guard_on
  if read_info && [ "${L[owner]}" = "$ME" ]; then L[renewed]=$(now); L[seen]=$(now); write_info; guard_off; return 0; fi
  guard_off; return 1
}

local cmd="${1:-status}"; shift || true
case "$cmd" in
  acquire)
    local WHAT="${1:?what (game|editor|cook|build)}"; shift
    local WAIT=0 NOTE="" T0 LASTMSG="" Q=0
    while [ $# -gt 0 ]; do case "$1" in --wait) WAIT="$2"; shift 2 ;; --note) NOTE="$2"; shift 2 ;; *) echo "unknown arg $1"; exit 2 ;; esac; done
    [ "$WAIT" -gt 0 ] && Q=1
    T0=$(now)
    [ "$Q" = 1 ] && trap 'q_leave' EXIT
    while :; do
      if try_acquire "$WHAT" "$NOTE" "$Q"; then echo "heavy_lock: $MSG"; exit 0; fi
      [ "$MSG" != "$LASTMSG" ] && { echo "heavy_lock: $MSG"; LASTMSG="$MSG"; }
      [ $(( $(now) - T0 )) -ge "$WAIT" ] && { echo "heavy_lock: NOT ACQUIRED after $(( $(now) - T0 )) s"; exit 1; }
      sleep "$POLL"
    done ;;
  release)
    guard_on
    if read_info; then
      if [ "${L[owner]}" = "$ME" ] || [ "${1:-}" = --force ]; then
        rm -f "$INFO"; log RELEASE "from=${L[owner]}${1:+ $1}"; guard_off
        local R; R="$(heavy_running)"; echo "heavy_lock: released"
        [ -n "$R" ] && echo "heavy_lock: WARNING still running: $(echo $R) - close what you started; other sessions wait while it runs"
        exit 0
      fi
      guard_off; echo "heavy_lock: not yours ($(describe)); use --force only if the user says so"; exit 1
    fi
    guard_off; echo "heavy_lock: not held"; exit 0 ;;
  check)
    renew_me ;;
  renew)
    renew_me && { echo "heavy_lock: renewed"; exit 0; }; echo "heavy_lock: not held by you"; exit 1 ;;
  hold)
    local EVERY=20 MAX=3600 T1
    while [ $# -gt 0 ]; do case "$1" in --every) EVERY="$2"; shift 2 ;; --max) MAX="$2"; shift 2 ;; *) echo "unknown arg $1"; exit 2 ;; esac; done
    renew_me || { echo "heavy_lock: not held by you, nothing to hold"; exit 1; }
    T1=$(now); log HOLD "start every=${EVERY}s max=${MAX}s"
    while :; do
      sleep "$EVERY"
      [ $(( $(now) - T1 )) -ge "$MAX" ] && { log HOLD "end: max reached"; echo "heavy_lock: hold ended (max ${MAX} s)"; exit 0; }
      [ -n "$ME_PID" ] && ! pid_alive "$ME_PID" && { log HOLD "end: owner pid gone"; exit 0; }
      renew_me || { log HOLD "end: lock no longer mine"; echo "heavy_lock: hold ended (lock no longer yours)"; exit 0; }
    done ;;
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
    echo "queue: $(q_head >/dev/null; for f in "$QDIR"/*; do [ -f "$f" ] && printf '%s ' "$(head -n1 "$f" | tr -d '\r')"; done)"
    echo "you are: $ME" ;;
  *) sed -n 2,23p "$0"; exit 2 ;;
esac
}
heavy_lock_main "$@"
exit $?
