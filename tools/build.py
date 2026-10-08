#!/usr/bin/env python3
"""BB-LAN build script (replaces build/Makefile on Windows; no make needed).

Usage:
    python tools/build.py              build build/rebb64-raw.prg
    python tools/build.py verify       build + check SHA256 against the original
    python tools/build.py release      build + packed, runnable build/bblan.prg
    python tools/build.py clean        remove build artifacts

Options:
    --compress-levels                  per-level bitmap compression (~1.2 KB free)

Tools: ca65/ld65 are taken from $CC65_HOME/bin, else ../c64/cc65/bin next to
this repo, else PATH.
"""
import argparse
import glob
import hashlib
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
RELEASE = "bblan.prg"
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


def build(compress_levels):
    ca65, ld65 = find_tool("ca65"), find_tool("ld65")
    level_bins = LEVEL_BINS_BASE + (LEVEL_BINS_COMPRESSED if compress_levels else [])
    defs = ["-D", "COMPRESS_LEVELS=1"] if compress_levels else []

    with open(os.path.join(BUILD, "sound-select.inc"), "w") as f:
        f.write(f'.include "{SOUND_SRC}"\n')

    print("[1/4] converting data")
    py("convert-levels.py", os.path.join(DATA, "levels.txt"), *level_bins)
    py("convert-zone-data.py", os.path.join(DATA, "zone-data.txt"), "zone-data.bin")
    for out, tga, args in TGA_CONVERSIONS:
        py("convert-tga.py", os.path.join(DATA, tga), out, *args)
    py("extract-bonus-sprites.py")

    print("[2/4] assembling")
    run([ca65, "--cpu", "6502", "-o", "loadaddr.o", os.path.join(SRC, "loadaddr.s")])
    run([ca65, "--cpu", "6502", *defs, "-I", SRC, "-I", ".", "-o", "master.o",
         os.path.join(SRC, "master.s")])

    print("[3/4] linking")
    run([ld65, "-C", "c64-prg.cfg", "-Ln", LBLFILE, "--dbgfile", DBGFILE,
         "-o", OUTPUT, "loadaddr.o", "master.o"])

    print("[4/4] checking gaps")
    py("check-gaps.py", DBGFILE)
    print(f"built build/{OUTPUT}")


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


def release():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pack
    entry = label("game_entry")
    pack.pack(os.path.join(BUILD, OUTPUT), os.path.join(BUILD, RELEASE), entry)


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
                    choices=["all", "verify", "release", "clean"])
    ap.add_argument("--compress-levels", action="store_true")
    a = ap.parse_args()
    if a.target == "clean":
        clean()
        return
    build(a.compress_levels)
    if a.target == "verify":
        verify()
    elif a.target == "release":
        release()


if __name__ == "__main__":
    main()
