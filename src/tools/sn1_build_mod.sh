#!/usr/bin/env bash
# Build a Subnautica 1 BepInEx plugin and install it.  Usage: bash src/tools/sn1_build_mod.sh <Mod>
# Builds src/sn1mods/<Mod>/<Mod>.csproj (net472, references from <SN1Dir>), copies <Mod>.dll to <SN1Dir>/BepInEx/plugins/<Mod>/.
# Refuses while Subnautica.exe is running (the dll would be locked / the game folder is in use).
. "$(dirname "$0")/sn2_env.sh"
: "${SN1_GAME_DIR:?set SN1_GAME_DIR in local.config}"
MOD="${1:?usage: sn1_build_mod.sh <Mod>}"
PROJ="$SN2_REPO/src/sn1mods/$MOD/$MOD.csproj"
[ -f "$PROJ" ] || { echo "REFUSED: $PROJ not found"; exit 2; }
if tasklist 2>/dev/null | grep -qi "^Subnautica.exe"; then echo "REFUSED: Subnautica.exe is running"; exit 3; fi
[ -f "$SN1_GAME_DIR/BepInEx/core/BepInEx.dll" ] || { echo "REFUSED: BepInEx not installed in the SN1 folder (see research/11_sn1_modding.md)"; exit 4; }
dotnet build "$PROJ" -c Release -p:SN1Dir="$SN1_GAME_DIR" -nologo -v:m || exit 5
DLL="$SN2_REPO/src/sn1mods/$MOD/bin/Release/net472/$MOD.dll"
[ -f "$DLL" ] || { echo "build produced no $DLL"; exit 6; }
mkdir -p "$SN1_GAME_DIR/BepInEx/plugins/$MOD"
cp -f "$DLL" "$SN1_GAME_DIR/BepInEx/plugins/$MOD/$MOD.dll" && echo "installed $MOD.dll -> BepInEx/plugins/$MOD/"
