"""
Интерактивная трассировка трека уровня.

Использование:
  python trace_track.py 01

Управление:
  ЛКМ          — добавить точку на трек (в порядке старт → финиш)
  ПКМ / Backspace — отменить последнюю точку
  S            — сохранить и выйти
  ESC / Q      — выйти без сохранения
  R            — переключить отображение (трек / прозрачно)

Выход:
  Levels/level_NN_track_pts.txt — список (x, y) в screen-координатах (360x256)
  Levels/level_NN_trace_preview.png — препросмотр

Дальше: convert_track.py возьмёт эти точки, построит сглаженный
полилинию через Bezier-сегменты с шагом ~1px (как track1.bin) и
сохранит финальный level_NN.bin.
"""
import sys
import os
import json
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.lines import Line2D

SRC_DIR = r"C:\Users\Администратор\Desktop\Zuma Deluxe\Levels"

def trace(level_num):
    src_path = os.path.join(SRC_DIR, f"level_{level_num:02d}_q256_nodither.png")
    if not os.path.exists(src_path):
        # fallback на scaled_rgb
        src_path = os.path.join(SRC_DIR, f"level_{level_num:02d}_scaled_rgb.png")
    if not os.path.exists(src_path):
        print(f"ERROR: scaled image not found, run scale_level.py {level_num} first")
        return

    img = mpimg.imread(src_path)
    h, w = img.shape[:2]
    print(f"Loaded: {src_path}  size={w}x{h}")

    points = []
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(img, interpolation="nearest")
    ax.set_title(f"Level {level_num:02d} — click track points start->end. S=save, ESC=quit, R=redraw")
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)

    line, = ax.plot([], [], "y-", linewidth=2, alpha=0.8)
    scatter = ax.scatter([], [], c="yellow", s=40, edgecolors="red", zorder=5)

    info_text = ax.text(5, 15, "Points: 0", color="white",
                        fontsize=11, bbox=dict(facecolor="black", alpha=0.7))

    def redraw():
        if points:
            xs, ys = zip(*points)
            line.set_data(xs, ys)
            scatter.set_offsets(points)
            # First point — green, last — red
            colors = ["lime"] + ["yellow"] * (len(points) - 2) + ["red"] if len(points) > 1 else ["lime"]
            scatter.set_color(colors)
        else:
            line.set_data([], [])
            scatter.set_offsets([[0, 0]])
            scatter.set_offsets([])
        info_text.set_text(f"Points: {len(points)}")
        fig.canvas.draw_idle()

    def autosave():
        # Инкрементальное сохранение после каждого изменения
        if not points:
            return
        out_pts = os.path.join(SRC_DIR, f"level_{level_num:02d}_track_pts.txt")
        with open(out_pts, "w") as f:
            f.write("# Track points for level {:02d}, screen-coords (360x256)\n".format(level_num))
            f.write("# Order: start -> end (chain head goes toward end)\n")
            for x, y in points:
                f.write(f"{x:.1f} {y:.1f}\n")

    def on_click(event):
        if event.inaxes != ax:
            return
        x, y = event.xdata, event.ydata
        if event.button == 1:  # left
            points.append((round(x, 1), round(y, 1)))
            print(f"  +({x:.1f}, {y:.1f})  [#{len(points)}]")
        elif event.button == 3:  # right (undo)
            if points:
                p = points.pop()
                print(f"  -{p}  [#{len(points)}]")
        autosave()
        redraw()

    def on_key(event):
        if event.key == "escape" or event.key == "q":
            print("Quit without saving")
            plt.close(fig)
        elif event.key == "s":
            save_and_exit()
        elif event.key == "backspace":
            if points:
                p = points.pop()
                print(f"  -{p}  [#{len(points)}]")
                redraw()
        elif event.key == "r":
            redraw()

    def save_and_exit():
        if len(points) < 2:
            print("Need at least 2 points")
            return
        out_pts = os.path.join(SRC_DIR, f"level_{level_num:02d}_track_pts.txt")
        with open(out_pts, "w") as f:
            f.write("# Track points for level {:02d}, screen-coords (360x256)\n".format(level_num))
            f.write("# Order: start -> end (chain head goes toward end)\n")
            for x, y in points:
                f.write(f"{x:.1f} {y:.1f}\n")
        print(f"Saved {len(points)} points to {out_pts}")

        # Preview PNG
        out_png = os.path.join(SRC_DIR, f"level_{level_num:02d}_trace_preview.png")
        fig.savefig(out_png, dpi=100, bbox_inches="tight")
        print(f"Preview: {out_png}")

        plt.close(fig)

    def on_close(event):
        # Автосохранение при закрытии окна (X), если точек хватает
        if len(points) >= 2:
            print("\nWindow closed — auto-saving...")
            save_and_exit()

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("close_event", on_close)
    print("\nControls: LMB=add point, RMB=undo, S=save, ESC=quit\n")
    plt.show()

if __name__ == "__main__":
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    trace(num)
