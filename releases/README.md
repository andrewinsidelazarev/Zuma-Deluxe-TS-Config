# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

| Версия | Дата | Что нового |
|--------|------|------------|
| v7 | 2026-05-08 | Match-3 explosion-анимация через TSU layer 1, refresh-race пофиксен, hemisphere insert, 6 цветов |
| v6 | 2026-05-08 | Match-3 explosion (первая рабочая версия), TSU integration |
| v5 | 2026-05-08 | HD-look шары (диаметр 21 px), gap-слева пофиксен (BALL_PIX 22→20) |
| v4 | 2026-05-08 | Python VDC emulator portированы все физик-фиксы в asm |

## Запуск

1. Скачать `.spg` файл.
2. Открыть в Unreal Speccy: `Unreal.exe zuma_vN_2026-05-08.spg`.
3. Управление — мышь (LMB — выстрел).

## Платформа

TS-Conf (TS-Labs): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites, 256C T0 canvas 360×288, 50 Гц.
