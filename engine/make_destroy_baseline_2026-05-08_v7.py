"""
Извлекает explosion-анимацию из Zuma-Deluxe-HD gameobjects.png:
  rectBallDestroy = {395, 0, 105, 120}, 13 frames vertical strip.
Прореживает до 7 кадров (равномерно), ресайзит 105x120 -> 24x24,
квантует в 16-color palette (greyscale + alpha-mask),
складывает в carpet layout = 3 cell-rows x 7 frames (3 cells/frame).

Output:
  destroy_gfx.bin     — 7 frames * 24x24 (bytes, 4bpp carpet) = 7*288 = 2016 байт
  destroy_pal.bin     — 1 палитра 32 байта (CRAM word x 16) с luminance gradient
  _destroy_preview.png — sanity check
"""
from PIL import Image
import numpy as np

SRC = r"C:\z80\zuma\_gameobjects_hd.png"
DST_BIN = r"C:\z80\zuma\destroy_gfx.bin"
DST_PAL = r"C:\z80\zuma\destroy_pal.bin"
PREVIEW = r"C:\z80\zuma\_destroy_preview.png"

NUM_HD_FRAMES = 13
NUM_FRAMES = 7              # сколько берём из 13
HD_W, HD_H = 105, 120
DST_BALL = 16
COLORS = 16

# Source rect
SRC_X, SRC_Y = 395, 0


def rgb8_to_cram(r, g, b):
    r5 = r >> 3; g5 = g >> 3; b5 = b >> 3
    byte0 = ((g5 & 7) << 5) | b5
    byte1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
    return bytes([byte0, byte1])


img = Image.open(SRC).convert("RGBA")
print(f"HD spritesheet: {img.size}")

# Equal-spaced frame picks: 0, 2, 4, 6, 8, 10, 12 — для NUM_FRAMES=7
indices = [round(i * (NUM_HD_FRAMES - 1) / (NUM_FRAMES - 1)) for i in range(NUM_FRAMES)]
print(f"Picking HD frames: {indices}")

frames_24 = []
for hd_idx in indices:
    raw = img.crop((SRC_X, SRC_Y + hd_idx * HD_H, SRC_X + HD_W, SRC_Y + (hd_idx + 1) * HD_H))
    small = raw.resize((DST_BALL, DST_BALL), Image.Resampling.LANCZOS)
    frames_24.append(small)

# Преview (горизонтальная лента)
preview = Image.new("RGBA", (NUM_FRAMES * DST_BALL * 4, DST_BALL * 4), (255, 0, 255, 255))
for i, f in enumerate(frames_24):
    big = f.resize((DST_BALL * 4, DST_BALL * 4), Image.NEAREST)
    preview.paste(big, (i * DST_BALL * 4, 0))
preview.save(PREVIEW)
print(f"Preview: {PREVIEW}")

# --- Палитра greyscale + alpha (idx 0 = transparent) ---
# Кадр HD по сути бесцветный (white/grey), color tint runtime через TSU palette swap.
# Идея: одна luminance palette idx0=transparent, idx1..15 = ramp white→bright.
palette = [(0, 0, 0)]  # idx 0 transparent
for i in range(1, COLORS):
    v = int(round(255 * i / (COLORS - 1)))
    palette.append((v, v, v))

# Сборка bin (carpet 64-wide × 3 cells/row, 7 frames в одной carpet-row 21 cells)
PAGE_BYTES = 16384
# Каждый шар занимает 3 carpet-rows × 3 cells = 9 cells = 9 * 64 byte = 576 b in 8bpp
# В 4bpp carpet (как balls24): 1 cell = 32 byte (8x8 px nibbles), ball 24x24 = 3x3=9 cells = 288 b
# 7 frames × 288 = 2016 byte. carpet stride: 1 cell-row = 2048 byte (64 cells × 32 byte).
# Frame N в carpet col = N*3.

NUM_CELL_ROWS = 4                 # 16×16: rows 0..1 = normal, rows 2..3 = shifted-up (для trackY<8)
gfx = bytearray(NUM_CELL_ROWS * 2048)
SHIFT_UP = 2                      # на сколько px вверх content внутри shifted variant (меньше обрезки)

def get_idx(r, g, b, a):
    # Brightness-ramp: HD pixel luminance → idx 1..15.
    # После sort palette в convert_balls24.py: idx 1=darkest, 15=brightest tone of ball-color.
    # Через SPAL=2+color destroy frame окрашен в gradient цвета шара.
    if a < 80:
        return 0
    lum = (r + g + b) // 3
    idx = 1 + lum * 14 // 255
    return max(1, min(15, idx))


def write_pixel(gfx, cy, cx, py_in_cell, px_in_cell, idx):
    bsel = px_in_cell // 2
    nibble = px_in_cell % 2
    addr = cy * 2048 + py_in_cell * 256 + cx * 4 + bsel
    if nibble == 0:
        gfx[addr] = (gfx[addr] & 0x0F) | ((idx & 0x0F) << 4)
    else:
        gfx[addr] = (gfx[addr] & 0xF0) | (idx & 0x0F)


for fr_idx, frame in enumerate(frames_24):
    pixels = frame.load()
    base_cx = fr_idx * 2
    # Normal variant — carpet rows 0..1
    for py in range(DST_BALL):
        for px in range(DST_BALL):
            r, g, b, a = pixels[px, py]
            idx = get_idx(r, g, b, a)
            write_pixel(gfx, py // 8, base_cx + px // 8, py % 8, px % 8, idx)
    # Shifted-up variant — carpet rows 2..3. Content поднят на SHIFT_UP, низ заполняется transparent.
    for py in range(DST_BALL):
        for px in range(DST_BALL):
            src_py = py + SHIFT_UP
            if src_py < DST_BALL:
                r, g, b, a = pixels[px, src_py]
                idx = get_idx(r, g, b, a)
            else:
                idx = 0
            write_pixel(gfx, 2 + py // 8, base_cx + px // 8, py % 8, px % 8, idx)

with open(DST_BIN, "wb") as f:
    f.write(gfx)
print(f"destroy_gfx.bin: {len(gfx)} bytes ({NUM_FRAMES} frames x 24x24, carpet {NUM_CELL_ROWS} rows)")

# Палитра CRAM
pal_bytes = bytearray(COLORS * 2)
for i, (r, g, b) in enumerate(palette):
    e = rgb8_to_cram(r, g, b)
    pal_bytes[i * 2 + 0] = e[0]
    pal_bytes[i * 2 + 1] = e[1]
pal_bytes[0] = 0; pal_bytes[1] = 0
with open(DST_PAL, "wb") as f:
    f.write(pal_bytes)
print(f"destroy_pal.bin: {len(pal_bytes)} bytes (1 palette x 16 colors, greyscale ramp)")
