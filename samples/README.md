# Samples: SN1 vs SN2 comparison shots

Each sample is one camera view taken in Subnautica 1 (the reference) and the same view in our Subnautica 2 world (L_SN2World).
Samples show how close the port looks to the original: water colour, fog and sight distance, light, terrain shape, and missing objects.

When the user says **"use the samples"**, follow the procedure below from start to end: take the prescribed SN2 photos, analyse them,
and report. The user saying it approves the one autotest run in step 3. Any fix the analysis suggests still needs its own approval.

**Take your own SN2 photos.** The stored `SN2/shot.png` only shows the mod as it was at that photo's `capture_time_utc` (and `run`).
If you (or your session) changed anything that can affect the SN2 world (Lua mods, the modkit map or terrain, cooked content,
install scripts, game build), the stored SN2 photos are stale: run steps 2-4 to take new ones before you analyse or compare.
Never judge a change from SN2 photos taken before it. Only the SN1 side is a fixed reference.

## Layout

```
samples/
  README.md                       this file
  <biome>/                        SN1 biome name at the camera, e.g. safeShallows
    <shot>/                       short name of the view, e.g. shallow_ravine (also the autotest waypoint name)
      SN1/shot.png                SN1 screenshot without HUD (fixed reference; never overwritten)
      SN1/info.json               SN1 pose, capture time, SN1 water settings at the camera
      SN2/shot.png                latest SN2 screenshot of the same view (with HUD)
      SN2/info.json               SN2 target and measured pose, capture time, run, game build, world
      SN2/plan.json               autotest plan for this one view (made from the SN1 pose by sn1_live.py)
      metrics.json                numbers from `samples.py analyze` (latest)
      analysis.md                 written analysis of the latest SN1/SN2 pair (template below)
      compare.png                 SN1 left, SN2 right (made by analyze; gitignored, regenerate it)
```

Tool: `src/tools/samples.py` (`list`, `plan`, `import`, `analyze`; run `python -I src/tools/samples.py` for the usage).

## Procedure: "use the samples"

0. Read `research/status.md` and `research/process/README.md` first, as for any task. Check `bash src/tools/heavy_lock.sh status`. The SN2 run is a
   heavy job: if another session holds the lock, wait with `bash src/tools/heavy_lock.sh acquire game --wait 3600 --note samples` in the
   background (do not poll). Never `release --force`.
1. `python -I src/tools/samples.py list` shows every sample and when each side was captured. Use all samples unless the user names a
   biome (`--biome <b>`) or shots (`--shot a,b`).
2. `python -I src/tools/samples.py plan [--biome <b>] [--shot a,b]` writes `src/mods/SN2AutoTest/plans/samples.json` and prints the run command
   with a timeout of 600 s or more (300 s + 30 s per view). The plan runs `envprobe` and then waits 3 s before every shot, so
   the water look at each view is logged too. Keep that timing: the water look changes in the first seconds after a teleport
   (2026-11-26, `shallow_ravine` clear at 1 s and brown haze at 4 s), so only shots taken with the same timing can be compared.
   Right after every shot it also runs the terrain check (`"probeAfter": "sn1"`, verb `sn1probe`): our SN1Terrain tile actors and a 40 m
   line trace straight down from the camera, logged as `SN1PROBE <shot>_sn1_after ...` in `UE4SS.log`.
3. Run `bash src/tools/autotest.sh samples --input engine --timeout <printed value>`. Do this every time; never skip it because SN2 photos
   already exist (they may predate your changes, see above). Install any other mod you changed first. It installs the current SN2AutoTest + SN2Census, backs up
   saves, launches, takes the shots, quits and deletes the test world it created. Result: `<Workspace>/autotest/<timestamp>_samples/`.
   If the result is not DONE, diagnose it first (`summary.txt`, `driver.log`, `UE4SS.log`, `crash/`). Raise the timeout only after you
   know why it ran out; a second timeout means something is broken. Import the shots that were taken anyway.
4. `python -I src/tools/samples.py import <run dir> --move` copies each shot into `<biome>/<shot>/SN2/shot.png` with a new `info.json`. The
   previous SN2 shot is replaced; git keeps the old one. It also writes `terrain_check` into `info.json` and prints `terrain: loaded` or
   `terrain: NOT CONFIRMED - <why>` per shot.
   **A photo only counts if its terrain is confirmed** (`terrain_check.loaded` true = the downward trace hit one of our SN1 tiles). If it is
   not, do not judge water, fog or light from that photo: write "terrain not confirmed" plus the reason in the analysis, and find out why
   (no hit within 40 m can also mean the seabed is farther than 40 m below the camera; then say so and check `tiles_visible`).
5. `python -I src/tools/samples.py analyze [--biome <b>] [--shot a,b]` writes `metrics.json` and `compare.png` per shot and prints a table:
   mean RGB, blue/red ratio (`B/R`: SN1 Safe Shallows is 1.5-2.3), mean luminance, the distance between the two mean colours (`colDist`),
   and the SN2 terrain check (`loaded`, `NOT CONFIRMED`, or `unknown (no probe)` for photos imported before 2026-11-26's terrain check).
6. Look at every `compare.png` (open it with the Read tool). Write `<shot>/analysis.md` with the template below. Before you overwrite it,
   read the previous `analysis.md` (or `git show HEAD:samples/<biome>/<shot>/analysis.md`) and say what got better or worse.
7. Get the water settings at each view from the run's `UE4SS.log`: lines `ENVPROBE <shot> ...` (which biome regions exist and their
   `WaterLightSettings`). Add anything relevant to the analysis.
8. Record the result in `research/` in the same turn, as text only. Never put images or image links in `research/`. Describe what the
   shots show, with the status word and date, e.g. **VERIFIED (2026-11-26, samples run `<Workspace>/autotest/<ts>_samples`)**. The water
   look goes in `research/features/biome_look.md` §6. Update the "State of play" row in `research/status.md` if the result changed.
9. Report to the user: one line per shot with the verdict, what changed since the last analysis, and the run id. Commit only if asked.

## analysis.md template

```markdown
# <biome>/<shot> - analysis <YYYY-MM-DD>

SN1 shot <capture_time_utc> | SN2 shot <capture_time_utc>, run `<Workspace>/autotest/<ts>_<plan>`, world <world>, build <game_build>
Pose error: target yaw/pitch vs measured (from SN2/info.json)
SN2 terrain: loaded (trace hit <tile> at <dist> cm, <n>/<n> tiles visible, HUD "<shader text>") | NOT CONFIRMED: <why>
(when not confirmed, the water/fog/light rows below are not judged)

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | | |
| blue/red | | |
| mean luminance | | |
| colour distance | | |

| Aspect | SN1 | SN2 | Verdict |
|---|---|---|---|
| Water colour / tint | | | MATCH / CLOSE / DIFFERENT |
| Fog / sight distance | | | |
| Light (sun rays, caustics, brightness) | | | |
| Terrain shape | | | |
| Objects (plants, coral, fish, prefabs) | | | |
| Artefacts (HUD messages, "Loading Shaders" count, holes) | | | |

Change since the previous analysis: ...
Probe (ENVPROBE at this view): ...
```

## Adding a sample (needs Subnautica 1)

The SN1 side is taken only from a Subnautica 1 session the user starts themselves:
- The user gets SN1 in game at the view and says "capture <shot>".
- You run `python src/tools/sn1_live.py capture <shot> [--biome <b>]`.
- This writes `<biome>/<shot>/SN1/{shot.png, info.json}` and `SN2/plan.json`.
- It refuses if that shot already has an SN1 picture, so an existing reference can never be overwritten.

The SN1 water settings of every biome can be dumped with `python src/tools/sn1_live.py waterbiomes <name>`, written to
`<Workspace>/sn1_shots/<name>.json`. The `SN2/shot.png` side is filled in by the next "use the samples" run.

## info.json fields

- **Both sides:** `game`, `shot`, `biome`, `image`, `capture_time_utc`, `capture_time_local`, `notes` (free text; kept when the
  same run is re-imported).
- **SN1:** `source`. Also the raw SN1Inspector capture:
  - `utc`.
  - `camera.pos` / `player` in Unity metres.
  - `yaw` and `pitch_up` in degrees.
  - `fovV`, `fovH` and `screen`.
  - `depth`, `biome` and `dayScalar` (time of day).
  - `settings`: the SN1 `WaterscapeVolume.Settings` at the camera.
- **SN2:**
  - `world`, `game_build` (`<GameDir>/version.txt`), `run`, `plan`.
  - `target`: the plan waypoint, with `at` as the pawn position in UE cm.
  - `measured`: `pawn`, `camera`, `yaw` and `pitch` as logged at the shot.
  - `image_size`.
  - `terrain_check` (from the `SN1PROBE <shot>_sn1_after` lines right after the shot): `loaded` (true = the 40 m downward trace from the
    camera hit one of our SN1 tiles; false; null = no probe lines), `tiles` / `tiles_visible` (SN1Terrain tile actors in the world /
    visible), `trace_down_40m` (hit, owner actor, impact, distance cm), `trace_tile` (mesh name of the tile hit), `shader_text` (HUD
    "Loading Shaders" text), `why` when not loaded.

SN1 to SN2 mapping, with map offset 0 (`research/sn1/world_files.md` §3):
- UE.X = 100 × Unity z, UE.Y = 100 × Unity x, UE.Z = 100 × Unity y.
- Yaw: the same number, wrapped to -180..180.
- Pitch: positive is up in both games.
- `at` is the SN1 player position, not the camera.
