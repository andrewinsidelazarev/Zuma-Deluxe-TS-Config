#!/usr/bin/env python3
"""Импорт scene выбора уровня (портал с пирамидами) в TS-Conf canvas format.

Вход:   Desktop/Zuma Deluxe/graphics/level_select_scene_360x288.png  (360×288 RGB)
Выход:  c:/z80/zuma/
          scene_levelsel_canvas_p0..p8.bin   (9 × 16K = framebuffer 360×288 stride 512)
          scene_levelsel_canvas_pal.bin      (128 × 2 байт = CRAM colours)

Алгоритм:  то же что в import_real_level1.py начиная с шага quantize —
   - 128 цветов medium cut
   - индексы += 128 (= вторая половина CRAM, чтобы не мешать палитре спрайтов)
   - padding столбцов >= 360 заполняем CRAM-цветом #80
   - 9 страниц 16KB подряд
"""
import struct
from pathlib import Path

from PIL import Image
import numpy as np

SRC_PNG     = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288.png")
ALPHA_PNG   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288_alpha.png")
DST_DIR     = Path(r"C:/z80/zuma")
SCREEN_W    = 360
SCREEN_H    = 288
LINE_STRIDE = 512
PAGE_BYTES  = 16384
PAL_START   = 128                       # индексы 128..255 (вторая половина CRAM)


SKY_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_sky_orig.png")
SKY_BAND_H = 100                         # высота скроллящегося sky-band (Y=0..99)
# Chern frame (rectangle preview уровня) — оставляем нетронутым.
CHERN_X, CHERN_Y = 102, 153
CHERN_W, CHERN_H = 166, 101


def main():
    img = Image.open(SRC_PNG).convert('RGB')
    if img.size != (SCREEN_W, SCREEN_H):
        raise SystemExit(f'expected {SCREEN_W}×{SCREEN_H}, got {img.size}')

    # --- Composite образ для квантизации: alpha-zones в Y=0..SKY_BAND_H
    # подменяем на sky-pixels, и дополнительно конкатим полный sky-band снизу.
    # Это даёт median-cut'у образец как scene-цветов, так и sky-градиента
    # → итоговая 128-цв palette содержит плавный gradient, и Floyd-Steinberg
    # dither в sky рендере получает достаточно оттенков для плавных переходов. ---
    sky_for_quant = None
    if SKY_PNG.exists() and ALPHA_PNG.exists():
        sky = Image.open(SKY_PNG).convert('RGB').resize((SCREEN_W, SKY_BAND_H), Image.LANCZOS)
        alpha = np.array(Image.open(ALPHA_PNG).convert('L'))           # (288, 360)
        arr_scene = np.array(img)
        arr_sky   = np.array(sky)
        sky_mask = alpha[:SKY_BAND_H] < 128                            # transparent в sprite_00
        arr_scene[:SKY_BAND_H][sky_mask] = arr_sky[sky_mask]
        img = Image.fromarray(arr_scene, 'RGB')
        sky_for_quant = arr_sky                                        # полный sky 360×100

    # Композит для построения палитры: scene + (опц.) sky-strip снизу.
    if sky_for_quant is not None:
        composite = np.vstack([np.array(img), sky_for_quant])          # (388, 360, 3)
        quant_img = Image.fromarray(composite, 'RGB')
    else:
        quant_img = img

    # --- Quantize 128 colors + Floyd-Steinberg dithering ---
    palette_img = quant_img.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    sub         = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)
    pixels_q    = np.array(sub, dtype=np.uint8)
    pal_flat    = palette_img.getpalette()[:128*3]
    pal_rgb     = np.array(pal_flat, dtype=np.uint8).reshape(128, 3)

    # --- Framebuffer ---
    fb = np.full((SCREEN_H, LINE_STRIDE), PAL_START, dtype=np.uint8)
    fb[:, :SCREEN_W] = pixels_q + PAL_START
    fb_bytes = fb.tobytes()
    print(f'Framebuffer: {len(fb_bytes)} bytes')

    # --- CRAM palette (128 × 2 байт): same формат что у уровней ---
    pal_bytes = bytearray(128 * 2)
    for i in range(128):
        r, g, b = pal_rgb[i]
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        pal_bytes[i*2]   = b0
        pal_bytes[i*2+1] = b1
    (DST_DIR / 'scene_levelsel_canvas_pal.bin').write_bytes(bytes(pal_bytes))
    print('Saved scene_levelsel_canvas_pal.bin (256 bytes)')

    # --- 9 pages × 16K ---
    for p in range(9):
        chunk = fb_bytes[p*PAGE_BYTES : (p+1)*PAGE_BYTES]
        if len(chunk) < PAGE_BYTES:
            chunk = chunk + bytes([PAL_START]) * (PAGE_BYTES - len(chunk))
        (DST_DIR / f'scene_levelsel_canvas_p{p}.bin').write_bytes(chunk)
        print(f'  scene_levelsel_canvas_p{p}.bin: {len(chunk)} bytes')

    # --- preview (визуальный референс) ---
    preview_q = pal_rgb[pixels_q]
    out_preview = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_scene_levelsel_quantized.png")
    Image.fromarray(preview_q, 'RGB').save(out_preview)
    print(f'Preview saved: {out_preview}')

    print('Done.')


if __name__ == '__main__':
    main()
