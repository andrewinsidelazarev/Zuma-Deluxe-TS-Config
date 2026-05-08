"""
Масштабирование уровня под TS-Config screen с сохранением максимальной красоты.

Pipeline:
1. Открываем level_NN.png (640x480 RGB).
2. Lanczos resample → target размер (360x256 для play area под UI margin).
3. Quantize в 256 цветов (TS-Config CRAM).
4. Сохраняем preview RGB и quantized PNG.
5. (TODO) Конвертируем в формат tile-данных для canvas-слоя TS-Config.

Аргумент: номер уровня (например 01).
"""
import sys
import os
from PIL import Image

SRC_DIR = r"C:\Users\Администратор\Desktop\Zuma Deluxe\Levels"

# Target play area: 360x256 (resv 32 пикс сверху на UI: счёт, level info, preview).
# Полный экран 360x288, нижние 32 пикс могут быть для UI или скулы.
TARGET_W = 360
TARGET_H = 256

def scale_level(level_num):
    src_path = os.path.join(SRC_DIR, f"level_{level_num:02d}.png")
    if not os.path.exists(src_path):
        print(f"ERROR: {src_path} not found")
        return

    im = Image.open(src_path).convert("RGB")
    print(f"Source: {src_path}  size={im.size}")

    # Высокое качество resample
    scaled = im.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    out_scaled = os.path.join(SRC_DIR, f"level_{level_num:02d}_scaled_rgb.png")
    scaled.save(out_scaled)
    print(f"  Scaled RGB: {out_scaled}")

    # Quantize в 256 цветов через median-cut
    # method=2 (median cut) обычно даёт лучше визуальный результат для иллюстраций
    # dither=Image.Dither.FLOYDSTEINBERG (default) — плавный градиент
    quant = scaled.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    out_quant = os.path.join(SRC_DIR, f"level_{level_num:02d}_q256.png")
    quant.save(out_quant)
    print(f"  Quantized (256 colors, Floyd-Steinberg dither): {out_quant}")

    # Также вариант без dither (резче, ступеньками — может быть лучше для tile graphics)
    quant_nd = scaled.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out_quant_nd = os.path.join(SRC_DIR, f"level_{level_num:02d}_q256_nodither.png")
    quant_nd.save(out_quant_nd)
    print(f"  Quantized (256 colors, no dither): {out_quant_nd}")

    # Также вариант с octree quantization для сравнения
    quant_oct = scaled.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
    out_quant_oct = os.path.join(SRC_DIR, f"level_{level_num:02d}_q256_octree.png")
    quant_oct.save(out_quant_oct)
    print(f"  Quantized (256 colors, octree+dither): {out_quant_oct}")

    # Side-by-side для сравнения
    cmp = Image.new("RGB", (TARGET_W * 2, TARGET_H * 2 + 20), (40, 40, 40))
    cmp.paste(scaled, (0, 0))
    cmp.paste(quant.convert("RGB"), (TARGET_W, 0))
    cmp.paste(quant_nd.convert("RGB"), (0, TARGET_H + 20))
    cmp.paste(quant_oct.convert("RGB"), (TARGET_W, TARGET_H + 20))
    out_cmp = os.path.join(SRC_DIR, f"level_{level_num:02d}_compare.png")
    cmp.save(out_cmp)
    print(f"  Comparison: {out_cmp}")
    print(f"    [TL] LANCZOS RGB   [TR] q256 + FS-dither")
    print(f"    [BL] q256 no dither   [BR] q256 octree+dither")

if __name__ == "__main__":
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    scale_level(num)
