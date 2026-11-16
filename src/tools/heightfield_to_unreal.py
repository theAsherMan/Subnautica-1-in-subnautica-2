"""Convert a SN2TerrainEdit heightfield text file into Unreal-importable files.

Input  : heightfield text (line 1: "<n> <spacing_cm>", then n*n heights in cm, row-major, Y outer) — same file the Lua mod loads.
Outputs (next to --out prefix):
  <prefix>.obj        triangle mesh in centimetres, Z up, centred on the patch, with UVs (1 UV unit = 4 m) and vertex normals.
                      Import as Static Mesh: units cm, "Convert Scene" OFF/forward axis X, enable Nanite + "Generate Missing Collision" / use complex as simple.
  <prefix>_h16.png    16-bit greyscale heightmap for Landscape import (n x n pixels).
  <prefix>_h16.json   values needed in the Landscape import dialog: scale X/Y (cm per pixel), scale Z, and the Z offset to place it correctly.
Unreal Landscape convention: height_cm = (pixel - 32768) / 128 * ScaleZ  ->  ScaleZ = range_cm * 128 / 65535 (pixel 0..65535 spans the data range).

Usage: python -I heightfield_to_unreal.py <heightfield.txt> --out <prefix>
"""
import argparse
import json
import math
import struct
import zlib


def read_heightfield(path):
    with open(path, encoding="ascii") as f:
        n_str, sp_str = f.readline().split()
        n, spacing = int(n_str), float(sp_str)
        h = [int(x) for x in f.read().split()]
    if len(h) != n * n:
        raise ValueError(f"expected {n*n} heights, got {len(h)}")
    return n, spacing, h


def write_obj(path, n, sp, h):
    half = (n - 1) * sp / 2

    def H(i, j):
        i = min(max(i, 0), n - 1)
        j = min(max(j, 0), n - 1)
        return h[j * n + i]

    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("# heightfield mesh, cm, Z up\n")
        for j in range(n):
            for i in range(n):
                f.write(f"v {i*sp - half:.1f} {j*sp - half:.1f} {H(i, j):.1f}\n")
        for j in range(n):
            for i in range(n):
                f.write(f"vt {i*sp/400:.4f} {j*sp/400:.4f}\n")
        for j in range(n):
            for i in range(n):
                dx = (H(i + 1, j) - H(i - 1, j)) / (2 * sp)
                dy = (H(i, j + 1) - H(i, j - 1)) / (2 * sp)
                l = math.sqrt(dx * dx + dy * dy + 1)
                f.write(f"vn {-dx/l:.5f} {-dy/l:.5f} {1/l:.5f}\n")
        for j in range(n - 1):
            for i in range(n - 1):
                a = j * n + i + 1          # OBJ is 1-based
                b, c, d = a + 1, a + n, a + n + 1
                # counter-clockwise seen from +Z
                f.write(f"f {a}/{a}/{a} {b}/{b}/{b} {d}/{d}/{d}\n")
                f.write(f"f {a}/{a}/{a} {d}/{d}/{d} {c}/{c}/{c}\n")


def write_png16(path, n, h):
    lo, hi = min(h), max(h)
    rng = max(hi - lo, 1)
    rows = []
    for j in range(n):
        row = bytearray(b"\x00")               # filter type 0
        for i in range(n):
            v = round((h[j * n + i] - lo) / rng * 65535)
            row += struct.pack(">H", v)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        return c + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 16, 0, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("heightfield")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    n, sp, h = read_heightfield(a.heightfield)
    write_obj(a.out + ".obj", n, sp, h)
    lo, hi = write_png16(a.out + "_h16.png", n, h)
    scale_z = (hi - lo) * 128 / 65535
    info = {
        "vertices_per_side": n, "spacing_cm": sp, "size_m": (n - 1) * sp / 100,
        "height_min_cm": lo, "height_max_cm": hi,
        "landscape_import": {
            "scale_xy_cm_per_pixel": sp, "scale_z": round(scale_z, 6),
            "note": "pixel 32768 sits at actor Z; pixel 0 = actor Z - 256*ScaleZ. Place actor Z = desired_min_height + 256*ScaleZ so pixel 0 lands on height_min",
            "actor_z_offset_from_min_cm": round(256 * scale_z, 2),
        },
        "triangles": 2 * (n - 1) ** 2,
    }
    with open(a.out + "_h16.json", "w", encoding="ascii") as f:
        json.dump(info, f, indent=2)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
