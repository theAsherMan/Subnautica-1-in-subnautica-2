# SN1 runs and reference shots

Sources: 11_sn1_modding.md "Run 1 (2026-11-22, `sn1_runs/20261122_153001`, `--timeout 60", 11_sn1_modding.md "Run 2 (2026-11-22, `sn1_runs/20261122_153935`, `--timeout 24", 11_sn1_modding.md "Test spot 1 (user-chosen, 2026-11-22, user's own Creative sa", 11_sn1_modding.md "Camera control, FOV and terrain dump (2026-11-22, spot 1 sho", 11_sn1_modding.md "Spot 1 reference shots (1280x720, pitch 0 unless stated, HUD", 11_sn1_modding.md "Origin shots run (2026-11-23)", 00_overview.md "State of play" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## Run 1 (2026-11-22, `sn1_runs/20261122_153001`, `--timeout 600 --check 120`, result DONE, total 90 s)
Phases: launch 0.6 s, `status.txt` after 5 s, menu after 2 s more, `newgame creative` at 8.9 s, ingame at 82.3 s (73 s load), quit at 89.1 s, process exit 1 s after the command. No CHECK line fired (run shorter than 120 s). Timeout reasoning: 600 s is about 6.5x the measured 90 s; later runs can use 180-240 s (load 73 s + margin).
- `LogOutput.log`: `Patching [UnityEngine.CoreModule] with [BepInEx.Chainloader]`, `Chainloader ready/started`, `Loading [SN1Inspector 0.1.0]`, `SN1Inspector loaded, io folder ...`, `Chainloader startup complete`; no exception lines. **VERIFIED 2026-11-22.**
- In world: `pos x=-24.93 y=1.85 z=307.85`, `biome Lifepod`, `batch 12-19-14` (the lifepod spawn; batch 12-18-12 is the Safe Shallows batch in `research/sn1/README.md`). **VERIFIED 2026-11-22.**
- `teleport 0 -50 0` -> `OK`; the next `pos` came back `ERR not ingame (state=loading)` (the streamer was resettling, 3 s was not enough); `near 30 20` 0.3 s later returned `1 objects within 30 m: [Player pos=0.00,-50.98,0.00 d=0.00 classId=-]` (player transform 0.98 m below the target y, within 1 m), and the last status snapshot read `pos x=0.00 y=-50.98 z=0.00`, `depth 50.98`, `biome safeShallows`, `batch 12-18-12`. Open: the world had not streamed objects around (only the player collider within 30 m), so `near` returning names/ClassIds is **not yet shown**; retry after the added `wait ingame 120`. UNTESTED.
- Screenshots: `shots/ingame.png` (in-game `ScreenCapture`, 1280x720) and `shots/ingame_hidden.png` (PrintWindow, 1296x759 with the window frame) both show the same view, non-black: open blue water, depth readout "50 m" at the top, a Creative hotbar of 5 tools at the bottom, a fabricator hint text box ("The fabricator draws from available data ...") and "Grab item / Load item from inventory", "Power: 100 %", a small HUD marker icon above the crosshair, a held tool at the bottom right, a rounded brown-orange frame around the edges (appears to be a vehicle or pod window). **VERIFIED 2026-11-22.** SN1 renders on the hidden desktop.
- Exit: `process exited 1 s after quit`; `FORCED_KILL` not used; pre-existing save files: 59 checked, 0 changed or missing; no slot folder created; registry diff 17 lines = display settings and Unity session counters (see Game facts).

## Run 2 (2026-11-22, `sn1_runs/20261122_153935`, `--timeout 240 --check 60`, result DONE, 76 s)
Timeout reasoning: run 1 took 90 s (73 s of it loading); 240 s covers load + a 60 s `nearpoll` cap + 120 s post-teleport wait cap.
- Script change: `wait ingame 120` after the teleport, and new script verb `nearpoll <cap_s> <radius> [max]` (repeat `near` every 3 s until more than the player is found or the cap passes).
- Random spawn differs per new game: run 1 x=-24.93 z=307.85, run 2 x=10.13 y=1.85 z=-103.75 (biome Lifepod, batch 12-19-12). **VERIFIED 2026-11-22.**
- `teleport 0 -50 0` -> OK; `pos` 2.7 s later -> `OK x=0.00 y=-50.15 z=0.00` (0.15 m from target; the `wait ingame` step fixed the run 1 `ERR not ingame`). **VERIFIED 2026-11-22.**
- `nearpoll` needed 53 s (until the cap passed the streaming wait) and then returned `OK 2 objects within 30.00 m (colliders 2)`: the Player and `Jumper(Clone) pos=-2.79,-28.43,-18.34 d=28.56 classId=fa7fa15c-5515-497f-872d-d6d579a39f60` (a creature, found via its PrefabIdentifier). `near` therefore returns real names and ClassIds. **VERIFIED 2026-11-22.** Only one non-player object at 50 m depth over open water is plausible; terrain colliders did not appear within 30 m, so whether terrain/static geometry counts as objects is open (the poll stopped at the first extra object; it was not tried at a radius with known static objects).
- Screenshot `shots/ingame.png` (1280x720): open blue water, "50 m" depth readout, fabricator hint box with a tutorial-style note text, Creative hotbar of 5 tools, "Power: 100 %", held tool at bottom right. Non-black. **VERIFIED 2026-11-22.**
- Saves: 59 pre-existing files, 0 changed or missing; no new files; no slot created (nothing to delete). Registry diff after restore: only `unity.player_session_count` and `unity.player_sessionid`. 0 Subnautica.exe left, lock FREE.

## Test spot 1 (user-chosen, 2026-11-22, user's own Creative save, read live while the user played)
- **VERIFIED 2026-11-22 (inspector `status.txt` + `pos`/`biome`/`batch` replies):** pos **x=-1245.47 y=-267.33 z=210.45**, yaw 222.64, pitch -2.33, depth 267.33 m, biome `dunes`, batch 5-17-14. The player is resting on the sand seabed (user). The nearest terrain `ChunkCollider` is centred at (-1248,-272,208). A first reading 15 m higher, in open water, was superseded by the user: (-1245.13, -251.99, 209.50). Raw: `<Workspace>/reports/sn1_testspot1_status_20261122.txt`.
- `near 20 40` on the seabed: 30 objects within 20 m (33 colliders), 14 of them terrain `ChunkCollider` objects. Earlier, `near 60 30` at the open-water point found `258 objects within 60.00 m (colliders 297)`. Among them are creatures (Boomerang, CaveCrawler, GarryFish, Jumper, RockGrub, SandShark, Peeper, HoopFish, Eyeye, SpadeFish), resource outcrops `limestone` 7e07fce9-0ad6-4c54-9da7-e43eb1e38cea, `quartz` 8ef17c52-2aa8-46b6-ada3-c3e3c4a78dd6, `sandstone` 5b702ef7-7403-49ee-99c5-1f67ab04954a, and terrain **`ChunkCollider(Clone)` objects with no ClassId at positions on a 16 m grid** (e.g. (-1248,-272,208), (-1232,-240,192)). So `near` does return static objects and terrain collider chunks. **VERIFIED 2026-11-22.** Raw: `<Workspace>/reports/sn1_testspot1_near_20261122.txt`.
- The plugin works in a normal user-launched game (not only under `sn1_run.sh`): `status.txt` updates live, and `cmd.txt` commands written from outside are answered within ~1 s. `status.txt` reported `gamemode=Survival, Creative` for this Creative save (flags enum printed as-is).
- The `pos` reply and `status.txt` pitch values differ a few seconds apart (54.38 vs -2.10), because the player was looking around; the position was identical.

## Camera control, FOV and terrain dump (2026-11-22, spot 1 shots, runs `sn1_runs/20261122_160509` (run 1), `_160632` (chunkinfo diagnostic), `_160742` (run 3, final); script `src/tools/sn1_scripts/spot1_shots.sn1s`; timeout 360 s / check 120 s, runs took ~50 s)
New SN1Inspector verbs (`src/sn1mods/SN1Inspector/Plugin.cs`):
- `look <yaw> <pitch>`: sets `MainCameraControl.rotationX` (yaw, degrees, 0 = +Z, 90 = +X, clockwise from above) and `rotationY` (pitch, + = up); widens `minimumY/maximumY` to +-89; waits 3 frames and corrects yaw by the measured world-yaw error. Reply: `OK yaw=.. pitch=.. (requested ..; pitch reported + = up; euler.x=..)`. Deferred reply (coroutine, `pendingId`). **VERIFIED 2026-11-22:** all 8 yaws returned exact values; pitch 89 gives `euler.x=-89` (Unity euler.x is negative when looking up), pitch -89 gives `euler.x=89`. The `pos` verb prints the raw euler pitch, so after `look 0 -89` it shows `pitch=89.00` (opposite sign to `look`).
- `cam`: **VERIFIED 2026-11-22:** `pos=-1245.13,-252.12,209.35 euler=0,0,0 fovV=60.00 fovH=91.49 aspect=1.7778 screen=1280x720 pixel=1280x720 near=0.03 far=1700 cam=MainCamera player=-1245.13,-252.16,209.50`. Unity `fieldOfView` is vertical: vertical 60 deg, horizontal 91.49 deg at 16:9 (2*atan(tan(30deg)*1.7778)). The camera sits ~0.15 m behind and ~0.03 m above the player transform (eye pos y = player y + ~0.04 here).
- `chunkinfo`: diagnostic for the 3 nearest terrain ChunkColliders (bounds, vertex counts).
- `dumpterrain <radius_m> <file>`: bare filename goes to `<SN1Dir>/BepInEx/SN1Inspector/`, rooted path as-is; sidecar `.txt` has the player position. Unity world space, one `o` group per object.
  - **FAILED 2026-11-22 (collider route):** the 103 terrain `ChunkCollider(Clone)` MeshColliders within 120 m have `sharedMesh.vertexCount == 0` (cooked physics mesh, CPU copy cleared), so a collider OBJ has 0 triangles. Colliders sit on a 16 m grid (centres like -1248,-272,208), bounds ~16.5 x 5.9 x 16.3, layer 30, component `TerrainChunkPieceCollider`.
  - Fallback A (`<name>_render.obj`): `TerrainChunkPiece.Mesh()` render meshes where `isReadable`: 834 of 1053 pieces readable, 508,288 triangles (26 MB). **VERIFIED 2026-11-22 (file written).**
  - Fallback B (main OBJ): raycast layer 30 on a 2 m XZ grid (RaycastAll down from y+r, up from y-r): `o heightfield` (first hit, triangulated where neighbours differ < 1.5 m), `o points_down_extra`, `o points_up`. Run 3: 3059 verts, 4945 tris, 3306 down hits, 362 up hits. Coverage limited to y +-r around the player.
  - Outputs copied to `<Workspace>/reports/sn1_spot1_shots/` (`spot1_terrain.obj`, `spot1_terrain.txt`, `spot1_terrain_render.obj`). The extractor should compare against `spot1_terrain_render.obj` (full mesh) or `spot1_terrain.obj` (collider surface sampled at 2 m).
- Timing: after `teleport` to spot 1 `wait ingame` passed in 0 s and `nearpoll 60 30` found 59 objects at once (no long stream wait this time). Position drift across all shots: 0 (y stays -252.16).
- Saves: 59 pre-existing files, 0 changed; no new slot created (Creative new game made no slot dir), so no deleted_slots.txt.

## Spot 1 reference shots (1280x720, pitch 0 unless stated, HUD and held tool visible in all; **VERIFIED 2026-11-22, viewed `<Workspace>/reports/sn1_spot1_shots/*.png`**)
Position x=-1245.13 y=-252.16 z=209.50, depth readout 252 m.
- yaw 000: dark blue water, sandy slope falling to the left, dark deeper water upper left, a fish silhouette, low flora bottom right.
- yaw 045: open sandy seabed with sparse flora, ridge/rock at the right edge, dark band of deeper water along the top, small fauna and glowing plankton.
- yaw 090: large rock arch/pillar with orange coral, sandy seabed with grass flora in front, small blue jellyfish-like creature.
- yaw 135: large rock arch in front with orange coral on the left, glowing fish schools seen through the opening, sand cloud and a fish at the bottom.
- yaw 180: tall rock pillar centre with orange coral at its base, fish school upper left, sandy floor to the left.
- yaw 225: rock mass on the left with orange coral and white smoke-like sand puffs, sloping seabed to the right falling into dark water.
- yaw 270: mostly empty dark water, seabed slope at the lower left with flora and a small glowing school.
- yaw 315: dark water, glowing fish school left, sandy slope falling off to the lower right, a red creature at lower right.
- up (pitch 89): uniform dark blue water with a slightly lighter blue centre (surface is 252 m away), tool lower right.
- down (pitch -89): sandy seabed with ripple light patterns, bush flora, small fish shoals, player fin and hands visible.
- The 8 yaw shots all differ in content (checked by eye). A PDA tutorial text box overlays the lower middle in most shots (different text per shot); a Creative hotbar and "Power: 100 %" are always shown. Not removed from the shots; hide HUD/PDA text before a pixel comparison with SN2.

## Origin shots run (2026-11-23)
- Script `src/tools/sn1_scripts/origin_shots.sn1s`: `teleport 40 -18 -10` (the SN1 side of the origin cube plan), 8 yaws + up + down, shots named `origin_*.png`. Run `sn1_runs/20261123_170955`: DONE, 138 s, timeout 360 s / check 120 s, 10 shots, no test slot left. VERIFIED (2026-11-23, run folder, shots viewed).
- Viewpoint is 9.1 m above the seabed, 18-19 m deep, about 41 m SSW of the lifepod. Shots show a rock slab with a spire (yaw 270), a floating rock with pink coral (yaw 0), plants and fish, a tube-shaped prefab on the seabed (down), blue sky with clouds (up).

## State of play detail (moved from 00_overview.md, 2026-11-28)

| Capability | Status |
|---|---|
| SN1 reference shots (open-water point, 8 yaws + up + down) via `sn1_run.sh` | **VERIFIED 2026-11-22** run `sn1_runs/20261122_160742` (10 shots, no test slot left). See `research/sn1/README.md` |
