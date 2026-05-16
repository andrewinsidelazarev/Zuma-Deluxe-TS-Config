#!/usr/bin/env python3
"""Pre-render sky bitmap (анимированный, scroll'ится) + pyramid overlay для
level-select экрана.

Источники:
  graphics/level_select_scene_360x288.png  — оригинальная сцена (без sky)
  graphics/level_select_sky_orig.png       — оранжевое sky-полотно (для scroll)
  c:/z80/zuma/scene_levelsel_canvas_pal.bin — целевая 128-цв палитра CRAM #80..

Выход:
  c:/z80/zuma/sky_atlas_p0..p3.bin       — 4×16K, 480×100 sky pixels, stride 512.
  c:/z80/zuma/pyramid_overlay_p0..p3.bin — 4×16K, 360×100 pyramid+cactus,
                                            0 в зонах неба (transparent), stride 512.

Каждый кадр Z80:
  1. DMA blit sky (NOTRANSP) → canvas top 100 lines, src offset = SkyScrollOffset.
  2. DMA blit pyramid_overlay (transparency) → canvas top 100 lines.
  3. Swap canvas.

Scroll: SkyScrollOffset инкрементируется на 1 каждые N кадров, ограничен 0..119
(= sky 480 - canvas 360 = 120 px max shift).
"""
import struct
from pathlib import Path

from PIL import Image
import numpy as np

SCENE_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288.png")
SCENE_ALPHA_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288_alpha.png")
SKY_PNG   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_sky_orig.png")
PAL_BIN   = Path(r"C:/z80/zuma/scene_levelsel_canvas_pal.bin")
DST_DIR   = Path(r"C:/z80/zuma")

SCREEN_W   = 360
SKY_BAND_H = 100
SKY_W      = 480
PAL_START  = 128
STRIDE     = 512
PAGE_BYTES = 16384


def cram_to_rgb(pal_bytes):
    """Decode 128 × 2-byte CRAM entries → (128, 3) RGB888 array."""
    out = np.zeros((128, 3), dtype=np.uint8)
    for i in range(128):
        b0, b1 = pal_bytes[i*2], pal_bytes[i*2+1]
        r5 = (b1 >> 2) & 0x1F
        g_hi = b1 & 0x03
        g_lo = (b0 >> 5) & 0x07
        g5 = (g_hi << 3) | g_lo
        b5 = b0 & 0x1F
        out[i] = [r5 << 3, g5 << 3, b5 << 3]
    return out


def nearest_palette(rgb_arr, palette):
    """rgb_arr shape (H,W,3) → indexed (H,W) using palette (N, 3) nearest match."""
    H, W, _ = rgb_arr.shape
    flat = rgb_arr.reshape(-1, 3).astype(np.int32)
    pal  = palette.astype(np.int32)
    # squared distance N×P
    diffs = flat[:, None, :] - pal[None, :, :]
    dists = (diffs**2).sum(axis=2)
    idx = dists.argmin(axis=1).astype(np.uint8)
    return idx.reshape(H, W)


def fs_dither(rgb_arr, palette):
    """Floyd-Steinberg dither rgb_arr (H,W,3 uint8) к фиксированной palette (N,3).
    Возвращает (H,W) uint8 индексы. Использовать для градиентов (sky)."""
    H, W, _ = rgb_arr.shape
    pal = palette.astype(np.int32)
    work = rgb_arr.astype(np.float32)
    out  = np.zeros((H, W), dtype=np.uint8)
    # Распределение ошибки по соседям (FS):
    #   x+1,y  : 7/16
    #   x-1,y+1: 3/16
    #   x,  y+1: 5/16
    #   x+1,y+1: 1/16
    for y in range(H):
        row = work[y]
        next_row = work[y+1] if y+1 < H else None
        for x in range(W):
            old = row[x]
            diffs = pal - old
            i = int(np.argmin((diffs * diffs).sum(axis=1)))
            new = pal[i].astype(np.float32)
            out[y, x] = i
            err = old - new
            if x + 1 < W:
                row[x+1]      += err * (7/16)
            if next_row is not None:
                if x > 0:
                    next_row[x-1] += err * (3/16)
                next_row[x]       += err * (5/16)
                if x + 1 < W:
                    next_row[x+1] += err * (1/16)
    return out


def main():
    palette_rgb = cram_to_rgb(PAL_BIN.read_bytes())                   # (128, 3)

    # --- Sky bitmap 480 × 100, indexed в scene palette ---
    # Crop только верхнюю часть source (там где облака), растянуть на всю высоту:
    # иначе нижняя половина монотонная и horizontal scroll визуально не виден.
    sky_full = Image.open(SKY_PNG).convert('RGB')
    sw, sh = sky_full.size
    # Skip top 4px and left 2px — там 1-2 px sprite-separator borders
    # (uniform dark RGB 53,15,15 на Y=2..3, на X=0..1).
    sky_top = sky_full.crop((2, 4, sw, sh // 2))                  # верхняя половина без border
    sky = sky_top.resize((SKY_W, SKY_BAND_H), Image.LANCZOS)
    sky_arr = np.array(sky)
    # Sky — гладкий градиент, делаем Floyd-Steinberg dither чтобы убрать ступеньки
    # на 128-цветной CRAM-палитре.
    sky_idx = fs_dither(sky_arr, palette_rgb) + PAL_START               # palette abs idx
    # Pad до stride 512 (за пределами 480 — нули, на канвас не попадут)
    sky_padded = np.zeros((SKY_BAND_H, STRIDE), dtype=np.uint8)
    sky_padded[:, :SKY_W] = sky_idx
    sky_bytes = sky_padded.tobytes()
    print(f'Sky bitmap: {SKY_W}×{SKY_BAND_H}, stride {STRIDE} → {len(sky_bytes)} bytes')

    # --- Pyramid overlay 360 × 100 ---
    # Opaque только в зонах pyramid + cactus (по бокам). Mountains в background
    # делаем transparent, чтобы scrolling sky был виден через них.
    scene = Image.open(SCENE_PNG).convert('RGB')
    scene_top = np.array(scene)[:SKY_BAND_H]
    pyramid_idx = nearest_palette(scene_top, palette_rgb) + PAL_START

    # Auto-derived mask: alpha канал из compose_levelsel_scene.py (sprite_00).
    # Opaque (alpha>128) — pyramid/cactus/idol/frame → рисуем в overlay.
    # Transparent (alpha<=128) — sky band → пропускаем (scrolling sky видно).
    if not SCENE_ALPHA_PNG.exists():
        raise SystemExit(f'missing alpha mask {SCENE_ALPHA_PNG} — запусти compose_levelsel_scene.py сначала')
    alpha_full = np.array(Image.open(SCENE_ALPHA_PNG).convert('L'))     # (288, 360)
    alpha_band = alpha_full[:SKY_BAND_H]
    keep_mask  = alpha_band > 128
    pyramid_idx[~keep_mask] = 0
    print(f'Overlay mask: {keep_mask.sum()} opaque px / {keep_mask.size} total ({100*keep_mask.sum()/keep_mask.size:.1f}%)')

    pyr_padded = np.zeros((SKY_BAND_H, STRIDE), dtype=np.uint8)
    pyr_padded[:, :SCREEN_W] = pyramid_idx
    pyr_bytes = pyr_padded.tobytes()
    print(f'Pyramid overlay: {SCREEN_W}×{SKY_BAND_H}, opaque zones [0..55, 100..260, 285..360]')

    # --- Split в 4 pages × 16K ---
    def split(bytes_, prefix):
        n_pages = (len(bytes_) + PAGE_BYTES - 1) // PAGE_BYTES
        for p in range(n_pages):
            chunk = bytes_[p*PAGE_BYTES : (p+1)*PAGE_BYTES]
            if len(chunk) < PAGE_BYTES:
                chunk = chunk + b'\x00' * (PAGE_BYTES - len(chunk))
            out = DST_DIR / f'{prefix}_p{p}.bin'
            out.write_bytes(chunk)
            print(f'  {out.name}: {len(chunk)} bytes')
        return n_pages

    n_sky = split(sky_bytes, 'sky_atlas')
    n_pyr = split(pyr_bytes, 'pyramid_overlay')

    # --- Previews ---
    sky_preview = palette_rgb[sky_idx - PAL_START]
    Image.fromarray(sky_preview.astype(np.uint8), 'RGB').save(
        r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_sky_atlas_preview.png")
    pyr_idx_rel = np.where(pyramid_idx == 0, 0, pyramid_idx - PAL_START)
    pyr_preview_arr = np.zeros((SKY_BAND_H, SCREEN_W, 4), dtype=np.uint8)
    pyr_preview_arr[..., :3] = palette_rgb[pyr_idx_rel]
    pyr_preview_arr[..., 3] = np.where(pyramid_idx == 0, 0, 255)
    Image.fromarray(pyr_preview_arr, 'RGBA').save(
        r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_pyramid_overlay_preview.png")
    print(f'\nPages: sky={n_sky}, pyramid={n_pyr}')


if __name__ == '__main__':
    main()
