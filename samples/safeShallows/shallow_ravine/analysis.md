# safeShallows/shallow_ravine - analysis 2026-11-28

SN2 shot run `<Workspace>/autotest/20261128_162423_samples`, world L_SN2World, build 131439; calibration iteration 5 (research/10 section 6c). SN2 terrain: loaded.

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (29, 50, 44) | (105, 118, 84) |
| blue/red | 1.50 | 0.80 |
| mean luminance | 46 | 113 |
| colour distance | 109.3 | |

| Aspect | Verdict |
|---|---|
| Water colour / tint | PARTIAL: teal water in the opening, but walls are saturated orange (terrain albedo, out of scope) |
| Fog / sight distance | MATCH-ish: the opening is visible |
| Light | DIFFERENT: much brighter than SN1's dark ravine (113 vs 46); the global exposure bias raises it |
| Terrain shape | MATCH (same camera pose) |

Result: WORSE than before calibration in luminance and colour distance (was 36 / 45 at the old dim setting) because exposure is global. Not acceptance-critical. A darker ravine would need a local exposure volume or darker terrain albedo, both out of scope.
