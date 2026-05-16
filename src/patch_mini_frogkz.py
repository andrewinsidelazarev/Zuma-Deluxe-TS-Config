#!/usr/bin/env python3
"""Patch mini-frog + mini-killzone tiles into level_select_tsu_p1.bin.

Это файл который spgbld load'ит в page #53, который копируется на TSU page #0D
во время LevelSelect_Init. Mini-tiles размещаются в свободные cells cy=6..7 cx=24..27
после Codex's TSU buttons (которые занимают cy=0..5 в #0D).

Сохраняет также level_01_preview_mini_pal.bin (32 bytes SPAL=4 palette).
НЕ создаёт PNG output.
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

# Level number from CLI arg (default 1).
LEVEL_N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LVL_TAG = f"{LEVEL_N:02d}"

# Per-level preview file. Level 1 used legacy `level_select_tsu_p1.bin`; новые levels
# patch'ят `level_NN_preview_p1.bin` (output make_level_preview.py NN).
if LEVEL_N == 1:
    TSU_P1 = Path(r"C:/z80/zuma/level_select_tsu_p1.bin")
else:
    TSU_P1 = Path(rf"C:/z80/zuma/level_{LVL_TAG}_preview_p1.bin")
PAL_OUT = Path(rf"C:/z80/zuma/level_{LVL_TAG}_preview_mini_pal.bin")

FROG_PNG          = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/frog-64-64.png")
SPRITESHEET_PNG   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/spritesheet.png")
KZ_SUN_CROP       = (370, 0, 448, 78)            # sun rays (row 0)
KZ_SKULL_CROP     = (370, 78, 448, 156)          # skull frame 0 (row 1) — поверх sun


def rgb_to_cram_bytes(rgb_palette):
    out = bytearray(len(rgb_palette) * 2)
    for i, (r, g, b) in enumerate(rgb_palette):
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        out[i*2]   = b0
        out[i*2+1] = b1
    return bytes(out)


SPRITE_PX = 32   # game frog/kz 64 px × preview-to-screen ratio (192/360 = 0.533) ≈ 32

def build_indices_and_palette():
    """Generate SPRITE_PX×SPRITE_PX frog + same kz as proportionally-downscaled
    sprites из source 64×64. Joint quantize в 15 colors + idx 0 transparent.
    Returns (idx_arr H × 2W, pal_rgb 16×3).
    """
    frog = Image.open(FROG_PNG).convert('RGBA').resize((SPRITE_PX, SPRITE_PX), Image.LANCZOS)
    # Killzone = sun base + skull overlay (как в игре).
    sheet = Image.open(SPRITESHEET_PNG).convert('RGBA')
    sun = sheet.crop(KZ_SUN_CROP).copy()              # 78×78 sun rays
    skull = sheet.crop(KZ_SKULL_CROP)                  # 78×78 skull alpha overlay
    sun.alpha_composite(skull)                         # composite skull on sun
    kz = sun.resize((SPRITE_PX, SPRITE_PX), Image.LANCZOS)
    combo = Image.new('RGBA', (SPRITE_PX*2, SPRITE_PX), (0, 0, 0, 0))
    combo.paste(frog, (0, 0))
    combo.paste(kz, (SPRITE_PX, 0))
    arr = np.array(combo)
    alpha = arr[..., 3]
    rgb = arr[..., :3].copy()
    rgb[alpha < 128] = (0, 0, 0)
    rgb_img = Image.fromarray(rgb, 'RGB')
    quant = rgb_img.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal15 = np.array(quant.getpalette()[:15*3], dtype=np.uint8).reshape(15, 3)
    pal_rgb = np.vstack([pal15[:1], pal15])     # (16, 3); palette[0] dummy
    idx_arr = np.array(quant, dtype=np.uint8) + 1
    idx_arr[alpha < 128] = 0
    return idx_arr, pal_rgb


def pack_tile_into_page(page: bytearray, idx_arr: np.ndarray, src_x0: int, dst_cy: int, dst_cx: int, size_px: int):
    """Pack size_px × size_px tile from idx_arr[:, src_x0:src_x0+size_px] into page
    at cells starting (dst_cy, dst_cx). Assumes size_px % 8 == 0.
    """
    for py in range(size_px):
        page_y = dst_cy * 8 + py
        p_cy = page_y // 8
        ycnt = page_y % 8
        for px in range(size_px):
            page_x = dst_cx * 8 + px
            p_cx = page_x // 8
            bsel = (page_x % 8) // 2
            nibble = page_x % 2
            idx = int(idx_arr[py, src_x0 + px]) & 0x0F
            addr = p_cy * 2048 + ycnt * 256 + p_cx * 4 + bsel
            if nibble == 0:
                page[addr] = (page[addr] & 0x0F) | (idx << 4)
            else:
                page[addr] = (page[addr] & 0xF0) | idx


def main():
    if not TSU_P1.exists():
        raise SystemExit(f"Missing {TSU_P1} — build level_select_tsu pages first")
    page = bytearray(TSU_P1.read_bytes())
    if len(page) != 16384:
        raise SystemExit(f"Expected 16K page, got {len(page)}")

    idx_arr, pal_rgb = build_indices_and_palette()
    # 32×32 tiles = 4×4 cells. Free area page #0D после NEXT button (cx=24..51 cy=3..5)
    # и preview (cx=0..23) — берём cy=3..6 cx=53..56 (frog) и cy=3..6 cx=57..60 (kz).
    pack_tile_into_page(page, idx_arr, src_x0=0,                dst_cy=3, dst_cx=53, size_px=SPRITE_PX)
    pack_tile_into_page(page, idx_arr, src_x0=SPRITE_PX,        dst_cy=3, dst_cx=57, size_px=SPRITE_PX)

    PAL_OUT.write_bytes(rgb_to_cram_bytes(pal_rgb))
    print(f"Saved {PAL_OUT.name} (32 bytes)")
    TSU_P1.write_bytes(bytes(page))
    print(f"Patched {TSU_P1.name} (frog cells cy=3..6 cx=53..56, kz cy=3..6 cx=57..60)")

    # Verify non-zero count.
    for label, cx0 in [('frog', 53), ('kz', 57)]:
        total = 0
        for cy in range(3, 7):
            for cx in range(cx0, cx0 + 4):
                for ycnt in range(8):
                    for i in range(4):
                        if page[cy*2048 + ycnt*256 + cx*4 + i] != 0:
                            total += 1
        print(f"  {label}: {total}/{4*4*8*4} non-zero bytes in tile region")


if __name__ == '__main__':
    main()
