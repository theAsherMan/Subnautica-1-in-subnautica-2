# safeShallows/shallow_ravine - analysis 2026-11-26

SN1 shot 2026-11-26T09:30:04Z | SN2 shot 2026-11-26T10:07:29Z, run `<Workspace>/autotest/20261126_180611_sn1cmp_shallows_env`, world L_SN2World, build 131439 2026-09-18T20:24:32
Pose error: target yaw -97.76 / pitch 1.99, measured yaw -96.66 / pitch 1.0 (+1.10 / -0.99 deg)

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (29, 50, 44) | (34, 29, 31) |
| blue/red | 1.50 | 0.90 |
| mean luminance | 46 | 30 |
| colour distance | 25.8 | |

| Aspect | SN1 | SN2 | Verdict |
|---|---|---|---|
| Water colour / tint | Teal-green water; the far opening glows bright turquoise | No water visible: the whole frame is one flat dark brown haze | DIFFERENT |
| Fog / sight distance | Ravine walls fade into teal at about 30-40 m | Opaque at under 1 m: nothing past the camera is visible | DIFFERENT |
| Light (sun rays, caustics, brightness) | Sunlit sand patches through the arch, dark teal cave shadow | No light structure, uniform dark brown | DIFFERENT |
| Terrain shape | Rock arch framing a sand path, rock lip in the foreground | Not visible in this shot (haze). Run `20261126_175137_sn1cmp_shallows` (shot 1 s after the view instead of 4 s) showed the same arch and path, lit bright orange | CLOSE (from run 175137) |
| Objects (plants, coral, fish, prefabs) | Coral bush, purple coral head, fish, small orange particles | None (flora/fauna not ported) | DIFFERENT (expected) |
| Artefacts (HUD messages, "Loading Shaders" count, holes) | - | HUD: "Loading Shaders... 5,467", oxygen-cheat toast, PDA message "There are no other lifepods in inventory...", depth 51 m | - |

Change since the previous analysis: First analysis (baseline).
Probe (ENVPROBE at this view): 42 SN1Biome regions + the ocean region + neutral CAT_0 present with their WaterLightSettings (research/10 §6, LOGGED 2026-11-26). The region at the camera is not identified yet.
