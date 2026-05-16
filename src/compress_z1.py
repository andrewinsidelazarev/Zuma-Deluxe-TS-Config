#!/usr/bin/env python3
"""Z1v2 — LZ77 для compressed scene bundles. Простой формат, ~80 byte Z80 unpacker.

Format (byte stream):
  TOKEN 0x00         — end of stream
  TOKEN 0x01..0x7F   — literal block: count = TOKEN (1..127), затем count байт
  TOKEN 0x80..0xFF   — match (длина 2..129):
                         length = (TOKEN & 0x7F) + 2 (2..129)
                         NEXT byte = offset_hi
                         NEXT byte = offset_lo
                         offset = (offset_hi << 8) | offset_lo + 1 (1..65536)

Encoder: greedy с hash chain (3-byte hash).
"""
import sys
from pathlib import Path


MAX_OFFSET = 65536
MAX_LENGTH = 129
MIN_LENGTH = 2


def lz1_compress(data: bytes) -> bytes:
    n = len(data)
    out = bytearray()
    literals = bytearray()
    i = 0

    # Hash table: key=3-byte → list of positions (latest)
    hash_table = {}

    def flush_literals():
        nonlocal literals
        while literals:
            chunk = bytes(literals[:127])
            out.append(len(chunk))
            out.extend(chunk)
            literals = literals[127:]

    while i < n:
        best_off, best_len = 0, 0
        # Find longest match starting at i
        if i + MIN_LENGTH + 1 <= n:
            key = bytes(data[i:i+3])
            positions = hash_table.get(key, [])
            # Check last 32 occurrences
            for pos in positions[-32:]:
                off = i - pos
                if off > MAX_OFFSET or off < 1:
                    continue
                l = 0
                while l < MAX_LENGTH and i + l < n and data[pos + l] == data[i + l]:
                    l += 1
                if l > best_len and l >= MIN_LENGTH:
                    best_off, best_len = off, l
                    if best_len >= MAX_LENGTH:
                        break

        if best_len >= MIN_LENGTH:
            flush_literals()
            off_idx = best_off - 1                                    # 0..65535
            off_hi = (off_idx >> 8) & 0xFF
            off_lo = off_idx & 0xFF
            token = 0x80 | (best_len - MIN_LENGTH)
            out.append(token)
            out.append(off_hi)
            out.append(off_lo)
            # update hash for consumed positions
            for k in range(best_len):
                pos = i + k
                if pos + 3 <= n:
                    hkey = bytes(data[pos:pos+3])
                    hash_table.setdefault(hkey, []).append(pos)
            i += best_len
        else:
            literals.append(data[i])
            if i + 3 <= n:
                hkey = bytes(data[i:i+3])
                hash_table.setdefault(hkey, []).append(i)
            i += 1
    flush_literals()
    out.append(0)
    return bytes(out)


def lz1_decompress(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        t = data[i]; i += 1
        if t == 0:
            break
        if t & 0x80:
            length = (t & 0x7F) + MIN_LENGTH
            off_hi = data[i]; i += 1
            off_lo = data[i]; i += 1
            offset = ((off_hi << 8) | off_lo) + 1
            src_pos = len(out) - offset
            for k in range(length):
                out.append(out[src_pos + k])
        else:
            out.extend(data[i:i+t])
            i += t
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    src = Path(sys.argv[1]).read_bytes()
    packed = lz1_compress(src)
    decoded = lz1_decompress(packed)
    if decoded != src:
        print('ERROR: round-trip mismatch!')
        for j in range(min(len(decoded), len(src))):
            if decoded[j] != src[j]:
                print(f'  first diff at byte {j}: src={src[j]}, decoded={decoded[j]}')
                break
        sys.exit(2)
    Path(sys.argv[2]).write_bytes(packed)
    print(f'{sys.argv[1]:60s} {len(src):6d} → {len(packed):6d} bytes ({100*len(packed)/len(src):.1f}%)')


if __name__ == '__main__':
    main()
