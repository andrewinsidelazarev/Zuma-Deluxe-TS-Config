#!/usr/bin/env python3
"""Simple RLE-byte compressor для PoC ресурс-pipeline TS-Conf.

Format (byte-aligned, ~25-байт Z80 unpacker):
  token 0x00         — end of stream
  token 0x01..0x7F   — literal block: token = count (1..127), затем count байт
  token 0x80..0xFF   — run:          length = (token & 0x7F) + 1 (1..128), next byte = value

Encoder greedy: runs >= 3 кодируются как run, иначе literal block.

Usage: py compress_rle.py <in> <out>
  py compress_rle.py c:/z80/zuma/level_01_canvas_p0.bin c:/z80/zuma/level_01_canvas_p0_rle.bin
"""
import sys
from pathlib import Path


def rle_compress(data: bytes) -> bytes:
    out = bytearray()
    literals = bytearray()
    i = 0
    n = len(data)

    def flush_literals():
        nonlocal literals
        while literals:
            chunk_size = min(len(literals), 127)
            out.append(chunk_size)
            out.extend(literals[:chunk_size])
            literals = literals[chunk_size:]

    while i < n:
        # detect run length at i
        b = data[i]
        run = 1
        while i + run < n and data[i + run] == b and run < 128:
            run += 1
        if run >= 3:
            flush_literals()
            out.append(0x80 | (run - 1))     # token 0x80..0xFF (length-1, decoder adds +1)
            out.append(b)
            i += run
        else:
            literals.append(b)
            i += 1
            if len(literals) >= 127:
                out.append(127)
                out.extend(literals)
                literals = bytearray()
    flush_literals()
    out.append(0)
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1]).read_bytes()
    packed = rle_compress(src)
    Path(sys.argv[2]).write_bytes(packed)
    print(f'{sys.argv[1]:60s} {len(src):6d} → {len(packed):6d} bytes ({100*len(packed)/len(src):.1f}%)')


if __name__ == '__main__':
    main()
