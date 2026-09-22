#!/usr/bin/env python3
"""Construct 3 (Scirra) desktop export 'asset bundle' (.dat) unpacker/repacker.

Bundle layout (all integers big-endian):
  offset 0  : b'c3ab'
  offset 4  : u32 (=0)
  offset 8  : u32 version (16)
  offset 12 : u32 (=0)
  offset 16 : b'fdir'            <- file directory chunk
  offset 20 : u32 (=0)
  offset 24 : u32 directoryByteSize (entries region size)
  offset 28 : u32 fileCount
  offset 32 : fileCount entries, each:
        u64 field0        (0 in vanilla files; probably a flags/compression field)
        u64 dataOffset    (relative to start of data region)
        u64 sizeInBundle
        u64 sizeInMemory  (== sizeInBundle when stored raw)
        u32 field4        (0)
        u8  nameLen
        name[nameLen]     (ascii, '/'-separated)
  data region starts right after the directory and holds the file payloads.
"""
import os
import struct
import sys

MAGIC = b"c3ab"


def read_directory(path):
    with open(path, "rb") as f:
        head = f.read(32)
        if head[:4] != MAGIC:
            raise ValueError("not a c3ab bundle")
        if head[16:20] != b"fdir":
            raise ValueError("missing fdir chunk")
        dir_size = int.from_bytes(head[24:28], "big")
        count = int.from_bytes(head[28:32], "big")
        entries = []
        for _ in range(count):
            rec = f.read(37)
            if len(rec) != 37:
                raise ValueError("truncated directory")
            f0, off, sz, usz = struct.unpack(">QQQQ", rec[:32])
            f4 = int.from_bytes(rec[32:36], "big")
            nlen = rec[36]
            name = f.read(nlen).decode("utf-8")
            entries.append(dict(name=name, field0=f0, offset=off, size=sz,
                                usize=usz, field4=f4))
        dir_end = f.tell()
        # The directory chunk is followed by 8 more bytes before the payload
        # region (4 bytes tail of the directory chunk + 4 byte chunk headers),
        # verified by matching file magic numbers at their declared offsets.
        data_start = 32 + dir_size + 8
        return entries, dir_end, data_start


def extract(bundle, outdir, verbose=True):
    entries, dir_end, data_start = read_directory(bundle)
    if verbose:
        print(f"{len(entries)} entries, dir ends at {dir_end}, data at {data_start}")
    with open(bundle, "rb") as f:
        for e in entries:
            f.seek(data_start + e["offset"])
            blob = f.read(e["size"])
            if len(blob) != e["size"]:
                raise ValueError("short read for " + e["name"])
            dest = os.path.join(outdir, e["name"].replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as g:
                g.write(blob)
    return entries, dir_end, data_start


def pack(srcdir, outfile, order=None):
    """Repack a directory tree into a c3ab bundle (raw storage, matching vanilla).

    `order` is an optional list of relative names giving the on-disk order; any
    file in srcdir not listed there is appended in sorted order afterwards.
    """
    found = {}
    for root, _dirs, files in os.walk(srcdir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, srcdir).replace(os.sep, "/")
            found[rel] = full
    names = [n for n in (order or []) if n in found]
    names += sorted(n for n in found if n not in set(names))

    entries = []
    blobs = []
    offset = 0
    for rel in names:
        with open(found[rel], "rb") as f:
            blob = f.read()
        entries.append((rel, offset, len(blob)))
        offset += len(blob)
        blobs.append(blob)

    dir_bytes = b"".join(
        struct.pack(">QQQQ", 0, off, sz, sz) + struct.pack(">I", 0)
        + bytes([len(rel.encode())]) + rel.encode()
        for rel, off, sz in entries
    )
    with open(outfile, "wb") as out:
        out.write(MAGIC)
        out.write(struct.pack(">III", 0, 16, 0))
        out.write(b"fdir")
        # vanilla writes the directory size 4 bytes larger than the records
        # themselves (it also counts the following chunk's magic), so mirror it
        out.write(struct.pack(">III", 0, len(dir_bytes) + 4, len(entries)))
        out.write(dir_bytes)
        out.write(b"blob")
        out.write(struct.pack(">II", 0, offset))
        for b in blobs:
            out.write(b)
    return len(entries), len(dir_bytes), offset


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "x":
        extract(sys.argv[2], sys.argv[3])
    elif cmd == "c":
        print(pack(sys.argv[2], sys.argv[3]))
    elif cmd == "l":
        ents, de, ds = read_directory(sys.argv[2])
        for e in ents:
            print(f"{e['offset']:>10d} {e['size']:>10d} {e['usize']:>10d} f0={e['field0']} f4={e['field4']} {e['name']}")
