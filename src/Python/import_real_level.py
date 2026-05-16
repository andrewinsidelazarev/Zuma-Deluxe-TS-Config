#!/usr/bin/env python3
"""Universal import for any level N (1..18) → generate track + canvas pages + palette.

Source:
  - BG image: graphics/levels/level_src_NN.png (640×480 HD)
  - Track:    graphics/levels-HD/<name>/<name>.dat where <name> = NAME_BY_LEVEL[N]

Outputs:
  - level_NN.bin            (track, resampled to 1 px steps)
  - level_NN_canvas_pal.bin (128 colors CRAM)
  - level_NN_canvas_p0..p8.bin (9 pages × 16K)
  - Archive copies в graphics/levels-ts-config/NN/

Usage: python import_real_level.py <N>
"""
import sys, struct, shutil
from pathlib import Path
from PIL import Image
import numpy as np

# Stage 1 progression — graphics by level index 1..18. From src/levels_meta.json.
NAME_BY_LEVEL = {
    1:  'spiral',
    2:  'claw',
    3:  'riverbed',
    4:  'targetglyph',
    5:  'turnaround',
    6:  'longrange',
    7:  'tiltspiral',
    8:  'underover',
    9:  'warshak',
    10: 'loopy',
    11: 'groovefest',
    12: 'spaceinvaders',
    13: 'triangle',
    14: 'coaster',
    15: 'squaresville',
    16: 'tunnellevel',
    17: 'overunder',
    18: 'inversespiral',
}

ROOT       = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe")
DST_DIR    = Path(r"C:/z80/zuma")
LEVELS_HD  = ROOT / "graphics" / "levels-HD"
LEVELS_PNG = ROOT / "graphics" / "levels"
LEVELS_TS  = ROOT / "graphics" / "levels-ts-config"

SRC_W, SRC_H         = 640, 480
SCREEN_W, SCREEN_H   = 360, 288
CROP_W               = SRC_H * SCREEN_W // SCREEN_H        # 600
CROP_X               = (SRC_W - CROP_W) // 2                # 20
SCALE                = SCREEN_H / SRC_H                    # 0.6 uniform
PAGE_BYTES           = 16384
LINE_STRIDE          = 512


def parse_dat(path: Path):
    data = path.read_bytes()
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
        # CurveDot format: t1 (byte) | t2 (byte) | dx (signed byte) | dy (signed byte).
        # HD source code: xprev += dx / 100.0f (Level.c:_CurveLoadFromFile).
        dx = struct.unpack_from("<b", data, o + 2)[0]
        dy = struct.unpack_from("<b", data, o + 3)[0]
        o += 4
        x += dx / 100.0
        y += dy / 100.0
        pts.append((x, y))
    return pts


def resample(pts, step=1.0):
    """Resample к exact step-pixel spacing via linear interpolation.
    For each input segment, walks along it placing points at every `step` from
    last kept point. Gives true 1px-per-sample track (≠ greedy skip).
    """
    if len(pts) < 2:
        return list(pts)
    out = [pts[0]]
    last_x, last_y = pts[0]
    leftover = 0.0   # how far past last kept point we've walked along current segment

    for nx, ny in pts[1:]:
        dx = nx - last_x
        dy = ny - last_y
        seg_len = (dx*dx + dy*dy) ** 0.5
        if seg_len < 1e-9:
            continue
        # Walk from last_kept (= last_x, last_y if leftover=0, else fractional in seg)
        # We want points at distance step, 2*step, ... from last kept.
        # Position along this segment after which we've accumulated `step`:
        # We have `step - leftover` distance to next sample target.
        # But leftover semantics: we've consumed `leftover` of current seg already from last_kept.
        # Actually simpler: maintain `dist_to_next` — remaining distance until next sample.
        # Init: dist_to_next = step - leftover.
        pos = leftover  # distance already walked along current seg (from last_x,last_y)
        # `step - leftover` is distance from current pos at segment-start to next sample.
        # Place samples at pos = step - leftover, 2*step - leftover, ... within seg_len.
        while pos + (step - leftover) <= seg_len:
            pos += (step - leftover)
            leftover = 0.0  # reset after first placement
            t = pos / seg_len
            px = last_x + dx * t
            py = last_y + dy * t
            out.append((px, py))
            # After placing, distance remaining до следующего sample = step
            # Continue walking next step within same seg if room.
            # Loop condition: pos + step ≤ seg_len
            # Reset leftover for next iterations on this seg.
            if pos + step <= seg_len:
                pos += step
                t = pos / seg_len
                px = last_x + dx * t
                py = last_y + dy * t
                out.append((px, py))
            break  # actually we want loop, but above placed up to 2 — restructure
        # Restart proper loop
    # ↑ above logic faulty — replace with clean version below
    out = [pts[0]]
    last_x, last_y = pts[0]
    leftover = 0.0
    for nx, ny in pts[1:]:
        dx = nx - last_x
        dy = ny - last_y
        seg_len = (dx*dx + dy*dy) ** 0.5
        if seg_len < 1e-12:
            continue
        # First target distance from last_kept = step - leftover
        target = step - leftover
        while target <= seg_len:
            t = target / seg_len
            px = last_x + dx * t
            py = last_y + dy * t
            out.append((px, py))
            target += step
        # After consuming this seg, leftover = how much past last target we went
        leftover = seg_len - (target - step)
        last_x, last_y = nx, ny
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: python import_real_level.py <N>  (N = 1..18)")
        sys.exit(1)
    N = int(sys.argv[1])
    if N not in NAME_BY_LEVEL:
        sys.exit(f"Level {N} not in NAME_BY_LEVEL (range 1..18)")
    name = NAME_BY_LEVEL[N]
    print(f"=== Level {N:02d} = '{name}' ===")

    src_png = LEVELS_PNG / f"level_src_{N:02d}.png"
    src_dat = LEVELS_HD / name / f"{name}.dat"
    if not src_png.exists():
        sys.exit(f"Missing source PNG: {src_png}")
    if not src_dat.exists():
        sys.exit(f"Missing source DAT: {src_dat}")

    lvl_dir = LEVELS_TS / f"{N:02d}"
    lvl_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Track ---
    pts = parse_dat(src_dat)
    print(f"Parsed {len(pts)} pts from {src_dat.name}")
    # Source coordinates → screen 360×288 (with same aspect-crop+scale as canvas).
    pts_screen = [((x - CROP_X) * SCALE, y * SCALE) for x, y in pts]
    pts_resampled = resample(pts_screen, step=1.0)
    print(f"Resampled to 1px: {len(pts_resampled)} pts. End at ({pts_resampled[-1][0]:.0f}, {pts_resampled[-1][1]:.0f})")
    out = bytearray()
    for x, y in pts_resampled:
        ix = int(round(x)) & 0xFFFF
        iy = int(round(y)) & 0xFFFF
        out.extend(struct.pack("<HH", ix, iy))
    out.extend(struct.pack("<H", 0xFFFF))
    track_name = f"level_{N:02d}.bin"
    (DST_DIR / track_name).write_bytes(bytes(out))
    (lvl_dir / track_name).write_bytes(bytes(out))
    print(f"Saved {track_name}: {len(out)} bytes")
    shutil.copy(src_png, lvl_dir / "src_bg.png")
    shutil.copy(src_dat, lvl_dir / "src_track.dat")

    # --- 2. Canvas: 640×480 → crop 600×480 → resize 360×288 → quantize 128 ---
    bg = Image.open(src_png).convert("RGB")
    bg_cropped = bg.crop((CROP_X, 0, CROP_X + CROP_W, SRC_H))
    canvas = bg_cropped.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
    canvas.save(lvl_dir / "scaled_bg.png")

    sub = canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    pixels_q = np.array(sub, dtype=np.uint8)
    pal_flat = sub.getpalette()[:128*3]
    pal_rgb = np.array(pal_flat, dtype=np.uint8).reshape(128, 3)

    fb = np.full((SCREEN_H, LINE_STRIDE), 128, dtype=np.uint8)
    fb[:, :SCREEN_W] = pixels_q + 128
    fb_bytes = fb.tobytes()
    print(f"Framebuffer: {len(fb_bytes)} bytes")

    pal_bytes = bytearray(128 * 2)
    for i in range(128):
        r, g, b = pal_rgb[i]
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        pal_bytes[i*2]   = b0
        pal_bytes[i*2+1] = b1
    pal_name = f"level_{N:02d}_canvas_pal.bin"
    (DST_DIR / pal_name).write_bytes(bytes(pal_bytes))
    (lvl_dir / pal_name).write_bytes(bytes(pal_bytes))
    print(f"Saved {pal_name} (256 bytes)")

    preview_q = pal_rgb[pixels_q]
    Image.fromarray(preview_q, "RGB").save(lvl_dir / "quantized_bg_preview.png")

    # --- 3. Split into 9 pages × 16K ---
    for p in range(9):
        chunk = fb_bytes[p*PAGE_BYTES : (p+1)*PAGE_BYTES]
        if len(chunk) < PAGE_BYTES:
            chunk = chunk + b'\x80' * (PAGE_BYTES - len(chunk))
        page_name = f"level_{N:02d}_canvas_p{p}.bin"
        (DST_DIR / page_name).write_bytes(chunk)
        (lvl_dir / page_name).write_bytes(chunk)
    print(f"Saved 9 canvas pages")


if __name__ == '__main__':
    main()
