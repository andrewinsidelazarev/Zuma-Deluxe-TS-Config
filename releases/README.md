# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

## Текущая версия

**v14 (2026-05-11)** — `zuma_v14_2026-05-11_level1_4colors.spg`

### Fixes 2026-05-11 (v14 — реальный Level 1 + 4 цвета + intro overlay + GAME OVER 64×64) — самые новые
- **Реальный Level 1 "Spiral of Doom"** — bg импортирован из ZumaHD `level_src_01.png` (640×480) с crop 640→600 (5:4) + scale 0.6 → 360×288. Track из `spiral.dat` пропорционально (`(x-20)*0.6, y*0.6`).
- **LevelNumColors=4** (per ZumaHD `levels.xml/level1`) — 4 цвета шаров. Раньше всегда 6.
- **Anti-3-spawn-guard bug fix** — `CP NUM_BALL_COLORS` (compile-time 6) → `CP (LevelNumColors)` (runtime 4). Раньше candidate+1 при wrap'е мог стать 4/5 → юзер видел 5+ цветов на цепи вместо 4.
- **LEVEL 1-1 intro overlay** — GameState=3 при InitGame, 150 кадров показывается "LEVEL 1-1" (5×64×64) + "SPIRAL OF DOOM" (5×64×32 subtitle) перед началом игры. Тот же gradient palette что у GAME OVER.
- **GAME OVER 64×64** — увеличен до полного размера 5 sprites × 64×64 (раньше пробный 64×32).
- **Atlas swap через LDIR** — page #0D = active overlay scratch buffer. Source pages #50 (GAME OVER) / #51 (LEVEL INTRO) → LDIR через временный slot 2/3 remap (DI/EI) при смене состояния. DMA с transparency src=0 не годилась — оставляла старые letters просвечивать.
- **Frog calibration на Spiral of Doom** — FROG_INIT_X=152, FROG_INIT_Y=108 (centre 184,140) — через `click_picker.py` (tkinter + zoom 3x).
- **levels-ts-config/01/ архив** — Spiral of Doom как self-contained папка: src_bg/src_track + scaled_bg + level_NN_canvas_*.bin + level_params.txt. Pipeline = `import_real_level1.py`.

### Fixes 2026-05-10 (v13 — GAME OVER text + gradient palette dithering)
- **GAME OVER text** — 5 TSU sprites 64×64 (= 320×64), centered на канвасе. Atlas в page #0D. TNUM_base=3584, sprite N → TNUM = base + N*8.
- **Custom 15-color gradient palette** — `gameover_pal.bin` (red→orange→yellow, quadratic G interp). Загружается в SPAL=5 (red ball palette) при входе в state 2, восстанавливается через RestoreRedBallPalette в InitGame на restart.
- **Nearest-color quantization** — antialised font edges (gradient pixels между red outline и yellow inner) автоматически маппятся в промежуточные palette indices = soft dithered transitions, без резких 2-color edges.
- **SPSIZ40/48/56/64** константы добавлены — TS-Conf TSU поддерживает 8 размеров через 3-bit SIZE field. SPSIZ64 (#0E) используется для big text sprites.
- **Skull relocated** — перенесён с page #0D на page_b cy=4..7 (после destroy_gfx). Освобождена вся page #0D под text atlas.
- **InitGame palette restore** — CALL RestoreRedBallPalette в начале InitGame вернёт red ball палитру если был state 2 → restart.

### Fixes 2026-05-10 (v12 — kz architectural split)

### Fixes 2026-05-10 (v12 — kz architectural split: sun DMA + skull TSU) — самые новые
- **Sun rays** — DMA blit single static frame в canvas (killzone_top.bin/bot.bin pages #46/#47, sun-only без skull композита).
- **Skull** — отдельный TSU sprite 32×32 на layer 1 над canvas. Atlas в page #0D (`kz_skull_atlas.bin`, 4bpp carpet, 10 frames). TNUM = 3584 + KzFrame*4. SPAL=4 (yellow palette).
- **Mouth animation** — UpdateKzSkullSprite в RenderFrame TSU pipeline пересчитывает TNUM по KzFrame каждый кадр. Open at distance < 96 трекпоинтов (= 3 cells), close on rollback. State 1 (absorbing) → full open (frame 9).
- **Шары визуально под skull** — TSU layer 1 над canvas даёт правильный Z-order: chain DMA балы видны поверх sun-rays canvas, но проходят за skull-sprite (= "balls fall into mouth" как в оригинальной Zuma).
- **Trash rectangle bug fixed** — `BcsGoldenOff` теперь устанавливается явно в начале `BlitKillzoneToShadow` по текущему ShadowPageBase. Раньше использовалось stale значение от prev frame's BlitChainToShadow → src page = #40+ (= ball atlas) → trash под kz.
- **Skull centering** — KZ_SKULL_X_OFFS=2, KZ_SKULL_Y_OFFS=0 для тонкой подгонки skull под видимый центр sun's hole (sun source имеет hole offset +2 px от crop center).
- **AbsorbHead continuity** — HSA НЕ декрементируем при shift_left, кадр совместим со старой формулой slot_t. Иначе backward-jump на CELL_SIZE при первой абсорпции.
- **HeadSub reset на trigger entry** — первый шар получает полный CELL_SIZE цикл advance перед absorb. Без reset hsub был ~30 в момент trigger → 1-2 calls до wrap = мгновенный absorb 1-го шара.
- **Per-level fast spawn parameter** — LEVEL_START_BALLS=35 (быстрая фаза «поезд»), LEVEL_REPEAT_BALLS=50 (нормальная скорость), LEVEL_TOTAL_BALLS=85.

### Fixes 2026-05-10 (v10 — рабочая Game Over absorption)
- **Chain rendering revert TSU → DMA** — UpdateChainTSUSprites заменён на HideChainSprites + BlitChainToShadow re-enabled. DMA blit имеет partial-clip (`BcsClipTop`/`BcsClipBot`), благодаря чему шары корректно вылезают из-за верхнего края экрана из spawn-зоны (track[0..29] с y<0). Chain TSU layer 1 не имел partial-clip → шары появлялись только когда полностью в visible зоне = «не из-за края».
- **TSU_CHAIN_SPRITES limit устранён** — DMA не имеет лимита 60 sprites как TSU. Tail больше не пропадает при росте chain >60 на insert. SFILE chain слоты держатся off-screen через HideChainSprites.
- **Game Over absorption trigger** — снят gate `BallsSpawned >= LEVEL_TOTAL_BALLS`. Теперь absorption запускается сразу как head Manhattan(KzCenter) < 16, в любой фазе (= как в Python emulator). Цепочка визуально влетает в killzone, шары исчезают по одному.
- **AbsorbHead continuity fix** — HSA НЕ декрементируем при shift_left (= old idx 1 становится new idx 0 при том же HSA → cell-step компенсация уже встроена в формулу slot_t). Иначе цепь дёргалась назад на 32 px при первой абсорпции и анимация выглядела как «начинается со второго шарика».
- **MAX_BALLS 16 → 8** + **TSU_CHAIN_SPRITES 60 → 70** — освободили SFILE descriptors на случай возврата chain TSU.

### Fixes 2026-05-10 (v9 — chain-TSU + Game Over state machine baseline)
- **Game Over state machine** — head ball Manhattan(KzCenter) < 16 → переход в state 1 (absorbing). Chain advance в темпе FAST_ADVANCE (как стартовая фаза появления цепи). Когда HSA достигает TRACK_NUM_SLOTS-1 — каждый тик shift Chain0_* arrays toward head + dec SlotsLen. SlotsLen=0 → state 2 (text TODO).
- **Input lock в state 1/2** — HandleInput сразу RET если GameState != 0. Стрельба и frog rotation заблокированы во время absorption.
- **GameState/AbsorbCounter** в #4015/16 (slot 1 page 5 first half, не SAVEBIN). InitGame явно зануляет — иначе random RAM на boot триггерит state machine.

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
