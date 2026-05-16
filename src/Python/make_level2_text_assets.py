from pathlib import Path

from PIL import Image


ROOT = Path(r"C:\z80\zuma")
FONT_PNG = ROOT / "_fonts" / "nativealien48.png"
FONT_TXT = ROOT / "_fonts" / "nativealien48.txt"

PAGE = 16384
CARPET_ROW_BYTES = 2048
CELL_BYTES_PER_LINE = 4


def load_font():
    lines = FONT_TXT.read_text().splitlines()
    count = int(lines[0].split()[1])
    chars = lines[1 : 1 + count]
    rect_start = next(i + 1 for i, line in enumerate(lines) if line.startswith("RectList"))
    rects = []
    for line in lines[rect_start : rect_start + count]:
        x, _y, w, _h = map(int, line.split()[:4])
        rects.append((x, w))
    return Image.open(FONT_PNG).convert("RGBA"), dict(zip(chars, rects))


FONT_IMG, CHAR_RECTS = load_font()
FONT_H = FONT_IMG.size[1]


def render_text(text, width, height):
    scale = height / FONT_H
    space_px = int(20 * scale)
    spacing = 1
    pieces = []
    total_w = 0
    for ch in text:
        if ch == " ":
            pieces.append((space_px, None))
            total_w += space_px
            continue
        if ch not in CHAR_RECTS:
            continue
        src_x, src_w = CHAR_RECTS[ch]
        crop = FONT_IMG.crop((src_x, 0, src_x + src_w, FONT_H))
        out_w = max(1, int(src_w * scale))
        crop = crop.resize((out_w, height), Image.Resampling.LANCZOS)
        pieces.append((out_w, crop))
        total_w += out_w
    if pieces:
        total_w += spacing * (len(pieces) - 1)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = max(0, (width - total_w) // 2)
    for w, piece in pieces:
        if piece is not None and x + w <= width:
            img.alpha_composite(piece, (x, 0))
        x += w + spacing
    return img


def gradient_palette():
    pal = [(0, 0, 0)]
    for i in range(1, 16):
        t = (i - 1) / 14.0
        pal.append((255 - int(50 * (1 - t)), int(255 * t * t), int(20 * (1 - t))))
    return pal


GRADIENT = gradient_palette()


def classify(r, g, b, a):
    if a < 64:
        return 0
    best_i = 1
    best_d = 1 << 60
    for i, (pr, pg, pb) in enumerate(GRADIENT[1:], 1):
        d = (r - pr) * (r - pr) + (g - pg) * (g - pg) + (b - pb) * (b - pb)
        if d < best_d:
            best_i = i
            best_d = d
    return best_i


def write_cell_pixel(buf, cy, cx, py, px, idx):
    addr = cy * CARPET_ROW_BYTES + py * 256 + cx * CELL_BYTES_PER_LINE + px // 2
    if px & 1:
        buf[addr] = (buf[addr] & 0xF0) | (idx & 0x0F)
    else:
        buf[addr] = (buf[addr] & 0x0F) | ((idx & 0x0F) << 4)


def encode_image(buf, img, dst_cx, dst_cy):
    pxs = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pxs[x, y]
            write_cell_pixel(buf, dst_cy + y // 8, dst_cx + x // 8, y % 8, x % 8, classify(r, g, b, a))


def make_intro():
    gfx = bytearray(PAGE)
    level = render_text("LEVEL 1-2", 320, 64)
    subtitle = render_text("MUD SLIDE", 320, 32)
    for i in range(5):
        encode_image(gfx, level.crop((i * 64, 0, i * 64 + 64, 64)), i * 8, 0)
    for i, (cx, cy) in enumerate([(40, 0), (48, 0), (56, 0), (40, 4), (48, 4)]):
        encode_image(gfx, subtitle.crop((i * 64, 0, i * 64 + 64, 32)), cx, cy)
    (ROOT / "level_02_intro_text_atlas.bin").write_bytes(gfx)


def make_menu_dispname():
    # Current menu descriptors use page #0C, TNUM 3352 = cy 4, cx 24, 11 sprites 16x24.
    page = bytearray((ROOT / "level_02_preview_p0.bin").read_bytes())
    img = render_text("MUD SLIDE", 176, 24)
    encode_image(page, img, 24, 4)
    (ROOT / "level_02_preview_p0.bin").write_bytes(page)


def main():
    make_intro()
    make_menu_dispname()
    print("wrote level_02_intro_text_atlas.bin and level_02 menu dispname tiles")


if __name__ == "__main__":
    main()
