#!/usr/bin/env python
"""Lint the research/ notes. Run: python -I src/tools/research_lint.py [--root <research dir>]

Errors (exit 1): a topic file not listed in its folder README; a `research/...md` reference or markdown
link that does not resolve (file, optional section number, optional quoted heading), checked in research/
and in the instruction files outside it (OUTSIDE); an image link whose file is missing; a note over 25 KB
(unless in EXEMPT); a lone CR (CRLF line ends are fine) or a C1 control character.
Also an error: a heading tagged "— OPEN (YYYY-MM-DD)" with no line in status.md "Next steps", or a Next steps
item without a `research/<file>.md "<heading>"` reference to an OPEN heading.
Warnings: a note over 15 KB; an image file over 1 MB.
The old numbered files (00_overview.md ... 12_sn1_assets.md) were deleted 2026-11-28; a reference to one is an
unresolved-reference error (recover old text with git show 7221ba9:research/<file>).
A reference written as  `research/x/y.md`, "phrase"  (comma form) is not heading-checked.
Images are allowed (user, 2026-11-28): convention research/<folder>/img/<name>.png, linked relatively.
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WARN_BYTES = 15 * 1024
ERR_BYTES = 25 * 1024
# files allowed over the hard limit (path relative to research/); keep this short
EXEMPT = {
    "crashes/gc_watchdog_renderpipe_2026-11-25.md": "one moved diagnostic series, split later",
}
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tga")
IMG_WARN_BYTES = 1024 * 1024
# instruction files outside research/ whose research/ references are checked (globs relative to the repo)
OUTSIDE = ["CLAUDE.md", ".claude/CLAUDE.md", ".claude/agents/*.md", ".claude/skills/*/SKILL.md",
           "README.md", "samples/README.md"]
IMGLINK = re.compile(r"!\[[^\]]*\]\((?P<t>[^)\s]+)\)|<img\b[^>]*\bsrc=[\"'](?P<s>[^\"']+)[\"']", re.I)

REF = re.compile(
    r"research/(?P<path>[A-Za-z0-9_./-]+?\.md)`?"
    r"(?:(?P<sec> §(?P<n>\d+[a-z]?(?:\.\d+)?))?"
    r"(?P<q> [\"'](?P<qt>[^\"'\n]{2,120}?)[\"'])?)")
MDLINK = re.compile(r"\]\((?P<t>[^)\s#]+\.md)(?:#[^)\s]*)?\)")
HEAD = re.compile(r"^(#{1,6}) (.*)$")
# an open topic: heading ends with " — OPEN (YYYY-MM-DD)" (date opened); see research/README.md "Open topics"
OPEN = re.compile(r"[—-] OPEN \(\d{4}-\d{2}-\d{2}\)\s*$")


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
            sz = os.path.getsize(os.path.join(root, f))
            if sz > IMG_WARN_BYTES:
                warns.append("%s: image %d bytes (over %d; consider a smaller JPG/PNG)" % (f, sz, IMG_WARN_BYTES))

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

    # instruction files outside research/: only their research/ references are checked
    import glob
    repo = os.path.dirname(root)
    outside = {}
    for g in OUTSIDE:
        for p in sorted(glob.glob(os.path.join(repo, g))):
            rel = "../" + os.path.relpath(p, repo).replace(os.sep, "/")
            outside[rel] = read(p).decode("utf-8", "replace")

    for f in md + sorted(outside):
        is_out = f in outside
        lines = (outside[f] if is_out else texts[f]).split("\n")
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
            if is_out:
                continue  # outside files: markdown links point anywhere in the repo, not checked here
            for m in MDLINK.finditer(line):
                tgt = m.group("t")
                if "://" in tgt:
                    continue
                full = os.path.normpath(os.path.join(os.path.dirname(f), tgt)).replace(os.sep, "/")
                if full not in texts:
                    errs.append("%s:%d: broken link %s" % (f, i, tgt))
            for m in IMGLINK.finditer(line):
                tgt = m.group("t") or m.group("s")
                if "://" in tgt or tgt.startswith("data:"):
                    continue
                full = os.path.normpath(os.path.join(root, os.path.dirname(f), tgt))
                if not os.path.isfile(full):
                    errs.append("%s:%d: missing image %s" % (f, i, tgt))

    # OPEN topics <-> status.md "Next steps", both directions
    if "status.md" in texts:
        items, sec = [], False
        for i, line in enumerate(texts["status.md"].split("\n"), 1):
            if line.startswith("## "):
                sec = line.startswith("## Next steps")
                continue
            if sec and re.match(r"^\d+\. ", line):
                items.append((i, line))
        pointed = set()
        for i, line in items:
            refs = [m for m in REF.finditer(line) if m.group("qt") and not m.group("sec")]
            if not refs:
                errs.append("status.md:%d: Next steps item has no `research/<file>.md \"<OPEN heading>\"` reference" % i)
                continue
            for m in refs:
                rel, qp = m.group("path"), qprefix(m.group("qt"))
                if rel not in texts:
                    continue  # reported above as unresolved
                hit = [tx for lv, tx in heads(rel) if norm(tx).startswith(qp)]
                if hit and not any(OPEN.search(tx) for tx in hit):
                    errs.append("status.md:%d: research/%s \"%s\" is not an OPEN heading" % (i, rel, m.group("qt")))
                for tx in hit:
                    pointed.add((rel, tx))
        for f in md:
            if f == "status.md":
                continue
            for lv, tx in heads(f):
                if OPEN.search(tx) and (f, tx) not in pointed:
                    errs.append("%s: OPEN heading \"%s\" has no line in status.md Next steps" % (f, tx))

    for w in warns:
        print("WARN  " + w)
    for e in errs:
        print("ERROR " + e)
    print("research_lint: %d files, %d errors, %d warnings" % (len(md), len(errs), len(warns)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
