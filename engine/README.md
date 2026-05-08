# Zuma engine — baseline v7 (2026-05-08)

Опорная стабильная версия движка игры на TS-Conf. Соответствует `reference_zuma_baseline_2026-05-08_v7.md` в memory.

## Содержимое

- `zuma_new_spg_baseline_2026-05-08_v7.asm` — основной исходник (sjasmplus, ~5460 строк)
- `zuma_baseline_2026-05-08_v7.spg` — собранный SPG-файл (готов к запуску в Unreal)
- `destroy_gfx_baseline_2026-05-08_v7.bin` — спрайты explosion-анимации (7 кадров 16×16, 4bpp carpet)
- `balls24_gfx_baseline_2026-05-08_v7.bin` — TSU спрайты шаров 24×24 (6 цветов)
- `balls_pal_baseline_2026-05-08_v7.bin` — палитры шаров (6 × 16 цветов CRAM)
- `vdc_visual_emulator_baseline_2026-05-08_v7.py` — Python-эмулятор VDC chain physics (tkinter, для отладки)
- `make_destroy_baseline_2026-05-08_v7.py` — генератор destroy-спрайтов из HD source
- `convert_balls24.py`, `make_dma_balls.py` — пайплайн ball graphics
- `spgbld.ini` — конфиг spgbld.exe (page mapping)

## Что работает

- VDC chain physics (slot-array model, GAP_STOP/GAP_CASCADE markers, DoGapStep, hemisphere insert)
- Match-3 detection с offset gap check, anti-3-spawn-guard
- Cascade roll-back velocity-capped
- DMA chain rendering (PASS1/PASS2/PRESERVE классификация)
- Match-3 explosion animation через TSU layer 1 (7 кадров, цветной gradient)
- Refresh-race пофиксен (TSU writes в early vblank, до DMA blits)
- 6 цветов шаров (runtime LevelNumColors)
- Hemisphere insert (target = i или i+1 по Manhattan-дистанции)

## Известные косметические дефекты

- Match-3 в самой первой строке canvas (trackY < 16) — explosion не показывается (skip render_y < 8 во избежание hardware-glitch). Match-логика правильна.
- `TSU_CHAIN_SPRITES = 60`: explosion на цепи длиннее 60 шаров не рендерится (редко).

## Сборка

```
sjasmplus zuma_new_spg_baseline_2026-05-08_v7.asm
spgbld -b spgbld.ini zuma_baseline_2026-05-08_v7.spg
```
(требуется sjasmplus и spgbld из tsconf_project)
