#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
Z80_LIB = Path(r"C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2\Source\OTHER\_z80_lib_cburbridge\src")
PAGE_SIZE = 0x4000
RETURN_MARKER = 0xFFFE

PAGE2 = 0x12AF
PAGE3 = 0x13AF
PALSEL = 0x07AF
FMADDR = 0x15AF
DMASADL = 0x1AAF
DMASADH = 0x1BAF
DMASADX = 0x1CAF
DMADADL = 0x1DAF
DMADADH = 0x1EAF
DMADADX = 0x1FAF
DMALEN = 0x26AF
DMACTR = 0x27AF
DMANUM = 0x28AF

sys.path.insert(0, str(Z80_LIB))
from z80 import instructions, registers, util  # noqa: E402


def parse_num(text: str) -> int:
    text = text.strip()
    if text.startswith("#"):
        return int(text[1:], 16)
    if text.lower().startswith("0x"):
        return int(text[2:], 16)
    return int(text, 10)


def parse_user_l(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    rx = re.compile(r"^([0-9A-F]{2}):([0-9A-F]{4})\s+([A-Za-z_][\w.]*)$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = rx.match(line.strip())
        if not m:
            continue
        page = int(m.group(1), 16)
        off = int(m.group(2), 16)
        # page 5 code is assembled at #6000; page 2 code at #8000.
        logical = 0x4000 * (off // 0x4000) + off
        if page == 5:
            logical = 0x4000 + off
        elif page == 2:
            logical = 0x8000 + off
        out[m.group(3)] = logical & 0xFFFF
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
        end = min(start + len(data), (page + 1) * PAGE_SIZE)
        self.phys[start:end] = data[: end - start]

    def page_bytes(self, page: int) -> bytes:
        start = page * PAGE_SIZE
        return bytes(self.phys[start : start + PAGE_SIZE])


class Machine:
    def __init__(self) -> None:
        self.mem = TSMem()
        self.reg = registers.Registers()
        with contextlib.redirect_stdout(io.StringIO()):
            self.ins = instructions.InstructionSet(self.reg)
        self.cram = bytearray(0x200)
        self.sfile = bytearray(0x200)
        self.fm_en = False
        self.palsel = 0
        self.dma = {
            "sad": 0,
            "sad_page": 0,
            "dad": 0,
            "dad_page": 0,
            "len": 0,
            "num": 0,
        }
        self.vpage = 0
        self.vconfig = 0
        self.out_log: list[tuple[int, int]] = []

    def load_spgbld(self) -> None:
        rx = re.compile(r"^\s*Block\s*=\s*([^,]+),\s*([^,]+),\s*(.+?)\s*$", re.I)
        for line in (ROOT / "spgbld.ini").read_text(encoding="utf-8", errors="replace").splitlines():
            m = rx.match(line)
            if not m:
                continue
            start = parse_num(m.group(1)) & 0x3FFF
            page = parse_num(m.group(2)) & 0xFF
            rel = m.group(3).strip()
            self.mem.load_page(page, start, (ROOT / rel).read_bytes())

    def read_ref(self, ref: int) -> int:
        if ref >= 0x10000:
            return self.in_port(ref & 0xFFFF)
        addr = ref & 0xFFFF
        if self.fm_en:
            if addr < 0x0200:
                return self.cram[addr]
            if 0x0200 <= addr < 0x0400:
                return self.sfile[addr - 0x0200]
        return self.mem.read(addr)

    def write_ref(self, ref: int, value: int) -> None:
        value &= 0xFF
        if ref >= 0x10000:
            self.out_port(ref & 0xFFFF, value)
            return
        addr = ref & 0xFFFF
        if self.fm_en:
            if addr < 0x0200:
                self.cram[addr] = value
                return
            if 0x0200 <= addr < 0x0400:
                self.sfile[addr - 0x0200] = value
                return
        self.mem.write(addr, value)

    def in_port(self, port: int) -> int:
        if port == DMACTR:
            return 0
        if (port & 0xFF) == 0xFE:
            return 0xFF
        return 0

    def out_port(self, port: int, value: int) -> None:
        self.out_log.append((port, value))
        if port == PAGE2:
            self.mem.pages[2] = value
        elif port == PAGE3:
            self.mem.pages[3] = value
        elif port == PALSEL:
            self.palsel = value
        elif port == FMADDR:
            self.fm_en = bool(value & 0x10)
        elif port == 0x01AF:
            self.vpage = value
        elif port == 0x00AF:
            self.vconfig = value
        elif port == DMASADL:
            self.dma["sad"] = (self.dma["sad"] & 0xFF00) | value
        elif port == DMASADH:
            self.dma["sad"] = (self.dma["sad"] & 0x00FF) | (value << 8)
        elif port == DMASADX:
            self.dma["sad_page"] = value
        elif port == DMADADL:
            self.dma["dad"] = (self.dma["dad"] & 0xFF00) | value
        elif port == DMADADH:
            self.dma["dad"] = (self.dma["dad"] & 0x00FF) | (value << 8)
        elif port == DMADADX:
            self.dma["dad_page"] = value
        elif port == DMALEN:
            self.dma["len"] = value
        elif port == DMANUM:
            self.dma["num"] = value
        elif port == DMACTR:
            self.run_dma(value)

    def run_dma(self, mode: int) -> None:
        burst = (self.dma["len"] + 1) * 2
        rows = self.dma["num"] + 1
        src_page = self.dma["sad_page"]
        dst_page = self.dma["dad_page"]
        src = self.dma["sad"]
        dst = self.dma["dad"]
        # Enough for this test: LsCopy9Pages uses 32 rows * 512 bytes = 16K.
        for row in range(rows):
            s = src_page * PAGE_SIZE + ((src + row * 0x200) & 0x3FFF)
            d = dst_page * PAGE_SIZE + ((dst + row * 0x200) & 0x3FFF)
            self.mem.phys[d : d + burst] = self.mem.phys[s : s + burst]

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

    def call(self, addr: int, max_steps: int = 2_000_000) -> int:
        self.reg.SP = 0xF000
        self.set_word(self.reg.SP - 2, RETURN_MARKER)
        self.reg.SP = (self.reg.SP - 2) & 0xFFFF
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
    m = Machine()
    m.load_spgbld()
    steps = m.call(labels["LevelSelect_GotoGame"])
    expected_pal = (ROOT / "level_01_canvas_pal.bin").read_bytes()
    actual_pal = bytes(m.cram[0x100:0x200])
    print(f"steps={steps} vpage=#{m.vpage:02X} vconfig=#{m.vconfig:02X} palsel=#{m.palsel:02X} pages={m.mem.pages}")
    print(f"cram_0100_match={actual_pal == expected_pal}")
    if actual_pal != expected_pal:
        for i, (got, exp) in enumerate(zip(actual_pal, expected_pal)):
            if got != exp:
                print(f"first_cram_diff=+#{i:02X} got=#{got:02X} exp=#{exp:02X}")
                break
    for page in range(0x10, 0x19):
        ok = m.mem.page_bytes(page) == m.mem.page_bytes(0x30 + (page - 0x10))
        print(f"page #{page:02X} == golden #{0x30 + (page - 0x10):02X}: {ok}")
    print("last palette-related OUTs:")
    for port, value in [x for x in m.out_log if x[0] in (PALSEL, FMADDR, 0x00AF, 0x01AF)][-24:]:
        print(f"  OUT #{port:04X}, #{value:02X}")


if __name__ == "__main__":
    main()
