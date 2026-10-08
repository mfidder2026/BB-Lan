#!/usr/bin/env python3
"""BB-LAN build script (replaces build/Makefile on Windows; no make needed).

Usage:
    python tools/build.py              BB-LAN build: build/bblan-raw.prg
    python tools/build.py release      + packed, runnable build/bblan.prg
    python tools/build.py release -D DETTEST=1 -o dettest   test variant
    python tools/build.py verify       ORIGINAL game: build/rebb64-raw.prg + SHA256 check
    python tools/build.py original     ORIGINAL game, packed: build/rebb64.prg
    python tools/build.py clean        remove build artifacts

The BB-LAN build assembles with -D BBLAN=1 and compressed level bitmaps. The
compressed bitmaps are split between PRG_MID and the I/O shadow; the split is
chosen so the I/O shadow is full, which frees PRG_MID space for BBLAN_CODE.

Options:
    -D NAME[=VALUE]                    extra ca65 define (e.g. -D DETTEST=1)

Tools: ca65/ld65 are taken from $CC65_HOME/bin, else ../c64/cc65/bin next to
this repo, else PATH.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
SRC = os.path.join(ROOT, "src")
DATA = os.path.join(ROOT, "data")

REFERENCE_SHA256 = "fdba2390782653ba2533b2d87c44c8f0480ab18968a2c0ccc0cef8300fcee7b6"
OUTPUT = "rebb64-raw.prg"
BBLAN_RAW = "bblan-raw.prg"
RELEASE = "bblan.prg"
ORIGINAL_RELEASE = "rebb64.prg"
ORIGINAL_BM_START = 0xC5F2
LBLFILE = "rebb64.lbl"
DBGFILE = "rebb64.dbg"
SOUND_SRC = "sound.s"

LEVEL_BINS_BASE = ["level-bitmaps.bin", "level-colors.bin", "level-flags.bin",
                   "enemy-spawns.bin", "item-positions.bin", "physics-flags.bin"]
LEVEL_BINS_COMPRESSED = ["level-bitmaps-compressed.bin", "level-bitmap-offsets.bin",
                         "bitmap-decode-table.bin", "bitmap-dict-pairs.bin"]

# (output, source tga, convert-tga.py args)
TGA_CONVERSIONS = [
    ("hud-font.bin", "hud-font.tga", ["--format", "multicolor-chars"]),
    ("sidebars.bin", "sidebars.tga", ["--format", "multicolor-chars"]),
    ("level-tiles.bin", "level-tiles.tga", ["--format", "multicolor-chars"]),
    ("charset.bin", "charset.tga", ["--format", "hires-chars"]),
    ("sprites-game.bin", "sprites-game.tga", ["--format", "multicolor-sprites"]),
    ("bubble-masks.bin", "bubble-masks.tga", ["--format", "bubble-masks"]),
    ("software-sprites.bin", "software-sprites.tga", ["--format", "software-sprites"]),
    ("diamond-sprite.bin", "diamond-sprite.tga", ["--format", "diamond-sprite"]),
    ("digit-font.bin", "digit-font.tga", ["--format", "digit-font"]),
    ("bubble-dragon-in-bubble.bin", "bubble-dragon-in-bubble.tga",
     ["--format", "level-sprites-stacked", "--stacked-groups", "2"]),
    ("grumple-gromit.bin", "grumple-gromit.tga",
     ["--format", "level-sprites-stacked", "--stacked-groups", "3"]),
]


def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = []
    if os.environ.get("CC65_HOME"):
        candidates.append(os.path.join(os.environ["CC65_HOME"], "bin", exe))
    candidates.append(os.path.join(ROOT, "..", "c64", "cc65", "bin", exe))
    for c in candidates:
        if os.path.isfile(c):
            return os.path.normpath(c)
    found = shutil.which(name)
    if found:
        return found
    sys.exit(f"error: {name} not found (set CC65_HOME)")


def run(cmd):
    print("  " + " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    r = subprocess.run(cmd, cwd=BUILD)
    if r.returncode != 0:
        sys.exit(f"error: command failed ({r.returncode})")


def py(script, *args):
    run([sys.executable, script, *args])


def assemble(ca65, defs):
    run([ca65, "--cpu", "6502", "-o", "loadaddr.o", os.path.join(SRC, "loadaddr.s")])
    run([ca65, "--cpu", "6502", "-g", *defs, "-I", SRC, "-I", ".", "-o", "master.o",
         os.path.join(SRC, "master.s")])


def link(ld65, output, bm_start, quiet=False):
    cmd = [ld65, "-C", "c64-prg.cfg", "-D", f"__LEVEL_BM_START__=${bm_start:04X}",
           "-Ln", LBLFILE, "--dbgfile", DBGFILE, "-o", output, "loadaddr.o", "master.o"]
    if quiet:
        return subprocess.run(cmd, cwd=BUILD, capture_output=True).returncode == 0
    run(cmd)
    return True


def segments():
    segs = {}
    with open(os.path.join(BUILD, DBGFILE)) as f:
        for line in f:
            if line.startswith("seg\t"):
                d = dict(kv.split("=", 1) for kv in line[4:].strip().split(","))
                segs[d["name"].strip('"')] = (int(d["start"], 16), int(d["size"], 16))
    return segs


def build(bblan, extra_defs=(), bblan_raw=BBLAN_RAW):
    ca65, ld65 = find_tool("ca65"), find_tool("ld65")
    level_bins = LEVEL_BINS_BASE + (LEVEL_BINS_COMPRESSED if bblan else [])
    output = bblan_raw if bblan else OUTPUT

    with open(os.path.join(BUILD, "sound-select.inc"), "w") as f:
        f.write(f'.include "{SOUND_SRC}"\n')

    print("[1/4] converting data")
    py("convert-levels.py", os.path.join(DATA, "levels.txt"), *level_bins)
    py("convert-zone-data.py", os.path.join(DATA, "zone-data.txt"), "zone-data.bin")
    for out, tga, args in TGA_CONVERSIONS:
        py("convert-tga.py", os.path.join(DATA, tga), out, *args)
    py("extract-bonus-sprites.py")

    print("[2/4] assembling + [3/4] linking")
    if not bblan:
        assemble(ca65, [])
        link(ld65, output, ORIGINAL_BM_START)
    else:
        defs = ["-D", "COMPRESS_LEVELS=1"]
        if not any(d.startswith("ORIGLAYOUT") for d in extra_defs):
            defs += ["-D", "BBLAN=1"]
        for d in extra_defs:
            defs += ["-D", d]
        clen = os.path.getsize(os.path.join(BUILD, "level-bitmaps-compressed.bin"))
        # Start with most of the bitmaps in the I/O shadow; move bytes down
        # into PRG_MID until it links, then hand back the unused shadow space.
        split = max(0, clen - 3600)
        while True:
            bm_start = 0xD000 - 100 - split
            assemble(ca65, defs + ["-D", f"LEVEL_BM_START=${bm_start:04X}"])
            if link(ld65, output, bm_start, quiet=True):
                break
            split += 64
            if split > clen:
                link(ld65, output, bm_start)        # show the error
                sys.exit("error: cannot fit level bitmaps")
        io_end = max(s + z for s, z in segments().values() if 0xD000 <= s < 0xE000)
        slack = 0xE000 - io_end
        if slack > 0:
            split = max(0, split - slack)
            bm_start = 0xD000 - 100 - split
            assemble(ca65, defs + ["-D", f"LEVEL_BM_START=${bm_start:04X}"])
            link(ld65, output, bm_start)
        segs = segments()
        code_start, code_size = segs.get("BBLAN_CODE", (bm_start, 0))
        free = bm_start - (code_start + code_size)
        print(f"  BBLAN_CODE ${code_start:04X} {code_size} bytes, "
              f"{free} bytes free in PRG_MID, bitmaps at ${bm_start:04X}")

    if bblan:
        layout_check()

    print("[4/4] checking gaps")
    py("check-gaps.py", DBGFILE)
    print(f"built build/{output}")


# Segments that may differ from the original: data that only the level
# renderer reads (with symbolic references), and the new BB-LAN code.
LAYOUT_FREE = {"BBLAN_CODE", "IO_LEVEL_BITMAPS", "IO_LEVEL_BITMAPS_HI",
               "IO_BITMAP_DECODE_TABLE", "IO_BITMAP_DICT_PAIRS",
               "IO_CODE_DECOMPRESSOR", "BSS", "CODE", "DATA", "NULL", "RODATA",
               "ZEROPAGE"}


def layout_check():
    """Every original segment must keep its start and size: the game still has
    hidden absolute references, and moved code crashes in subtle ways."""
    with open(os.path.join(ROOT, "tools", "original-layout.json")) as f:
        ref = json.load(f)
    bad = []
    for name, (start, size) in segments().items():
        if name in LAYOUT_FREE or name not in ref:
            continue
        if [start, size] != ref[name]:
            bad.append(f"{name}: ${start:04X}+{size}, original ${ref[name][0]:04X}+{ref[name][1]}")
    if bad:
        sys.exit("error: layout differs from the original game:\n  " + "\n  ".join(bad))
    print("  layout: all original segments in place")


def verify():
    with open(os.path.join(BUILD, OUTPUT), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != REFERENCE_SHA256:
        sys.exit(f"VERIFY FAILED: {digest}")
    print("SUCCESS: hash matches original")


def label(name):
    with open(os.path.join(BUILD, LBLFILE)) as f:
        for line in f:
            m = re.match(r"al ([0-9A-Fa-f]+) \.(\S+)", line)
            if m and m.group(2) == name:
                return int(m.group(1), 16)
    sys.exit(f"error: label {name} not found")


def release(raw, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pack
    entry = label("game_entry")
    pack.pack(os.path.join(BUILD, raw), os.path.join(BUILD, out), entry)


def clean():
    keep_ext = (".py", ".cfg")
    for pat in ("*.o", "*.bin", "*.prg", "*.lbl", "*.dbg", "*.lst", "*.map", "*.sid",
                "sound-select.inc"):
        for p in glob.glob(os.path.join(BUILD, pat)):
            if not p.endswith(keep_ext):
                os.remove(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default="all",
                    choices=["all", "release", "verify", "original", "clean"])
    ap.add_argument("-D", dest="defs", action="append", default=[])
    ap.add_argument("-o", dest="name", default="bblan",
                    help="output name: build/NAME-raw.prg and build/NAME.prg")
    a = ap.parse_args()
    if a.target == "clean":
        clean()
        return
    if a.target in ("verify", "original"):
        build(False)
        if a.target == "verify":
            verify()
        else:
            release(OUTPUT, ORIGINAL_RELEASE)
        return
    build(True, a.defs, a.name + "-raw.prg")
    shutil.copy(os.path.join(BUILD, LBLFILE), os.path.join(BUILD, a.name + ".lbl"))
    if a.target == "release":
        release(a.name + "-raw.prg", a.name + ".prg")


if __name__ == "__main__":
    main()
