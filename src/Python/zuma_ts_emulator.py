#!/usr/bin/env python3
"""TS-Conf Zuma Z80 harness (adapted from VDAC2 zuma_full_z80_emulator.py).

Differences from VDAC2 harness:
  * Loads TS-Conf spgbld.ini (no FT812 / VDAC2 SPI).
  * Models FM_EN bank: writes to #0000..#03FF go to CRAM/SFILE when FM_EN
    bit (#10) is set in FMADDR port (#15AF). Otherwise normal RAM.
  * Models PALSEL port (#07AF) — toggles palette select bank.
  * Mouse port: MOUSE_BTN (#FADF).
  * No FT812 RAM_G/RAM_DL/RAM_CMD.

Usage:
    py -3.12 zuma_ts_emulator.py --call LevelSelect_Init
    py -3.12 zuma_ts_emulator.py --test-isolation
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
Z80_LIB = HERE / "_z80_lib_cburbridge" / "src"
RETURN_MARKER = 0xFFFE
PAGE_SIZE = 0x4000
NUM_PAGES = 256

sys.path.insert(0, str(Z80_LIB))
from z80 import instructions, registers, util  # noqa: E402


def parse_num(text: str) -> int:
    text = text.strip()
    if text.startswith("#"):
        return int(text[1:], 16)
    if text.lower().startswith("0x"):
        return int(text[2:], 16)
    return int(text, 10)


def parse_sym(path: Path) -> Dict[str, int]:
    syms: Dict[str, int] = {}
    rx = re.compile(r"^\s*([\w.]+):\s+EQU\s+([#$0-9A-Fa-fx]+)\s*$")
    if not path.exists():
        return syms
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = rx.match(line)
            if m:
                syms[m.group(1)] = parse_num(m.group(2))
    return syms


def parse_listing_sym(path: Path) -> Dict[str, int]:
    """Parse sjasmplus LABELSLIST lines: slot:offset name."""
    syms: Dict[str, int] = {}
    rx = re.compile(r"^\s*([0-3][0-9A-Fa-f]?):([0-9A-Fa-f]{4})\s+([\w.]+)\s*$")
    if not path.exists():
        return syms
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = rx.match(line)
            if not m:
                continue
            slot = int(m.group(1), 16)
            off = int(m.group(2), 16)
            syms[m.group(3)] = slot * PAGE_SIZE + off
    return syms


@dataclass
class InputState:
    mouse_x: int = 0
    mouse_y: int = 0
    mouse_buttons: int = 0x03   # 1=released, 0=pressed (active-low)
    kempston: int = 0x00
    keyboard_rows: Dict[int, int] = field(default_factory=dict)
    rtc_seconds_bcd: int = 0x17


class TSConfigMemory:
    """16K-paged 64K address space + FM_EN-banked CRAM/SFILE (1KB each).

    Slots: pages[0]=#0000-#3FFF, pages[1]=#4000-#7FFF, pages[2]=#8000-#BFFF, pages[3]=#C000-#FFFF.
    """
    def __init__(self) -> None:
        self.physical = bytearray(NUM_PAGES * PAGE_SIZE)
        self.pages = [0, 5, 2, 0]   # default: page #00, #05 (main0), #02 (main1), #00
        self.cram = bytearray(512)    # #0000..#01FF when FM_EN
        self.sfile = bytearray(512)   # #0200..#03FF when FM_EN
        self.fm_en = False
        self.palsel = 0

    def map_addr(self, addr: int) -> int:
        slot = (addr >> 14) & 3
        return self.pages[slot] * PAGE_SIZE + (addr & 0x3FFF)

    def read(self, addr: int) -> int:
        if self.fm_en and addr < 0x0400:
            if addr < 0x0200:
                return self.cram[addr]
            return self.sfile[addr - 0x0200]
        return self.physical[self.map_addr(addr)]

    def write(self, addr: int, value: int) -> None:
        value &= 0xFF
        if self.fm_en and addr < 0x0400:
            if addr < 0x0200:
                self.cram[addr] = value
            else:
                self.sfile[addr - 0x0200] = value
            return
        self.physical[self.map_addr(addr)] = value

    def read_block(self, addr: int, length: int) -> bytes:
        return bytes(self.read(addr + i) for i in range(length))

    def load_page_block(self, page: int, offset: int, data: bytes) -> None:
        start = page * PAGE_SIZE + offset
        end = min(start + len(data), (page + 1) * PAGE_SIZE)
        self.physical[start:end] = data[: end - start]


class ZumaTSEmulator:
    def __init__(self, root: Path = HERE, trace: bool = False) -> None:
        self.root = Path(root)
        self.sym = parse_sym(self.root / "zuma.sym")
        self.sym.update(parse_listing_sym(self.root / "user.l"))
        self.mem = TSConfigMemory()
        self.input = InputState()
        self.trace = trace
        self.ports_out: List[Tuple[int, int]] = []
        self.ports_in: List[Tuple[int, int]] = []
        self.tstates = 0

        self.reg = registers.Registers()
        with contextlib.redirect_stdout(io.StringIO()):
            self.ins = instructions.InstructionSet(self.reg)

        self._load_spg_blocks()
        self.reg.SP = parse_num(self._ini_scalar("Stack", "0xC000"))
        self.reg.PC = parse_num(self._ini_scalar("Start", "0x6000"))
        self.min_sp = self.reg.SP
        self.stack_guard_top = self.reg.SP    # initial stack top
        self.stack_overflow = False
        # Set default PAGE0..3 mapping based on ini (Page3 = ?)
        # From spgbld.ini: Page3 = 0 by default; runtime sets to #60 etc.
        self.mem.pages[0] = 0
        self.mem.pages[1] = 5     # main0.bin on page 5
        self.mem.pages[2] = 2     # main1.bin on page 2
        self.mem.pages[3] = 0

    def _ini_scalar(self, key: str, default: str) -> str:
        ini = self.root / "spgbld.ini"
        rx = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", re.I)
        with ini.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = rx.match(line)
                if m:
                    return m.group(1).strip()
        return default

    def _load_spg_blocks(self) -> None:
        ini = self.root / "spgbld.ini"
        rx = re.compile(r"^\s*Block\s*=\s*([^,]+),\s*([^,]+),\s*(.+?)\s*$", re.I)
        with ini.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = rx.match(line)
                if not m:
                    continue
                offset = parse_num(m.group(1)) & 0x3FFF
                page = parse_num(m.group(2)) & 0xFF
                rel = m.group(3).strip().replace("/", os.sep)
                path = self.root / rel
                if not path.exists():
                    continue
                data = path.read_bytes()
                self.mem.load_page_block(page, offset, data)

    def get_byte(self, addr: int) -> int:
        return self.mem.read(addr)

    def set_byte(self, addr: int, value: int) -> None:
        self.mem.write(addr, value)

    def get_word(self, addr: int) -> int:
        return self.get_byte(addr) | (self.get_byte(addr + 1) << 8)

    def set_word(self, addr: int, value: int) -> None:
        self.set_byte(addr, value & 0xFF)
        self.set_byte(addr + 1, (value >> 8) & 0xFF)

    def get_memory(self, addr: int, length: int) -> bytes:
        return self.mem.read_block(addr, length)

    def step(self) -> int:
        pc0 = self.reg.PC
        ins, args = False, ()
        try:
            while not ins:
                op = self.mem.read(self.reg.PC)
                ins, args = self.ins << op
                self.reg.PC = util.inc16(self.reg.PC)
        except Exception as exc:
            raise RuntimeError(f"decode failed at PC=#{pc0:04X}: {exc}") from exc

        reads = ins.get_read_list(args)
        data = [self._read_ref(ref) for ref in reads]
        writes = ins.execute(data, args)
        for ref, value in writes:
            self._write_ref(ref, value)
        self.tstates += getattr(ins, "tstates", 0)
        # Track minimum SP for stack-depth analysis.
        if self.reg.SP < self.min_sp:
            self.min_sp = self.reg.SP
        if self.trace:
            print(f"{pc0:04X}: {ins.assembler(args)}")
        return getattr(ins, "tstates", 0)

    def run_until_pc(self, pc: int, max_steps: int = 2_000_000) -> int:
        steps = 0
        while self.reg.PC != pc:
            if steps >= max_steps:
                raise TimeoutError(f"timeout at PC=#{self.reg.PC:04X}, target=#{pc:04X}")
            self.step()
            steps += 1
        return steps

    def call(self, addr: int, *, a: int = 0, b: int = 0, c: int = 0, d: int = 0,
             e: int = 0, h: int = 0, l: int = 0, max_steps: int = 2_000_000) -> int:
        self.reg.A = a & 0xFF
        self.reg.B = b & 0xFF
        self.reg.C = c & 0xFF
        self.reg.D = d & 0xFF
        self.reg.E = e & 0xFF
        self.reg.H = h & 0xFF
        self.reg.L = l & 0xFF
        sp = (self.reg.SP - 2) & 0xFFFF
        self.set_word(sp, RETURN_MARKER)
        self.reg.SP = sp
        self.reg.PC = addr & 0xFFFF
        return self.run_until_pc(RETURN_MARKER, max_steps=max_steps)

    def _read_ref(self, ref: int) -> int:
        if ref >= 0x10000:
            value = self.in_port(ref & 0xFFFF)
            self.ports_in.append((ref & 0xFFFF, value))
            return value
        return self.mem.read(ref)

    def _write_ref(self, ref: int, value: int) -> None:
        value &= 0xFF
        if ref >= 0x10000:
            self.out_port(ref & 0xFFFF, value)
            self.ports_out.append((ref & 0xFFFF, value))
        else:
            self.mem.write(ref, value)

    def in_port(self, port: int) -> int:
        low = port & 0xFF
        high = (port >> 8) & 0xFF
        if port == 0xBFF7:
            return self.input.rtc_seconds_bcd
        if low == 0x1F:
            return self.input.kempston
        if low == 0xDF:
            # MOUSE_BTN = #FADF
            if high == 0xFA:
                return self.input.mouse_buttons
            return self.input.mouse_x & 0xFF
        if low == 0xFF:
            return self.input.mouse_y & 0xFF
        if low == 0xFE:
            return self.input.keyboard_rows.get(high, 0xFF)
        if low == 0xAF:
            # DMA status read (DMACTR #27AF). Bit 7 = DMAWNR (busy).
            # Mock: always return 0 — DMA done immediately. Lets game code proceed
            # past `IN A,(C); AND DMAWNR; JR NZ, wait` polling loops.
            return 0x00
        return 0xFF

    def out_port(self, port: int, value: int) -> None:
        low = port & 0xFF
        high = (port >> 8) & 0xFF
        if low == 0xAF:
            self._write_tsconf_register(high, value)

    def _write_tsconf_register(self, reg: int, value: int) -> None:
        if reg == 0x10:    # PAGE0
            self.mem.pages[0] = value & 0xFF
        elif reg == 0x11:  # PAGE1
            self.mem.pages[1] = value & 0xFF
        elif reg == 0x12:  # PAGE2
            self.mem.pages[2] = value & 0xFF
        elif reg == 0x13:  # PAGE3
            self.mem.pages[3] = value & 0xFF
        elif reg == 0x15:  # FMADDR — FM_EN bit (#10) gates CRAM/SFILE access
            self.mem.fm_en = bool(value & 0x10)
        elif reg == 0x07:  # PALSEL
            self.mem.palsel = value & 0xFF

    # ---- Inspection helpers ----
    def sfile_dump(self) -> bytes:
        return bytes(self.mem.sfile)

    def cram_dump(self) -> bytes:
        return bytes(self.mem.cram)


# =============================================================================
# Tests
# =============================================================================
def test_isolation(root: Path = HERE) -> int:
    """Verify LevelSelect_Init clears stale Game descriptors from SFILE."""
    emu = ZumaTSEmulator(root)

    # Pre-inject "stale Game state" into SFILE — pretend Game just exited:
    # - DESC_CHAIN0 area #0218..#03BB filled with garbage active descriptors.
    # - DESC_BALL0 area #03BC..#03EB filled with garbage.
    # All SFILE bytes set to 0xAA (= active-looking descriptor garbage).
    for off in range(0x0200, 0x03FE):
        emu.mem.sfile[off - 0x0200] = 0xAA

    # Verify pre-state
    pre = emu.sfile_dump()
    pre_garbage_count = sum(1 for b in pre[:0x1FE] if b == 0xAA)  # #0200..#03FD
    print(f"[before LS_Init] SFILE #0200..#03FD: {pre_garbage_count} bytes = 0xAA (garbage)")

    # Call LevelSelect_Init
    ls_init = emu.sym["LevelSelect_Init"]
    print(f"[call] LevelSelect_Init @ #{ls_init:04X}")
    try:
        # Cap steps so we don't run full Init (which calls UnpackZX7 / DMA etc).
        # SFILE clear happens early — first ~600 instructions.
        emu.reg.SP = 0xC000
        sp = (emu.reg.SP - 2) & 0xFFFF
        emu.set_word(sp, RETURN_MARKER)
        emu.reg.SP = sp
        emu.reg.PC = ls_init

        # Step through, stop after SFILE clear is done (= when FMADDR=0 written after lsi_clr2)
        # We'll watch for the OUT (#15AF), 0 sequence after lsi_clr2 (#892D).
        # Simpler: step 5000 instructions and inspect SFILE.
        for _ in range(20000):
            if emu.reg.PC == RETURN_MARKER:
                break
            # Stop if we got past the SFILE clear loop section.
            if emu.reg.PC > emu.sym.get("LevelSelect_Init.lsi_clr2", 0) + 20:
                if emu.reg.PC > 0x8940:  # post-loop
                    break
            emu.step()
    except Exception as e:
        print(f"[error] {e}")

    # Verify SFILE cleared
    post = emu.sfile_dump()
    post_zeros = sum(1 for b in post[:0x1FE] if b == 0)
    post_garbage = sum(1 for b in post[:0x1FE] if b == 0xAA)
    print(f"[after  loop] SFILE #0200..#03FD: {post_zeros} zeros, {post_garbage} still-garbage bytes")

    if post_garbage == 0 and post_zeros >= 510:
        print("PASS: SFILE fully cleared (510/510 bytes zeroed, isolation works)")
        return 0
    else:
        print(f"FAIL: SFILE not fully cleared. {post_garbage} bytes of stale garbage remain.")
        # Dump first bytes for diagnostic
        sample = post[:32]
        print(f"  First 32 bytes: {sample.hex()}")
        return 1


def test_stack(root: Path = HERE, symbol: str = "LevelSelect_Init") -> int:
    """Verify stack balance, sentinel intact, and report max depth for symbol call."""
    emu = ZumaTSEmulator(root)
    if symbol not in emu.sym:
        print(f"unknown symbol: {symbol}")
        return 1

    SENTINEL_LO = 0xBE00   # ниже допустимой глубины стека
    SENTINEL = (0xDE, 0xAD, 0xBE, 0xEF)
    for i, b in enumerate(SENTINEL):
        emu.set_byte(SENTINEL_LO + i, b)

    sp_before = emu.reg.SP
    emu.min_sp = sp_before
    print(f"[{symbol}] SP before = #{sp_before:04X}, sentinel #{SENTINEL_LO:04X}..#{SENTINEL_LO+3:04X} = {bytes(SENTINEL).hex()}")

    try:
        emu.call(emu.sym[symbol], max_steps=200000)
    except Exception as e:
        print(f"[error during call] {e}")
        return 1

    sp_after = emu.reg.SP
    sentinel_after = bytes(emu.get_byte(SENTINEL_LO + i) for i in range(4))
    used = sp_before - emu.min_sp
    print(f"[{symbol}] SP after  = #{sp_after:04X}  (delta from before: {sp_before - sp_after:+d})")
    print(f"[{symbol}] min SP    = #{emu.min_sp:04X}  (max stack used: {used} bytes)")
    print(f"[{symbol}] sentinel after = {sentinel_after.hex()}  ({'intact' if sentinel_after == bytes(SENTINEL) else 'OVERWRITTEN'})")

    failures = []
    if sp_before != sp_after:
        failures.append(f"stack leak ({sp_before - sp_after:+d} bytes)")
    if sentinel_after != bytes(SENTINEL):
        failures.append("sentinel overwritten — stack overflow into data area")
    if emu.min_sp < SENTINEL_LO + 4:
        failures.append(f"min SP #{emu.min_sp:04X} crossed sentinel boundary #{SENTINEL_LO:04X}")

    if failures:
        print(f"FAIL: {'; '.join(failures)}")
        return 1
    print("PASS: stack balanced, sentinel intact, depth within budget")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-isolation", action="store_true", help="run SFILE isolation test")
    ap.add_argument("--test-stack", action="store_true", help="run stack integrity test")
    ap.add_argument("--symbol", type=str, default="LevelSelect_Init", help="symbol for --test-stack")
    ap.add_argument("--call", type=str, help="call a symbol and report state")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    if args.test_isolation:
        return test_isolation()

    if args.test_stack:
        return test_stack(symbol=args.symbol)

    if args.call:
        emu = ZumaTSEmulator(trace=args.trace)
        if args.call not in emu.sym:
            print(f"unknown symbol: {args.call}")
            return 1
        steps = emu.call(emu.sym[args.call])
        print(f"call {args.call} done: steps={steps}, pc=#{emu.reg.PC:04X}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
