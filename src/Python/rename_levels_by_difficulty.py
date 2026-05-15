"""
Переименовывает level_src_NN.png в level_NN.png по возрастанию сложности.

Оценка сложности (визуальная):
Tier 1 (очень просто, одна простая кривая):
  02 → S-curve (frog слева)            #1
  11 → U-shape                         #2
  06 → одинарное кольцо                #3
  03 → петля + поворот                 #4

Tier 2 (средне, единственная кривая с витками):
  01 → малая спираль (frog в центре)   #5
  04 → концентрические овалы           #6
  07 → лунная дуга (космос)            #7
  08 → средняя спираль                 #8

Tier 3 (сложнее, много витков):
  09 → змейка                          #9
  10 → петля + frog в центре           #10
  14 → длинный меандр                  #11
  13 → пещера с препятствиями          #12

Tier 4 (хард, комплексные пути):
  16 → вложенные скруглённые квадраты  #13
  17 → прямоугольник с витками         #14
  15 → треугольник с витками           #15
  19 → длинный прямоугольный           #16
  20 → стадион (Hong Kong)             #17
  18 → лабиринт-город                  #18

Special (откладываются для отдельной обработки):
  05 → 2 frogs (простой)               #19
  12 → 2 frogs (меандр)                #20
  21 → скрытые участки                 #21
  22 → космос (без трека)              #22
"""
import os
import shutil

DST = r"C:\Users\Администратор\Desktop\Zuma Deluxe\Levels"

# (source index, comment) — порядок = возрастание сложности
ranking = [
    ( 2, "S-curve"),
    (11, "U-shape"),
    ( 6, "single ring"),
    ( 3, "loop+turn"),
    ( 1, "small spiral"),
    ( 4, "concentric ovals"),
    ( 7, "moon arc / space theme"),
    ( 8, "medium spiral"),
    ( 9, "snake winding"),
    (10, "loop + center frog"),
    (14, "long meander"),
    (13, "cave with obstacles"),
    (16, "nested rounded squares"),
    (17, "rectangle winds"),
    (15, "triangle spiral"),
    (19, "long rectangular"),
    (20, "stadium (Hong Kong)"),
    (18, "city maze"),
    ( 5, "TWO FROGS (simple)"),       # special
    (12, "TWO FROGS (meander)"),      # special
    (21, "HIDDEN segments"),          # special
    (22, "SPACE (no track)"),         # special
]

assert len(ranking) == 22, f"Got {len(ranking)} entries"

# Сохраняем mapping для документации
mapping_path = os.path.join(DST, "_difficulty_mapping.txt")
with open(mapping_path, "w", encoding="utf-8") as f:
    f.write("# Mapping: difficulty rank → original source index\n")
    f.write("# Source = level_src_NN.png (исходный порядок в zuma_levels_22.png)\n")
    f.write("# Final  = level_NN.png (по возрастанию сложности)\n\n")
    for new_idx, (src_idx, comment) in enumerate(ranking, start=1):
        f.write(f"level_{new_idx:02d}.png  <-  level_src_{src_idx:02d}.png   # {comment}\n")

# Renaming via copy (safer than rename — keeps source files for audit)
for new_idx, (src_idx, comment) in enumerate(ranking, start=1):
    src = os.path.join(DST, f"level_src_{src_idx:02d}.png")
    dst = os.path.join(DST, f"level_{new_idx:02d}.png")
    shutil.copy2(src, dst)
    print(f"  level_{new_idx:02d}.png  <-  src_{src_idx:02d}  ({comment})")

print(f"\nMapping saved: {mapping_path}")
print(f"Source files (level_src_NN.png) kept for audit.")
