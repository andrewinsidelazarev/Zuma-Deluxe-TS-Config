#!/usr/bin/env python3
"""Re-cut level-select sprite sheets excluding black separator lines from output.

Sources (все 4 PNG этого экрана):
   graphics/level_select_orig.png             (1612×663)  — мастер: scene + buttons
   graphics/level_select_scene_orig.png       (644×663)   — только сцена-портал
   graphics/level_select_buttons_orig.png     (967×378)   — только лист кнопок
   graphics/level_select_buttons_scaled.png   (580×227)   — кнопки ×0.6

Outputs: graphics/levelsel_sprites/<source_stem>/sprite_<idx>_x<x>_y<y>_w<w>_h<h>.png
         + _overlay.png рядом

Separator pixel = transparent (alpha<64) OR dark-red border (R≤80, G≤30, B≤30).
Эти полосы — между спрайтами, в оригинальном rip'е — НЕ должны попадать в
выходные картинки.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

GFX = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics")
SHEETS = [
    GFX / "level_select_orig.png",
    GFX / "level_select_scene_orig.png",
    GFX / "level_select_buttons_orig.png",
    GFX / "level_select_buttons_scaled.png",
]
OUT_DIR = GFX / "levelsel_sprites"

ROW_SEP_THR    = 0.85   # ≥85% sep px в строке → row-separator
COL_SEP_STRONG = 0.85   # сильный col-separator
COL_SEP_MED    = 0.70   # средний col-separator (для тонких dark-red borders)
MIN_BAND_H     = 10
MIN_SPRITE_W   = 12
TRIM_EDGE_THR  = 0.85   # триммим строку/колонку только если она ≥85% sep
                        # (то же как порог row/col separator). Это срезает явные
                        # separator-полосы, но не трогает wood-design dark-red.


def runs(mask):
    """Return list of (start, end_exclusive) for runs of True."""
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


def segs(sep_runs, total, min_w):
    out = []
    prev = 0
    for s0, s1 in sep_runs:
        if s0 > prev and (s0 - prev) >= min_w:
            out.append((prev, s0))
        prev = s1
    if total > prev and (total - prev) >= min_w:
        out.append((prev, total))
    return out


def trim_box(is_sep, y0, y1, x0, x1):
    """Trim ОТКЛЮЧЕН — dark-red wood-borders НЕ убираются.
    Возвращаем bbox как есть (cut между separator-полосами, всё содержимое
    включая собственный wood-frame дизайна остаётся в выходной картинке).
    """
    return y0, y1, x0, x1


def cut_main(arr, is_sep):
    """Return list of (y0,y1,x0,x1) bbox'ов после двухуровневой нарезки."""
    H, W = is_sep.shape
    row_frac = is_sep.mean(axis=1)
    row_sep_runs = runs(row_frac >= ROW_SEP_THR)
    row_bands = segs(row_sep_runs, H, MIN_BAND_H)

    bboxes = []
    for y0, y1 in row_bands:
        band = is_sep[y0:y1]
        col_frac = band.mean(axis=0)
        strong = runs(col_frac >= COL_SEP_STRONG)
        primary = segs(strong, W, MIN_SPRITE_W)
        for px0, px1 in primary:
            # Доп. проход: внутри primary band ищем medium-strength
            # вертикальные separator'ы (тонкая dark-red линия 1-2px).
            sub_frac = col_frac[px0:px1]
            med = runs(sub_frac >= COL_SEP_MED)
            # min 1 px толщина для med-separator'а
            subs = segs(med, px1 - px0, MIN_SPRITE_W)
            if not subs:
                subs = [(0, px1 - px0)]
            for sx0, sx1 in subs:
                ax0 = px0 + sx0
                ax1 = px0 + sx1
                ty0, ty1, tx0, tx1 = trim_box(is_sep, y0, y1, ax0, ax1)
                if (ty1 - ty0) >= MIN_BAND_H and (tx1 - tx0) >= MIN_SPRITE_W:
                    bboxes.append((ty0, ty1, tx0, tx1))
    return bboxes


def process_sheet(sheet_path: Path):
    stem = sheet_path.stem
    out = OUT_DIR / stem
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()

    img = Image.open(sheet_path).convert("RGBA")
    arr = np.array(img)
    H, W, _ = arr.shape
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    is_sep = ((r <= 80) & (g <= 30) & (b <= 30) & (a > 64)) | (a < 64)
    print(f"\n=== {sheet_path.name} {W}x{H}  sep={is_sep.mean()*100:.1f}% ===")

    bboxes = cut_main(arr, is_sep)
    print(f"  Detected {len(bboxes)} sprites")

    pad = max(len(str(len(bboxes))), 2)
    for i, (y0, y1, x0, x1) in enumerate(bboxes):
        crop = img.crop((x0, y0, x1, y1))
        name = f"sprite_{i:0{pad}d}_x{x0}_y{y0}_w{x1-x0}_h{y1-y0}.png"
        crop.save(out / name)
    print(f"  Saved → {out}")

    overlay = img.copy().convert("RGBA")
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    for i, (y0, y1, x0, x1) in enumerate(bboxes):
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(0, 255, 0, 255), width=1)
        draw.text((x0 + 2, y0 + 1), str(i), fill=(0, 255, 0, 255), font=font)
    overlay.save(out / "_overlay.png")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # очищаем legacy-файлы в корне (от прошлой версии cutter'а)
    for old in OUT_DIR.glob("*.png"):
        old.unlink()
    for sh in SHEETS:
        if not sh.exists():
            print(f"SKIP {sh} (нет файла)")
            continue
        process_sheet(sh)


if __name__ == "__main__":
    main()
