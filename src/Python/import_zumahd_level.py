"""
Импорт одного ZumaHD-уровня в наш TS-Config формат.
Использование:
    python import_zumahd_level.py 14    # импорт level 14 (spiral по сложности)

Делает:
  1. Парсит .dat → list of (X, Y) HD-coords (в пределах ~640×480)
  2. Map HD 16:9 assets to TS 360×288 by center-cropping the HD frame
     to 5:4 first. For .dat coordinates in the 640×480 reference this is:
       x_screen = (x - 20) * 0.6
       y_screen = y * 0.6
  4. Resample на 1px arc-length
  5. Save level_NN.bin в нашем формате (DW X, DW Y, ..., DW #FFFF)
  6. Конвертирует .jpg фон → level_NN_canvas_*.bin (8bpp + палитра)
"""
import sys
import struct
import math
from pathlib import Path
from PIL import Image

LVL_NUM = (sys.argv[1] if len(sys.argv) > 1 else "14").zfill(2)

# Mapping by difficulty
LEVEL_NAMES = [
    "tiltspiral", "underover", "longrange", "claw", "triangle",
    "inversespiral", "loopy", "turnaround", "squaresville", "warshak",
    "overunder", "spaceinvaders", "coaster", "spiral", "blackswirley",
    "serpents", "groovefest", "riverbed", "snakepit", "targetglyph",
    "tunnellevel", "space",
]

ZUMAHD_DIR = Path(r"C:\z80\zuma\zumahd")
DST_DIR = Path(r"C:\z80\zuma\zumahd_out")
DST_DIR.mkdir(exist_ok=True)

# Track в 640×480 (old Zuma coords). HD jpg = 1280×720, где 640×480 reference
# scaled 1.5× and centered horizontally in 16:9. TS screen is 360×288 (5:4).
# Correct conversion crops the HD frame to center 900×720 first:
#   HD crop x = 190..1090
#   track crop x = (190 - 160) / 1.5 = 20, width = 900 / 1.5 = 600
#   screen scale = 360 / 600 = 288 / 480 = 0.6
TRACK_CROP_X = 20.0
TRACK_CROP_W = 600.0
TRACK_REF_H = 480.0
SCALE_X = 360 / TRACK_CROP_W
SCALE_Y = 288 / TRACK_REF_H
SCREEN_W = 360
SCREEN_H = 288
BG_TARGET_H = 288   # full screen, no letterbox
LETTERBOX_TOP = 0   # screen aspect 5:4 = 1.25
BALL_PIX = 20
CELL_SIZE = 32
ENTRY_OFFSCREEN_MARGIN = BALL_PIX + 4

LVL_INDEX = int(LVL_NUM) - 1
NAME = LEVEL_NAMES[LVL_INDEX]
DAT_FILE = ZUMAHD_DIR / f"lvl{LVL_NUM}_{NAME}.dat"
JPG_FILE = ZUMAHD_DIR / f"lvl{LVL_NUM}_{NAME}.jpg"
print(f"  bg from HD jpg: {JPG_FILE.name}")

if not DAT_FILE.exists():
    print(f"NO DAT: {DAT_FILE}")
    sys.exit(1)


# --- 1. parse .dat ---
def parse_dat(path):
    data = Path(path).read_bytes()
    o = 0x10
    count1 = struct.unpack_from("<i", data, o)[0]
    o += 4 + count1 * 10
    curve_len = struct.unpack_from("<i", data, o)[0]
    o += 4
    x = struct.unpack_from("<f", data, o)[0]; o += 4
    y = struct.unpack_from("<f", data, o)[0]; o += 4
    pts = [(x, y)]
    for _ in range(curve_len):
        if o + 4 > len(data):
            break
        dx = struct.unpack_from("<b", data, o + 2)[0]
        dy = struct.unpack_from("<b", data, o + 3)[0]
        o += 4
        x += dx / 100.0
        y += dy / 100.0
        pts.append((x, y))
    return pts


pts_hd = parse_dat(DAT_FILE)
print(f"Level {LVL_NUM} ({NAME}): {len(pts_hd)} HD points")
xs = [p[0] for p in pts_hd]
ys = [p[1] for p in pts_hd]
print(f"  HD X range: {min(xs):.1f}..{max(xs):.1f}  Y: {min(ys):.1f}..{max(ys):.1f}")


# --- 2. Scale + letterbox shift ---
def scale_pt(x, y):
    sx = (x - TRACK_CROP_X) * SCALE_X
    sy = y * SCALE_Y + LETTERBOX_TOP
    return sx, sy


pts_screen = [scale_pt(x, y) for x, y in pts_hd]


# --- 3. Resample на 1px arc-length (linear interp) ---
def resample_arclength(pts, step=1.0):
    out = [pts[0]]
    accum = 0.0
    for i in range(1, len(pts)):
        x0, y0 = out[-1]
        x1, y1 = pts[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        accum += seg
        # сколько новых точек добавить: t = step / seg, в пределах [0, accum/step]
        while accum >= step:
            t = (seg - (accum - step)) / seg
            nx = x0 + (x1 - x0) * t
            ny = y0 + (y1 - y0) * t
            out.append((nx, ny))
            accum -= step
            x0, y0 = nx, ny
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg < 1e-9:
                break
    return out

def ensure_offscreen_entry_leadin(pts, margin=ENTRY_OFFSCREEN_MARGIN):
    """Prepend a cell-aligned off-screen lead-in only when the entry point is still visible."""
    if len(pts) < 2:
        return pts

    x0, y0 = pts[0]
    if x0 <= -margin or x0 >= SCREEN_W + margin or y0 <= -margin or y0 >= SCREEN_H + margin:
        return pts

    x1, y1 = pts[1]
    dx = x0 - x1
    dy = y0 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return pts
    dx /= length
    dy /= length

    lead = []
    x, y = x0, y0
    while len(lead) < CELL_SIZE or not (x <= -margin or x >= SCREEN_W + margin or y <= -margin or y >= SCREEN_H + margin):
        x += dx
        y += dy
        lead.append((x, y))
        if len(lead) > 128:
            break
    lead.reverse()
    return lead + pts


pts_resampled = resample_arclength(pts_screen, step=1.0)
pts_resampled = ensure_offscreen_entry_leadin(pts_resampled)
print(f"  Resampled to 1px: {len(pts_resampled)} points")


# --- 4. Save level_NN.bin ---
out = bytearray()
for x, y in pts_resampled:
    ix = int(round(x)) & 0xFFFF
    iy = int(round(y)) & 0xFFFF
    out.extend(struct.pack("<HH", ix, iy))
out.extend(struct.pack("<H", 0xFFFF))   # терминатор

DST_BIN = DST_DIR / f"level_{LVL_NUM}.bin"
DST_BIN.write_bytes(bytes(out))
print(f"  -> {DST_BIN.name}: {len(out)} bytes ({len(pts_resampled)} pts)")


# --- 5. Background → fixed center 5:4 crop, matching track remap ---
if JPG_FILE.exists():
    img = Image.open(JPG_FILE).convert("RGB")
    JW, JH = img.size
    print(f"  bg HD jpg: {JW}x{JH}")

    # Track ref = 640×480. HD jpg = 1280×720 = 640×480 content scaled UNIFORM 1.5×,
    # центрирован в 16:9 frame (= 320 px горизонтальных полей по сторонам).
    UNIFORM_SCALE = JH / 480.0  # = 1.5
    OFFSET_X = (JW - 640 * UNIFORM_SCALE) / 2  # = 160
    OFFSET_Y = 0
    target_aspect = SCREEN_W / SCREEN_H
    crop_w = JH * target_aspect
    jx_min = (JW - crop_w) / 2
    jx_max = jx_min + crop_w
    jy_min = 0
    jy_max = JH

    print(f"  fixed 5:4 crop: x={jx_min:.0f}..{jx_max:.0f}, y={jy_min:.0f}..{jy_max:.0f}")
    bg = img.crop((int(jx_min), int(jy_min), int(jx_max), int(jy_max)))
    bg = bg.resize((SCREEN_W, BG_TARGET_H), Image.Resampling.LANCZOS)

    # Перерасчёт scale для track: координаты в track-system должны
    # отображаться внутри cropped области. Crop был [jx_min..jx_max] в jpg-coords.
    # В track-coords это [tx_min..tx_max]. После resize в 360×270:
    # screen_x = (track_x - tx_min) * SCREEN_W / (tx_max - tx_min)
    # screen_y = (track_y - ty_min) * BG_TARGET_H / (ty_max - ty_min) + LETTERBOX_TOP
    actual_tx_min = (jx_min - OFFSET_X) / UNIFORM_SCALE
    actual_ty_min = (jy_min - OFFSET_Y) / UNIFORM_SCALE
    actual_tx_max = (jx_max - OFFSET_X) / UNIFORM_SCALE
    actual_ty_max = (jy_max - OFFSET_Y) / UNIFORM_SCALE
    sx_factor = SCREEN_W / (actual_tx_max - actual_tx_min)
    sy_factor = BG_TARGET_H / (actual_ty_max - actual_ty_min)
    print(f"  track remap: tx[{actual_tx_min:.1f}..{actual_tx_max:.1f}] -> screen 0..{SCREEN_W}, scale_x={sx_factor:.3f}")

    # Перерасчёт track-точек для fixed crop:
    pts_screen_v2 = []
    for x, y in pts_hd:
        sx = (x - actual_tx_min) * sx_factor
        sy = (y - actual_ty_min) * sy_factor + LETTERBOX_TOP
        pts_screen_v2.append((sx, sy))
    pts_resampled = resample_arclength(pts_screen_v2, step=1.0)
    pts_resampled = ensure_offscreen_entry_leadin(pts_resampled)
    print(f"  Re-resampled to 1px: {len(pts_resampled)} points")

    out = bytearray()
    for x, y in pts_resampled:
        ix = int(round(x)) & 0xFFFF
        iy = int(round(y)) & 0xFFFF
        out.extend(struct.pack("<HH", ix, iy))
    out.extend(struct.pack("<H", 0xFFFF))
    DST_BIN.write_bytes(bytes(out))
    print(f"  -> updated {DST_BIN.name}: {len(out)} bytes")

    # Quantize 128 colors (CRAM 128..255)
    sub = bg.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    pal_flat = sub.getpalette()[:128*3]
    pixels_q = sub.tobytes()
    palette_rgb = [tuple(pal_flat[i:i + 3]) for i in range(0, 128 * 3, 3)]

    # 8bpp framebuffer 360×288 stride 512, bg at rows LETTERBOX_TOP..LETTERBOX_TOP+BG_H
    fb = bytearray(SCREEN_H * 512)
    for y in range(BG_TARGET_H):
        src = y * SCREEN_W
        dst = (LETTERBOX_TOP + y) * 512
        fb[dst:dst + SCREEN_W] = bytes((v + 128) & 0xFF for v in pixels_q[src:src + SCREEN_W])

    DST_FB = DST_DIR / f"level_{LVL_NUM}_canvas.bin"
    DST_FB.write_bytes(bytes(fb))

    # CRAM palette (128 colors × 2 bytes)
    pal_bytes = bytearray(128 * 2)
    for i in range(128):
        r, g, b = palette_rgb[i]
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        pal_bytes[i*2] = b0
        pal_bytes[i*2+1] = b1
    DST_PAL = DST_DIR / f"level_{LVL_NUM}_canvas_pal.bin"
    DST_PAL.write_bytes(bytes(pal_bytes))

    print(f"  -> {DST_FB.name}: {len(fb)} bytes (stride 512)")
    print(f"  -> {DST_PAL.name}: 256 bytes (128 colors)")
else:
    print(f"  no bg jpg")
