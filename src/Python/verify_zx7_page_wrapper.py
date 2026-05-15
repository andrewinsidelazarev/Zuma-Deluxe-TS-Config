#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EMU = Path(r"C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2\Source\OTHER\_z80_lib_cburbridge\src")
PAGE_SIZE = 0x4000
RETURN_MARKER = 0xFFFE
PAGE2 = 0x12AF
PAGE3 = 0x13AF

sys.path.insert(0, str(EMU))
from z80 import instructions, registers, util  # noqa: E402


def parse_user_l(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    rx = re.compile(r"^[0-9A-F]{2}:([0-9A-F]{4})\s+([A-Za-z_][\w.]*)$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = rx.match(line.strip())
        if m:
            out[m.group(2)] = 0x4000 + int(m.group(1), 16)
    return out


class TSMem:
    def __init__(self) -> None:
        self.phys = bytearray(256 * PAGE_SIZE)
        self.pages = [0, 5, 2, 0x60]

    def map(self, addr: int) -> int:
        addr &= 0xFFFF
        return self.pages[addr >> 14] * PAGE_SIZE + (addr & 0x3FFF)

    def read(self, addr: int) -> int:
        return self.phys[self.map(addr)]

    def write(self, addr: int, value: int) -> None:
        self.phys[self.map(addr)] = value & 0xFF

    def load_page(self, page: int, offset: int, data: bytes) -> None:
        start = page * PAGE_SIZE + offset
        self.phys[start : start + len(data)] = data

    def page_bytes(self, page: int) -> bytes:
        start = page * PAGE_SIZE
        return bytes(self.phys[start : start + PAGE_SIZE])


class Machine:
    def __init__(self) -> None:
        self.mem = TSMem()
        self.reg = registers.Registers()
        with contextlib.redirect_stdout(io.StringIO()):
            self.ins = instructions.InstructionSet(self.reg)

    def read_ref(self, ref: int) -> int:
        if ref >= 0x10000:
            return 0xFF
        return self.mem.read(ref)

    def write_ref(self, ref: int, value: int) -> None:
        value &= 0xFF
        if ref >= 0x10000:
            port = ref & 0xFFFF
            if port == PAGE2:
                self.mem.pages[2] = value
            elif port == PAGE3:
                self.mem.pages[3] = value
            return
        self.mem.write(ref, value)

    def set_word(self, addr: int, value: int) -> None:
        self.mem.write(addr, value)
        self.mem.write(addr + 1, value >> 8)

    def step(self) -> None:
        ins = False
        args = ()
        while not ins:
            op = self.mem.read(self.reg.PC)
            ins, args = self.ins << op
            self.reg.PC = util.inc16(self.reg.PC)
        data = [self.read_ref(ref) for ref in ins.get_read_list(args)]
        for ref, value in ins.execute(data, args):
            self.write_ref(ref, value)

    def call(self, addr: int, a: int, b: int, max_steps: int = 1_000_000) -> int:
        self.reg.A = a
        self.reg.B = b
        self.reg.SP = 0x5000
        self.set_word(self.reg.SP - 2, RETURN_MARKER)
        self.reg.SP -= 2
        self.reg.PC = addr
        steps = 0
        while self.reg.PC != RETURN_MARKER:
            if steps >= max_steps:
                raise TimeoutError(f"timeout at PC=#{self.reg.PC:04X}")
            self.step()
            steps += 1
        return steps


def main() -> None:
    labels = parse_user_l(ROOT / "user.l")
    entry = labels["UnpackZX7Page"]
    m = Machine()
    m.mem.load_page(5, 0x2000, (ROOT / "main0.bin").read_bytes())
    m.mem.load_page(0x5E, 0, (ROOT / "level_01_canvas_p0_zx7.bin").read_bytes())
    steps = m.call(entry, a=0x5E, b=0x10)
    expected = (ROOT / "level_01_canvas_p0.bin").read_bytes()
    actual = m.mem.page_bytes(0x10)
    if actual != expected:
        for i, (a, b) in enumerate(zip(actual, expected)):
            if a != b:
                raise SystemExit(f"FAIL page wrapper at +#{i:04X}: got #{a:02X}, expected #{b:02X}")
        raise SystemExit("FAIL page wrapper: size mismatch")
    print(f"OK: UnpackZX7Page #5E -> #10, {len(expected)} bytes, steps={steps}")


if __name__ == "__main__":
    main()
