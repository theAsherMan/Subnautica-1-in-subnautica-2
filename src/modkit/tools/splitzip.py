"""Read / extract a byte-split zip (name.zip.001, .002, ...) without concatenating the parts.

Usage:
  python -I splitzip.py list    <first_part> [--top N]
  python -I splitzip.py test    <first_part>            (CRC-check every member)
  python -I splitzip.py extract <first_part> <dest_dir>
"""
import io
import os
import sys
import time
import zipfile


class MultiPart(io.RawIOBase):
    def __init__(self, first):
        base = first[:-4]
        self.paths, i = [], 1
        while os.path.exists(f"{base}.{i:03d}"):
            self.paths.append(f"{base}.{i:03d}")
            i += 1
        self.sizes = [os.path.getsize(p) for p in self.paths]
        self.starts, s = [], 0
        for z in self.sizes:
            self.starts.append(s)
            s += z
        self.total, self.pos = s, 0
        self.files = [open(p, "rb") for p in self.paths]

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.total + off
        return self.pos

    def readinto(self, b):
        n, done = len(b), 0
        while done < n and self.pos < self.total:
            k = max(i for i, st in enumerate(self.starts) if st <= self.pos)
            f = self.files[k]
            f.seek(self.pos - self.starts[k])
            chunk = f.read(min(n - done, self.starts[k] + self.sizes[k] - self.pos))
            if not chunk:
                break
            b[done:done + len(chunk)] = chunk
            done += len(chunk)
            self.pos += len(chunk)
        return done


def open_zip(first):
    mp = MultiPart(first)
    print("parts:", len(mp.paths), "total bytes:", mp.total)
    return zipfile.ZipFile(io.BufferedReader(mp, 1 << 20))


def main():
    cmd, first = sys.argv[1], sys.argv[2]
    z = open_zip(first)
    infos = z.infolist()
    unc = sum(i.file_size for i in infos)
    comp = sum(i.compress_size for i in infos)
    print(f"members: {len(infos)}  uncompressed: {unc/2**30:.2f} GiB  compressed: {comp/2**30:.2f} GiB")
    if cmd == "list":
        tops = {}
        for i in infos:
            top = "/".join(i.filename.split("/")[:2])
            tops[top] = tops.get(top, 0) + i.file_size
        for k, v in sorted(tops.items(), key=lambda kv: -kv[1])[:40]:
            print(f"{v/2**30:8.2f} GiB  {k}")
        bad = [i.filename for i in infos if i.filename.startswith("/") or ".." in i.filename.split("/")]
        print("unsafe paths:", len(bad))
    elif cmd == "test":
        badf = z.testzip()
        print("testzip first bad member:", badf)
    elif cmd == "extract":
        dest = os.path.abspath(sys.argv[3])
        t0, done = time.time(), 0
        for n, i in enumerate(infos):
            target = os.path.abspath(os.path.join(dest, i.filename))
            if not target.startswith(dest + os.sep) and target != dest:
                raise SystemExit("unsafe path: " + i.filename)
            z.extract(i, dest)
            done += i.file_size
            if n % 2000 == 0:
                print(f"{n}/{len(infos)} files  {done/2**30:.1f}/{unc/2**30:.1f} GiB  {time.time()-t0:.0f}s", flush=True)
        print(f"DONE {len(infos)} files {done/2**30:.2f} GiB in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
