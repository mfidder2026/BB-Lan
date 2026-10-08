#!/usr/bin/env python3
"""Pack the raw $0400-$FFFA game image into a self-extracting, autostartable PRG.

The unpacker (tools/sfx.s) is assembled with ca65/ld65. Format: see sfx.s.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

OUT_START = 0x0400
BLOB_END = 0xFFFB           # end of the raw image ($FFFA inclusive)
LOAD_LIMIT = 0xD000         # the PRG must load below the I/O area
MIN_MATCH, MAX_MATCH = 3, 130
MAX_LIT = 128
MAX_TAIL = 0xFF             # tail copy uses an 8-bit index
WINDOW_CHAIN = 96


def compress(data):
    """Greedy LZ with hash chains. Returns (stream, [(dst_after, src_after)])."""
    out = bytearray()
    marks = []
    heads = {}
    lits = bytearray()
    i, n = 0, len(data)

    def flush_lits():
        nonlocal lits
        p = 0
        while p < len(lits):
            run = lits[p:p + MAX_LIT]
            out.append(len(run) - 1)
            out.extend(run)
            p += len(run)
            marks.append((i - len(lits) + p, len(out)))
        lits = bytearray()

    def insert(pos):
        if pos + 3 <= n:
            heads.setdefault(bytes(data[pos:pos + 3]), []).append(pos)

    while i < n:
        best_len, best_dist = 0, 0
        if i + MIN_MATCH <= n:
            chain = heads.get(bytes(data[i:i + 3]), [])
            for cand in reversed(chain[-WINDOW_CHAIN:]):
                dist = i - cand
                if dist > 0xFFFF:
                    break
                ln = 0
                limit = min(MAX_MATCH, n - i)
                while ln < limit and data[cand + ln] == data[i + ln]:
                    ln += 1
                if ln > best_len:
                    best_len, best_dist = ln, dist
                    if ln == limit:
                        break
        if best_len >= MIN_MATCH:
            flush_lits()
            out.append(0x80 | (best_len - MIN_MATCH))
            out.append(best_dist & 0xFF)
            out.append(best_dist >> 8)
            for k in range(best_len):
                insert(i + k)
            i += best_len
            marks.append((i, len(out)))
        else:
            lits.append(data[i])
            insert(i)
            i += 1
    flush_lits()
    return bytes(out), marks


def decompress(stream, n):
    """Reference decoder, used to verify the packer output."""
    out = bytearray()
    p = 0
    while len(out) < n:
        t = stream[p]
        if t < 0x80:
            out += stream[p + 1:p + 2 + t]
            p += 2 + t
        else:
            ln = (t & 0x7F) + MIN_MATCH
            dist = stream[p + 1] | (stream[p + 2] << 8)
            for _ in range(ln):
                out.append(out[-dist])
            p += 3
    return bytes(out)


def overlap(marks, clen):
    """Max bytes by which the output overtakes unread input (<= 0 is safe)."""
    base = BLOB_END - clen
    return max(OUT_START + d - (base + s) for d, s in marks)


def pack(raw_prg, out_prg, entry):
    with open(raw_prg, "rb") as f:
        raw = f.read()
    assert raw[0] | (raw[1] << 8) == OUT_START, "raw image must start at $0400"
    image = raw[2:]
    assert OUT_START + len(image) == BLOB_END, f"image ends at ${OUT_START + len(image):04X}"

    # Find the smallest raw tail that makes in-place decompression safe.
    tail_len = 0
    while True:
        body = image[:len(image) - tail_len]
        stream, marks = compress(body)
        need = overlap(marks, len(stream)) + tail_len
        # the output ends tail_len bytes below BLOB_END, which is our margin
        if overlap(marks, len(stream)) <= 0:
            break
        tail_len = need
        if tail_len > MAX_TAIL:
            sys.exit(f"pack: tail too large ({tail_len})")
    assert decompress(stream, len(body)) == body
    tail = image[len(image) - tail_len:]

    build = os.path.dirname(os.path.abspath(out_prg))
    with open(os.path.join(build, "sfx-blob.bin"), "wb") as f:
        f.write(stream)
    with open(os.path.join(build, "sfx-tail.bin"), "wb") as f:
        f.write(tail)

    sys.path.insert(0, HERE)
    from build import find_tool
    ca65, ld65 = find_tool("ca65"), find_tool("ld65")
    defs = {"ENTRY": entry, "BLOB_END": BLOB_END, "OUT_END": BLOB_END - tail_len,
            "CLEN": len(stream), "TAIL_LEN": tail_len}
    dargs = []
    for k, v in defs.items():
        dargs += ["-D", f"{k}=${v:04X}"]
    subprocess.run([ca65, "--cpu", "6502", *dargs, "-o", "sfx.o",
                    os.path.join(HERE, "sfx.s")], cwd=build, check=True)
    subprocess.run([ld65, "-C", os.path.join(HERE, "sfx.cfg"), "-o", out_prg, "sfx.o"],
                   cwd=build, check=True)
    size = os.path.getsize(out_prg) - 2
    end = 0x0801 + size
    if end > LOAD_LIMIT:
        sys.exit(f"pack: PRG too large, ends at ${end:04X}")
    print(f"packed {len(image)} -> {len(stream)} bytes (+{tail_len} raw tail), "
          f"PRG $0801-${end - 1:04X}, entry ${entry:04X}")
