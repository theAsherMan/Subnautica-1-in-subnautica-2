#!/usr/bin/env bash
# Cook + package the modkit project and install one Blueprint mod's pak chunk into the game's LogicMods folder
# (same steps as the SN2 Mod Tools "Cook & Install" menu, but scriptable and with TEMP inside SN2_MODKIT_DIR).
# Usage: bash src/modkit/tools/cook_install.sh <ModName> <ChunkId>      e.g. bash src/modkit/tools/cook_install.sh SN2Terrain 1
# ChunkId = Rules.ChunkId of Content/Mods/<ModName>/PAL_<ModName>. Log: <SN2_MODKIT_DIR>/cook_<ModName>.log
# First run builds the Shipping target (~12 min) + full cook (~7 min); later runs are incremental.
set -euo pipefail
. "$(dirname "$0")/../../tools/sn2_env.sh"
MOD="${1:?mod name}"; CHUNK="${2:?chunk id}"
: "${SN2_MODKIT_DIR:?set SN2_MODKIT_DIR in local.config}"
ENGINE="${SN2_ENGINE_DIR:-$SN2_MODKIT_DIR/UE_5.6_SN2}"
PROJ="$SN2_MODKIT_DIR/Subnautica2-Project"
LOG="$SN2_MODKIT_DIR/cook_$MOD.log"
win() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
export TEMP="$(win "$SN2_MODKIT_DIR/Temp")" TMP="$(win "$SN2_MODKIT_DIR/Temp")"
mkdir -p "$SN2_MODKIT_DIR/Temp"
cmd.exe //c "$(win "$ENGINE/Engine/Build/BatchFiles/RunUAT.bat") BuildCookRun -project=$(win "$PROJ/Subnautica2.uproject") -platform=Win64 -clientconfig=Shipping -build -cook -stage -pak -iostore -archive -archivedirectory=$(win "$PROJ")\\ -nocompileeditor -installed -iterativecooking -cookincremental -nop4 -utf8output -unattended" > "$LOG" 2>&1 || { echo "COOK FAILED - see $LOG"; tail -5 "$LOG"; exit 1; }
grep -E "Packages Cooked|BUILD SUCCESSFUL" "$LOG" | tail -2
PAKS="$PROJ/Windows/Subnautica2/Content/Paks"
DST="$SN2_GAME_DIR/Subnautica2/Content/Paks/LogicMods/$MOD"
if tasklist 2>/dev/null | grep -qi "Subnautica2-Win64"; then echo "game is running - quit it, then re-run to install"; exit 1; fi
mkdir -p "$DST"
for e in pak ucas utoc; do cp "$PAKS/pakchunk$CHUNK-Windows.$e" "$DST/$MOD.$e"; done
ls -la "$DST"
echo "installed $MOD (chunk $CHUNK). Uninstall = delete $DST"
