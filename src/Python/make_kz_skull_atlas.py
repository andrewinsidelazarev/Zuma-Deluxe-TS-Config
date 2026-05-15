#!/usr/bin/env python3
"""Skull TSU atlas — 10 frames 32×32, 4bpp carpet. Размещается в page #0B
(= page_b после destroy_gfx) в byte offset 8192 = carpet cy=4 of page.
TNUM_global = 5*512 + 4*64 + N*4 = 2816 + 4*N.
Output bin = 8K (= 4 carpet rows). INCBIN'ится в asm после destroy_gfx.bin.
"""
import os
import numpy as np
from PIL import Image

SRC = r'C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/spritesheet.png'
PAL_BIN = r'C:/z80/zuma/balls_pal.bin'
OUT = r'C:/z80/zuma'
SPRITE_PIX = 32
ROW_STRIDE = 78
SRC_X0 = 370
SRC_X_END = 448
NUM_FRAMES = 10
YELLOW_K = 2
COLORS_PER_PAL = 16
PAGE = 16384
PAGE_BYTES_OUT = 8192   # 4 carpet rows = только skull (без destroy и без padding)

def cram_to_rgb(b0, b1):
    word = b0 | (b1 << 8)
    r5 = (word >> 10) & 0x1F
    g5 = (word >> 5) & 0x1F
    b5 = word & 0x1F
    return (r5 << 3, g5 << 3, b5 << 3)

pal_bytes = open(PAL_BIN, 'rb').read()
yellow_pal = [cram_to_rgb(pal_bytes[YELLOW_K*32 + c*2], pal_bytes[YELLOW_K*32 + c*2 + 1]) for c in range(COLORS_PER_PAL)]
yellow_pal_np = np.array(yellow_pal, dtype=np.int32)

def get_idx(r, g, b, a):
    if a < 80:
        return 0   # transparent
    target = np.array([r, g, b], dtype=np.int32)
    diffs = ((yellow_pal_np - target) ** 2).sum(axis=1)
    return int(np.argmin(diffs))

src = Image.open(SRC).convert('RGBA')
gfx = bytearray(PAGE_BYTES_OUT)   # 8K = 4 carpet rows (= skull only, INCBIN'ится в page_b)

for fi in range(NUM_FRAMES):
    sprite_row = fi + 1
    skull_full = src.crop((SRC_X0, sprite_row*ROW_STRIDE, SRC_X_END, sprite_row*ROW_STRIDE+ROW_STRIDE))
    skull_arr = np.array(skull_full)
    ys_s, xs_s = np.where(skull_arr[:, :, 3] > 80)
    if len(ys_s) == 0:
        # Empty frame — write transparent sprite
        continue
    sx0, sy0 = xs_s.min(), ys_s.min()
    sx1, sy1 = xs_s.max(), ys_s.max()
    skull_tight = skull_full.crop((sx0, sy0, sx1+1, sy1+1))
    tw, th = skull_tight.size
    # Fit tight bbox в SPRITE_PIX×SPRITE_PIX, aspect preserved.
    scale = SPRITE_PIX / max(tw, th)
    new_w = max(1, int(round(tw * scale)))
    new_h = max(1, int(round(th * scale)))
    skull_scaled = skull_tight.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new('RGBA', (SPRITE_PIX, SPRITE_PIX), (0, 0, 0, 0))
    paste_x = (SPRITE_PIX - new_w) // 2
    paste_y = (SPRITE_PIX - new_h) // 2
    canvas.paste(skull_scaled, (paste_x, paste_y), skull_scaled)
    pixels = canvas.load()

    base_cx = fi * 4               # 32×32 = 4 cells wide; frame N at carpet col = N*4
    for py in range(SPRITE_PIX):
        for px in range(SPRITE_PIX):
            r, g, b, a = pixels[px, py]
            idx = get_idx(r, g, b, a)
            cy = py // 8
            cx = base_cx + px // 8
            ycnt = py % 8
            bsel = (px % 8) // 2
            nibble = px % 2
            addr = cy * 2048 + ycnt * 256 + cx * 4 + bsel
            if nibble == 0:
                gfx[addr] = (gfx[addr] & 0x0F) | ((idx & 0x0F) << 4)
            else:
                gfx[addr] = (gfx[addr] & 0xF0) | (idx & 0x0F)
    print(f'Frame {fi}: row {sprite_row}, scaled to {new_w}×{new_h}, TNUM_local={base_cx}')

with open(os.path.join(OUT, 'kz_skull_atlas.bin'), 'wb') as f:
    f.write(gfx)
print(f'Saved kz_skull_atlas.bin ({len(gfx)} bytes)')
