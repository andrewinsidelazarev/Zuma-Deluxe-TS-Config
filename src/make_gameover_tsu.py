#!/usr/bin/env python3
"""Render "GAME OVER" в виде 5 TSU sprites 64×64, 4bpp carpet формат.
Атлас в page #0D (full 16K). TNUM_global = 7*512 + 8*N = 3584 + 8*N.
Палитра: red ball CRAM #50..#5F (SPAL=5), цвет idx 15 = bright red.
"""
import os
import numpy as np
from PIL import Image

FONT_PNG = 'C:/z80/zuma/_fonts/nativealien48.png'
FONT_TXT = 'C:/z80/zuma/_fonts/nativealien48.txt'
PAL_BIN  = 'C:/z80/zuma/balls_pal.bin'
OUT_BIN  = 'C:/z80/zuma/gameover_text_atlas.bin'

NUM_SPRITES = 5
SPRITE_W = SPRITE_H = 64
TEXT_W = NUM_SPRITES * SPRITE_W                  # 320
TEXT_H = SPRITE_H                                 # 64
PAGE = 16384
SPAL_GAMEOVER = 5   # переиспользуем red ball palette во время state 2

# 16-color gradient palette: idx 0 transparent, idx 1..15 = красный → оранжевый → жёлтый
def gen_gradient():
    """Smooth red→orange→yellow gradient. idx 0 transparent."""
    palette = [(0, 0, 0)]  # idx 0 (will be transparent in CRAM)
    # idx 1: dark red
    # idx 15: bright yellow
    # Linear interp: R stays high, G grows from 0 to 255, B stays low
    for i in range(1, 16):
        t = (i - 1) / 14.0  # 0..1
        r = 255 - int(50 * (1 - t))         # 205..255 (slight red darkening for outline shades)
        g = int(255 * t * t)                 # 0..255 quadratic for более плавный yellow inner
        b = int(20 * (1 - t))                # 20..0 minor blue для richer red
        palette.append((r, g, b))
    return palette

GRADIENT = gen_gradient()

# Parse font txt
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

# Render text to one big image 320×64
font_img = Image.open(FONT_PNG).convert('RGBA')
font_w, font_h = font_img.size
print(f'Font PNG: {font_w}×{font_h}')
text = "GAME OVER"
SCALE = TEXT_H / font_h
SPACE_PX = int(20 * SCALE)
total_w = 0
char_imgs = []
for c in text:
    if c == ' ':
        char_imgs.append((SPACE_PX, None))
        total_w += SPACE_PX
        continue
    cx, cw = char_x[c]
    crop = font_img.crop((cx, 0, cx + cw, font_h))
    new_w = max(1, int(cw * SCALE))
    crop = crop.resize((new_w, TEXT_H), Image.LANCZOS)
    char_imgs.append((new_w, crop))
    total_w += new_w
SPACING = 1
total_w += SPACING * (len(char_imgs) - 1)
start_x = (TEXT_W - total_w) // 2
print(f'Text width={total_w}, centered X={start_x} in {TEXT_W}-wide canvas')

text_img = Image.new('RGBA', (TEXT_W, TEXT_H), (0, 0, 0, 0))
xx = start_x
for w, crop in char_imgs:
    if crop is not None:
        text_img.paste(crop, (xx, 0), crop)
    xx += w + SPACING

text_img.save('C:/z80/zuma/_gameover_tsu_preview.png')

# Encode 4bpp carpet, 5 sprites × 64×64. Single color (red palette idx 15).
gfx = bytearray(PAGE)
pixels = text_img.load()

def classify(r, g, b, a):
    """Nearest-color quantization: map source RGB to closest gradient idx 1..15.
    Transparent → 0. Antialiased font edges naturally → intermediate indices = soft gradient."""
    if a < 64:
        return 0
    # Find nearest in GRADIENT[1..15]
    best_idx, best_d = 1, 1e18
    for i in range(1, 16):
        pr, pg, pb = GRADIENT[i]
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best_d = d
            best_idx = i
    return best_idx

for sprite_idx in range(NUM_SPRITES):
    base_cx = sprite_idx * 8       # 64px wide = 8 cells
    src_x_start = sprite_idx * SPRITE_W
    for py in range(SPRITE_H):
        for px in range(SPRITE_W):
            src_px = src_x_start + px
            r, g, b, a = pixels[src_px, py]
            idx = classify(r, g, b, a)
            cy = py // 8                  # 0..7 (full page)
            cx = base_cx + px // 8
            ycnt = py % 8
            bsel = (px % 8) // 2
            nibble = px % 2
            addr = cy * 2048 + ycnt * 256 + cx * 4 + bsel
            if nibble == 0:
                gfx[addr] = (gfx[addr] & 0x0F) | ((idx & 0x0F) << 4)
            else:
                gfx[addr] = (gfx[addr] & 0xF0) | (idx & 0x0F)

open(OUT_BIN, 'wb').write(bytes(gfx))
print(f'Saved {OUT_BIN} ({len(gfx)} bytes)')

# Custom palette: 32 bytes = 16 CRAM words. idx 0 transparent, idx 1..15 = gradient.
def cram_word(r, g, b):
    word = (1 << 15) | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return bytes([word & 0xFF, (word >> 8) & 0xFF])

pal = bytearray(32)
pal[0:2] = b'\x00\x00'                       # idx 0 transparent (C=0)
for i in range(1, 16):
    rgb = GRADIENT[i]
    pal[i*2:i*2+2] = cram_word(*rgb)

open('C:/z80/zuma/gameover_pal.bin', 'wb').write(bytes(pal))
print(f'Saved gameover_pal.bin (32 bytes, {len(GRADIENT)-1}-color gradient)')

TNUM_BASE = 7 * 512   # = 3584
print(f'GAMEOVER text TNUM_base = {TNUM_BASE} (sprite N → TNUM = {TNUM_BASE} + N*8)')
print(f'SPAL = {SPAL_GAMEOVER} (red ball palette repurposed для state 2)')
