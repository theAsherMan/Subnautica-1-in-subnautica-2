#!/usr/bin/env python
"""Lint the research/ notes. Run: python -I src/tools/research_lint.py [--root <research dir>]

Errors (exit 1): a topic file not listed in its folder README; a `research/...md` reference or markdown
link that does not resolve (file, optional section number, optional quoted heading); a file over 25 KB
(unless in EXEMPT); an image; a lone CR (CRLF line ends are fine) or a C1 control character.
Warnings: a file over 15 KB; a reference to an old numbered stub.
A reference written as  `research/x/y.md`, "phrase"  (comma form) is not heading-checked.
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True

WARN_BYTES = 15 * 1024
ERR_BYTES = 25 * 1024
# files allowed over the hard limit (path relative to research/); keep this short
EXEMPT = {
    "crashes/gc_watchdog_renderpipe_2026-11-25.md": "one moved diagnostic series, split later",
}
# the old numbered files are kept as short pointer stubs
STUBS = {
    "00_overview.md", "01_runbook.md", "02_world_systems_reference.md", "03_creating_terrain.md",
    "04_placing_features.md", "05_console_commands.md", "06_asset_index.md", "07_mods_reference.md",
    "08_modkit_setup.md", "09_intro_and_world_replacement.md", "10_sn1_world_data.md",
    "11_sn1_modding.md", "12_sn1_assets.md",
}
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tga")

REF = re.compile(
    r"research/(?P<path>[A-Za-z0-9_./-]+?\.md)`?"
    r"(?:(?P<sec> §(?P<n>\d+[a-z]?(?:\.\d+)?))?"
    r"(?P<q> [\"'](?P<qt>[^\"'\n]{2,120}?)[\"'])?)")
MDLINK = re.compile(r"\]\((?P<t>[^)\s#]+\.md)(?:#[^)\s]*)?\)")
HEAD = re.compile(r"^(#{1,6}) (.*)$")


def norm(s):
    s = s.replace("**", "").replace("`", "").replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


def qprefix(q):
    q = re.split(r"\.\.\.|…", q)[0]
    return norm(q).rstrip(" ,:;(-")


def read(path):
    with open(path, "rb") as f:
        return f.read()


def headings(text):
    out, fence = [], False
    for l in text.split("\n"):
        s = l.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence:
            continue
        m = HEAD.match(l)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(here, "..", "..", "research"))
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    errs, warns = [], []

    files = []
    for d, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            full = os.path.join(d, f)
            files.append(os.path.relpath(full, root).replace(os.sep, "/"))
    md = [f for f in files if f.endswith(".md")]
    texts = {}
    for f in md:
        b = read(os.path.join(root, f))
        texts[f] = b.decode("utf-8", "replace")
        if re.search(rb"\r(?!\n)", b):
            errs.append("%s: contains a lone CR" % f)
        if re.search("[\u0080-\u009f]", texts[f]):
            errs.append("%s: contains a C1 control character" % f)
        n = len(b) - b.count(b"\r\n")  # size counted with LF line ends
        if n > ERR_BYTES and f not in EXEMPT:
            errs.append("%s: %d bytes (hard limit %d)" % (f, n, ERR_BYTES))
        elif n > WARN_BYTES:
            warns.append("%s: %d bytes (soft limit %d)" % (f, n, WARN_BYTES))
    for f in files:
        if f.lower().endswith(IMG_EXT):
            errs.append("%s: image file in research/" % f)
    for f in md:
        t = texts[f]
        if "![" in t or re.search(r"<img\b", t, re.I):
            errs.append("%s: image markup" % f)

    # folder READMEs list every topic file
    for f in md:
        if "/" not in f or f.endswith("/README.md"):
            continue
        d = f.split("/")[0]
        rd = d + "/README.md"
        if rd not in texts:
            errs.append("%s: folder has no README.md" % d)
            continue
        name = f.split("/", 1)[1]
        if "](%s)" % name not in texts[rd]:
            errs.append("%s: not listed in %s" % (f, rd))

    hcache = {}

    def heads(rel):
        if rel not in hcache:
            hcache[rel] = headings(texts[rel])
        return hcache[rel]

    for f in md:
        lines = texts[f].split("\n")
        fence = False
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("```") or s.startswith("~~~"):
                fence = not fence
                continue
            if fence:
                continue
            for m in REF.finditer(line):
                rel = m.group("path")
                if "<" in rel or "*" in rel or line[:m.start()].endswith(":"):
                    continue  # placeholder, glob, or `git show <hash>:research/...`
                if rel not in texts:
                    errs.append("%s:%d: unresolved reference research/%s" % (f, i, rel))
                    continue
                if rel in STUBS and f not in STUBS:
                    warns.append("%s:%d: reference to old stub research/%s" % (f, i, rel))
                before = line[:m.start()]
                comma = line[m.end("path"):].lstrip("`").startswith(",")
                if comma:
                    continue
                hs = heads(rel)
                if m.group("n"):
                    n = m.group("n").lower()
                    rx = re.compile(r"^%s(?![0-9a-z])" % re.escape(n))
                    if not any(lv > 1 and rx.match(tx.lower()) for lv, tx in hs):
                        errs.append("%s:%d: research/%s has no section %s" % (f, i, rel, n))
                    continue
                if m.group("qt") and not m.group("sec"):
                    qp = qprefix(m.group("qt"))
                    if qp and not any(norm(tx).startswith(qp) for lv, tx in hs):
                        errs.append("%s:%d: research/%s has no heading \"%s\"" % (f, i, rel, m.group("qt")))
            for m in MDLINK.finditer(line):
                tgt = m.group("t")
                if "://" in tgt:
                    continue
                full = os.path.normpath(os.path.join(os.path.dirname(f), tgt)).replace(os.sep, "/")
                if full not in texts:
                    errs.append("%s:%d: broken link %s" % (f, i, tgt))

    for w in warns:
        print("WARN  " + w)
    for e in errs:
        print("ERROR " + e)
    print("research_lint: %d files, %d errors, %d warnings" % (len(md), len(errs), len(warns)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
