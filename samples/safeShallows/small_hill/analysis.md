# safeShallows/small_hill - analysis 2026-11-26

SN1 shot 2026-11-26T09:32:02Z | SN2 shot 2026-11-26T10:07:36Z, run `<Workspace>/autotest/20261126_180611_sn1cmp_shallows_env`, world L_SN2World, build 131439 2026-09-18T20:24:32
Pose error: target yaw 147.49 / pitch -31.65, measured yaw 148.32 / pitch -30.63 (+0.83 / +1.02 deg)

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (93, 147, 152) | (49, 39, 44) |
| blue/red | 1.64 | 0.89 |
| mean luminance | 136 | 42 |
| colour distance | 158.9 | |

| Aspect | SN1 | SN2 | Verdict |
|---|---|---|---|
| Water colour / tint | Bright blue-turquoise | Dark brown-red haze, slightly purple-grey at the top right | DIFFERENT |
| Fog / sight distance | Kelp and mesas visible at 40 m+ with blue falloff | Terrain only as dark silhouettes at about 10-20 m, everything beyond is haze | DIFFERENT |
| Light (sun rays, caustics, brightness) | Strong caustics on cream sand, bright from above | Dim, no caustics, sand dark rust-orange | DIFFERENT |
| Terrain shape | Rock on the left, mesas behind, sand ridge, trench | Same rock on the left, mesa silhouettes and sand ridge at the same places | CLOSE |
| Objects (plants, coral, fish, prefabs) | Green plants along the ridge, purple shelf fungus, kelp silhouettes, a fish | None (flora/fauna not ported) | DIFFERENT (expected) |
| Artefacts (HUD messages, "Loading Shaders" count, holes) | - | HUD "Loading Shaders..." (count unreadable), depth 3 m; no toasts | - |

Change since the previous analysis: First analysis (baseline). Run `20261126_175137_sn1cmp_shallows` (shot 1 s after the view) was rust-orange and clearer; this one (4 s) is darker and hazier.
Probe (ENVPROBE at this view): As for shallow_ravine (research/10 §6).
