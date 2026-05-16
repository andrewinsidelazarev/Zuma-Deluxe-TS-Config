#!/usr/bin/env python3
"""Z3 — bit-packed LZ77 с Elias-gamma длиной, 16-bit offset.

Format:
  Header: 2 bytes = uncompressed size (little-endian)
  Bit stream MSB-first внутри bytes:
    bit 0 = literal: следующие 8 bits = байт
    bit 1 = match: Elias-gamma length (≥ 2), потом 16-bit offset (high:low, offset = value + 1)

Encoder: greedy с hash chain (3-byte key, до 64 candidates за position).
Z80 decoder ~100 байт.

Usage:
  python compress_z3.py <in> <out>
"""
import sys
from pathlib import Path


MAX_OFFSET = 65536


class BitWriter:
    __slots__ = ('out', 'byte', 'bits')

    def __init__(self):
        self.out = bytearray()
        self.byte = 0
        self.bits = 0

    def write_bit(self, b: int) -> None:
        self.byte = (self.byte << 1) | (b & 1)
        self.bits += 1
        if self.bits == 8:
            self.out.append(self.byte)
            self.byte = 0
            self.bits = 0

    def write_bits(self, value: int, count: int) -> None:
        for i in range(count - 1, -1, -1):
            self.write_bit((value >> i) & 1)

    def write_byte(self, b: int) -> None:
        self.write_bits(b, 8)

    def write_u16_le(self, v: int) -> None:
        self.out.append(v & 0xFF)
        self.out.append((v >> 8) & 0xFF)

    def write_gamma(self, value: int) -> None:
        """Elias-gamma: floor(log2(V)) zeros + V в binary (MSB first)."""
        assert value >= 1
        bits = value.bit_length()
        for _ in range(bits - 1):
            self.write_bit(0)
        self.write_bits(value, bits)

    def flush(self) -> bytes:
        if self.bits > 0:
            self.byte <<= (8 - self.bits)
            self.out.append(self.byte)
            self.byte = 0
            self.bits = 0
        return bytes(self.out)


def z3_compress(data: bytes) -> bytes:
    n = len(data)
    bw = BitWriter()
    bw.write_u16_le(n)                                 # uncompressed size header

    i = 0
    hash_tab = {}                                       # 3-byte key → positions list

    while i < n:
        best_off, best_len = 0, 0
        if i + 2 < n:
            key = bytes(data[i:i+3])
            for pos in hash_tab.get(key, [])[-64:]:
                off = i - pos
                if off < 1 or off > MAX_OFFSET:
                    continue
                l = 0
                max_l = min(n - i, 65535)
                while l < max_l and data[pos + l] == data[i + l]:
                    l += 1
                if l > best_len and l >= 2:
                    best_off, best_len = off, l
                    if l >= 258:
                        break

        if best_len >= 2:
            bw.write_bit(1)
            bw.write_gamma(best_len)                    # length ≥ 2
            off_idx = best_off - 1
            bw.write_bits((off_idx >> 8) & 0xFF, 8)     # high byte
            bw.write_bits(off_idx & 0xFF, 8)            # low byte
            for k in range(best_len):
                pos = i + k
                if pos + 3 <= n:
                    hash_tab.setdefault(bytes(data[pos:pos+3]), []).append(pos)
            i += best_len
        else:
            bw.write_bit(0)
            bw.write_byte(data[i])
            if i + 3 <= n:
                hash_tab.setdefault(bytes(data[i:i+3]), []).append(i)
            i += 1

    return bw.flush()


def z3_decompress(packed: bytes) -> bytes:
    size = packed[0] | (packed[1] << 8)
    out = bytearray()

    # Bit reader
    byte_pos = 2
    byte_val = 0
    bits_left = 0

    def read_bit():
        nonlocal byte_val, bits_left, byte_pos
        if bits_left == 0:
            byte_val = packed[byte_pos]
            byte_pos += 1
            bits_left = 8
        b = (byte_val >> 7) & 1
        byte_val = (byte_val << 1) & 0xFF
        bits_left -= 1
        return b

    def read_bits(n):
        v = 0
        for _ in range(n):
            v = (v << 1) | read_bit()
        return v

    def read_gamma():
        zeros = 0
        while read_bit() == 0:
            zeros += 1
        v = 1
        for _ in range(zeros):
            v = (v << 1) | read_bit()
        return v

    while len(out) < size:
        mode = read_bit()
        if mode == 0:
            out.append(read_bits(8))
        else:
            length = read_gamma()
            off = (read_bits(8) << 8) | read_bits(8)
            offset = off + 1
            src_pos = len(out) - offset
            for k in range(length):
                out.append(out[src_pos + k])
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    src = Path(sys.argv[1]).read_bytes()
    packed = z3_compress(src)
    decoded = z3_decompress(packed)
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
