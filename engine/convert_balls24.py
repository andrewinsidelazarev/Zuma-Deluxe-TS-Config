"""
Конвертер шаров 24×24 для Zuma на TS-Config.

Source: Zuma Deluxe - Gameplay - Balls.png (192×1632, 6 цветов × frame 32×32, frame 0 top row)
- Resize каждого frame 32→24 (LANCZOS)
- Per-ball палитра 16 цветов (idx 0 = transparent)
- Carpet 64-wide: ball 24×24 = 3×3 cells, frame N at carpet (cy=base, cx=N*3).
  6 шаров уместятся в 1 carpet-row (6*3=18 cells < 64). Carpet height = 3 cells.

Размещение в page #A (после frog 64×64 и до preview):
  Cursor 16×16 в carpet rows 0..1 (carpet TNUM 0..1) — расположение page-10-relative.
  Balls 24×24 в carpet rows 4..6 (TNUM_local=256, _global=2304+256=2560).
  Preview 8×8 в carpet row 7 (TNUM_local=448, _global=2752).

Outputs:
  balls24_gfx.bin — bytes for ball region
  balls_pal.bin   — 6 палитр × 32 байта = 192 байта (как раньше; idx 0 transparent, idx 1..15 цвет)
"""
from PIL import Image

SRC = r"C:\Users\Администратор\Desktop\Zuma Deluxe\spritesheet.png"
DST_BIN = r"C:\z80\zuma\balls24_gfx.bin"
DST_PAL = r"C:\z80\zuma\balls_pal.bin"

SRC_BALL = 28           # frame size в spritesheet.png (определено эмпирически)
DST_BALL = 24           # размер cell-области (SPSIZ24)
CONTENT = 22            # visual ball size (center in 24x24 frame, 1px transparent border)
                        # diameter = 21 px @ radius 10.5 — соответствует cell-spacing на нашем треке (1986/96≈20.7)
NUM_BALLS = 6
COLORS_PER_BALL = 16


def rgb8_to_cram(r, g, b):
    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3
    byte0 = ((g5 & 7) << 5) | b5
    byte1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
    return bytes([byte0, byte1])


img = Image.open(SRC).convert("RGBA")
W, H = img.size
print(f"Source: {W}x{H}, finding ball bboxes via alpha")

import numpy as np

# Авто-детекция bbox каждого шара по alpha. Делаем по-секционно: первая section
# atlas (cols 0..170) содержит 6 балов. Разбиваем равномерно (stride 28.5)
# и для каждой подобласти находим bbox.
arr_full = np.array(img)
SECTION_W = 170
APPROX_STRIDE = SECTION_W / NUM_BALLS    # ~28.33

top_row = Image.new("RGBA", (NUM_BALLS * DST_BALL, DST_BALL), (0, 0, 0, 0))
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
    half = 14
    x0 = int(round(cx)) - half
    y0 = int(round(cy)) - half
    raw = img.crop((x0, y0, x0 + 28, y0 + 28))
    # Resize до CONTENT×CONTENT (визуальный размер шара)
    content_img = raw.resize((CONTENT, CONTENT), Image.Resampling.LANCZOS)

    # Кладём 20×20 контент в 24×24 frame с offset (2,2), по 2px прозрачного border
    crop = Image.new("RGBA", (DST_BALL, DST_BALL), (0, 0, 0, 0))
    crop.paste(content_img, ((DST_BALL - CONTENT) // 2, (DST_BALL - CONTENT) // 2))

    # Circular mask: радиус 10.5 → diameter 21 px (касается соседей на cell-step 20.7)
    arr_crop = np.array(crop)
    yy, xx = np.ogrid[:DST_BALL, :DST_BALL]
    cx_pix = (DST_BALL - 1) / 2
    cy_pix = (DST_BALL - 1) / 2
    radius = 9.5      # diam 18 — +1 step (~2 px) зазор vs 20
    out_of_circle = (xx - cx_pix) ** 2 + (yy - cy_pix) ** 2 > radius ** 2
    arr_crop[out_of_circle] = (0, 0, 0, 0)
    crop = Image.fromarray(arr_crop, "RGBA")

    top_row.paste(crop, (i * DST_BALL, 0))
top_row.save(r"C:\z80\zuma\_balls24_preview.png")

# carpet 64-wide × 3 cells высоты на ball-row. Балы в carpet row 0..2 (TNUM_local 0..127).
# Каждый ball занимает 3 cells x 3 cells = 9 cells.
# Полный размер: 3 cell-rows × 2048 = 6144 байт. Это часть page A (cursor отдельно).
PAGE_BYTES = 16384
balls_region_bytes = 3 * 2048    # 3 cell-rows of carpet
gfx = bytearray(balls_region_bytes)

all_pals = bytearray(NUM_BALLS * 32)

for ball_idx in range(NUM_BALLS):
    crop = top_row.crop((ball_idx * DST_BALL, 0, (ball_idx + 1) * DST_BALL, DST_BALL))
    pixels = crop.load()

    # Quantize opaque pixels to 15 colors
    opaque_img = Image.new("RGB", (DST_BALL, DST_BALL), (0, 0, 0))
    for y in range(DST_BALL):
        for x in range(DST_BALL):
            r, g, b, a = pixels[x, y]
            if a >= 128:
                opaque_img.putpixel((x, y), (r, g, b))

    quant = opaque_img.quantize(colors=COLORS_PER_BALL - 1, method=Image.Quantize.MEDIANCUT)
    pal_flat = quant.getpalette()
    # Sort quantized colors by brightness (R+G+B), idx 15 = brightest.
    # destroy_gfx использует pixel=15 → автоматически brightest tone каждого ball-цвета.
    raw_colors = []
    for i in range(COLORS_PER_BALL - 1):
        raw_colors.append((pal_flat[i*3], pal_flat[i*3+1], pal_flat[i*3+2]))
    raw_colors.sort(key=lambda c: c[0] + c[1] + c[2])
    palette_rgb = [(0, 0, 0)] + raw_colors      # idx 0 = transparent, 1..15 = darkest→brightest

    def get_idx(r, g, b, a, _pal=palette_rgb):
        if a < 128:
            return 0
        best_i, best_d = 1, 10**9
        for i in range(1, COLORS_PER_BALL):
            cr, cg, cb = _pal[i]
            d = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    base_cx = ball_idx * 3       # ball N в carpet col base = N*3 cells
    for py in range(DST_BALL):
        for px in range(DST_BALL):
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

    for i, (r, g, b) in enumerate(palette_rgb):
        e = rgb8_to_cram(r, g, b)
        all_pals[ball_idx*32 + i*2 + 0] = e[0]
        all_pals[ball_idx*32 + i*2 + 1] = e[1]
    all_pals[ball_idx*32 + 0] = 0
    all_pals[ball_idx*32 + 1] = 0

with open(DST_BIN, "wb") as f:
    f.write(gfx)
print(f"Wrote {DST_BIN}: {len(gfx)} bytes (3 carpet rows)")

with open(DST_PAL, "wb") as f:
    f.write(all_pals)
print(f"Wrote {DST_PAL}: {len(all_pals)} bytes (6 palettes x 32, SPAL 2..7)")

print()
print("TNUM (page #A start, ball N в carpet):")
for n in range(NUM_BALLS):
    cx = n * 3
    print(f"  Ball {n}: cy=0, cx={cx}, TNUM_local = {cx} (page-relative)")
