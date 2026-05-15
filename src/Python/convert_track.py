"""
Convert track points (clicked by user) into dense ~1px polyline + binary.

Pipeline:
1. Load level_NN_track_pts.txt (user-clicked points).
2. Interpolate via Catmull-Rom spline (passes through all points).
3. Resample to ~1px arc-length spacing.
4. Save as level_NN.bin (DW X, DW Y, ..., DW #FFFF) — same format as track1.bin.
5. Render preview overlay on the level image.

Usage: python convert_track.py 01
"""
import sys
import os
import math
from PIL import Image, ImageDraw

SRC_DIR = r"C:\Users\Администратор\Desktop\Zuma Deluxe\Levels"
TARGET_W = 360
TARGET_H = 256

def load_points(level_num):
    path = os.path.join(SRC_DIR, f"level_{level_num:02d}_track_pts.txt")
    points = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            x, y = map(float, line.split())
            points.append((x, y))
    return points

def catmull_rom_segment(p0, p1, p2, p3, n_samples=20):
    """Catmull-Rom spline segment from p1 to p2, with p0/p3 as tangent guides."""
    pts = []
    for i in range(n_samples):
        t = i / n_samples
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (
            (2 * p1[0]) +
            (-p0[0] + p2[0]) * t +
            (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
            (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
        )
        y = 0.5 * (
            (2 * p1[1]) +
            (-p0[1] + p2[1]) * t +
            (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
            (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
        )
        pts.append((x, y))
    return pts

def catmull_rom_full(points, n_samples=40):
    """Build full Catmull-Rom curve through all points. Endpoint tangents = duplicate ends."""
    pts = []
    n = len(points)
    if n < 2:
        return points[:]
    # Pad endpoints by duplication for tangent calc
    padded = [points[0]] + list(points) + [points[-1]]
    for i in range(len(padded) - 3):
        seg = catmull_rom_segment(padded[i], padded[i+1], padded[i+2], padded[i+3], n_samples)
        pts.extend(seg)
    pts.append(points[-1])  # closing point
    return pts

def resample_arclength(pts, step=1.0):
    """Resample exactly `step` px apart via linear interpolation between dense pts.
    Каждая выходная точка ровно step пикселей от предыдущей."""
    if len(pts) < 2:
        return pts[:]
    out = [pts[0]]
    i = 1
    while i < len(pts):
        dx = pts[i][0] - out[-1][0]
        dy = pts[i][1] - out[-1][1]
        d = math.hypot(dx, dy)
        if d >= step:
            ratio = step / d
            x = out[-1][0] + dx * ratio
            y = out[-1][1] + dy * ratio
            out.append((x, y))
            # не инкрементим i — продолжим от новой out[-1]
        else:
            i += 1
    return out

def save_bin(pts, level_num):
    """Save as DW X, DW Y, ..., DW #FFFF (uint16 LE), same format as track1.bin."""
    out_path = os.path.join(SRC_DIR, f"level_{level_num:02d}.bin")
    with open(out_path, "wb") as f:
        for x, y in pts:
            xi = max(0, min(65534, int(round(x))))
            yi = max(0, min(65534, int(round(y))))
            f.write(xi.to_bytes(2, "little"))
            f.write(yi.to_bytes(2, "little"))
        f.write(b"\xFF\xFF")  # X==#FFFF marker
    return out_path

def render_preview(level_num, pts, original_pts):
    """Overlay smoothed curve + control points on level image."""
    src = os.path.join(SRC_DIR, f"level_{level_num:02d}_q256_nodither.png")
    if not os.path.exists(src):
        src = os.path.join(SRC_DIR, f"level_{level_num:02d}_scaled_rgb.png")
    im = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(im)
    # Smoothed curve = yellow line
    for i in range(1, len(pts)):
        draw.line([pts[i-1], pts[i]], fill=(255, 230, 80), width=1)
    # Control points = red dots
    for i, (x, y) in enumerate(original_pts):
        r = 3 if 0 < i < len(original_pts) - 1 else 5
        col = (0, 255, 0) if i == 0 else (255, 60, 60) if i == len(original_pts) - 1 else (200, 100, 100)
        draw.ellipse([x-r, y-r, x+r, y+r], fill=col)
    out = os.path.join(SRC_DIR, f"level_{level_num:02d}_curve_preview.png")
    im.save(out)
    return out

def main(level_num):
    raw_pts = load_points(level_num)
    print(f"Loaded {len(raw_pts)} clicked points")
    if len(raw_pts) < 2:
        print("Need at least 2 points")
        return
    # Catmull-Rom через все точки
    smooth = catmull_rom_full(raw_pts, n_samples=40)
    print(f"  Catmull-Rom dense: {len(smooth)} points")
    # Resample на ~1 px arc-length
    final = resample_arclength(smooth, step=1.0)
    print(f"  Resampled @1px: {len(final)} points")
    # Save bin
    bin_path = save_bin(final, level_num)
    print(f"  Saved: {bin_path} ({len(final)*4 + 2} bytes)")
    # Preview
    prev = render_preview(level_num, final, raw_pts)
    print(f"  Preview: {prev}")

if __name__ == "__main__":
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    main(num)
