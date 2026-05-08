#!/usr/bin/env python3
"""
Конвертирует Zuma шары в DMA-формат для TS-Conf, используя
УЖЕ ЗАГРУЖЕННУЮ TSU-палитру шаров (balls_pal.bin в CRAM #20..#7F, SPAL 2..7).

Идея от Gemini Pro: TS-Conf CRAM единая для TSU и canvas. DMA-блит на
canvas с pixel value #20..#7F попадает в те же CRAM-ячейки что TSU.
Поэтому DMA-шары автоматически окрашиваются TSU-палитрой, а CRAM #80..#FF
остаётся полностью свободна под 128 цветов canvas.

Маппинг:
  ball color k → SPAL (2+k) → pixel #(20+16*k)..#(2F+16*k)
  transparent (alpha<128) → 0 (BLT1 пропустит)

ВАЖНО: используем тот же источник и пайплайн что convert_balls24.py
(spritesheet.png + auto-detect bbox), иначе порядок цветов и оттенки
расходятся с balls_pal.bin → искажения цветов в DMA-шарах.

------------------------------------------------------------------
Решение шатания DMA-шаров (Слободчиков, 2026-05-06):
  TS-Conf DMA-blit имеет 2-pixel granularity по X. Нечётные X «снапаются»
  к чётным → шар прыгает на 1 px в сторону. Лечится двумя вариантами
  спрайта на каждый цвет:
    even: ball на col 0..17, col 18..19 = transparent (для чётного X).
    odd:  col 0 = transparent, ball на col 1..18, col 19 = transparent
          (blit на чётный X-1, шар физически отображается на нужном X).
  В asm: dst_X = X & #FE, sprite = (X & 1) ? odd : even, DMALEN = 10-1.
  Все шары в DMA - 20 px wide, height 18.
"""
import os
import numpy as np
from PIL import Image

SRC = r'C:/Users/Администратор/Desktop/Zuma Deluxe/spritesheet.png'
OUT = r'C:/z80/zuma'
BALLS_PAL_BIN = r'C:/z80/zuma/balls_pal.bin'

BALL_PIX = 20                                   # DMA-burst 10 words. Visible круг 18 px (radius 9.5).
SPRITE_W = 22                                   # ширина DMA-спрайта (BALL_PIX + 2 для X-granularity odd offset)
NUM_BALLS = 6
COLORS_PER_BALL = 16
SECTION_W = 170                                 # как в convert_balls24.py
APPROX_STRIDE = SECTION_W / NUM_BALLS           # ~28.33
RAW_HALF = 14                                   # crop 28×28 вокруг центра


def cram_to_rgb(b0, b1):
    word = b0 | (b1 << 8)
    r5 = (word >> 10) & 0x1F
    g5 = (word >> 5) & 0x1F
    b5 = word & 0x1F
    return (r5 << 3, g5 << 3, b5 << 3)


# --- Грузим TSU-палитру шаров: 192 byte = 6 SPAL × 16 цветов ---
pal_bytes = open(BALLS_PAL_BIN, 'rb').read()
assert len(pal_bytes) == NUM_BALLS * COLORS_PER_BALL * 2, f"Expected {NUM_BALLS*COLORS_PER_BALL*2}, got {len(pal_bytes)}"
ball_palettes = []                              # 6 списков по 16 RGB
for k in range(NUM_BALLS):
    pal = []
    for c in range(COLORS_PER_BALL):
        offset = (k * COLORS_PER_BALL + c) * 2
        rgb = cram_to_rgb(pal_bytes[offset], pal_bytes[offset+1])
        pal.append(rgb)
    ball_palettes.append(np.array(pal, dtype=np.int32))

# --- Source: spritesheet.png, auto-detect bbox 6 шаров ---
src = Image.open(SRC).convert('RGBA')
print(f"Source: {src.size}, {src.mode}")
arr_full = np.array(src)

balls_rgba = []
for i in range(NUM_BALLS):
    region_x0 = int(i * APPROX_STRIDE)
    region_x1 = int((i + 1) * APPROX_STRIDE) + 2
    region = arr_full[:32, region_x0:region_x1, :]
    a = region[:, :, 3]
    ys, xs = np.where(a > 100)
    cx_local = (xs.min() + xs.max()) / 2
    cy_local = (ys.min() + ys.max()) / 2
    cx = region_x0 + cx_local
    cy = cy_local
    x0 = int(round(cx)) - RAW_HALF
    y0 = int(round(cy)) - RAW_HALF
    raw = src.crop((x0, y0, x0 + 28, y0 + 28))
    b = raw.resize((BALL_PIX, BALL_PIX), Image.LANCZOS)

    # Circular mask: радиус BALL_PIX/2 - 0.5 = 10.5 при BALL_PIX=22
    arr = np.array(b)
    yy, xx = np.ogrid[:BALL_PIX, :BALL_PIX]
    cpix = (BALL_PIX - 1) / 2
    radius = 9.5                  # diam ~18 px (текущий look)
    out_of_circle = (xx - cpix) ** 2 + (yy - cpix) ** 2 > radius ** 2
    arr[out_of_circle] = (0, 0, 0, 0)
    balls_rgba.append(arr)

# --- Для каждого ball pixel: найти ближайший цвет в SPAL шара ---
STRIDE = 512
PAGE = 16384

def write_ball_page(arr, pal, cram_base, x_offset, fname):
    """
    arr — RGBA шара 18×18, pal — 16×3 RGB.
    x_offset — смещение шара внутри 20-wide спрайта (0 для even, 1 для odd).
    Колонки вне [x_offset, x_offset+BALL_PIX) — нули (transparent).
    """
    rgb = arr[:, :, :3].astype(np.int32)
    alpha = arr[:, :, 3]
    page = bytearray(PAGE)
    for y in range(BALL_PIX):
        for x in range(BALL_PIX):
            dst_x = x + x_offset
            if alpha[y, x] < 128:
                page[y * STRIDE + dst_x] = 0    # transparent
                continue
            target = rgb[y, x]
            diffs = ((pal - target) ** 2).sum(axis=1)
            nearest_idx = int(np.argmin(diffs))
            page[y * STRIDE + dst_x] = cram_base + nearest_idx
    open(os.path.join(OUT, fname), 'wb').write(bytes(page))


for k in range(NUM_BALLS):
    arr = balls_rgba[k]
    pal = ball_palettes[k]                      # 16 × 3
    cram_base = 0x20 + 16 * k                   # CRAM #20 для k=0, ..., #70 для k=5

    fname_even = f'balls_dma_even_{k}.bin'
    fname_odd  = f'balls_dma_odd_{k}.bin'
    write_ball_page(arr, pal, cram_base, 0, fname_even)
    write_ball_page(arr, pal, cram_base, 1, fname_odd)
    print(f"  {fname_even} / {fname_odd}: ball color {k}, CRAM #{cram_base:02X}..#{cram_base+15:02X} (SPAL {2+k})")

# --- Sanity preview ---
preview_arr = np.zeros((BALL_PIX, NUM_BALLS * BALL_PIX, 3), dtype=np.uint8)
for k in range(NUM_BALLS):
    arr = balls_rgba[k]
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    pal = ball_palettes[k]
    for y in range(BALL_PIX):
        for x in range(BALL_PIX):
            if alpha[y, x] < 128:
                preview_arr[y, k*BALL_PIX + x] = (255, 0, 255)
            else:
                target = rgb[y, x].astype(np.int32)
                diffs = ((pal - target) ** 2).sum(axis=1)
                nearest_idx = int(np.argmin(diffs))
                preview_arr[y, k*BALL_PIX + x] = pal[nearest_idx]
Image.fromarray(preview_arr, 'RGB').resize((NUM_BALLS*BALL_PIX*4, BALL_PIX*4), Image.NEAREST).save(
    os.path.join(OUT, 'balls_dma_preview.png'))
print(f"  balls_dma_preview.png: visual sanity check")
print("\nDone — DMA-шары на источнике spritesheet.png, палитра balls_pal.bin.")
