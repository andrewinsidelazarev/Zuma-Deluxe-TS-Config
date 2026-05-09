# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

## Текущая версия

**v7 (обновлено 2026-05-10)** — `zuma_v7_2026-05-08.spg`

### Fixes 2026-05-09 / 10 (новые сверху)
- **Stack overlap TrackData** — root cause «false killzone V7» glitch. Stack at `#BFFF` затирал TrackData[2643..2648] (= точки трека на canvas (58,103)). Fix: stack перенесён в slot 3 page #0C (`LD SP, #FFFE`), 14KB safe zone после track_overflow.
- **Stack canary "ZUM"** at `0xC800` — RenderFrame проверяет каждый кадр. Если затёрт (= stack overflowed) — bg pavement палитра становится ярко-красной, видно сразу.
- **TrackData spillover** — page 2 (16K) не вмещает 12386 байт TrackData. Часть в slot 3 page #0C, читается через PAGE3=#0C. Killzone (track[3095]) теперь корректно достижим.
- **Ложный match-3** — ExplodingFrame/ExplodingMarker shift'ятся синхронно со Slots/Offsets/Shot2 при insert/cascade-close. SpawnChainBall обнуляет stale значения.
- **ChainStalled** — теперь stall только при наличии GAP-cells (раньше также при `offsets != 0` — давало +32 кадра паузу при insert).
- **ChainFreezeCounter из insert удалён** — голова теперь продолжает движение, не паузит хвост.
- **Mouse low-pass фильтр** (alpha=1/4) — гасит kempston jitter, плавный frog aim.
- **Плавная chain motion** (1 px/frame, без stutter) — убран subdivider /2.

### Fixes 2026-05-08 (предыдущие)
- VDC chain physics, match-3 detection, cascade roll-back.
- Match-3 explosion-анимация через TSU layer 1 (7 кадров, цветной gradient).
- Refresh-race пофиксен (TSU writes в early vblank).
- Hemisphere insert (target = i или i+1 по ближайшему соседу).
- 6 цветов шаров (runtime LevelNumColors).
- HD-look шары (диаметр ~20 px, цепь занимает весь трек).

## Запуск

1. Скачать `zuma_v7_2026-05-08.spg`.
2. `Unreal.exe zuma_v7_2026-05-08.spg`.
3. Управление: мышь (LMB — выстрел).

## Платформа

TS-Conf (TS-Labs): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites, 256C T0 canvas 360×288, 50 Гц.
