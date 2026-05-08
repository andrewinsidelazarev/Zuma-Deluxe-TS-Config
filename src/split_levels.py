"""
Splits zuma_levels_22.png (4480x1920) into individual level tiles.
Grid: 7 cols x 4 rows of 640x480 each.
First 3 rows = 21 levels, row 4 col 0 = level 22 (space), rest = credits text.

Output: Levels/level_src_NN.png (NN = 01..22 in source order).
"""
from PIL import Image
import os

SRC = r"C:\Users\Администратор\Desktop\Zuma Deluxe\zuma_levels_22.png"
DST = r"C:\Users\Администратор\Desktop\Zuma Deluxe\Levels"
os.makedirs(DST, exist_ok=True)

TILE_W = 640
TILE_H = 480

im = Image.open(SRC)
print(f"Source: {im.size}")

# Layout: rows 0..2 → cols 0..6 (21 tiles), row 3 → col 0 (1 tile)
positions = []
for r in range(3):
    for c in range(7):
        positions.append((r, c))
positions.append((3, 0))  # 22nd level (space)

assert len(positions) == 22, f"Got {len(positions)} positions"

for idx, (r, c) in enumerate(positions, start=1):
    box = (c * TILE_W, r * TILE_H, (c + 1) * TILE_W, (r + 1) * TILE_H)
    tile = im.crop(box)
    out_path = os.path.join(DST, f"level_src_{idx:02d}.png")
    tile.save(out_path)
    print(f"  level_src_{idx:02d}.png  from row={r} col={c}")

print(f"Done. {len(positions)} files in {DST}")
