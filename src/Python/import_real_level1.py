#!/usr/bin/env python3
"""Import REAL level 1 (= original Zuma Deluxe Level 1 "Spiral of Doom") в наш формат.
Source:
- BG image: Desktop/Zuma Deluxe/graphics/levels/level_src_01.png (640×480)
- Track:    Desktop/Zuma Deluxe/graphics/levels-HD/spiral/spiral.dat

Outputs (overwrite our test level files):
- level_01.bin (track resampled 1px)
- level_01_canvas_pal.bin (128 colors CRAM)
- level_01_canvas_p0..p8.bin (9 pages × 16K = 144K = 360×288 stride 512)
"""
import struct, math
from pathlib import Path
from PIL import Image
import numpy as np

SRC_PNG = r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels/level_src_01.png"
SRC_DAT = r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels-HD/spiral/spiral.dat"
DST_DIR = Path(r"C:/z80/zuma")                                                            # build dir для asm/spgbld
LVL_DIR = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels-ts-config/01")  # архив для уровня
LVL_DIR.mkdir(parents=True, exist_ok=True)

# Source: 640×480 (4:3 = 1.33) → screen 360×288 (5:4 = 1.25). Aspect разный.
# Решение: crop горизонтально source с 640 до 600 (= 5:4) → scale uniform 0.6 → 360×288.
# Crop X: (640-600)/2 = 20 пикселей с каждой стороны.
SRC_W, SRC_H = 640, 480
SCREEN_W, SCREEN_H = 360, 288
CROP_W = SRC_H * SCREEN_W // SCREEN_H        # = 600 (5:4 from 480)
CROP_X = (SRC_W - CROP_W) // 2                # = 20
SCALE = SCREEN_H / SRC_H                      # = 0.6 (uniform)
PAGE_BYTES = 16384
LINE_STRIDE = 512
BALL_PIX = 20
CELL_SIZE = 32
ENTRY_OFFSCREEN_MARGIN = BALL_PIX + 4

# --- 1. Parse spiral.dat (= curve data) ---
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

pts_hd = parse_dat(SRC_DAT)
xs, ys = [p[0] for p in pts_hd], [p[1] for p in pts_hd]
print(f"Track: {len(pts_hd)} HD points, X={min(xs):.1f}..{max(xs):.1f}  Y={min(ys):.1f}..{max(ys):.1f}")

# --- 2. Crop + scale ---
def scale_pt(x, y):
    """Track point: crop X by CROP_X offset (20 px), then scale uniform 0.6."""
    return (x - CROP_X) * SCALE, y * SCALE

pts_screen = [scale_pt(x, y) for x, y in pts_hd]

# --- 3. Resample to 1px arc-length ---
def resample(pts, step=1.0):
    out = [pts[0]]
    accum = 0.0
    for i in range(1, len(pts)):
        x0, y0 = out[-1]
        x1, y1 = pts[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9: continue
        accum += seg
        while accum >= step:
            t = (seg - (accum - step)) / seg
            nx = x0 + (x1 - x0) * t
            ny = y0 + (y1 - y0) * t
            out.append((nx, ny))
            accum -= step
            x0, y0 = nx, ny
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg < 1e-9: break
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

pts_resampled = resample(pts_screen, step=1.0)
pts_resampled = ensure_offscreen_entry_leadin(pts_resampled)
print(f"Resampled to 1px: {len(pts_resampled)} pts. End at ({pts_resampled[-1][0]:.0f}, {pts_resampled[-1][1]:.0f})")

# --- 4. Save level_01.bin ---
out = bytearray()
for x, y in pts_resampled:
    ix = int(round(x)) & 0xFFFF
    iy = int(round(y)) & 0xFFFF
    out.extend(struct.pack("<HH", ix, iy))
out.extend(struct.pack("<H", 0xFFFF))
(DST_DIR / "level_01.bin").write_bytes(bytes(out))
(LVL_DIR / "level_01.bin").write_bytes(bytes(out))                # архивная копия
print(f"Saved level_01.bin: {len(out)} bytes")
# Save копии исходных файлов в архив уровня (один раз — для документации/repro)
import shutil
shutil.copy(SRC_PNG, LVL_DIR / "src_bg.png")
shutil.copy(SRC_DAT, LVL_DIR / "src_track.dat")

# --- 5. BG: 640×480 → crop horiz to 600×480 → scale to 360×288 ---
bg = Image.open(SRC_PNG).convert("RGB")
bg_cropped = bg.crop((CROP_X, 0, CROP_X + CROP_W, SRC_H))     # 600×480
canvas = bg_cropped.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
canvas.save(DST_DIR / "_level_01_bg_preview.png")
canvas.save(LVL_DIR / "scaled_bg.png")    # архив scaled bg в папку уровня

# --- 6. Quantize 128 colors → palette + framebuffer ---
sub = canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
pixels_q = np.array(sub, dtype=np.uint8)
pal_flat = sub.getpalette()[:128*3]
pal_rgb = np.array(pal_flat, dtype=np.uint8).reshape(128, 3)

fb = np.full((SCREEN_H, LINE_STRIDE), 128, dtype=np.uint8)   # padding (col >= 360) = CRAM #80
fb[:, :SCREEN_W] = pixels_q + 128                              # bg fills полностью 360×288
fb_bytes = fb.tobytes()
print(f"Framebuffer size: {len(fb_bytes)} bytes")

# CRAM palette (128 × 2 bytes)
pal_bytes = bytearray(128 * 2)
for i in range(128):
    r, g, b = pal_rgb[i]
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    b0 = ((g5 & 7) << 5) | b5
    b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
    pal_bytes[i*2]   = b0
    pal_bytes[i*2+1] = b1
(DST_DIR / "level_01_canvas_pal.bin").write_bytes(bytes(pal_bytes))
(LVL_DIR / "level_01_canvas_pal.bin").write_bytes(bytes(pal_bytes))
print("Saved level_01_canvas_pal.bin (256 bytes)")

# Также сохраняем quantized canvas как PNG preview в папку уровня (визуальный референс)
preview_q = pal_rgb[pixels_q]
Image.fromarray(preview_q, "RGB").save(LVL_DIR / "quantized_bg_preview.png")

# --- 7. Split into 9 pages × 16K ---
for p in range(9):
    chunk = fb_bytes[p*PAGE_BYTES : (p+1)*PAGE_BYTES]
    if len(chunk) < PAGE_BYTES:
        chunk = chunk + b'\x80' * (PAGE_BYTES - len(chunk))
    (DST_DIR / f"level_01_canvas_p{p}.bin").write_bytes(chunk)
    (LVL_DIR / f"level_01_canvas_p{p}.bin").write_bytes(chunk)
    print(f"  level_01_canvas_p{p}.bin: {len(chunk)} bytes")

print("Done.")
