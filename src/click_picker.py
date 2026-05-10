#!/usr/bin/env python3
"""Open level bg in tkinter, on click — write coords to _click_coords.txt."""
import tkinter as tk
from PIL import Image, ImageTk

BG_PATH = r"C:/Users/Администратор/Desktop/Zuma Deluxe/graphics/levels-ts-config/01/scaled_bg.png"
OUT = r"C:/z80/zuma/_click_coords.txt"
SCALE = 3   # zoom для удобства

img = Image.open(BG_PATH)
W, H = img.size
img_zoom = img.resize((W * SCALE, H * SCALE), Image.NEAREST)

root = tk.Tk()
root.title(f'Click frog center — {W}x{H} (zoom {SCALE}x)')
photo = ImageTk.PhotoImage(img_zoom)
canvas = tk.Canvas(root, width=W * SCALE, height=H * SCALE)
canvas.pack()
canvas.create_image(0, 0, anchor='nw', image=photo)

# Show grid lines every 32 px (= cell size)
for x in range(0, W, 32):
    canvas.create_line(x * SCALE, 0, x * SCALE, H * SCALE, fill='#404040', dash=(2, 4))
for y in range(0, H, 32):
    canvas.create_line(0, y * SCALE, W * SCALE, y * SCALE, fill='#404040', dash=(2, 4))

label = tk.Label(root, text='Click anywhere — coords write to _click_coords.txt', bg='#222', fg='white')
label.pack(fill='x')

def on_click(event):
    gx = event.x // SCALE
    gy = event.y // SCALE
    msg = f'click: ({gx}, {gy})'
    label.config(text=msg)
    with open(OUT, 'w') as f:
        f.write(f'{gx} {gy}\n')
    canvas.create_oval(event.x-5, event.y-5, event.x+5, event.y+5, outline='red', width=2)
    print(msg)

canvas.bind('<Button-1>', on_click)
root.mainloop()
