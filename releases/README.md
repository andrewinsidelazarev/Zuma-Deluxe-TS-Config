# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

## Текущая версия

**v9 (обновлено 2026-05-10)** — `zuma_v9_2026-05-10_chain_tsu_gameover.spg`

### Fixes 2026-05-10 (Game Over absorption) — новые
- **Game Over state machine** — head ball Manhattan(KzCenter) < 16 → переход в state 1 (absorbing). Chain advance в темпе FAST_ADVANCE (как стартовая фаза появления цепи). Когда HSA достигает TRACK_NUM_SLOTS-1 — каждый тик shift Chain0_* arrays toward head + dec SlotsLen. SlotsLen=0 → state 2 (text TODO).
- **Input lock в state 1/2** — HandleInput сразу RET если GameState != 0. Стрельба и frog rotation заблокированы во время absorption.
- **GameState/AbsorbCounter** в #4015/16 (slot 1 page 5 first half, не SAVEBIN). InitGame явно зануляет — иначе random RAM на boot триггерит state machine.

**Открытые после v9:**
- Spawn-zone TSU rendering: balls вылетают не из-за края экрана (TSU не делает partial-clip как DMA chain в baseline relocated).
- Tail ball пропадает при выстреле (insert artifact).

### Fixes 2026-05-10 (chain-TSU + relocated vars)
- **Chain рисуется через TSU layer 1 поверх canvas** — шар в killzone-зоне теперь корректно поверх killzone-картинки, без pavement-gap под ним. Раньше chain DMA + restore golden→shadow затирал killzone-pixels pavement'ом для prev ball positions.
- **UpdateChainTSUSprites** — новая функция (по pattern UpdateExplodeSprites): TNUM=2304+COLOR×3, SPAL=COLOR+2, SPSIZ24=24×24. UpdateExplodeSprites override-ит destroy frame для exploding слотов как раньше.
- **Chain DMA blit отключён** (RET в начале BlitChainToShadow). BcsGoldenOff setup сохранён до RET — его читает BlitKillzoneToShadow для restore golden→shadow.
- **Variables relocated на ORG #4000** (page 5 first half) — все большие arrays (ChainPrev*/Bcs*) переехали в свободные 8K до main0.bin. Раньше straddle slot 1/2 boundary #8000 — любой shift кода в #6000+ ломал bg corruption. Теперь добавление функций безопасно.
- **TSU 4-sprites-per-line — НЕ лимит TS-Conf**: 60+ sprites одновременно везде на экране без missing.

### Fixes 2026-05-09 / 10
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

1. Скачать `zuma_v7_2026-05-10.spg`.
2. `Unreal.exe zuma_v7_2026-05-10.spg`.
3. Управление: мышь (LMB — выстрел).

## Платформа

TS-Conf (TS-Labs): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites, 256C T0 canvas 360×288, 50 Гц.
