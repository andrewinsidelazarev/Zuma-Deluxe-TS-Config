#!/usr/bin/env python3
"""Generate level preview for level-select scene.

Preview = inner area of level-select preview frame: 192×128 (3:2). Через 2 TSU
pages (#0C + #0D), 6×4 спрайтов 32×32. track_overflow перенесён в page #60
чтобы освободить #0C под sprite data.

Aspect frame 3:2; level source 360:288 = 5:4. Чтобы НЕ сжимать по вертикали,
вертикально crop level (Y центр), потом resize в 192×128.

Source: оригинал HD level_src_NN.png (640×480), aspect-crop как у уровня
(600×480 → 360×288), затем vertical-crop 360×240 (Y=24..264), resize 192×128.

Pipeline:
  1) Crop 640×480 → 600×480 → LANCZOS resize → 360×288.
  2) Vertical crop 360×288 → 360×240 (центр).
  3) Resize 360×240 → 192×128.
  4) Quantize 15 цветов (index 0 = transparent в TSU) → idx 1..15.
  4) Pack как TSU 4bpp tiles 8×8:
     - Sprites 32×32 (4×4 tiles each) разложены в 2 TSU pages по 5×2 sprite grid:
        page #0C (TSU index 6): row 0 (cy=0..3) + row 1 (cy=4..7) = sprite rows 0,1
        page #0D (TSU index 7): row 0 + row 1                       = sprite rows 2,3
     - Внутри page tile layout: cy * 64 + cx, каждая tile 8×8 = 32 bytes 4bpp.
  5) CRAM palette: 16 × 2 байта, индексы #10..#1F (SPAL=1).

Output (в c:/z80/zuma/):
  level_01_preview_p0.bin   (16K, TSU page #0C → spgbld page #52)
  level_01_preview_p1.bin   (16K, TSU page #0D → spgbld page #53)
  level_01_preview_pal.bin  (32 байта, palette CRAM #10..#1F)
"""
import struct
from pathlib import Path
from PIL import Image
import numpy as np

DST_DIR    = Path(r"C:/z80/zuma")
SRC_PNG    = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels/level_src_01.png")
FONT_PNG   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/_fonts/cancunfloat14.png")
FONT_TXT   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/_fonts/cancunfloat14.txt")

# Dispname (TSU sprites) — 11 sprites 16×24 = 176×24, centered в frame inner X=96..273
DISPNAME_TEXT     = 'SPIRAL OF DOOM'
DISPNAME_SPRITE_W = 16
DISPNAME_SPRITE_H = 24
DISPNAME_COLS     = 11
DISPNAME_W        = DISPNAME_COLS * DISPNAME_SPRITE_W       # 176
DISPNAME_H        = DISPNAME_SPRITE_H                       # 24
# Tile placement в page #0C cells: cy=4..6 (24px = 3 carpet rows), cx=24..45 (22 cells = 11 sprites × 2)
DISPNAME_PAGE_CY  = 4
DISPNAME_PAGE_CX  = 24

# Same aspect-crop as у уровня: 640×480 → 600×480 → 360×288 → 160×128.
SRC_W, SRC_H = 640, 480
SCREEN_W, SCREEN_H = 360, 288
CROP_W = SRC_H * SCREEN_W // SCREEN_H        # 600 (5:4)
CROP_X = (SRC_W - CROP_W) // 2                # 20

PREVIEW_W, PREVIEW_H = 192, 120    # TSU sprite area
VISIBLE_W, VISIBLE_H = 178, 112    # только inner cream area; wood frame в scene canvas остаётся видимой ВОКРУГ preview
PAD_X = (PREVIEW_W - VISIBLE_W) // 2     # 7
PAD_Y = 5                                  # asymmetric: top 5, bottom 3 — visible Y=145..256 матчит cream area
SPRITE_W, SPRITE_H = 64, 8         # 64-wide thin sprites чтобы вписать в SFILE budget
COLS = PREVIEW_W // SPRITE_W       # 3
ROWS = PREVIEW_H // SPRITE_H       # 15 (8 в page #0C + 7 в page #0D)
TILE = 8

# Zoom in source чтобы убрать decorative corners level_src_01 — preview показывает
# только playable spiral, без своего frame border. Frame border берётся ИЗ scene
# canvas (визуально "поверх" preview).
ZOOM = 1.25
SRC_CROP_W = round(SCREEN_W / ZOOM)
SRC_CROP_H = round(SCREEN_W * VISIBLE_H / VISIBLE_W / ZOOM)
SRC_CROP_X0 = (SCREEN_W - SRC_CROP_W) // 2
SRC_CROP_Y0 = (SCREEN_H - SRC_CROP_H) // 2


def rgb_to_cram_bytes(rgb_palette):
    """(N, 3) uint8 → bytes (N × 2) в CRAM 5-5-5 format."""
    out = bytearray(len(rgb_palette) * 2)
    for i, (r, g, b) in enumerate(rgb_palette):
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        out[i*2]   = b0
        out[i*2+1] = b1
    return bytes(out)


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


def render_dispname_rgba():
    """RGBA DISPNAME_W × DISPNAME_H, текст centered horizontally."""
    font_img = Image.open(FONT_PNG).convert('RGBA')
    font_meta = parse_font_txt(FONT_TXT)
    width = 0
    for ch in DISPNAME_TEXT.upper():
        if ch == ' ': width += 4; continue
        m = font_meta.get(ch)
        if not m or m['rect'][2] <= 0:
            width += m.get('width', 0) if m else 0; continue
        width += m['width']
    out = Image.new('RGBA', (DISPNAME_W, DISPNAME_H), (0, 0, 0, 0))
    x = max(0, (DISPNAME_W - width) // 2)
    for ch in DISPNAME_TEXT.upper():
        if ch == ' ': x += 4; continue
        m = font_meta.get(ch)
        if not m: continue
        rx, ry, rw, rh = m['rect']
        if rw <= 0: x += m['width']; continue
        glyph = font_img.crop((rx, ry, rx + rw, ry + rh))
        ox, oy = m['offset']
        out.paste(glyph, (x + ox, oy + (DISPNAME_H - 14) // 2), glyph)
        x += m['width']
        if x >= DISPNAME_W: break
    return out


def pack_dispname_tiles(page, rgba_img):
    """Pack RGBA dispname в page bytes at (DISPNAME_PAGE_CY, DISPNAME_PAGE_CX).
    Alpha 0..255 → idx 0..15 gradient."""
    arr = np.array(rgba_img)
    H, W, _ = arr.shape
    alpha = arr[..., 3]
    idx_2d = np.where(alpha == 0, 0, (alpha.astype(np.uint16) * 15 // 255).clip(1, 15)).astype(np.uint8)
    base_cy = DISPNAME_PAGE_CY
    base_cx = DISPNAME_PAGE_CX
    for py in range(H):
        page_y = py
        local_cy = base_cy + page_y // 8
        ycnt = page_y % 8
        for px in range(W):
            page_x = px
            local_cx = base_cx + page_x // 8
            bsel = (page_x % 8) // 2
            nibble = page_x % 2
            addr = local_cy * 2048 + ycnt * 256 + local_cx * 4 + bsel
            idx = idx_2d[py, px] & 0x0F
            if nibble == 0:
                page[addr] = (page[addr] & 0x0F) | (idx << 4)
            else:
                page[addr] = (page[addr] & 0xF0) | idx


def load_level_rgb():
    """640×480 HD level bg → crop 600×480 (5:4) → resize 360×288 LANCZOS RGB."""
    bg = Image.open(SRC_PNG).convert('RGB')
    if bg.size != (SRC_W, SRC_H):
        raise SystemExit(f'expected {SRC_W}×{SRC_H}, got {bg.size}')
    bg_cropped = bg.crop((CROP_X, 0, CROP_X + CROP_W, SRC_H))   # 600×480
    return bg_cropped.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)


def pack_tsu_4bpp(image_indices, sprite_rows_in_page):
    """TS-Conf TSU carpet-row layout (см. make_kz_skull_atlas.py).

    Page 16K = 8 carpet rows × 2048 bytes. Carpet row = 8 lines × 256 bytes.
    Line = 64 cells × 4 bytes; cell = 4 bytes/8 px (2 px per byte, even px = high nibble,
    odd px = low nibble).

    addr = page_cy*2048 + ycnt*256 + page_cx*4 + bsel
        page_cy = global page Y / 8     (carpet row 0..7)
        ycnt    = global page Y % 8     (line within carpet row)
        page_cx = global page X / 8     (cell column 0..63)
        bsel    = (page X % 8) // 2     (byte within cell 0..3)
        nibble  = page X % 2            (0 → high, 1 → low)
    """
    page = bytearray(16384)
    for sr in range(*sprite_rows_in_page):
        rel_sr = sr - sprite_rows_in_page[0]               # 0..3 (4 sprite rows per page for sprite_h=16)
        page_y_off = rel_sr * SPRITE_H                     # 0, 16, 32, 48
        for sc in range(COLS):
            page_x_off = sc * SPRITE_W                     # 0, 32, 64, 96, 128
            src_y0 = sr * SPRITE_H
            src_x0 = sc * SPRITE_W
            for py in range(SPRITE_H):
                py_page = page_y_off + py
                p_cy   = py_page // 8
                ycnt   = py_page % 8
                row = image_indices[src_y0 + py]
                for px in range(SPRITE_W):
                    idx = row[src_x0 + px] & 0x0F
                    px_page = page_x_off + px
                    p_cx   = px_page // 8
                    bsel   = (px_page % 8) // 2
                    nibble = px_page % 2
                    addr = p_cy * 2048 + ycnt * 256 + p_cx * 4 + bsel
                    if nibble == 0:
                        page[addr] = (page[addr] & 0x0F) | (idx << 4)
                    else:
                        page[addr] = (page[addr] & 0xF0) | idx
    return bytes(page)


def main():
    img = load_level_rgb()                                    # PIL Image 360×288 RGB
    # Source → visible content (VISIBLE_W×VISIBLE_H).
    cropped = img.crop((SRC_CROP_X0, SRC_CROP_Y0, SRC_CROP_X0 + SRC_CROP_W, SRC_CROP_Y0 + SRC_CROP_H))
    visible = cropped.resize((VISIBLE_W, VISIBLE_H), Image.LANCZOS)
    # Paste visible content на 192×112 canvas; padding фоном-марker для последующего idx 0.
    preview = Image.new('RGB', (PREVIEW_W, PREVIEW_H), (0, 0, 0))
    preview.paste(visible, (PAD_X, PAD_Y))
    # 15 цветов вместо 16 — index 0 в TSU 4bpp всегда transparent (hardware).
    # Используем индексы 1..15, palette[0] = unused dummy.
    # Quantize ТОЛЬКО visible area (без padding) чтобы palette не тратилась на чёрный фон.
    palette_img = visible.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    sub = preview.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)
    idx_arr = np.array(sub, dtype=np.uint8) + 1               # сдвиг 0..14 → 1..15
    # Forcing padding zones к idx 0 (transparent в TSU).
    idx_arr[:PAD_Y, :] = 0
    idx_arr[PAD_Y + VISIBLE_H:, :] = 0
    idx_arr[:, :PAD_X] = 0
    idx_arr[:, PAD_X + VISIBLE_W:] = 0

    # (Transparent dispname window удалён — dispname через TSU sprite поверх preview)
    pal_flat = sub.getpalette()[:15*3]
    pal_rgb_15 = np.array(pal_flat, dtype=np.uint8).reshape(15, 3)
    pal_rgb = np.vstack([pal_rgb_15[:1], pal_rgb_15])         # (16, 3); palette[0] = dummy

    # Save preview PNG для визуального reference
    preview_arr = pal_rgb[idx_arr]
    out_png = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_level_01_preview.png")
    Image.fromarray(preview_arr.astype(np.uint8), 'RGB').save(out_png)
    print(f"Preview RGB: {out_png}")

    # CRAM palette → bytes (16 × 2)
    (DST_DIR / 'level_01_preview_pal.bin').write_bytes(rgb_to_cram_bytes(pal_rgb))
    print('Saved level_01_preview_pal.bin (32 bytes)')

    # Pack в 2 TSU pages: sprite rows 0..7 (8 rows) → page #0C; 8..14 → page #0D
    page0 = bytearray(pack_tsu_4bpp(idx_arr, (0, 8)))
    page1 = pack_tsu_4bpp(idx_arr, (8, ROWS))

    # Dispname palette: idx 0 transparent, idx 1..15 gradient warm yellow
    dispname_pal_rgb = np.zeros((16, 3), dtype=np.uint8)
    for i in range(1, 16):
        t = i / 15.0
        r = int(80 + (248 - 80) * t)
        g = int(40 + (224 - 40) * t)
        b = int(8  + (64  - 8)  * t)
        dispname_pal_rgb[i] = (r, g, b)
    (DST_DIR / 'level_01_dispname_pal.bin').write_bytes(rgb_to_cram_bytes(dispname_pal_rgb))

    # Render dispname → pack в page0 на cy=4..6 cx=24..45
    dispname_rgba = render_dispname_rgba()
    pack_dispname_tiles(page0, dispname_rgba)
    dispname_rgba.save(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_level_01_dispname.png")

    (DST_DIR / 'level_01_preview_p0.bin').write_bytes(bytes(page0))
    (DST_DIR / 'level_01_preview_p1.bin').write_bytes(page1)
    print('Saved level_01_preview_p0.bin / p1.bin (16384 bytes each)')


if __name__ == '__main__':
    main()
