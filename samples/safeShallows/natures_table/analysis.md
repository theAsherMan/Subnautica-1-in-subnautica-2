# safeShallows/natures_table - analysis 2026-11-26

SN1 shot 2026-11-26T09:34:15Z | SN2 shot 2026-11-26T10:07:43Z, run `<Workspace>/autotest/20261126_180611_sn1cmp_shallows_env`, world L_SN2World, build 131439 2026-09-18T20:24:32
Pose error: target yaw 155.36 / pitch 5.47, measured yaw 154.48 / pitch 4.34 (-0.88 / -1.13 deg)

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (83, 157, 191) | (54, 49, 57) |
| blue/red | 2.30 | 1.04 |
| mean luminance | 144 | 50 |
| colour distance | 174.7 | |

| Aspect | SN1 | SN2 | Verdict |
|---|---|---|---|
| Water colour / tint | Clear blue, sea surface bright with ripples above | Brown haze on the left, grey-purple on the right; the surface shows as broken white patches at the top | DIFFERENT |
| Fog / sight distance | Table mesa with arches and the tube prefab sharp at about 30 m | Table mesa not visible (at most a faint dark silhouette); sight distance a few metres | DIFFERENT |
| Light (sun rays, caustics, brightness) | Sun rays, caustics on the sand | No rays, no caustics, dim | DIFFERENT |
| Terrain shape | Table mesa with arches, sand slope in the foreground | Not readable through the haze | UNKNOWN |
| Objects (plants, coral, fish, prefabs) | Grass, pink coral, tube prefab, fish | None (flora/fauna/prefabs not ported) | DIFFERENT (expected) |
| Artefacts (HUD messages, "Loading Shaders" count, holes) | - | HUD "Loading Shaders... 5,017", depth 12 m, O2 45; small red-orange blobs bottom right (unidentified) | - |

Change since the previous analysis: First analysis (baseline). The earlier run 175137 crashed here (PODDUMP, since removed), so there is no older shot.
Probe (ENVPROBE at this view): As for shallow_ravine (research/10 §6).
