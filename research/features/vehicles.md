# Vehicles and the SN2Tadpole mod

Full pass-1 notes: `git show 3449200:research/features/vehicles.md`.

## Vehicles: spawning a Tadpole (2026-11-23, mod `SN2Tadpole`, run `autotest/20261123_164556_tadpole`, plan `tadpole.json`, DONE 156 s)
- `FindFirstOf("SN2CheatManager"):Spawn("Tadpole")` spawns a real vehicle: **VERIFIED (2026-11-23)** UE4SS.log `cheat produced 1 new Tadpole actor(s)`, class `BP_Tadpole_C` (native `SN2Tadpole`, found with `FindAllOf("SN2Tadpole")`). The cheat places it near the player; `K2_SetActorLocation` + `K2_SetActorRotation` then moved it: final loc read back (-731,-951,-143), as requested.
- Screenshot `autotest/20261123_164556_tadpole/shots/01_uw_pod_k5.png` (pawn 1 m under water at the pod, looking toward yaw -136): a white Tadpole hull with cockpit and cyan glow, partly overexposed, just under the horizon about 12 m away. **VERIFIED (2026-11-23, autotest screenshot)** that it exists and is visible. Not seen in the other yaws (k6 also shows it at the left edge).
- Power: the actor has `BPC_PowerCell` (component), `PowerInventoryComponent`, `PowerInventoryInteraction`, `PowerCellItemType` (soft ptr on `SN2Tadpole`). Charge value NOT read (UNTESTED); enterability and driving UNTESTED (cannot be automated).
- **Enter and drive: VERIFIED (2026-11-23, user F1 report `<Workspace>/bugshots/20261123_181716_004` `screen.png`).** The user was piloting an F4 Tadpole about 250 m from the pod at UE (-2882,24957,-6669), HUD 66 m depth. The screenshot shows:
  - the cockpit view, with both hands on the control sticks;
  - prompts "Exit (E)" and "Turn Lights On (mouse)";
  - a gauge panel at the bottom right with 100 (wrench, hull) and 100 (lightning, power).

  So the spawned Tadpole has full power and can be entered and driven. Persistence in a save is still UNTESTED.
- Direct spawn fallback (`BeginDeferredActorSpawnFromClass` of `/Game/Blueprints/Vehicle/BP_Tadpole.BP_Tadpole_C`) is coded but UNTESTED (cheat worked, so it never ran).
- L_SN2World geometry measured 2026-11-23: `BP_StaticLifepod_Surface_C` actor location (0,0,100), yaw 52.4; `BP_Ocean_C` at Z=0 (water surface); player standing inside the pod is at about Z=235.
- Cheat state: cheat commands change only the world actor list; the Tadpole is a normal world actor (whether it persists in a save is UNTESTED).

## SN2Tadpole (new 2026-11-23, `src/mods/SN2Tadpole/Scripts/{main.lua,tadpole_spawn.lua}`, installed + enabled)
`main.lua` binds F4 and `dofile`s `tadpole_spawn.lua` (returns `spawn()`): finds `BP_StaticLifepod_Surface_C` (fallback: pawn), skips if a Tadpole is within 100 m, target = pod + 12 m horizontally at yaw+180, Z = pod Z - 400 (pod actor Z 100, ocean Z 0 => 3 m under water), then `SN2CheatManager:Spawn("Tadpole")` + move after 2 s (fallback direct deferred spawn of `BP_Tadpole_C`), logs `[SN2Tadpole] RESULT ...` and `POWER ...` property names. Test trigger: SN2AutoTest verb `tadpole` (loads the same file) + driver waypoint field `"cmd": "<verb>"`, `"cmdWait": s`; plan `tadpole.json`. VERIFIED 2026-11-23 (cheat path), see `research/features/README.md`.
