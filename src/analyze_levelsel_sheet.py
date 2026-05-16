#!/usr/bin/env python3
"""Анализ структуры с разделением по band'ам.

Шаг 1: находим горизонтальные separator-полосы (rows).
Шаг 2: для каждой band'ы находим вертикальные separator-полосы (cols).
Шаг 3: выводим итоговую сетку sprite-rect'ов.

Separator = пиксель ≈ dark-red border (53,15,15) ИЛИ alpha<64.
"""
from pathlib import Path
import numpy as np
from PIL import Image

SHEET = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_buttons_orig.png")

ROW_SEP_THR = 0.85   # ≥85% sep px в строке
COL_SEP_THR = 0.85
MIN_SEG_W   = 6      # игнорируем очень тонкие band'ы (< 6 px)


def runs(mask):
    out = []
    n = len(mask)
    i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def segs(seps, total, min_w=1):
    out = []
    prev = 0
    for s0, s1 in seps:
        if s0 > prev and (s0 - prev) >= min_w:
            out.append((prev, s0))
        prev = s1
    if total > prev and (total - prev) >= min_w:
        out.append((prev, total))
    return out


def main():
    img = Image.open(SHEET).convert("RGBA")
    arr = np.array(img)
    H, W, _ = arr.shape
    print(f"Sheet: {W}x{H}")

    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    is_sep = ((r <= 80) & (g <= 30) & (b <= 30) & (a > 64)) | (a < 64)

    row_frac = is_sep.mean(axis=1)
    row_sep_runs = runs(row_frac >= ROW_SEP_THR)
    row_bands = segs(row_sep_runs, H, MIN_SEG_W)

    print(f"\n=== Row bands ({len(row_bands)}) ===")
    for bi, (y0, y1) in enumerate(row_bands):
        bh = y1 - y0
        band = is_sep[y0:y1]  # bool (bh, W)
        col_frac = band.mean(axis=0)
        col_sep_runs = runs(col_frac >= COL_SEP_THR)
        col_bands = segs(col_sep_runs, W, MIN_SEG_W)
        print(f"\n[band {bi}]  Y={y0:3d}..{y1-1:3d}  h={bh}  sprites={len(col_bands)}")
        for ci, (x0, x1) in enumerate(col_bands):
            print(f"    sprite #{ci:2d}  X={x0:4d}..{x1-1:4d}  W={x1-x0}")


if __name__ == "__main__":
    main()
