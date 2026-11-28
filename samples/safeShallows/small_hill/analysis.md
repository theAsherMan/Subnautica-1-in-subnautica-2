# safeShallows/small_hill - analysis 2026-11-28

SN2 shot run `<Workspace>/autotest/20261128_162423_samples`, world L_SN2World, build 131439; calibration iteration 5 (research/10 section 6c). SN2 terrain: loaded, pose matches.

| Metric | SN1 | SN2 |
|---|---|---|
| mean RGB | (93, 147, 152) | (123, 147, 147) |
| blue/red | 1.64 | 1.20 |
| mean luminance | 136 | 142 |
| colour distance | 30.4 | |

| Aspect | Verdict |
|---|---|
| Water colour / tint | PARTIAL: cyan-green haze in the distance; the foreground sand is orange-brown (terrain albedo) so B/R stays under 1.5 |
| Fog / sight distance | DIFFERENT: midground is milky, fades within ~20 m |
| Light | PARTIAL: brightness matches; no caustics on the sand |
| Terrain shape | MATCH (same camera pose) |

Result: luminance and colour distance met; B/R 1.20 is below the band, limited by the orange terrain albedo (out of scope).
