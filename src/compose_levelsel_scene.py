#!/usr/bin/env python3
"""Compose level-select scene 360×288 — ОСНОВНОЙ ФОН (без кнопок):

Aspect-fit как у уровней (import_real_level1.py):
  source 640×472 → 1.356:1
  target 360×288 → 1.25:1   (5:4)
  → crop горизонтально до 590×472 (= 472*1.25), 25 px с каждой стороны
  → uniform resize до 360×288 (scale 0.610)

Кнопки PLAY/BACK НЕ запекаем — потом отдельным слоем (DMA / TSU).
Sky/pyramid_overlay добавляются Z80'ом каждый кадр (make_animated_sky.py).

Потом запустить import_scene_levelselect.py чтобы переcгенерить canvas pages.
"""
from pathlib import Path
from PIL import Image
import numpy as np

GFX = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics")
SCENE_SRC = GFX / "level_select_scene_orig.png"
OUT = GFX / "level_select_scene_360x288.png"
OUT_ALPHA = GFX / "level_select_scene_360x288_alpha.png"

TARGET_W, TARGET_H = 360, 288

# scene_orig.png — sprite_00 = X=2..642, Y=10..482  (640×472).
SRC_X0, SRC_Y0 = 2, 10
SRC_X1, SRC_Y1 = 642, 482
SRC_W = SRC_X1 - SRC_X0          # 640
SRC_H = SRC_Y1 - SRC_Y0          # 472

# Crop horiz: width = height * (TARGET_W / TARGET_H) = 472 * 1.25 = 590
CROP_W = SRC_H * TARGET_W // TARGET_H        # 590
CROP_X = (SRC_W - CROP_W) // 2               # 25 px с каждой стороны


def main():
    if not SCENE_SRC.exists():
        raise SystemExit(f"missing {SCENE_SRC}")

    scene_full = Image.open(SCENE_SRC).convert("RGBA")
    # Сначала вырезаем рабочую зону sprite_00 (X=2..642, Y=10..482).
    scene_crop = scene_full.crop((SRC_X0, SRC_Y0, SRC_X1, SRC_Y1))     # 640×472
    # Затем aspect-crop по бокам до 590×472.
    scene_ac = scene_crop.crop((CROP_X, 0, CROP_X + CROP_W, SRC_H))    # 590×472
    # Uniform-resize 590×472 → 360×288.
    scene_resized = scene_ac.resize((TARGET_W, TARGET_H), Image.LANCZOS)

    # Сохраняем alpha-канал ОТДЕЛЬНО (255 = opaque = pyramid/cactus/idol/frame,
    # 0 = transparent = sky band sky/mountains). Используется make_animated_sky.py
    # как auto-derived keep_mask для pyramid_overlay (без hardcoded coords).
    arr = np.array(scene_resized)
    alpha = arr[..., 3].copy()
    Image.fromarray(alpha, "L").save(OUT_ALPHA)
    print(f"Saved {OUT_ALPHA}  (alpha mask {alpha.shape[1]}×{alpha.shape[0]})")

    # Заливаем прозрачные пиксели нижним цветом (для quantize-friendly).
    bottom_color = tuple(int(c) for c in arr[-1, TARGET_W // 2, :3])
    transp = arr[..., 3] < 64
    arr[transp, :3] = bottom_color
    arr[..., 3] = 255
    canvas = Image.fromarray(arr, "RGBA").convert("RGB")

    canvas.save(OUT)
    print(f"Saved {OUT}  ({canvas.size}), crop {CROP_W}×{SRC_H} → {TARGET_W}×{TARGET_H}")


if __name__ == "__main__":
    main()
