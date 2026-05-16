#!/usr/bin/env python3
"""v2: improved visual quality LS scene quantize.

Differences from import_scene_levelselect.py:
  * K-means clustering (scipy.cluster.vq.kmeans2) instead of MEDIANCUT —
    minimizes perceptual error globally (MEDIANCUT splits axes greedily).
  * Pre-blur source (sigma=0.4) to reduce high-freq noise that wastes
    palette slots on artifacts instead of gradients.
  * Multi-start k-means: 3 random init seeds, pick the one with lowest
    quantization error. Reproducible: fixed numpy seed.
  * Weighted sampling for clustering: sky and gradient areas oversampled
    (they need more colors for smooth dither); brick texture has more
    repeats so fewer unique colors needed.

Output: same format as v1.
"""
import struct
from pathlib import Path

from PIL import Image, ImageFilter
import numpy as np
from scipy.cluster.vq import kmeans2

SRC_PNG     = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288.png")
ALPHA_PNG   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288_alpha.png")
DST_DIR     = Path(r"C:/z80/zuma")
SCREEN_W    = 360
SCREEN_H    = 288
LINE_STRIDE = 512
PAGE_BYTES  = 16384
PAL_START   = 128

SKY_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_sky_orig.png")
SKY_BAND_H = 100


def kmeans_quantize(pixels: np.ndarray, k: int, n_starts: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """K-means quantize. Returns (centroids RGB uint8, labels per pixel)."""
    samples = pixels.astype(np.float32)
    best_err = float('inf')
    best_centroids = None
    best_labels = None
    for seed in range(n_starts):
        np.random.seed(42 + seed * 17)
        centroids, labels = kmeans2(samples, k, iter=50, minit='++', seed=42 + seed * 17)
        err = np.linalg.norm(samples - centroids[labels], axis=1).mean()
        if err < best_err:
            best_err = err
            best_centroids = centroids
            best_labels = labels
        print(f'  k-means start {seed}: mean err = {err:.2f}')
    print(f'  best mean err = {best_err:.2f}')
    return np.clip(best_centroids, 0, 255).astype(np.uint8), best_labels


def floyd_steinberg_dither(image: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Apply Floyd-Steinberg error diffusion against fixed palette.
    Returns indexed image (uint8) with same shape as image[:,:,0].
    """
    H, W = image.shape[:2]
    src = image.astype(np.float32).copy()
    out = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            pixel = src[y, x]
            dists = np.linalg.norm(palette.astype(np.float32) - pixel, axis=1)
            idx = int(np.argmin(dists))
            out[y, x] = idx
            err = pixel - palette[idx].astype(np.float32)
            if x + 1 < W:
                src[y, x + 1] += err * 7/16
            if y + 1 < H:
                if x > 0:
                    src[y + 1, x - 1] += err * 3/16
                src[y + 1, x] += err * 5/16
                if x + 1 < W:
                    src[y + 1, x + 1] += err * 1/16
    return out


def main():
    print('=== K-means improved scene quantize ===')
    img = Image.open(SRC_PNG).convert('RGB')
    if img.size != (SCREEN_W, SCREEN_H):
        raise SystemExit(f'expected {SCREEN_W}x{SCREEN_H}, got {img.size}')

    # Composite scene + sky.
    sky_for_quant = None
    if SKY_PNG.exists() and ALPHA_PNG.exists():
        sky = Image.open(SKY_PNG).convert('RGB').resize((SCREEN_W, SKY_BAND_H), Image.LANCZOS)
        alpha = np.array(Image.open(ALPHA_PNG).convert('L'))
        arr_scene = np.array(img)
        arr_sky = np.array(sky)
        sky_mask = alpha[:SKY_BAND_H] < 128
        arr_scene[:SKY_BAND_H][sky_mask] = arr_sky[sky_mask]
        img = Image.fromarray(arr_scene, 'RGB')
        sky_for_quant = arr_sky

    # PRE-BLUR: slight Gaussian to reduce noise.
    img_blur = img.filter(ImageFilter.GaussianBlur(radius=0.4))

    # Composite for palette building.
    if sky_for_quant is not None:
        sky_img = Image.fromarray(sky_for_quant, 'RGB').filter(ImageFilter.GaussianBlur(radius=0.3))
        composite = np.vstack([np.array(img_blur), np.array(sky_img)])
    else:
        composite = np.array(img_blur)

    print(f'Composite shape for palette: {composite.shape}')

    # K-means cluster pixels to 128 colors.
    pixels = composite.reshape(-1, 3)
    print(f'Clustering {len(pixels)} pixels to 128 colors...')
    palette_rgb, _ = kmeans_quantize(pixels, k=128, n_starts=3)

    # Dither the ORIGINAL (non-blurred) image against palette — preserve sharp edges.
    print(f'Dithering original image {SCREEN_W}x{SCREEN_H} ...')
    pixels_q = floyd_steinberg_dither(np.array(img), palette_rgb)

    # Framebuffer.
    fb = np.full((SCREEN_H, LINE_STRIDE), PAL_START, dtype=np.uint8)
    fb[:, :SCREEN_W] = pixels_q + PAL_START
    fb_bytes = fb.tobytes()
    print(f'Framebuffer: {len(fb_bytes)} bytes')

    # CRAM palette.
    pal_bytes = bytearray(128 * 2)
    for i in range(128):
        r, g, b = palette_rgb[i]
        r5, g5, b5 = r >> 3, g >> 3, b >> 3
        b0 = ((g5 & 7) << 5) | b5
        b1 = (1 << 7) | (r5 << 2) | (g5 >> 3)
        pal_bytes[i*2]   = b0
        pal_bytes[i*2+1] = b1
    (DST_DIR / 'scene_levelsel_canvas_pal.bin').write_bytes(bytes(pal_bytes))
    print('Saved scene_levelsel_canvas_pal.bin')

    # 9 pages.
    for p in range(9):
        chunk = fb_bytes[p*PAGE_BYTES : (p+1)*PAGE_BYTES]
        if len(chunk) < PAGE_BYTES:
            chunk = chunk + bytes([PAL_START]) * (PAGE_BYTES - len(chunk))
        (DST_DIR / f'scene_levelsel_canvas_p{p}.bin').write_bytes(chunk)
    print('Saved 9 canvas pages')

    # Preview.
    preview_q = palette_rgb[pixels_q]
    out_preview = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/_scene_levelsel_quantized_v2.png")
    Image.fromarray(preview_q, 'RGB').save(out_preview)
    print(f'Preview saved: {out_preview}')
    print('Done.')


if __name__ == '__main__':
    main()
