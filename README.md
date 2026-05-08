# Zuma Deluxe для TS-Conf

Реализация игры Zuma Deluxe на платформе TS-Conf (Z80, 14 МГц, 256 цветов, DMA blitter, TSU sprites).

Основной код игры лежит в отдельном репозитории `c:\z80\zuma\` (zuma_new_spg.asm). Эта папка содержит ассеты, инструменты подготовки уровней и материалы документации.

## Структура

- `src/` — Python-скрипты пайплайна подготовки уровней:
  - `convert_track.py` — Catmull-Rom сглаживание + 1px ресемпл траектории
  - `scale_level.py` — масштабирование уровня под TS-Conf canvas (360×256)
  - `split_levels.py`, `trace_track.py`, `rename_levels_by_difficulty.py` — вспомогательные
- `graphics/` — игровая графика и game-data:
  - `spritesheet.png` — атлас шаров (источник для `convert_balls24.py`/`make_dma_balls.py`)
  - `frog-64-64.png` — лягушка-стрелок
  - `Blackswirley/` — дополнительные данные/арт
  - `levels/` — bin-данные уровней (полилинии трека) + превью PNG
- `images/` — скриншоты эмулятора и референсы оригинальной Zuma HD (для сравнения визуала)
- `docs/` — документация:
  - `uchebnik/` — HTML-учебник по TS-Conf (`index.html`)
  - `Программирование для tsconfig.docx`/`.md` — справочник по платформе
  - `tsconfig_doc.txt` — текстовая версия документации TS-Conf
  - `claude_session_*.md` — заметки по сессиям разработки

## Платформа

- TS-Conf (TS-Labs) — расширение ZX Spectrum: 14 МГц Z80, 4 МБ RAM, DMA blitter, TSU спрайтовый процессор, 256C T0 canvas 360×288.
- Эмулятор: Unreal Speccy 0.39.x (driver=gdi).

## Сборка

См. отдельный репозиторий с asm-кодом (`c:\z80\zuma\`).
Шаги:
1. `sjasmplus zuma_new_spg.asm` — собрать main0.bin, main1.bin, page_*.bin
2. `spgbld -b spgbld.ini zuma_new_spg.spg` — упаковать в SPG-файл
3. `Unreal.exe zuma_new_spg.spg` — запустить
