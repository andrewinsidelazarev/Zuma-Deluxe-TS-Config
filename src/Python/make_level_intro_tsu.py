#!/usr/bin/env python3
"""Render LEVEL INTRO atlas: "LEVEL 1-1" 64×64 + "SPIRAL OF DOOM" 64×32.

Layout в 16K странице:
  LEVEL 1-1 (5 sprites 64×64) — cx=0..39, cy=0..7. Side-by-side. TNUM = 3584 + N*8.
  SPIRAL OF DOOM (5 sprites 64×32) — рассыпан по cx=40..63 cy=0..7.
    SP0 (40, 0) → TNUM = 3624
    SP1 (48, 0) → TNUM = 3632
    SP2 (56, 0) → TNUM = 3640
    SP3 (40, 4) → TNUM = 3880
    SP4 (48, 4) → TNUM = 3888
   (cx=56..63 cy=4..7 — 32 cells free, unused)

Same custom red->yellow gradient palette (= gameover_pal.bin).
"""
import os
import numpy as np
from PIL import Image

FONT_PNG = 'C:/z80/zuma/_fonts/nativealien48.png'
FONT_TXT = 'C:/z80/zuma/_fonts/nativealien48.txt'
OUT_BIN  = 'C:/z80/zuma/level_intro_text_atlas.bin'

LEVEL_NUM_SPRITES = 5
LEVEL_SPRITE_W = 64
LEVEL_SPRITE_H = 64
LEVEL_TEXT_W = LEVEL_NUM_SPRITES * LEVEL_SPRITE_W      # 320
LEVEL_TEXT_H = LEVEL_SPRITE_H                          # 64

DOOM_NUM_SPRITES = 5
DOOM_SPRITE_W = 64
DOOM_SPRITE_H = 32
DOOM_TEXT_W = DOOM_NUM_SPRITES * DOOM_SPRITE_W         # 320
DOOM_TEXT_H = DOOM_SPRITE_H                            # 32

PAGE = 16384

# Same gradient as GAME OVER
def gen_gradient():
    palette = [(0, 0, 0)]
    for i in range(1, 16):
        t = (i - 1) / 14.0
        r = 255 - int(50 * (1 - t))
        g = int(255 * t * t)
        b = int(20 * (1 - t))
        palette.append((r, g, b))
    return palette

GRADIENT = gen_gradient()

def classify(r, g, b, a):
    if a < 64:
        return 0
    best_idx, best_d = 1, 1e18
    for i in range(1, 16):
        pr, pg, pb = GRADIENT[i]
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best_d = d
            best_idx = i
    return best_idx

# Parse font
with open(FONT_TXT) as f:
    lines = [l.strip() for l in f.readlines()]
n = int(lines[0].split()[1])
chars = lines[1:1+n]
rect_start = None
for i, line in enumerate(lines):
    if line.startswith('RectList'):
        rect_start = i + 1
        break
rects = []
for i in range(rect_start, rect_start + n):
    parts = lines[i].split()
    rects.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])))
char_x = {}
for c, r in zip(chars, rects):
    char_x[c] = (r[0], r[2])

font_img = Image.open(FONT_PNG).convert('RGBA')
_, font_h = font_img.size

def render_text(text, w, h):
    SCALE = h / font_h
    SPACE_PX = int(20 * SCALE)
    total_w = 0
    char_imgs = []
    for c in text:
        if c == ' ':
            char_imgs.append((SPACE_PX, None))
            total_w += SPACE_PX
            continue
        if c not in char_x:
            print(f'Char {c!r} not in font, skipping')
            continue
        cx_src, cw_src = char_x[c]
        crop = font_img.crop((cx_src, 0, cx_src + cw_src, font_h))
        new_w = max(1, int(cw_src * SCALE))
        crop = crop.resize((new_w, h), Image.LANCZOS)
        char_imgs.append((new_w, crop))
        total_w += new_w
    SPACING = 1
    total_w += SPACING * (len(char_imgs) - 1)
    start_x = max(0, (w - total_w) // 2)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    xx = start_x
    for ww, crop in char_imgs:
        if crop is not None and xx + ww <= w:
            img.paste(crop, (xx, 0), crop)
        xx += ww + SPACING
    return img

level_img = render_text("LEVEL 1-1", LEVEL_TEXT_W, LEVEL_TEXT_H)
doom_img  = render_text("SPIRAL OF DOOM", DOOM_TEXT_W, DOOM_TEXT_H)
level_img.save('C:/z80/zuma/_levelintro_tsu_preview.png')
doom_img.save('C:/z80/zuma/_spiralofdoom_tsu_preview.png')

gfx = bytearray(PAGE)

def write_cell_pixel(cy, cx, py_in_cell, px_in_cell, idx):
    """Write one pixel into the 4bpp carpet at (cy, cx) cell, internal (py_in_cell, px_in_cell)."""
    bsel = (px_in_cell) // 2
    nibble = px_in_cell % 2
    addr = cy * 2048 + py_in_cell * 256 + cx * 4 + bsel
    if nibble == 0:
        gfx[addr] = (gfx[addr] & 0x0F) | ((idx & 0x0F) << 4)
    else:
        gfx[addr] = (gfx[addr] & 0xF0) | (idx & 0x0F)

def encode_sprite(image, src_x_start, sprite_w, sprite_h, dst_cx_start, dst_cy_start):
    """Encode one sprite region of image into atlas at given (cx, cy) start."""
    pixels = image.load()
    for py in range(sprite_h):
        for px in range(sprite_w):
            r, g, b, a = pixels[src_x_start + px, py]
            idx = classify(r, g, b, a)
            cy = dst_cy_start + py // 8
            cx = dst_cx_start + px // 8
            write_cell_pixel(cy, cx, py % 8, px % 8, idx)

# LEVEL 1-1: 5 sprites 64×64, cx=N*8, cy=0..7
for i in range(LEVEL_NUM_SPRITES):
    encode_sprite(level_img, i * LEVEL_SPRITE_W, LEVEL_SPRITE_W, LEVEL_SPRITE_H,
                  dst_cx_start=i * 8, dst_cy_start=0)

# SPIRAL OF DOOM: 5 sprites 64×32, scattered in cx=40..63 cy=0..7
doom_positions = [
    (40, 0),   # SP0
    (48, 0),   # SP1
    (56, 0),   # SP2
    (40, 4),   # SP3
    (48, 4),   # SP4
]
for i, (cx_start, cy_start) in enumerate(doom_positions):
    encode_sprite(doom_img, i * DOOM_SPRITE_W, DOOM_SPRITE_W, DOOM_SPRITE_H,
                  dst_cx_start=cx_start, dst_cy_start=cy_start)

open(OUT_BIN, 'wb').write(bytes(gfx))
print(f'Saved {OUT_BIN} ({len(gfx)} bytes)')
print(f'LEVEL 1-1: TNUM = 3584 + N*8 (5 sprites 64×64, cx=0..39 cy=0..7)')
print(f'SPIRAL OF DOOM scattered TNUMs:')
for i, (cx, cy) in enumerate(doom_positions):
    tnum = 3584 + cy * 64 + cx
    print(f'  SP{i}: cx={cx} cy={cy} -> TNUM = {tnum}')
