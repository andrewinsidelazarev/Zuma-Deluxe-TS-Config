#!/usr/bin/env python3
"""Render GAME OVER atlas: 5 TSU sprites 64x64.
Atlas в page #0D — занимает cx=0..39 cy=0..7 (5 × 8 cx × 8 cy = 320 cells = 10K).
TNUM_global = 3584 + 8*N  (N=0..4, sprite N at cx=N*8 cy=0..7)
SPSIZ64 horiz × SPSIZ64 vert. Custom red->yellow gradient palette.
"""
import os
import numpy as np
from PIL import Image

FONT_PNG = 'C:/z80/zuma/_fonts/nativealien48.png'
FONT_TXT = 'C:/z80/zuma/_fonts/nativealien48.txt'
OUT_BIN  = 'C:/z80/zuma/gameover_text_atlas.bin'
PAL_BIN_OUT = 'C:/z80/zuma/gameover_pal.bin'

NUM_SPRITES = 5
SPRITE_W = 64
SPRITE_H = 64
TEXT_W = NUM_SPRITES * SPRITE_W                  # 320
TEXT_H = SPRITE_H                                 # 64
PAGE = 16384
SPAL_GAMEOVER = 5

# 16-color gradient red->orange->yellow
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
    """Render text in w×h RGBA image, centered."""
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
        cx, cw = char_x[c]
        crop = font_img.crop((cx, 0, cx + cw, font_h))
        new_w = max(1, int(cw * SCALE))
        crop = crop.resize((new_w, h), Image.LANCZOS)
        char_imgs.append((new_w, crop))
        total_w += new_w
    SPACING = 1
    total_w += SPACING * (len(char_imgs) - 1)
    start_x = (w - total_w) // 2
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    xx = start_x
    for ww, crop in char_imgs:
        if crop is not None:
            img.paste(crop, (xx, 0), crop)
        xx += ww + SPACING
    return img

go_img = render_text("GAME OVER", TEXT_W, TEXT_H)
go_img.save('C:/z80/zuma/_gameover_tsu_preview.png')

# Encode atlas: 5 sprites at cx=N*8, cy=0..7. Each sprite 8 cx × 8 cy cells.
gfx = bytearray(PAGE)

def encode_text(image, base_cx_per_sprite, base_cy):
    """Encode image (NUM_SPRITES × sprite_w wide) into atlas. base_cx_per_sprite = function(sprite_idx)→cx_start."""
    pixels = image.load()
    sw, sh = image.size
    for sprite_idx in range(NUM_SPRITES):
        cx_start = base_cx_per_sprite(sprite_idx)
        src_x_start = sprite_idx * SPRITE_W
        for py in range(SPRITE_H):
            for px in range(SPRITE_W):
                src_px = src_x_start + px
                r, g, b, a = pixels[src_px, py]
                idx = classify(r, g, b, a)
                cy = base_cy + py // 8
                cx = cx_start + px // 8
                ycnt = py % 8
                bsel = (px % 8) // 2
                nibble = px % 2
                addr = cy * 2048 + ycnt * 256 + cx * 4 + bsel
                if nibble == 0:
                    gfx[addr] = (gfx[addr] & 0x0F) | ((idx & 0x0F) << 4)
                else:
                    gfx[addr] = (gfx[addr] & 0xF0) | (idx & 0x0F)

# GAME OVER: side-by-side cx=0..39 cy=0..7. Sprite N at cx=N*8.
encode_text(go_img, lambda i: i * 8, base_cy=0)

open(OUT_BIN, 'wb').write(bytes(gfx))
print(f'Saved {OUT_BIN} ({len(gfx)} bytes)')

# Custom palette
def cram_word(r, g, b):
    word = (1 << 15) | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return bytes([word & 0xFF, (word >> 8) & 0xFF])

pal = bytearray(32)
pal[0:2] = b'\x00\x00'
for i in range(1, 16):
    rgb = GRADIENT[i]
    pal[i*2:i*2+2] = cram_word(*rgb)
open(PAL_BIN_OUT, 'wb').write(bytes(pal))
print(f'Saved {PAL_BIN_OUT} (32 bytes, 15-color gradient)')

print(f'GAME OVER 5 sprites 64×64. TNUM_base = 3584. Sprite N -> 3584 + N*8.')
print(f'SPAL = {SPAL_GAMEOVER}, SPSIZ64 horiz × SPSIZ64 vert.')
