#!/usr/bin/env python3
"""Только sun base (frame 0, без skull) для DMA blit. Один static фрейм."""
import os
import numpy as np
from PIL import Image

SRC = r'C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/spritesheet.png'
PAL_BIN = r'C:/z80/zuma/balls_pal.bin'
OUT = r'C:/z80/zuma'
KZ_PIX = 64
ROW_STRIDE = 78
SRC_X0 = 370
SRC_X_END = 448
YELLOW_K = 2
COLORS_PER_PAL = 16
CRAM_BASE = 0x20 + 16 * YELLOW_K  # = 0x40
STRIDE = 512
PAGE = 16384

def cram_to_rgb(b0, b1):
    word = b0 | (b1 << 8)
    r5 = (word >> 10) & 0x1F
    g5 = (word >> 5) & 0x1F
    b5 = word & 0x1F
    return (r5 << 3, g5 << 3, b5 << 3)

pal_bytes = open(PAL_BIN, 'rb').read()
yellow_pal = [cram_to_rgb(pal_bytes[YELLOW_K*32 + c*2], pal_bytes[YELLOW_K*32 + c*2 + 1]) for c in range(COLORS_PER_PAL)]
yellow_pal_np = np.array(yellow_pal, dtype=np.int32)

src = Image.open(SRC).convert('RGBA')
sun_full = src.crop((SRC_X0, 0, SRC_X_END, ROW_STRIDE))      # 78×78 sun only
sun = sun_full.resize((KZ_PIX, KZ_PIX), Image.LANCZOS)
arr = np.array(sun)
rgb_arr = arr[:, :, :3].astype(np.int32)
alpha = arr[:, :, 3]

top_page = bytearray(PAGE)
bot_page = bytearray(PAGE)
for y in range(KZ_PIX):
    for x in range(KZ_PIX):
        if alpha[y, x] < 80:
            byte_val = 0
        else:
            target = rgb_arr[y, x]
            diffs = ((yellow_pal_np - target) ** 2).sum(axis=1)
            byte_val = CRAM_BASE + int(np.argmin(diffs))
        if y < 32:
            top_page[y * STRIDE + x] = byte_val
        else:
            bot_page[(y - 32) * STRIDE + x] = byte_val
open(os.path.join(OUT, 'killzone_top.bin'), 'wb').write(bytes(top_page))
open(os.path.join(OUT, 'killzone_bot.bin'), 'wb').write(bytes(bot_page))
print('Saved sun-only killzone_top.bin / killzone_bot.bin')
