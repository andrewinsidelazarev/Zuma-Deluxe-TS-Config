#!/usr/bin/env python3
"""Pre-render dispname'ов в 8-bit indexed atlas для level-select экрана.

Цикл 1-2-3 повторяется 4 раза в <StageProgression>, поэтому уникальных
dispnames для первой графики каждого stage всего **4-5** (плюс stage13="SPACE").
Атлас хранит только uniq строки + stage_to_row mapping.

Источник:
  _fonts/cancun10.png + cancun10.txt
  src/levels_meta.json
  c:/z80/zuma/scene_levelsel_canvas_pal.bin   (для подбора golden idx)

Выход:
  c:/z80/zuma/dispname_atlas.bin       — N × ROW_H × ROW_W байт 8-bit indexed.
  c:/z80/zuma/dispname_stage_row.bin   — 13 байт: stage_idx → row_in_atlas.

cancun10 — только UPPERCASE + цифры + символы (66 chars). dispnames конвертим
в UPPER-CASE.
"""
import json
import struct
from pathlib import Path

from PIL import Image
import numpy as np

FONT_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/_fonts/cancun10.png")
FONT_TXT = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/_fonts/cancun10.txt")
META     = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/src/levels_meta.json")
SCENE_PAL_BIN = Path(r"C:/z80/zuma/scene_levelsel_canvas_pal.bin")
OUT_ATLAS_A = Path(r"C:/z80/zuma/dispname_atlas_a.bin")
OUT_ATLAS_B = Path(r"C:/z80/zuma/dispname_atlas_b.bin")
OUT_MAPPING = Path(r"C:/z80/zuma/dispname_stage_row.bin")
PREVIEW    = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_dispname_atlas_preview.png")

ROW_W = 144      # отображаемая ширина строки.
ROW_H = 11       # полная высота cancun10 (uppercase без descenders).
ROW_STRIDE = 512 # выравниваем под canvas line stride — DMA blit с одинаковым stride.
ROWS_PER_PAGE = 2  # 2 rows × 11 lines × 512 = 11264 bytes per page (помещается в 16K)


# ── Parse cancun .txt ───────────────────────────────────────────────────────
def parse_font_txt(path):
    lines = path.read_text().splitlines()
    i = 0
    def take(n):
        nonlocal i
        i += 1
        out = lines[i:i+n]
        i += n
        return out

    assert lines[0].startswith('CharList ')
    n = int(lines[0].split()[1])
    chars = take(n)
    assert lines[i].startswith('WidthList ')
    widths = [int(x) for x in take(n)]
    assert lines[i].startswith('RectList ')
    rects = [tuple(int(x) for x in r.split()) for r in take(n)]
    assert lines[i].startswith('OffsetList ')
    offs = [tuple(int(x) for x in r.split()) for r in take(n)]
    return {ch: {'rect': rects[j], 'width': widths[j], 'offset': offs[j]}
            for j, ch in enumerate(chars)}


def render_text(font_img, font_meta, text, max_w=ROW_W, h=ROW_H):
    out = Image.new('RGBA', (max_w, h), (0, 0, 0, 0))
    x = 0
    for ch in text:
        if ch == ' ':
            x += 4
            continue
        m = font_meta.get(ch)
        if not m:
            continue
        rx, ry, rw, rh = m['rect']
        if rw <= 0:
            x += m['width']
            continue
        glyph = font_img.crop((rx, ry, rx + rw, ry + rh))
        ox, oy = m['offset']
        out.paste(glyph, (x + ox, oy), glyph)
        x += m['width']
        if x >= max_w:
            break
    return out, x   # x = фактическая ширина строки


def find_top3_warm_in_cram(pal_bin):
    """Возвращает топ-3 absolute CRAM idx (128..255) самых warm-yellow цветов,
    отсортированных по убыванию яркости (для dithering: bright → mid → dim)."""
    data = pal_bin.read_bytes()
    scored = []
    for i in range(128):
        b0, b1 = data[i*2], data[i*2+1]
        r5 = (b1 >> 2) & 0x1F
        g_hi = b1 & 0x03
        g_lo = (b0 >> 5) & 0x07
        g5 = (g_hi << 3) | g_lo
        b5 = b0 & 0x1F
        warmth = r5 + g5 - 2*b5
        brightness = r5 + g5 + b5
        scored.append((warmth, brightness, i, (r5 << 3, g5 << 3, b5 << 3)))
    # warmth filter > threshold, sort by brightness desc
    warm = sorted([s for s in scored if s[0] > 15], key=lambda s: -s[1])
    if len(warm) < 3:
        warm = sorted(scored, key=lambda s: -s[1])
    return [(w[2] + 128, w[3]) for w in warm[:3]]


def main():
    font_img  = Image.open(FONT_PNG).convert('RGBA')
    font_meta = parse_font_txt(FONT_TXT)
    meta      = json.loads(META.read_text(encoding='utf-8'))
    top3 = find_top3_warm_in_cram(SCENE_PAL_BIN)
    text_idx_bright, _ = top3[0]
    text_idx_mid,    _ = top3[1]
    text_idx_dim,    _ = top3[2]
    text_rgb = top3[0][1]
    print(f'Text palette (dithering): bright={text_idx_bright} mid={text_idx_mid} dim={text_idx_dim}')

    stage_prog   = meta['stage_progression']
    graphics_map = meta['graphics']
    settings_map = meta['settings']

    # Для каждого stage — dispname первой графики.
    stage_dispnames = []
    for n in range(1, 14):
        sp = stage_prog[f'stage{n}']
        first_gid = None
        for gid, did in zip(sp['graphics'], sp['difficulty']):
            if gid in graphics_map and did in settings_map:
                first_gid = gid
                break
        dn = (graphics_map.get(first_gid, {}).get('dispname')
              or first_gid or '?')
        stage_dispnames.append(dn.upper())                           # CANCUN10 = uppercase only

    # Уникальные строки → их индекс в atlas
    uniq = []
    seen = {}
    stage_to_row = []
    for dn in stage_dispnames:
        if dn not in seen:
            seen[dn] = len(uniq)
            uniq.append(dn)
        stage_to_row.append(seen[dn])

    print(f'\nUnique dispnames: {len(uniq)}')
    for i, dn in enumerate(uniq):
        print(f'  row {i}: "{dn}"')
    print(f'\nstage_to_row: {stage_to_row}')

    # Render каждую uniq строку → 8-bit indexed row, полная высота cancun10 (11 lines).
    # 4 rows × 11 × 512 = 22528 > 16K, поэтому делим на 2 page'а × 2 rows.
    row_bins = []
    actual_widths = []
    for dn in uniq:
        rgba, w = render_text(font_img, font_meta, dn, max_w=ROW_W, h=ROW_H)
        arr = np.array(rgba, dtype=np.uint8)
        alpha = arr[:, :, 3]
        row = np.zeros_like(alpha, dtype=np.uint8)
        row[alpha > 200] = text_idx_bright
        row[(alpha > 100) & (alpha <= 200)] = text_idx_mid
        row[(alpha > 32) & (alpha <= 100)] = text_idx_dim
        padded = np.zeros((ROW_H, ROW_STRIDE), dtype=np.uint8)
        padded[:, :ROW_W] = row
        row_bins.append(padded.tobytes())
        actual_widths.append(w)
        print(f'  "{dn}" rendered width={w} px')

    # Pack rows в 2 page'а по ROWS_PER_PAGE rows each
    atlas_a = b''.join(row_bins[0:ROWS_PER_PAGE])
    atlas_b = b''.join(row_bins[ROWS_PER_PAGE:])

    OUT_ATLAS_A.write_bytes(atlas_a)
    OUT_ATLAS_B.write_bytes(atlas_b)
    print(f'\nAtlas A: {len(atlas_a)} bytes, Atlas B: {len(atlas_b)} bytes ({len(uniq)} rows × {ROW_H} lines × {ROW_STRIDE} stride)')

    OUT_MAPPING.write_bytes(bytes(stage_to_row))
    print(f'Mapping size: {len(stage_to_row)} bytes')

    # Preview
    rgb_bright = top3[0][1]
    rgb_mid    = top3[1][1]
    rgb_dim    = top3[2][1]
    full_atlas = atlas_a + atlas_b
    preview_arr = np.zeros((len(uniq)*ROW_H, ROW_W, 4), dtype=np.uint8)
    for n in range(len(uniq)):
        row_bytes = full_atlas[n*ROW_H*ROW_STRIDE : (n+1)*ROW_H*ROW_STRIDE]
        row_arr = np.frombuffer(row_bytes, dtype=np.uint8).reshape(ROW_H, ROW_STRIDE)[:, :ROW_W]
        mask_b = row_arr == text_idx_bright
        mask_m = row_arr == text_idx_mid
        mask_d = row_arr == text_idx_dim
        preview_arr[n*ROW_H:(n+1)*ROW_H][mask_b] = (*rgb_bright, 255)
        preview_arr[n*ROW_H:(n+1)*ROW_H][mask_m] = (*rgb_mid, 255)
        preview_arr[n*ROW_H:(n+1)*ROW_H][mask_d] = (*rgb_dim, 255)
    Image.fromarray(preview_arr, 'RGBA').save(PREVIEW)
    print(f'Preview: {PREVIEW}')


if __name__ == '__main__':
    main()
