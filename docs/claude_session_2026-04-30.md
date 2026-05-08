# Claude Session Memory — ZUMA DELUXE — 2026-04-30

## Что было исследовано в этой сессии

### Учебник "Программирование для tsconfig.md"
Прочитаны ключевые разделы. Главное открытие:
- **FMEN=#10** — это ЕДИНСТВЕННОЕ значение порта FMADDR
- **FMCRAM=#0000** и **FMSFILE=#0200** — это Z80-АДРЕСА, а не значения порта
- TSU спрайты: **всегда 4bpp (15 цветов + прозрачный)**
- Дескриптор спрайта: 6 байт (Y, flags, X, flags, TNUM_L, SPAL+TNUM_H)
- SGPAGE = номер страницы где хранится 4bpp графика

### Официальная документация tsconf_en.md
- Подтверждено: "15 colors per pixel for tiles and sprites" = 4bpp
- Спрайты 8×8 до 64×64, шаг 8px
- SGPAGE, T0GPage, T1GPage — отдельные регистры для каждого слоя

---

## Найденные баги в zuma_new.asm

| # | Баг | Причина | Исправление |
|---|-----|---------|-------------|
| 1 | SGPAGE=64 → чёрный экран | Страница 64 требует >1MB RAM, не в SNA | SGPAGE=6 |
| 2 | CopyFrogGfx копировала страницы 64-65 | Страница 64 недоступна/пуста | Убрать CopyFrogGfx |
| 3 | frog_gfx.bin 8bpp, TSU нужно 4bpp | TSU всегда 4bpp | Перегенерировать в 4bpp |
| 4 | FM_SFILE EQU #20 | Нет второго режима FM | Убрать константу |
| 5 | TNUM формула: (N&7)*8 | Неверный множитель для 4bpp | (N&15)*4 |

---

## Изменения в convert_frog.py

**Было (8bpp):**
- 32768 байт, 8bpp (1 байт/пиксель)
- Раскладка 8×4 кадров
- TNUM = 3072 + (N//8)*256 + (N%8)*8

**Стало (4bpp):**
- 16384 байт, 4bpp (2 пикселя/байт, nibble)
- Раскладка 16×2 кадров (16 кадров в ряд)
- TNUM = (N//16)*256 + (N%16)*4
- Квантизация: 15 цветов + прозрачный
- frog_pal.bin: только записи 0-15 заполнены (для SPAL=0)

---

## Что нужно сделать в zuma_new.asm

### 1. Убрать FM_SFILE (строка ~37)
```asm
; УДАЛИТЬ эту строку:
FM_SFILE EQU #20    ; %00100000 — запись в SFILE
```

### 2. Изменить SGPAGE (строка ~98)
```asm
; БЫЛО:
LD BC, SGPAGE  : LD A, 64 : OUT (C), A
; СТАЛО:
LD BC, SGPAGE  : LD A, 6 : OUT (C), A
```

### 3. Убрать вызов CopyFrogGfx (строка ~94)
```asm
; УДАЛИТЬ:
CALL CopyFrogGfx
```

### 4. Убрать функцию CopyFrogGfx (строки ~682-693)

### 5. Исправить TNUM формулу в UpdateFrogSprite (строки ~589-597)
```asm
; БЫЛО:
SRL A : SRL A : SRL A       ; A = N (0-31)
LD D, A
SRL A : SRL A : SRL A       ; A = N>>3 (0-3)
LD E, A
LD A, D : AND 7
ADD A, A : ADD A, A : ADD A, A  ; (N&7)*8
; СТАЛО:
SRL A : SRL A : SRL A       ; A = N (0-31)
LD D, A
SRL A : SRL A : SRL A : SRL A  ; A = N>>4 (0-1)
LD E, A
LD A, D : AND #0F           ; N&15
ADD A, A : ADD A, A         ; (N&15)*4
```

### 6. Исправить INCBIN (конец файла)
```asm
; БЫЛО:
    SLOT 1 : PAGE 6 : ORG #4000
    INCBIN "frog_gfx.bin", 0, 16384
    SLOT 1 : PAGE 7 : ORG #4000
    INCBIN "frog_gfx.bin", 16384, 16384
    SLOT 1 : PAGE 5
; СТАЛО:
    SLOT 1 : PAGE 6 : ORG #4000
    INCBIN "frog_gfx.bin"   ; ровно 16384 байт после пересборки
    SLOT 1 : PAGE 5
```

---

## Порядок действий для получения рабочего спрайта

1. `cd c:\z80\zuma && python convert_frog.py` → frog_gfx.bin (16384 байт), frog_pal.bin
2. Применить правки в zuma_new.asm (см. выше)
3. Собрать: sjasmplus zuma_new.asm → zuma_game.sna
4. Запустить в эмуляторе → должен быть виден вращающийся спрайт лягушки

---

## Ключевые технические правила TS-Config

```
FMADDR = #10 (FMEN) — включает FM доступ
Запись в #0000 при FM = CRAM (палитра)
Запись в #0200 при FM = SFILE (дескрипторы спрайтов)

TSU спрайты: 4bpp, 16 цветов (SPAL выбирает 1 из 16 палитр)
SGPAGE = страница с 4bpp bitmap данными
TNUM = номер тайла 8×8 в карпете (верхний левый угол спрайта)

Адрес тайла: addr = tnum_y*2048 + ycnt*256 + tnum_x*4 + bsel
В 4bpp: tnum_x шаг = 8px, карпет = 512px шириной

Спрайт 32×32 = 4×4 тайла = 512 байт
32 кадра × 512 байт = 16384 байт = 1 страница ✓
```
