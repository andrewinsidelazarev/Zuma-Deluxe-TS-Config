# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

## Текущая версия

**v7 (2026-05-08)** — `zuma_v7_2026-05-08.spg`

Что работает:
- VDC chain physics, match-3 detection, cascade roll-back
- Match-3 explosion-анимация через TSU layer 1 (7 кадров, цветной gradient)
- Refresh-race пофиксен (TSU writes в early vblank)
- Hemisphere insert (target = i или i+1 по ближайшему соседу)
- 6 цветов шаров (runtime LevelNumColors)
- HD-look шары (диаметр ~20 px, цепь занимает весь трек)

## Запуск

1. Скачать `zuma_v7_2026-05-08.spg`.
2. `Unreal.exe zuma_v7_2026-05-08.spg`.
3. Управление: мышь (LMB — выстрел).

## Платформа

TS-Conf (TS-Labs): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites, 256C T0 canvas 360×288, 50 Гц.
