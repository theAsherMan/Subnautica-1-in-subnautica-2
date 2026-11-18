#!/usr/bin/env bash
# Wait until the running game has really exited (3 consecutive checks, 2 s apart), then relaunch it through Steam.
# Run with the Bash tool's run_in_background=true; you get one notification when the relaunch is sent.
# If the game is not running when started, it relaunches immediately.
# NOTE: tasklist truncates image names to 25 chars -> match "Subnautica2-Win64", not the full exe name.
gone=0
while [ $gone -lt 3 ]; do
  if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then gone=0; else gone=$((gone+1)); fi
  sleep 2
done
echo "game exited at $(date +%H:%M:%S); relaunching"
sleep 4
bash "$(dirname "$0")/launch_game.sh"
echo "relaunch sent $(date +%H:%M:%S)"
