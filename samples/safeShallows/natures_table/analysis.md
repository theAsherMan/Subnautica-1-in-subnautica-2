# safeShallows/natures_table - analysis 2026-11-28

SN2 shot run `<Workspace>/autotest/20261128_162423_samples`, world L_SN2World, build 131439; calibration iteration 5 (research/features/biome_look.md §6c). SN2 terrain: loaded.

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (83, 157, 191) | (88, 151, 173) |
| blue/red | 2.30 | 1.97 |
| mean luminance | 144 | 139 |
| colour distance | 19.1 | |

| Aspect | Verdict |
|---|---|
| Water colour / tint | CLOSE: blue-aquamarine haze; slightly less saturated blue than SN1 |
| Fog / sight distance | DIFFERENT: the table structure is a soft silhouette within ~25 m, SN1 is crisp |
| Light | PARTIAL: brightness matches; no caustics, god rays or surface sparkle |
| Terrain shape | MATCH (same camera pose) |

Result: acceptance MET (luminance within 4%, B/R in 1.5-2.3, colour distance under 60). Remaining: sight distance, no light rays.
