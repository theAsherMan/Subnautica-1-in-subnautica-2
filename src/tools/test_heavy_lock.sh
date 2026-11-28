#!/usr/bin/env bash
# Automated tests for heavy_lock.sh. Uses a temp lock dir and a fake "heavy" process (a copy of ping.exe renamed sn2testheavy.exe), so the real
# lock, the game and the editor are never touched. Takes ~1.5 min.
#   bash src/tools/test_heavy_lock.sh [path-to-heavy_lock.sh]     (default: the sibling heavy_lock.sh)
HERE="$(cd "$(dirname "$0")" && pwd)"
HL="${1:-$HERE/heavy_lock.sh}"
T="$(mktemp -d)"
export SN2_LOCK_DIR="$T/locks" SN2_HEAVY_PROCS="sn2testheavy sn2testadopt" SN2_HEAVY_DOTNET="sn2nomatchxyz" SN2_ADOPT_EDITOR="sn2testadopt"
export SN2_LOCK_IDLE=6 SN2_LOCK_POLL=1 SN2_LOCK_QTTL=5
unset CLAUDE_PID SN2_LOCK_OWNER SN2_LOCK_OWNER_PID
FAKE="$T/sn2testheavy.exe"; cp "$(command -v ping)" "$FAKE" 2>/dev/null || cp /c/Windows/System32/PING.EXE "$FAKE"
ADOPT="$T/sn2testadopt.exe"; cp "$FAKE" "$ADOPT"
PASS=0; FAILN=0
ok()   { PASS=$((PASS+1)); echo "PASS  $1"; }
bad()  { FAILN=$((FAILN+1)); echo "FAIL  $1"; }
# as <owner> <args...>: run heavy_lock.sh as that owner; sets RC and OUT
as() { local o="$1"; shift; OUT="$(SN2_LOCK_OWNER="$o" bash "$HL" "$@" 2>&1)"; RC=$?; }
expect() { local name="$1" want="$2"; if [ "$RC" = "$want" ]; then ok "$name"; else bad "$name (rc=$RC want $want) :: $OUT"; fi; }
reset() { rm -rf "$SN2_LOCK_DIR"; }
heavy_start() { "$FAKE" -t localhost >/dev/null 2>&1 & HPID=$!; sleep 1; }
heavy_stop() { taskkill //F //IM sn2testheavy.exe >/dev/null 2>&1; taskkill //F //IM sn2testadopt.exe >/dev/null 2>&1; HPID=""; sleep 1; }
cleanup() { heavy_stop; jobs -p | xargs -r kill 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT

echo "== script under test: $HL"
reset
as A acquire game --note t1;                 expect "1 free -> A acquires" 0
as B acquire game;                           expect "2 B busy while A holds (rc 1)" 1
as A check;                                  expect "3 check: holder 0" 0
as B check;                                  expect "3b check: non-holder 1" 1
as B release;                                expect "3c non-holder release refused (rc 1)" 1
as A acquire editor;                         expect "4 A re-acquire refreshes" 0
echo "$OUT" | grep -q renewed || grep -q 'what=game,editor' <<<"$OUT" || bad "4b what list: $OUT"
as A bogus;                                  expect "5 unknown command rc 2" 2
as A acquire game --bad;                     expect "5b unknown arg rc 2" 2

echo "== gap inside lease keeps the lock (acceptance 1)"
sleep 3; as B acquire game;                  expect "6 gap 3 s < lease 6 s: B still busy" 1
echo "== lease expiry frees a forgotten lock (acceptance 2)"
sleep 5; as B acquire game;                  expect "7 idle > lease: B takes over" 0
grep -q 'TAKEOVER.*from=A' "$SN2_LOCK_DIR/history.log" && ok "7b takeover logged" || bad "7b takeover not logged"

echo "== renew / check / hold extend the lease"
reset; as A acquire game
for i in 1 2 3 4 5; do sleep 2; as A renew; done; expect "8 renew works (rc 0)" 0
as B acquire game;                           expect "8b 10 s of renews > lease, B still busy" 1
reset; as A acquire game
for i in 1 2 3 4 5; do sleep 2; as A check; done
as B acquire game;                           expect "9 check renews the lease" 1
reset; as A acquire game
( SN2_LOCK_OWNER=A bash "$HL" hold --every 1 --max 60 >/dev/null 2>&1 & echo $! > "$T/hold.pid" )
sleep 10; as B acquire game;                 expect "10 hold heartbeat keeps lock through a 10 s gap" 1
as A release; sleep 2
grep -q "HOLD owner=A end: lock no longer mine" "$SN2_LOCK_DIR/history.log" && ok "10b hold exits after release" || bad "10b hold did not exit"
as B acquire game;                           expect "10c B acquires after A released" 0
as B release

echo "== dead owner pid is freed immediately (acceptance 2)"
reset
"$FAKE" -n 1 localhost >/dev/null 2>&1 & DP=$!; WP=$(cat /proc/$DP/winpid); wait $DP
SN2_LOCK_OWNER_PID=$WP as A acquire game
SN2_LOCK_OWNER_PID="" as B acquire game;     expect "11 owner pid dead -> B takes over at once" 0
grep -q 'holder session gone' "$SN2_LOCK_DIR/history.log" && ok "11b reason logged" || bad "11b reason missing"
reset
"$FAKE" -t localhost >/dev/null 2>&1 & LP=$!; WP=$(cat /proc/$LP/winpid)
SN2_LOCK_OWNER_PID=$WP as A acquire game
as B acquire game;                           expect "11c owner pid alive -> B busy" 1
kill $LP 2>/dev/null; taskkill //F //PID "$WP" >/dev/null 2>&1

echo "== heavy process checks (acceptance 3)"
reset
as A acquire game; expect "12 A acquires" 0; heavy_start
sleep 8; as B acquire game;                  expect "12b heavy process running keeps lock past the lease" 1
as A release; echo "$OUT" | grep -q WARNING && ok "12c release warns about running heavy process" || bad "12c no warning: $OUT"
as B acquire game;                           expect "12d unowned heavy process blocks (no holder)" 1
heavy_stop
as B acquire game;                           expect "12e free after heavy stops" 0
as B release
"$ADOPT" -t localhost >/dev/null 2>&1 & sleep 1
as A acquire game;                           expect "13 non-editor cannot adopt an open editor-like process" 1
as A acquire editor;                         expect "13b editor adopts the open editor" 0
heavy_stop; reset

echo "== FIFO fairness (acceptance 4)"
as A acquire game
( as B acquire game --wait 60 --note b ; echo "$RC" > "$T/B.rc" ) >"$T/B.out" 2>&1 &
sleep 2
( as C acquire game --wait 60 --note c ; echo "$RC" > "$T/C.rc" ) >"$T/C.out" 2>&1 &
sleep 2
as A release; expect "14 A releases" 0
as A acquire game;                           expect "14b releasing holder cannot re-acquire ahead of waiters (rc 1)" 1
sleep 3
grep -q 'holder=B' <(bash "$HL" status) && ok "14c B (first in queue) holds it" || bad "14c B does not hold: $(bash "$HL" status)"
[ ! -f "$T/C.rc" ] && ok "14d C still waiting" || bad "14d C finished early"
as D acquire game;                           expect "14e newcomer D (wait 0) refused while C queued" 1
as B release
sleep 3
grep -q 'holder=C' <(bash "$HL" status) && ok "15 C gets it next" || bad "15 C does not hold: $(bash "$HL" status)"
as C release
as A acquire game;                           expect "16 queue empty again: A acquires" 0
as A release
ls "$SN2_LOCK_DIR/queue" | grep -q . && bad "16b queue files left: $(ls "$SN2_LOCK_DIR/queue")" || ok "16b queue is empty"

echo "== stale holder goes to the queue head, not a newcomer (acceptance 4)"
reset; as A acquire game
( as B acquire game --wait 60 ; echo "$RC" > "$T/B2.rc" ) >/dev/null 2>&1 &
sleep 9    # A idles past the 6 s lease; B (waiting) takes over at its next poll
as C acquire game;                           expect "17 C refused, B has the lock" 1
grep -q 'holder=B' <(bash "$HL" status) && ok "17b B took the stale lock" || bad "17b status: $(bash "$HL" status)"
as B release
reset; as A acquire game; as A release
mkdir -p "$SN2_LOCK_DIR/queue"; echo ghost > "$SN2_LOCK_DIR/queue/1.ghost"; touch -d '2 minutes ago' "$SN2_LOCK_DIR/queue/1.ghost"
as C acquire game;                           expect "18 queue entry of a dead waiter (no poll > QTTL) is pruned, C acquires" 0

echo; echo "RESULT: $PASS passed, $FAILN failed"
[ "$FAILN" = 0 ]
