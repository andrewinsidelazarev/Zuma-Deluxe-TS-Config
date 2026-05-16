#!/usr/bin/env python3
"""Генерация Z80-таблиц из levels_meta.json для экрана выбора уровней
и загрузки уровня в SceneGame.

Вход:   Desktop/Zuma Deluxe/src/levels_meta.json
Выход:  c:/z80/zuma/levels/  (новая папка для build артефактов):
        - graphics_table.bin   — 22 × 8 байт: per-graphics метадата
        - settings_table.bin   — N × 8 байт: per-settings (speed, start, …)
        - stage_pairs.bin      — пары (graphics_idx, settings_idx) × M
        - stage_table.bin      — 13 × 4 байта: (offset_lo,hi, count, _pad)
        - dispnames.bin        — ASCII строки, NUL-terminated
        - dispname_offsets.bin — 22 × 2 байта: offset в dispnames
        - levels_const.asm     — sjasmplus include с EQU константами

Интерпретация StageProgression (вариант a из обсуждения):
  каждая пара (stageN[i], diffiN[i]) = один уровень в stage N.
  При несоответствии длин (stage1: 18 graphics, 5 difficulty) берётся zip-min.
"""
import json
import struct
from pathlib import Path

SRC = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/src/levels_meta.json")
OUT = Path(r"C:/z80/zuma/levels")
OUT.mkdir(parents=True, exist_ok=True)

GAP = 0xFF  # маркер "нет значения"


# ────────────────────────────────────────────────────────────────────────────
def quant_speed(speed):
    """speed (0.5..1.5) → 0..150 (×100, 1 байт)."""
    if speed is None: return 50
    return min(255, max(0, int(round(speed * 100))))


def quant_score(score):
    """score (1000..10000) → score/100 (0..100, 1 байт)."""
    if score is None: return 0
    return min(255, score // 100)


def quant_slow(slow):
    """slowfactor (1..5) × 16 → 16..80 (1 байт)."""
    if slow is None: return 0
    return min(255, int(round(slow * 16)))


def quant_partime(partime):
    """partime (sec, 0..240) — прямо в байт."""
    if partime is None: return 0
    return min(255, partime)


# ────────────────────────────────────────────────────────────────────────────
def main():
    meta = json.loads(SRC.read_text(encoding='utf-8'))
    graphics  = meta['graphics']
    settings  = meta['settings']
    stage_progression = meta['stage_progression']

    # ─── индексы ─────────────────────────────────────────────────────────
    g_ids = list(graphics.keys())                                 # 22
    s_ids = list(settings.keys())                                 # 130
    g_idx = {gid: i for i, gid in enumerate(g_ids)}
    s_idx = {sid: i for i, sid in enumerate(s_ids)}

    # ─── dispnames + offsets ────────────────────────────────────────────
    dispnames_buf  = bytearray()
    dispname_offs  = []
    for gid in g_ids:
        dn = graphics[gid].get('dispname') or gid
        dispname_offs.append(len(dispnames_buf))
        dispnames_buf += dn.encode('ascii', errors='replace') + b'\x00'

    (OUT / 'dispnames.bin').write_bytes(bytes(dispnames_buf))
    offs_buf = b''.join(struct.pack('<H', o) for o in dispname_offs)
    (OUT / 'dispname_offsets.bin').write_bytes(offs_buf)

    # ─── graphics_table: 22 × 8 байт ────────────────────────────────────
    #   byte  0  flags          (bit0 space, bit1 drawcurve,
    #                            bit2 has_image_top, bit3 has_curve_b)
    #   byte  1  treasure_count (0..4)
    #   byte  2  frog_x_lo
    #   byte  3  frog_x_hi
    #   byte  4  frog_y_lo
    #   byte  5  frog_y_hi
    #   byte  6  dispname_offs_lo
    #   byte  7  dispname_offs_hi
    g_table = bytearray()
    for i, gid in enumerate(g_ids):
        g = graphics[gid]
        flags = 0
        if g.get('space'):              flags |= 0x01
        if g.get('drawcurve'):          flags |= 0x02
        if g.get('image_top'):          flags |= 0x04
        if g.get('curve2'):             flags |= 0x08
        fx = g.get('gx') or 0
        fy = g.get('gy') or 0
        dn_off = dispname_offs[i]
        entry = struct.pack(
            '<BBhhH',
            flags,
            len(g.get('treasure', [])),
            int(fx) & 0xFFFF if fx >= 0 else (int(fx) & 0xFFFF),
            int(fy) & 0xFFFF if fy >= 0 else (int(fy) & 0xFFFF),
            dn_off,
        )
        assert len(entry) == 8, f'graphics entry size {len(entry)}'
        g_table += entry
    (OUT / 'graphics_table.bin').write_bytes(bytes(g_table))

    # ─── settings_table: N × 8 байт ─────────────────────────────────────
    #   byte  0  speed_x100      (0..150)
    #   byte  1  ball_start_count
    #   byte  2  score_x100      (score / 100)
    #   byte  3  colors          (4..8, default 6)
    #   byte  4  partime         (sec)
    #   byte  5  slowfactor_x16  (16..80)
    #   byte  6  single_limit    (0/7/8/9)
    #   byte  7  flags           (bit0 has_repeat, bit1 has_zumaslow)
    s_table = bytearray()
    for sid in s_ids:
        s = settings[sid]
        flags = 0
        if s.get('repeat')    is not None: flags |= 0x01
        if s.get('zumaslow')  is not None: flags |= 0x02
        if s.get('zumaback')  is not None: flags |= 0x04
        if s.get('mergespeed') is not None: flags |= 0x08
        if s.get('firespeed') is not None: flags |= 0x10
        entry = struct.pack(
            '<BBBBBBBB',
            quant_speed(s.get('speed')),
            min(255, s.get('start') or 0),
            quant_score(s.get('score')),
            s.get('colors') or 6,
            quant_partime(s.get('partime')),
            quant_slow(s.get('slowfactor')),
            s.get('single') or 0,
            flags,
        )
        s_table += entry
    (OUT / 'settings_table.bin').write_bytes(bytes(s_table))

    # ─── stage_pairs + stage_table ──────────────────────────────────────
    # zip-min между graphics и difficulty в каждом stageN/diffiN.
    pairs_buf = bytearray()
    stage_offsets = []                                            # 13 entries
    for n in range(1, 14):
        sp = stage_progression[f'stage{n}']
        gxs = sp['graphics']
        dfs = sp['difficulty']
        offset = len(pairs_buf)
        cnt    = 0
        for gid, did in zip(gxs, dfs):
            if gid not in g_idx or did not in s_idx:
                continue
            pairs_buf += bytes([g_idx[gid], s_idx[did]])
            cnt += 1
        stage_offsets.append((offset, cnt))

    (OUT / 'stage_pairs.bin').write_bytes(bytes(pairs_buf))

    stage_tbl = bytearray()
    for off, cnt in stage_offsets:
        stage_tbl += struct.pack('<HBB', off, cnt, 0)             # +1 pad для align 4
    (OUT / 'stage_table.bin').write_bytes(bytes(stage_tbl))

    # ─── levels_const.asm ───────────────────────────────────────────────
    asm = []
    asm.append('; Авто-сгенерировано gen_levels_tables.py — НЕ ПРАВИТЬ ВРУЧНУЮ')
    asm.append(f'; Source: {SRC}')
    asm.append('')
    asm.append('LVL_GRAPHICS_COUNT EQU 22')
    asm.append(f'LVL_SETTINGS_COUNT EQU {len(s_ids)}')
    asm.append('LVL_STAGES_COUNT   EQU 13')
    asm.append(f'LVL_PAIRS_COUNT    EQU {len(pairs_buf)//2}')
    asm.append('')
    asm.append('LVL_GRAPHICS_ENTRY_BYTES EQU 8')
    asm.append('LVL_SETTINGS_ENTRY_BYTES EQU 8')
    asm.append('LVL_STAGE_ENTRY_BYTES    EQU 4')
    asm.append('LVL_PAIR_ENTRY_BYTES     EQU 2')
    asm.append('')
    asm.append('; ── Graphics IDs ─────────────────────────────────────────')
    for i, gid in enumerate(g_ids):
        asm.append(f'GID_{gid.upper():<14s} EQU {i:3d}    ; "{graphics[gid].get("dispname") or ""}"')
    asm.append('')
    asm.append('; ── Settings IDs (selected) ──────────────────────────────')
    for i, sid in enumerate(s_ids):
        asm.append(f'SID_{sid.upper():<8s} EQU {i:3d}')
    asm.append('')
    asm.append('; ── Stage offsets (debug, для проверки совпадения с .bin)')
    for n, (off, cnt) in enumerate(stage_offsets, 1):
        asm.append(f'; stage{n:2d}: offset={off:3d} count={cnt}')

    asm_text = '\n'.join(asm) + '\n'
    (OUT / 'levels_const.asm').write_text(asm_text, encoding='utf-8')

    # ─── summary ────────────────────────────────────────────────────────
    print(f'Output: {OUT}')
    for f in sorted(OUT.iterdir()):
        print(f'  {f.name:30s} {f.stat().st_size:6d} B')

    total_levels = sum(c for _, c in stage_offsets)
    print(f'\nTotal levels in StageProgression: {total_levels}')
    for n, (off, cnt) in enumerate(stage_offsets, 1):
        print(f'  stage{n:2d}: {cnt} levels (offset {off})')


if __name__ == '__main__':
    main()
