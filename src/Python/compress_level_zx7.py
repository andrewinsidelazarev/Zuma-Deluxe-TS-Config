#!/usr/bin/env python3
"""ZX7-compress 9 canvas pages of level N → level_NN_canvas_p0..p8_zx7.bin.

Usage: python compress_level_zx7.py <N>
"""
import sys
import subprocess
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python compress_level_zx7.py <N>")
    sys.exit(1)

N = int(sys.argv[1])
TAG = f"{N:02d}"
DST = Path(r"C:/z80/zuma")
TOOL = DST / "compress_zx7_lite.py"

if not TOOL.exists():
    sys.exit(f"Missing compressor: {TOOL}")

total_in = 0
total_out = 0
for p in range(9):
    in_bin = DST / f"level_{TAG}_canvas_p{p}.bin"
    out_zx7 = DST / f"level_{TAG}_canvas_p{p}_zx7.bin"
    if not in_bin.exists():
        sys.exit(f"Missing canvas page: {in_bin} — run import_real_level.py {N} first")
    result = subprocess.run(["python3", str(TOOL), str(in_bin), str(out_zx7)],
                            capture_output=True, text=True, cwd=str(DST))
    if result.returncode != 0:
        print(f"  p{p}: FAILED — {result.stderr.strip()}")
        sys.exit(1)
    in_size = in_bin.stat().st_size
    out_size = out_zx7.stat().st_size
    total_in += in_size
    total_out += out_size
    print(f"  p{p}: {in_size} → {out_size} ({100*out_size/in_size:.1f}%)")

print(f"Total: {total_in} → {total_out} ({100*total_out/total_in:.1f}%)")
