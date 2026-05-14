#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EMU = Path(r"C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2\Source\OTHER\_z80_lib_cburbridge\src")
RETURN_MARKER = 0xFFFE

sys.path.insert(0, str(EMU))
from z80 import instructions, registers, util  # noqa: E402


class FlatZ80:
    def __init__(self, image: bytes) -> None:
        self.mem = bytearray(0x10000)
        self.mem[0x6000 : 0x6000 + len(image)] = image
        self.reg = registers.Registers()
        with contextlib.redirect_stdout(io.StringIO()):
            self.ins = instructions.InstructionSet(self.reg)
        self.reg.SP = 0x5F00
        self.reg.PC = 0x6000
        self._set_word(self.reg.SP - 2, RETURN_MARKER)
        self.reg.SP -= 2

    def _get_word(self, addr: int) -> int:
        return self.mem[addr & 0xFFFF] | (self.mem[(addr + 1) & 0xFFFF] << 8)

    def _set_word(self, addr: int, value: int) -> None:
        self.mem[addr & 0xFFFF] = value & 0xFF
        self.mem[(addr + 1) & 0xFFFF] = (value >> 8) & 0xFF

    def _read_ref(self, ref: int) -> int:
        if ref >= 0x10000:
            return 0xFF
        return self.mem[ref & 0xFFFF]

    def _write_ref(self, ref: int, value: int) -> None:
        if ref < 0x10000:
            self.mem[ref & 0xFFFF] = value & 0xFF

    def step(self) -> None:
        ins = False
        args = ()
        while not ins:
            op = self.mem[self.reg.PC]
            ins, args = self.ins << op
            self.reg.PC = util.inc16(self.reg.PC)
        data = [self._read_ref(ref) for ref in ins.get_read_list(args)]
        for ref, value in ins.execute(data, args):
            self._write_ref(ref, value)

    def run(self, max_steps: int = 5_000_000) -> int:
        steps = 0
        while self.reg.PC != RETURN_MARKER:
            if steps >= max_steps:
                raise TimeoutError(f"timeout at PC=#{self.reg.PC:04X}")
            self.step()
            steps += 1
        return steps


def main() -> None:
    image = (ROOT / "zx7_poc_test.bin").read_bytes()
    expected = (ROOT / "level_01_canvas_p0.bin").read_bytes()
    z = FlatZ80(image)
    steps = z.run()
    actual = bytes(z.mem[0xC000 : 0xC000 + len(expected)])
    if actual != expected:
        for i, (a, b) in enumerate(zip(actual, expected)):
            if a != b:
                raise SystemExit(f"FAIL at +#{i:04X}: got #{a:02X}, expected #{b:02X}")
        raise SystemExit("FAIL: size mismatch")
    print(f"OK: ZX7 PoC decompressed {len(expected)} bytes, steps={steps}")


if __name__ == "__main__":
    main()
