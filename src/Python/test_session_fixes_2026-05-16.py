#!/usr/bin/env python3
"""Регрессионные тесты для правок сессии 2026-05-16 (TS-Conf).

Проверяет 6 фиксов:
  1. APPROACH_SPEED EQU=8 (закрывает moving-target glitch)
  2. TSU_BALL_HALF EQU=12 (legacy +8→+12 для bullet 24×24 center)
  3. head-comp invariance в InsertChainBall (offsets всех знаков -= CELL_SIZE)
  4. SetupMiniFrogKzSprites — позиции из LevelMiniCfg + scale 5/8
  5. LoadCurStagePreviewPalette — SPAL=0 палитра под уровень
  6. LogEvent + GameLog ring buffer (256 entries × 8 байт)

Запускается через Z80 harness (zuma_ts_emulator.py).
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


# ============================================================================
# Test 1: APPROACH_SPEED EQU = 8
# ============================================================================
def test_approach_speed(sym):
    expected = 8
    actual = sym.get('APPROACH_SPEED')
    ok = actual == expected
    print(f'[1] APPROACH_SPEED EQU: actual={actual}, expected={expected}  {"PASS" if ok else "FAIL"}')
    return ok


# ============================================================================
# Test 2: TSU_BALL_HALF EQU = 12
# ============================================================================
def test_tsu_ball_half(sym):
    expected = 12
    actual = sym.get('TSU_BALL_HALF')
    ok = actual == expected
    print(f'[2] TSU_BALL_HALF EQU: actual={actual}, expected={expected}  {"PASS" if ok else "FAIL"}')
    return ok


# ============================================================================
# Test 3: InsertChainBall head-comp invariance
#   Setup: SlotsLen=20, offsets[0..14] = -10 (negative), TmpInsertIdx=15, HSA=30.
#   После insert: offsets[0..14] должны быть = -30 (= -10 - 20), не -20 (старый bug cap).
# ============================================================================
def test_head_comp_invariance(sym):
    emu = ZumaTSEmulator(HERE)
    emu.set_byte(sym['CurStageIdx'], 0)
    emu.call(sym['SetupCurLevelPaging'])

    SlotsLen = sym['Chain0_SlotsLen']
    Slots = sym['Chain0_Slots']
    SlotOffsets = sym['Chain0_SlotOffsets']
    Shot2 = sym['Chain0_Shot2']
    ExplodingFrame = sym['Chain0_ExplodingFrame']
    ExplodingMarker = sym['Chain0_ExplodingMarker']
    HSA = sym['Chain0_HeadSlotAbs']
    HSub = sym['Chain0_HeadSub']

    # Initial state
    emu.set_byte(SlotsLen, 20)
    for i in range(20):
        emu.set_byte(Slots + i, i % 3)
        emu.set_byte(SlotOffsets + i, (-10) & 0xFF if i < 15 else 0)
        emu.set_byte(Shot2 + i, 0)
        emu.set_byte(ExplodingFrame + i, 0)
        emu.set_byte(ExplodingMarker + i, 0)
    emu.set_byte(HSA, 30)
    emu.set_byte(HSub, 0)

    # Insert at idx=15
    emu.set_byte(sym['TmpInsertIdx'], 15)
    emu.set_byte(sym['TmpInsertColor'], 0)
    emu.call(sym['InsertChainBall'])

    # After: offsets[0..14] должны быть -30 (с моим fix'ом — SUB CELL_SIZE без cap).
    # Старый bug: -20 (cap к -CELL_SIZE).
    expected = -30 & 0xFF
    failures = []
    for i in range(15):
        actual = emu.get_byte(SlotOffsets + i)
        actual_signed = actual if actual < 128 else actual - 256
        if actual != expected:
            failures.append((i, actual_signed))
    ok = not failures
    if ok:
        print(f'[3] head-comp invariance: offsets[0..14] = -30  PASS')
    else:
        print(f'[3] head-comp invariance: FAIL — got {failures[:3]}... (expected -30)')
    return ok


# ============================================================================
# Test 4: SetupMiniFrogKzSprites positions для каждого уровня
# ============================================================================
def test_mini_sprites_positions(sym):
    LVLSEL_MINI_DESC_BASE = sym['LVLSEL_MINI_DESC_BASE']
    TSU_BALL_HALF = sym['TSU_BALL_HALF']    # not used here, but symbolic

    # Expected (game→screen ×5/8 + origin - 16):
    #   frog_X game=184 → (184-36)*5/8 + 96 - 16 = 92+80 = 172
    #   frog_Y game=140 → (140-53)*5/8 + 145 - 16 = 54+129 = 183
    #   L0 kz_X game=115 → (115-36)*5/8 + 96 - 16 = 49+80 = 129
    #   L0 kz_Y game=130 → (130-53)*5/8 + 145 - 16 = 48+129 = 177
    #   L1 kz_X game=64  → (64-36)*5/8 + 96 - 16 = 17+80 = 97
    #   L1 kz_Y game=146 → (146-53)*5/8 + 145 - 16 = 58+129 = 187
    expected = {
        0: {'frog': (172, 183), 'kz': (129, 177)},
        1: {'frog': (172, 183), 'kz': ( 97, 187)},
    }

    all_ok = True
    for level_idx in (0, 1):
        emu = ZumaTSEmulator(HERE)
        emu.set_byte(sym['CurStageIdx'], level_idx)
        # Enable FM_EN for descriptor access (SetupMiniFrogKzSprites uses it internally
        # via OUT (C),A — emulator will toggle correctly).
        emu.call(sym['SetupMiniFrogKzSprites'])

        # Descriptors в SFILE (CRAM-banked). Layout per descriptor (6 bytes):
        #   +0 Y_L
        #   +1 Y_H | SPACT | SPSIZ
        #   +2 X_L
        #   +3 X_H | SPSIZ
        #   +4 TNUM_L
        #   +5 TNUM_H | SPAL
        def read_desc(base):
            sfile_off = base - 0x0200
            y = emu.mem.sfile[sfile_off] | ((emu.mem.sfile[sfile_off + 1] & 0x01) << 8)
            x = emu.mem.sfile[sfile_off + 2] | ((emu.mem.sfile[sfile_off + 3] & 0x01) << 8)
            return x, y

        frog_x, frog_y = read_desc(LVLSEL_MINI_DESC_BASE)
        kz_x, kz_y = read_desc(LVLSEL_MINI_DESC_BASE + 6)

        e_frog = expected[level_idx]['frog']
        e_kz = expected[level_idx]['kz']
        ok_frog = (frog_x, frog_y) == e_frog
        ok_kz = (kz_x, kz_y) == e_kz
        ok = ok_frog and ok_kz
        all_ok &= ok
        print(f'[4] mini-sprites L{level_idx + 1}: frog=({frog_x},{frog_y}) expect {e_frog} {"✓" if ok_frog else "✗"}, '
              f'kz=({kz_x},{kz_y}) expect {e_kz} {"✓" if ok_kz else "✗"}  {"PASS" if ok else "FAIL"}')
    return all_ok


# ============================================================================
# Test 5: LoadCurStagePreviewPalette — выбор палитры под CurStageIdx
# ============================================================================
def test_preview_palette_per_stage(sym):
    pal_l1 = (HERE / "level_01_preview_pal.bin").read_bytes()[:32]
    pal_l2 = (HERE / "level_02_preview_pal.bin").read_bytes()[:32]

    all_ok = True
    for level_idx, expected_pal in [(0, pal_l1), (1, pal_l2)]:
        emu = ZumaTSEmulator(HERE)
        emu.set_byte(sym['CurStageIdx'], level_idx)
        # Clear CRAM #0000..#001F before call
        for i in range(32):
            emu.mem.cram[i] = 0
        emu.call(sym['LoadCurStagePreviewPalette'])

        actual = bytes(emu.mem.cram[:32])
        ok = actual == expected_pal
        all_ok &= ok
        if ok:
            print(f'[5] preview palette L{level_idx + 1}: 32 bytes CRAM #0000..#001F match  PASS')
        else:
            diff = sum(1 for a, b in zip(actual, expected_pal) if a != b)
            print(f'[5] preview palette L{level_idx + 1}: {diff}/32 bytes differ  FAIL')
    return all_ok


# ============================================================================
# Test 6: LogEvent — запись 8-байтового entry с инкрементом GameLogIdx mod 256.
# ============================================================================
def test_log_event(sym):
    emu = ZumaTSEmulator(HERE)
    emu.set_byte(sym['GameLogIdx'], 0)
    emu.set_byte(sym['FrameCounter'], 0x42)

    # Заполнить LogTmp
    emu.set_byte(sym['LogTmpType'], sym['EVT_BBOX_HIT'])
    emu.set_byte(sym['LogTmpCtx'], 99)
    emu.set_word(sym['LogTmpData'], 0x1234)
    emu.set_word(sym['LogTmpData'] + 2, 0x5678)

    emu.call(sym['LogEvent'])

    # Verify entry 0 = [1, 99, 0x42, 0, 0x34, 0x12, 0x78, 0x56]
    base = sym['GameLog']
    expected = [1, 99, 0x42, 0, 0x34, 0x12, 0x78, 0x56]
    actual = [emu.get_byte(base + i) for i in range(8)]
    ok_entry = actual == expected

    idx_after = emu.get_byte(sym['GameLogIdx'])
    ok_idx = idx_after == 1

    # Test wrap: set idx=255, call again, check wraps to 0
    emu.set_byte(sym['GameLogIdx'], 255)
    emu.call(sym['LogEvent'])
    idx_wrap = emu.get_byte(sym['GameLogIdx'])
    ok_wrap = idx_wrap == 0

    ok = ok_entry and ok_idx and ok_wrap
    if ok:
        print(f'[6] LogEvent: entry written, idx incremented, wraps 255→0  PASS')
    else:
        print(f'[6] LogEvent: entry={actual} (exp {expected}), idx={idx_after} (exp 1), '
              f'wrap={idx_wrap} (exp 0)  FAIL')
    return ok


# ============================================================================
def main():
    sym = parse_full_sym(HERE / "zuma_new_spg.sym")
    if not sym:
        print("ERROR: cannot parse zuma_new_spg.sym")
        return 1
    print(f"Loaded {len(sym)} symbols\n")

    tests = [
        ('APPROACH_SPEED=8', test_approach_speed),
        ('TSU_BALL_HALF=12', test_tsu_ball_half),
        ('head-comp invariance', test_head_comp_invariance),
        ('mini-sprite positions', test_mini_sprites_positions),
        ('preview palette per stage', test_preview_palette_per_stage),
        ('LogEvent + GameLog', test_log_event),
    ]
    results = []
    for name, fn in tests:
        try:
            ok = fn(sym)
        except Exception as exc:
            print(f'[!] {name}: EXCEPTION {exc!r}')
            ok = False
        results.append((name, ok))
        print()

    n_pass = sum(1 for _, ok in results if ok)
    n_total = len(results)
    print(f"=== {n_pass}/{n_total} tests passed ===")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
