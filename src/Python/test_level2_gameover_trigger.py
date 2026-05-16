#!/usr/bin/env python3
"""Regression test для level 2 Game Over trigger.

Проверяет что CheckHeadAtKillzone возвращает A=1 когда HSA достиг cap
(CurTrackNumSlots-1) и HSub=CELL_SIZE-1 — т.е. голова физически на killzone.

Изначально (до 2026-05-16 fix) на level 2 LVL02_TRACK_SLOTS использовал
floor-деление 1656/20=82. HSA cap = 81, max head t = 81*20+19 = 1639, KzCenter
в TrackData[1655]. Manhattan ≥ 16 → CheckHeadAtKillzone (CP 16: JR NC, skip)
никогда не triggered → Game Over не запускался.

Fix: LVL02_TRACK_SLOTS = ceil(1656/20) = 83. HSA cap = 82, max t = 1659,
clamp к points-1 = 1655 → head точно на KzCenter → Manhattan=0 → trigger.

Test прогоняет оба уровня в Z80 harness и проверяет результат.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from zuma_ts_emulator import ZumaTSEmulator, parse_num


def parse_full_sym(path):
    """Parse sjasmplus .sym output (Name: EQU 0xVALUE)."""
    syms = {}
    rx = re.compile(r"^\s*([\w.]+):\s+EQU\s+([#$0-9A-Fa-fx]+)\s*$")
    if not path.exists():
        return syms
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = rx.match(line)
        if m:
            syms[m.group(1)] = parse_num(m.group(2))
    return syms


def setup_level(emu, sym, level_idx):
    """Configure emulator state for given CurStageIdx."""
    emu.set_byte(sym['CurStageIdx'], level_idx)
    emu.call(sym['SetupCurLevelPaging'])

    # SetupCurLevelPaging оставляет CurTrackPage = #03 (stack-стабильность).
    # В реальной игре GotoGame копирует source page → #03 через CopyAtlasToPage.
    # В harness просто маппим PAGE3 на актуальную source page из spgbld.ini:
    #   level 1 → page #03 (= в spgbld есть Block = #C000, #03, level_01.bin)
    #   level 2 → page #66 (= Block = #C000, #66, level_02.bin)
    if level_idx == 0:
        emu.mem.pages[3] = 0x03
    else:
        emu.mem.pages[3] = 0x66

    num_pts = emu.get_word(sym['CurTrackNumPoints'])
    num_slots = emu.get_byte(sym['CurTrackNumSlots'])
    return num_pts, num_slots


def load_killzone(emu, sym, num_pts):
    """Replicate InitGame L865-873: KzCenter = TrackData[num_pts-1]."""
    kz_t = num_pts - 1
    base = sym['TrackData'] + kz_t * 4
    kz_x = emu.get_word(base)
    kz_y = emu.get_word(base + 2)
    emu.set_word(sym['KzCenterX'], kz_x)
    emu.set_word(sym['KzCenterY'], kz_y)
    return kz_x, kz_y


def set_chain_head_at_cap(emu, sym, num_slots):
    """Setup chain: HSA=cap, HSub=CELL_SIZE-1, SlotsLen=1, Slots[0]=0."""
    hsa_max = num_slots - 1
    emu.set_byte(sym['Chain0_HeadSlotAbs'], hsa_max)
    emu.set_byte(sym['Chain0_HeadSub'], 19)    # CELL_SIZE-1
    emu.set_byte(sym['Chain0_SlotsLen'], 1)
    emu.set_byte(sym['Chain0_Slots'], 0)
    emu.set_byte(sym['Chain0_SlotOffsets'], 0)
    emu.set_byte(sym['Chain0_ExplodingFrame'], 0)
    return hsa_max


def compute_head_pos(emu, sym, hsa, hsub, offset=0):
    """Replicate ComputeSlotXY for slot 0 → TrackData[t]."""
    t = hsa * 20 + hsub + offset
    num_pts = emu.get_word(sym['CurTrackNumPoints'])
    if t >= num_pts:
        t = num_pts - 1
    if t < 0:
        t = 0
    base = sym['TrackData'] + t * 4
    return t, emu.get_word(base), emu.get_word(base + 2)


def manhattan(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def run_level(level_idx, expected_slots, sym):
    label = f"Level {level_idx + 1} (CurStageIdx={level_idx})"
    emu = ZumaTSEmulator(HERE)
    num_pts, num_slots = setup_level(emu, sym, level_idx)

    print(f"--- {label} ---")
    print(f"  CurTrackNumPoints = {num_pts}")
    print(f"  CurTrackNumSlots  = {num_slots}  (expected {expected_slots})")

    if num_slots != expected_slots:
        print(f"  FAIL slot count mismatch")
        return False

    kz_x, kz_y = load_killzone(emu, sym, num_pts)
    print(f"  KzCenter = ({kz_x}, {kz_y})  from TrackData[{num_pts - 1}]")

    hsa_max = set_chain_head_at_cap(emu, sym, num_slots)
    t, hx, hy = compute_head_pos(emu, sym, hsa_max, 19)
    dist = manhattan((hx, hy), (kz_x, kz_y))
    print(f"  Head: HSA={hsa_max}, HSub=19 → t={t} → ({hx}, {hy})  Manhattan(KZ)={dist}")

    emu.call(sym['CheckHeadAtKillzone'])
    a = emu.reg.A
    ok = a == 1
    print(f"  CheckHeadAtKillzone → A={a}  {'PASS' if ok else 'FAIL (expected 1)'}")

    # Дополнительно: проверка нижней границы — HSA=0 не должно триггерить.
    emu.set_byte(sym['Chain0_HeadSlotAbs'], 0)
    emu.set_byte(sym['Chain0_HeadSub'], 0)
    emu.call(sym['CheckHeadAtKillzone'])
    a0 = emu.reg.A
    ok0 = a0 == 0
    print(f"  Negative case: HSA=0 → A={a0}  {'PASS' if ok0 else 'FAIL (expected 0)'}")
    return ok and ok0


def main():
    sym_path = HERE / "zuma_new_spg.sym"
    sym = parse_full_sym(sym_path)
    if not sym:
        print(f"ERROR: cannot parse {sym_path}")
        return 1

    print(f"Loaded {len(sym)} symbols from {sym_path.name}")
    print()

    required = [
        'CurStageIdx', 'CurTrackNumPoints', 'CurTrackNumSlots',
        'SetupCurLevelPaging', 'CheckHeadAtKillzone',
        'Chain0_HeadSlotAbs', 'Chain0_HeadSub', 'Chain0_SlotsLen',
        'Chain0_Slots', 'Chain0_SlotOffsets', 'Chain0_ExplodingFrame',
        'KzCenterX', 'KzCenterY', 'TrackData',
    ]
    missing = [s for s in required if s not in sym]
    if missing:
        print(f"ERROR: symbols not found: {missing}")
        return 1

    # Ожидаемые slot counts после ceil-fix 2026-05-16:
    # Level 1: TRACK_NUM_POINTS=1673, ceil(1673/20)=84
    # Level 2: LVL02_TRACK_POINTS=1656, ceil(1656/20)=83
    l1_ok = run_level(0, expected_slots=84, sym=sym)
    print()
    l2_ok = run_level(1, expected_slots=83, sym=sym)
    print()

    overall = l1_ok and l2_ok
    print(f"=== {'ALL PASS' if overall else 'SOME FAILED'} ===")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
