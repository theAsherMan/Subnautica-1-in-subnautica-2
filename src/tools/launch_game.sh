#!/usr/bin/env bash
# Launch Subnautica 2 with the project's start options. Steam must be running.
# Default option: -OverridePlayerStart=Shallows  = new games skip the intro and start with an empty hotbar (VERIFIED 2026-11-18, see research/09).
# Usage: bash src/tools/launch_game.sh [extra game args...]      e.g. SN2_START=Deep bash src/tools/launch_game.sh   (SN2_START=none -> no override)
# Why not steam://run/<id>//<args>/: Steam did not start the game from that URL (2026-11-18); starting the exe directly with SteamAppId set works.
. "$(dirname "$0")/sn2_env.sh"
START="${SN2_START:-Shallows}"
ARGS="$*"
[ "$START" != "none" ] && ARGS="-OverridePlayerStart=$START $ARGS"
DIR="$SN2_GAME_DIR/Subnautica2/Binaries/Win64"
powershell -NoProfile -c "\$d=(Resolve-Path '$DIR').Path; \$env:SteamAppId='1962700'; \$env:SteamGameId='1962700'; Start-Process -FilePath \"\$d\Subnautica2-Win64-Shipping.exe\" -WorkingDirectory \$d -ArgumentList '$ARGS'"
echo "launched with: $ARGS"
