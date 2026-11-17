"""Generate a test heightfield (pass the output path, e.g. src/modkit/data/seafloor_test.txt; originally made for the removed Lua mod SN2TerrainEdit).

Stand-in for one converted Subnautica 1 terrain chunk: 160 m x 160 m (one SN1 batch),
101 x 101 vertices (1.6 m spacing, 20,000 triangles), heights in centimetres relative to the patch origin.

Format (plain text, easy to parse from Lua):
    line 1:  <vertices_per_side> <spacing_cm>
    then:    vertices_per_side * vertices_per_side heights, row-major (Y outer, X inner), whitespace separated
"""
import math
import sys

N = 101
SPACING = 160.0  # cm
SIZE = (N - 1) * SPACING


def height(x, y):
    """Rolling hills + a ridge + a crater, all in cm."""
    u, v = x / SIZE, y / SIZE
    h = 0.0
    h += 600 * math.sin(u * math.pi * 2.0) * math.cos(v * math.pi * 1.5)      # broad hills, +/-6 m
    h += 250 * math.sin(u * math.pi * 7.0 + 1.3) * math.sin(v * math.pi * 6.0)  # smaller bumps
    ridge = math.exp(-((u - 0.25) ** 2) / 0.004)                               # a ridge along Y
    h += 900 * ridge
    d = math.hypot(u - 0.65, v - 0.6)                                          # a crater with a rim
    h += -1200 * math.exp(-(d ** 2) / 0.008) + 500 * math.exp(-((d - 0.12) ** 2) / 0.0015)
    return h


def main(out_path):
    with open(out_path, "w", encoding="ascii", newline="\n") as f:
        f.write(f"{N} {SPACING:.1f}\n")
        for j in range(N):
            row = [f"{height(i * SPACING, j * SPACING):.0f}" for i in range(N)]
            f.write(" ".join(row) + "\n")
    print(f"wrote {out_path}: {N}x{N} vertices, {2 * (N - 1) ** 2} triangles, {SIZE / 100:.0f} m square")


if __name__ == "__main__":
    main(sys.argv[1])
