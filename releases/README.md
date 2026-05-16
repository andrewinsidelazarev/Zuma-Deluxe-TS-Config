# Готовые релизы

Собранные SPG-файлы для запуска в Unreal Speccy. Достаточно открыть `.spg` в эмуляторе.

## Что есть в игре (state v16, 2026-05-16)

**Геймплей:**
- 2 играбельных уровня: «Spiral of Doom» (level 1) и «Mud Slide» (level 2)
- Полная VDC chain physics: spawn → train phase (35 шаров FAST_ADVANCE) → repeat phase (50 шаров normal) → end-of-level
- 6 цветов шаров (runtime `LevelNumColors`, per level: L1=4 цвета, L2=4)
- Bullet collision с bbox 28×28 + hemisphere insert (target = i или i+1 по ближайшему non-GAP соседу через Manhattan)
- Match-3 detection (window-3 scan) + GAP_STOP/GAP_CASCADE markers
- Cascade chain: gap closure → новый match → roll-back головы (HSA--)
- Match-3 explosion-анимация: 7 кадров TSU layer 1 с цветным gradient
- Approach physics (8 px/frame, frozen-target chase до прибытия в slot)
- Auto-spawn по таймеру, anti-3-spawn-guard
- Game Over absorption: head вылетает в killzone → arrays shift_left → chain ушла → GAME OVER overlay
- Auto-restart через ~4 сек после GAME OVER

**Управление:**
- Mouse: aim + LMB выстрел
- Keyboard: O/P для поворота лягушки, SPACE для выстрела
- Mouse low-pass фильтр (alpha=1/4) — гасит jitter мыши

**Level Select экран:**
- Scene 1: декоративная заставка с pyramid overlay + sky scroll dither
- 13 уровней в таблице (только L1, L2 играбельны на текущий момент)
- TSU-превью текущего уровня 192×120 (sprite 64×8 grid)
- Mini-frog + mini-killzone (32×32 SPSIZ32 sprites) поверх превью, позиции из `LevelMiniCfg` (per level game-coords) + scale ×5/8
- Per-level palette переключение (`LoadCurStagePreviewPalette`) — превью соответствует bg-цветовой схеме уровня
- Per-level dispname в кастомном шрифте nativealien48 (gradient orange→yellow): «SPIRAL OF DOOM», «MUD SLIDE»
- LEVEL N-N intro screen (150 кадров) перед началом игры

**Графика и звук:**
- HD-look шары диаметром ~24 px (TSU SPSIZ24), 4bpp atlas
- HD frog 64×64 с rotation (через atan LUT, 8-octant ComputeAngle, hybrid follow)
- Custom killzone: sun (DMA static blit) + skull (TSU sprite layer 1) с mouth animation (10 frames, open at distance < 3 cells)
- Background canvas 360×288, ZX7-compressed pages (#80..#88 для L1, #89..#91 для L2)
- Cursor 24×24 (TSU sprite, raw mouse pos)
- Frog blink animation (3 frames)
- Spin physics шаров — rolling-without-slip (per-level runtime K calibration)
- Звука пока нет

**Архитектура:**
- TS-Conf (ZX-Evo): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites/tiles, canvas 360×288 @ 50 Гц
- SPG-сборка (`sjasmplus` → `spgbld.exe`), 64 pages × 16K
- VDC chain model (slot array + offsets, не rigid body)
- Single TrackData в slot 3 page #03 (stack-safe), per-level data копируется через `CopyAtlasToPage`
- FM_EN-banked CRAM + SFILE для регистров TSU
- Сжатие graphics: ZX7-Turbo для canvas, raw 4bpp для sprites/atlas

**Инструменты разработки:**
- `zuma_ts_emulator.py` — Z80 harness (cburbridge emulator) с CALL хуками
- `vdc_visual_emulator.py` — Python-симулятор chain physics (Tkinter GUI)
- `full_vdc_simulation.py` — fuzz testing (50 runs × 15000 кадров, invariant checks)
- Circular RAM log в игре (256 entries × 8 байт, F12-dump для post-mortem диагностики редких багов)
- Регрессионные тесты: `test_level2_gameover_trigger.py`, `test_session_fixes_2026-05-16.py`, `test_chain_advance.py`, `test_gameover.py`, etc.
- Документация: `docs/uchebnik/index.html` (учебник 21 раздел про TS-Conf + Zuma примеры)

## Текущая версия

**v16 (2026-05-16)** — `2026-05-16-v16-level2_playable/zuma.spg`

### Fixes 2026-05-16 (v16 — Level 2 (Mud Slide) playable + Game Over L2 + moving-target fix + RAM log diagnostic) — самые новые
- **Game Over на level 2** — `LVL02_TRACK_SLOTS`/`TRACK_NUM_SLOTS` теперь ceil-деление (`(points+CELL-1)/CELL`). На L2 floor давал 82 slots, HSA cap=81, head max t=1639, KzCenter в t=1655 → Manhattan ≥16 → `CheckHeadAtKillzone (CP 16: JR NC, skip)` никогда не triggered → Game Over не запускался.
- **head-comp invariance** в `InsertChainBall` — `offsets[0..idx-1] -= CELL_SIZE` для всех знаков (с floor'ом -2×CELL_SIZE). Раньше negative offsets обрезались к `-CELL_SIZE`, теряя дельту → head-side слоты «прыгали» по треку на |offset_old| px вперёд при insert. На L2 fold-зоне это давало 23 px смещение = ширина межрядового зазора.
- **TSU_BALL_HALF=12 EQU** — bullet center = top-left + 12 (24×24 sprite). Legacy +8 (16×16) давал логический центр на 4 px влево/вверх от визуального → hemisphere check (`prev/next Manhattan`) ошибался при snipe через gap.
- **APPROACH_SPEED=8 EQU** (было 4) — bullet добегает до target slot за 5-10 кадров вместо 10-20. Slot не успевает физически дрейфить от offset decay / HSA change → закрывает «moving-target» glitch: шар не «улетает влево» к новой позиции slot'а.
- **Circular RAM log** — `GameLog` ring buffer 256×8 байт + `LogEvent` (preserve all regs) + 5 event types (SHOT_FIRED, BBOX_HIT, HEMI, INSERT, APPR_END). По F12-дампу парсер реконструирует пайплайн действий перед глюком, на свежем софте поймали moving-target glitch за одну сессию.
- **Mini-sprites из level config** — `LevelMiniCfg` таблица (game-coords frog/kz per level, 4 байта на запись) + `PreviewScaleGameToTop` с scale ×5/8. Раньше hardcoded final screen-coords только под level 1; PREV/NEXT не обновлял позиции.
- **Per-stage preview palette** — `LoadCurStagePreviewPalette` переключает SPAL=0 палитру preview-тайлов под уровень (L1→`level_01_preview_pal.bin`, L2→`level_02_preview_pal.bin`).
- **Track entry leadin** — `ensure_offscreen_entry_leadin()` в обоих импортёрах (`import_zumahd_level.py`, `import_real_level1.py`) добавляет 32 точки lead-in перед первой видимой точкой если track начинается на экране. Закрывает «недорисовку шаров в начале трека».
- **Level 1 dispname в nativealien48 font** — «SPIRAL OF DOOM» рендерится тем же gradient-шрифтом, что и «MUD SLIDE» на level 2 (`make_level1_text_assets.py`).
- **Регрессионные тесты** — `test_level2_gameover_trigger.py` (Z80 harness проверка `CheckHeadAtKillzone` L1/L2) + `test_session_fixes_2026-05-16.py` (6 subtests на все правки сессии).
- **uchebnik HTML раздел 21** — «Circular RAM log — отладка редких runtime багов через F12-dump» с примерами LogEvent, парсера, auto-freeze pattern.

### Fixes 2026-05-11 (v14 — реальный Level 1 + 4 цвета + intro overlay + GAME OVER 64×64)

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

1. Скачать последний `2026-05-16-v16-level2_playable/zuma.spg` (или соответствующий .spg другой версии).
2. `Unreal.exe zuma.spg`.
3. Управление: мышь (LMB — выстрел), либо O/P + SPACE.

## Платформа

TS-Conf (TS-Labs): Z80 14 МГц, 4 МБ RAM, DMA blitter, TSU sprites, 256C T0 canvas 360×288, 50 Гц.
