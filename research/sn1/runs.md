# SN1 runs and reference shots

Condensed 2026-11-28 (pass 2). Run-by-run narratives of 2026-11-22/23 removed (full notes: `git show 3449200:research/sn1/runs.md`).
Sources before the split: 11_sn1_modding.md and 00_overview.md "State of play".

## SN1 headless-run facts (runs `sn1_runs/20261122_153001`, `_153935`)
- `sn1_run.sh` run of a new Creative game: launch to menu ~8 s, `newgame creative` at ~9 s, in-game at ~82 s (73 s load), quit at ~89 s, process exits 1 s after `quit`. Total 76-90 s. Timeouts used: 600 s (first), then 240 s (load + 60 s `nearpoll` cap + 120 s post-teleport wait cap); later script runs 360 s / check 120 s. **VERIFIED 2026-11-22.**
- `LogOutput.log` shows `Patching [UnityEngine.CoreModule] with [BepInEx.Chainloader]`, `Loading [SN1Inspector 0.1.0]`, `Chainloader startup complete`, no exception lines. **VERIFIED 2026-11-22.**
- New-game spawn is random per game: seen `x=-24.93 y=1.85 z=307.85` (batch 12-19-14) and `x=10.13 y=1.85 z=-103.75` (batch 12-19-12), biome `Lifepod`; batch 12-18-12 is the Safe Shallows batch. **VERIFIED 2026-11-22.**
- `teleport 0 -50 0` then `pos` right away returns `ERR not ingame (state=loading)` (streamer resettling); script verb `wait ingame 120` after the teleport fixes it (`pos` then `OK x=0.00 y=-50.15 z=0.00`). Script verb `nearpoll <cap_s> <radius> [max]` repeats `near` every 3 s until more than the player is found or the cap passes. **VERIFIED 2026-11-22.**
- `near` returns real names and ClassIds, e.g. `Jumper(Clone) ... classId=fa7fa15c-5515-497f-872d-d6d579a39f60` (creature, found via PrefabIdentifier); at 50 m depth over open water it needed 53 s of streaming (nearpoll). **VERIFIED 2026-11-22.**
- SN1 renders on the hidden desktop: `shots/ingame.png` (in-game `ScreenCapture`, 1280x720) and `shots/ingame_hidden.png` (PrintWindow, 1296x759 incl. frame) are non-black (blue water, "50 m" readout, Creative hotbar of 5 tools, "Power: 100 %", held tool). **VERIFIED 2026-11-22.**
- Saves: 59 pre-existing files checked, 0 changed or missing; a Creative new game made no slot folder (nothing to delete). Registry diff after restore: only `unity.player_session_count` and `unity.player_sessionid` (plus display settings). No `FORCED_KILL`. **VERIFIED 2026-11-22.**

## Test spot 1 (user-chosen, 2026-11-22, user's own Creative save, read live)
- **VERIFIED 2026-11-22 (inspector `status.txt` + `pos`/`biome`/`batch` replies):** the user's seabed spot: pos **x=-1245.47 y=-267.33 z=210.45**, biome `dunes`, batch 5-17-14, depth 267.33 m; nearest terrain `ChunkCollider` centred at (-1248,-272,208). The open-water point 15 m higher (-1245.13, -251.99, 209.50) is the camera spot of the reference shots. Raw: `<Workspace>/reports/sn1_testspot1_status_20261122.txt`.
- `near 60 30` at the open-water point found 258 objects within 60 m (297 colliders): creatures (Boomerang, CaveCrawler, GarryFish, Jumper, RockGrub, SandShark, Peeper, HoopFish, Eyeye, SpadeFish), outcrops `limestone` 7e07fce9-0ad6-4c54-9da7-e43eb1e38cea, `quartz` 8ef17c52-2aa8-46b6-ada3-c3e3c4a78dd6, `sandstone` 5b702ef7-7403-49ee-99c5-1f67ab04954a, and terrain `ChunkCollider(Clone)` objects with no ClassId on a 16 m grid. `near 20 40` on the seabed: 30 objects, 14 of them terrain colliders. So `near` returns static objects and terrain chunks. **VERIFIED 2026-11-22.** Raw: `<Workspace>/reports/sn1_testspot1_near_20261122.txt`.
- The plugin works in a normal user-launched game (not only under `sn1_run.sh`): `status.txt` updates live, `cmd.txt` commands from outside are answered within ~1 s. `status.txt` printed `gamemode=Survival, Creative` for the Creative save (flags enum as-is). **VERIFIED 2026-11-22.**

## Camera control, FOV and terrain dump (2026-11-22; script `src/tools/sn1_scripts/spot1_shots.sn1s`; runs took ~50 s; final run `sn1_runs/20261122_160742`)
Verbs in `src/sn1mods/SN1Inspector/Plugin.cs`:
- `look <yaw> <pitch>`: sets `MainCameraControl.rotationX` (yaw degrees, 0 = +Z, 90 = +X, clockwise from above) and `rotationY` (pitch, + = up), widens `minimumY/maximumY` to +-89, waits 3 frames and corrects yaw by the measured world-yaw error. Deferred reply (coroutine, `pendingId`). **VERIFIED 2026-11-22:** all 8 yaws returned exact values; pitch 89 gives `euler.x=-89` (Unity euler.x is negative looking up). The `pos` verb prints the raw euler pitch, so after `look 0 -89` it shows `pitch=89.00`.
- `cam`: **VERIFIED 2026-11-22:** `fovV=60.00 fovH=91.49 aspect=1.7778 screen=1280x720 near=0.03 far=1700 cam=MainCamera`. Unity `fieldOfView` is vertical (horizontal = 2*atan(tan(30deg)*1.7778)). The camera sits ~0.15 m behind and ~0.03 m above the player transform.
- `chunkinfo`: diagnostic for the 3 nearest terrain ChunkColliders (bounds, vertex counts).
- `dumpterrain <radius_m> <file>`: bare filename goes to `<SN1Dir>/BepInEx/SN1Inspector/`, rooted path as-is; sidecar `.txt` has the player position. Unity world space, one `o` group per object.
  - Fallback A (`<name>_render.obj`): `TerrainChunkPiece.Mesh()` render meshes where `isReadable`: 834 of 1053 pieces, 508,288 triangles (26 MB). **VERIFIED 2026-11-22 (file written).**
  - Fallback B (main OBJ): raycast layer 30 on a 2 m XZ grid (`o heightfield`, `o points_down_extra`, `o points_up`): 3059 verts, 4945 tris, 3306 down hits, 362 up hits; coverage limited to y +-r around the player.
  - Outputs in `<Workspace>/reports/sn1_spot1_shots/` (`spot1_terrain.obj`, `spot1_terrain.txt`, `spot1_terrain_render.obj`); the extractor compares against `spot1_terrain_render.obj` (full mesh) or `spot1_terrain.obj`.
- Dead ends:
  - **FAILED 2026-11-22** collider OBJ dump: the 103 terrain `ChunkCollider(Clone)` MeshColliders within 120 m have `sharedMesh.vertexCount == 0` (cooked physics mesh, CPU copy cleared), so 0 triangles. Colliders: 16 m grid, bounds ~16.5 x 5.9 x 16.3, layer 30, component `TerrainChunkPieceCollider`.

## Spot 1 reference shots (1280x720, pitch 0 unless stated; **VERIFIED 2026-11-22, viewed `<Workspace>/reports/sn1_spot1_shots/*.png`**)
Position x=-1245.13 y=-252.16 z=209.50, depth readout 252 m; position drift across all shots 0. HUD and held tool visible in all; a PDA tutorial text box overlays the lower middle in most (hide HUD/PDA text before pixel comparison with SN2).
- yaw 000: dark blue water, sandy slope falling left, fish silhouette, low flora bottom right.
- yaw 045: open sandy seabed, sparse flora, ridge at right edge, deeper water band along the top.
- yaw 090: large rock arch/pillar with orange coral, grass flora in front, small blue jellyfish-like creature.
- yaw 135: rock arch with orange coral left, glowing fish schools through the opening, sand cloud.
- yaw 180: tall rock pillar with orange coral at its base, fish school upper left.
- yaw 225: rock mass left with orange coral and white sand puffs, seabed sloping right into dark water.
- yaw 270: mostly empty dark water, seabed slope lower left with flora.
- yaw 315: dark water, glowing fish school left, sandy slope lower right, a red creature.
- up (pitch 89): uniform dark blue (surface 252 m away). down (pitch -89): sandy seabed with ripple light, bush flora, fish shoals, player fin and hands.

## Origin shots (2026-11-23)
- Script `src/tools/sn1_scripts/origin_shots.sn1s`: `teleport 40 -18 -10` (SN1 side of the origin cube plan), 8 yaws + up + down, shots `origin_*.png`. Run `sn1_runs/20261123_170955`: DONE, 138 s, 10 shots, no test slot left. **VERIFIED (2026-11-23, run folder, shots viewed).**
- Viewpoint 9.1 m above the seabed, 18-19 m deep, ~41 m SSW of the lifepod: rock slab with a spire (yaw 270), floating rock with pink coral (yaw 0), plants, fish, a tube-shaped prefab on the seabed (down), blue sky with clouds (up).
