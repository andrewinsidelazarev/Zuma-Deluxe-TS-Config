from pathlib import Path

from PIL import Image


ROOT = Path(r"C:\z80\zuma")
SRC = Path(r"C:\Users\Администратор\Desktop\Zuma Deluxe\graphics\levels-ts-config\02\scaled_bg.png")
SCREEN_W = 360
SCREEN_H = 288
STRIDE = 512
COLORS = 128
CRAM_OFFSET = 128


def rgb8_to_cram(r, g, b):
    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3
    return ((g5 & 7) << 5) | b5, (1 << 7) | (r5 << 2) | (g5 >> 3)


def main():
    img = Image.open(SRC).convert("RGB")
    if img.size != (SCREEN_W, SCREEN_H):
        raise RuntimeError(f"expected {SCREEN_W}x{SCREEN_H}, got {img.size}")

    quantized = img.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT)
    pixels = quantized.tobytes()
    pal = quantized.getpalette()[: COLORS * 3]

    framebuffer = bytearray(SCREEN_H * STRIDE)
    for y in range(SCREEN_H):
        src_off = y * SCREEN_W
        dst_off = y * STRIDE
        framebuffer[dst_off : dst_off + SCREEN_W] = bytes(
            (v + CRAM_OFFSET) & 0xFF for v in pixels[src_off : src_off + SCREEN_W]
        )

    (ROOT / "level_02_canvas.bin").write_bytes(framebuffer)
    for page in range(9):
        start = page * 0x4000
        (ROOT / f"level_02_canvas_p{page}.bin").write_bytes(framebuffer[start : start + 0x4000])

    pal_bytes = bytearray(COLORS * 2)
    for i in range(COLORS):
        r, g, b = pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]
        b0, b1 = rgb8_to_cram(r, g, b)
        pal_bytes[i * 2] = b0
        pal_bytes[i * 2 + 1] = b1
    (ROOT / "level_02_canvas_pal.bin").write_bytes(pal_bytes)

    print(f"wrote level_02 canvas from {SRC}")
    print(f"  framebuffer: {len(framebuffer)} bytes")
    print(f"  palette: {len(pal_bytes)} bytes")


if __name__ == "__main__":
    main()
