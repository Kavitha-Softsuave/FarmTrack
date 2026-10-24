"""Download a sample of the Indigenous Apple Leaf Dataset (Kashmir; Yatoo & Sharma, Mendeley Data 10.17632/9m2dcb5mmr.3, CC BY 4.0)
using HTTP range reads of the dataset zip (the whole zip is never downloaded). Classes used: Healthy, Alternaria.
Usage: python fetch_jk_apple.py [--per-class N] [--list]"""
import argparse, csv, io, random, re, sys, urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).parent
ZIP_API = "https://data.mendeley.com/public-api/zip/9m2dcb5mmr/download/3"
MAP = {"healthy": "Apple___healthy", "alternaria": "Apple___Alternaria_leaf_spot"}
AUTHOR = "Arshad Yatoo and Amit Sharma (Lovely Professional University), Kashmir Valley orchards"


def zip_url():
    import http.client
    c = http.client.HTTPSConnection("data.mendeley.com", timeout=30)
    c.request("GET", "/public-api/zip/9m2dcb5mmr/download/3")
    r = c.getresponse()
    loc = r.getheader("Location")
    if not loc:
        raise RuntimeError(f"no redirect (status {r.status})")
    return loc


class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Range"].split("/")[1])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def read(self, n=-1):
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        if n <= 0:
            return b""
        start, block = getattr(self, "_blk", (0, b""))
        if not (start <= self.pos and self.pos + n <= start + len(block)):      # read ahead 64 KB (the images are about 12 KB): zipfile reads in 4 KB steps
            want = min(max(n, 64 << 10), self.size - self.pos)
            block = self._fetch(self.pos, want)
            self._blk = (self.pos, block)
            start = self.pos
        data = block[self.pos - start: self.pos - start + n]
        self.pos += len(data)
        return data

    def _fetch(self, pos, n):
        for attempt in range(2):
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={pos}-{pos + n - 1}"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.read()
            except urllib.error.HTTPError as e:     # signed URL expires after 300 s: fetch a fresh one
                if e.code not in (400, 403) or attempt:
                    raise
                self.url = zip_url()

    def readinto(self, b):
        d = self.read(len(b)); b[: len(d)] = d; return len(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=250)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", choices=list(MAP), help="one class only (run two copies in parallel)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    z = zipfile.ZipFile(RangeFile(zip_url()))
    names = [i.filename for i in z.infolist() if re.search(r"\.(jpe?g|png)$", i.filename, re.I)]
    if a.list:
        from collections import Counter
        print(len(names), Counter("/".join(n.split("/")[:-1]) for n in names)); return
    rnd = random.Random(a.seed)
    rows = []
    for key, cid in MAP.items():
        if a.only and key != a.only:
            continue
        sel = sorted(n for n in names if n.split("/")[-2].lower() == key and "/Train_Set/" in n)
        rnd.shuffle(sel)
        for n in sel[: a.per_class]:
            fn = "jk_" + re.sub(r"[^A-Za-z0-9._-]", "_", "_".join(n.split("/")[-2:]))
            dest = HERE / "photos" / cid / fn
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))
            rows.append([f"{cid}/{fn}", cid, f"https://data.mendeley.com/datasets/9m2dcb5mmr/3 ({n})", "CC-BY-4.0", AUTHOR, "dataset label; unconfirmed"])
    sp = HERE / f"sources_{a.only or 'all'}.part.csv"   # merge into sources.csv afterwards (parallel runs)
    with sp.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(len(rows), "files")


if __name__ == "__main__":
    main()
