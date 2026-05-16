#!/usr/bin/env python3
"""Click-to-define preview frame: 4 клика по углам рамки preview в scene.

Сцена 360×288 показывается с zoom 3x. Юзер делает 4 клика по углам frame.
После 4-го клика окно само закрывается и сохраняет:
  Desktop/Zuma Deluxe/src/preview_corners.txt:
    X1=<>
    Y1=<>
    X2=<>
    Y2=<>
  где (X1,Y1) = top-left, (X2,Y2) = bottom-right в координатах 360×288.

Запуск: py src/position_preview.py
"""
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

SCENE_PNG = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/level_select_scene_360x288.png")
OUT_TXT   = Path(r"C:/Users/Администратор/Desktop/Zuma Deluxe/src/preview_corners.txt")
SCALE = 3


def main():
    scene = Image.open(SCENE_PNG).convert('RGB')
    sw, sh = scene.size
    scene_z = scene.resize((sw*SCALE, sh*SCALE), Image.NEAREST)

    root = tk.Tk()
    root.title('Click 4 frame corners (any order)')
    canvas = tk.Canvas(root, width=sw*SCALE, height=sh*SCALE, highlightthickness=0)
    canvas.pack()
    scene_tk = ImageTk.PhotoImage(scene_z)
    canvas.create_image(0, 0, anchor='nw', image=scene_tk)

    points = []

    def on_click(e):
        cx = e.x // SCALE
        cy = e.y // SCALE
        points.append((cx, cy))
        # draw marker
        r = 5
        canvas.create_oval(e.x-r, e.y-r, e.x+r, e.y+r, outline='lime', width=2)
        canvas.create_text(e.x+8, e.y-8, text=f'{len(points)}: ({cx},{cy})', fill='lime', anchor='w')
        root.title(f'Click 4 frame corners — {len(points)}/4')
        if len(points) == 4:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)
            OUT_TXT.write_text(
                f'X1={x1}\nY1={y1}\nX2={x2}\nY2={y2}\nW={x2-x1+1}\nH={y2-y1+1}\n',
                encoding='utf-8',
            )
            print(f'Saved bbox X={x1}..{x2} ({x2-x1+1}w) Y={y1}..{y2} ({y2-y1+1}h) → {OUT_TXT}')
            root.after(500, root.destroy)

    canvas.bind('<Button-1>', on_click)
    root.mainloop()


if __name__ == '__main__':
    main()
