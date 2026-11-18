#!/usr/bin/env bash
# Copy a mod from src/mods into the game and into the drop-in install bundle.
# Usage: bash src/tools/install_mod.sh <ModName>        e.g. bash src/tools/install_mod.sh SN2WorldProbe
# Copies Scripts/ and data/ (if present), creates enabled.txt, and registers the mod in mods.txt. Paths come from local.config.
set -euo pipefail
. "$(dirname "$0")/sn2_env.sh"
MOD="${1:?mod name}"
SRC="$SN2_REPO/src/mods/$MOD"
GAME="$SN2_UE4SS_DIR/Mods"
BUNDLE="$SN2_WORKSPACE/install/Win64/ue4ss/Mods"
[ -f "$SRC/Scripts/main.lua" ] || { echo "no $SRC/Scripts/main.lua"; exit 1; }
[ -d "$GAME" ] || { echo "UE4SS Mods folder not found: $GAME (install UE4SS, check SN2_GAME_DIR)"; exit 1; }
for DST in "$GAME" "$BUNDLE"; do
  mkdir -p "$DST/$MOD/Scripts"
  cp "$SRC/Scripts/"*.lua "$DST/$MOD/Scripts/"
  if [ -d "$SRC/data" ]; then mkdir -p "$DST/$MOD/data"; cp -r "$SRC/data/." "$DST/$MOD/data/"; fi
  : > "$DST/$MOD/enabled.txt"
  touch "$DST/mods.txt"
  grep -q "^$MOD :" "$DST/mods.txt" || printf '%s : 1\n' "$MOD" >> "$DST/mods.txt"
done
echo "installed $MOD ($(wc -l < "$SRC/Scripts/main.lua") lines) into game + bundle"
if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then
  echo "NOTE: the game is running; UE4SS only reads Lua at launch -> quit + relaunch to pick this up"
fi
