# Offline tools

Pass-1 text: `git show 3449200:research/process/offline_tools.md`.

## Offline tools (in `tools\bin\`, SHA-256 verified at download; never run yet)
- `repak.exe` v0.2.3 — unpack legacy pak: `repak unpack <pak> -o <dir>` (the `.ini` configs live in `Subnautica2-Windows.pak`).
- `retoc.exe` v0.1.5 — IoStore ↔ legacy; needed to build asset mods (`to-zen`). SN2 loads only IoStore triples (`.pak/.utoc/.ucas`), not plain `.pak`.
- Earlier attempts to run them were blocked by the Claude Code auto-mode classifier; ask the tester to allow if needed.
- FModel (not installed) + `.usmap` from UE4SS GUI → Dumpers tab, for browsing asset contents (Data Asset fields).
- Subnautica2-Project modkit (github.com/Subnautica2Modding/Subnautica2-Project): custom UE 5.6 cooked editor; ~60 GB, Epic↔GitHub link, VS 2022 MSVC 14.38,
  FMOD for Unreal 2.03.x. Packages pak chunks (id 1–300) → `Content\Paks\LogicMods\<Mod>\<Mod>.pak/.utoc/.ucas`; content-only plugins in `<game>\Mods\` auto-register items/recipes/etc.
- Packaged file list (43,525 paths, from `Manifest_UFSFiles_Win64.txt`): `tools\sn2_packaged_files.txt` — grep it to find asset paths.
