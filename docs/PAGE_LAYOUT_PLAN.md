# Page layout plan — Zuma Deluxe на TS-Config

Расчёт распределения памяти TS-Config для полной игры: 13 stages × 4 difficulty + Level Select + Start screen + More Games screen. С учётом текущей ZX7-компрессии canvases.

---

## Бюджет

- **Total RAM**: 4 MB = **256 страниц × 16 KB**.
- **Currently used (baseline `2026-05-15_sfile_isolation`)**: 66 pages.
- **Free**: 190 pages.

---

## Per-level сметы (на основе level_01)

| Ресурс | Raw size | ZX7-compressed | Allocated pages |
|---|---:|---:|---:|
| Canvas (фон 360×288, 9 chunks) | 144 KB | 110 KB (76% от raw) | **9** (один ZX7-stream = одна page) |
| Track (path data) | 11.7 KB | ~7 KB (estimate) | **1** (с трекером — можно 2 трека/page) |
| Dispname text | shared atlas | — | 0 (row in #4E/#4F) |
| Palette | 512 bytes | — | 0 (in runtime page #61) |
| **Per-level total** | | | **~10 pages** |

## Per-scene сметы (на основе LS scene)

| Ресурс | Pages | Примечание |
|---|---:|---|
| Scene canvas (9 ZX7-streams) | 9 | как и level canvas |
| Sky/pyramid/decor (если есть) | 4 + 4 = 8 | LS уже использует |
| Sprite atlas (если TSU) | 2 | level preview |
| Palette | 0 | shared |
| **Per-scene total** | **~10-20 pages** | depends на содержимое |

---

## Scope игры

Из `src/levels_meta.json`:
- **22 unique graphics** (background images, 4 difficulty могут делить один graphics)
- **130 settings** (difficulty configs)
- **52 unique (stage, difficulty) combos** = 13 stages × 4 difficulty
- **13 unique tracks** (один track per stage, все difficulty same track)

Поэтому реалистичный per-level cost:
- 22 unique canvas × 9 pages = **198 pages** для всех график
- 13 unique tracks × 1 page = **13 pages**
- 3 scenes (LS, Start, More Games) × ~10 pages = **30 pages**

---

## Naïve all-static layout (НЕ ВЛЕЗАЕТ)

| Группа | Pages |
|---|---:|
| Code (main0/main1) | 3 |
| Sprites (frog/balls/cursor/preview/dispname/sky/pyramid/atlases) | 26 |
| Palettes (runtime page #61) | 1 |
| Runtime workspace (canvas A/B/golden + boot pages) | 27 |
| **22 graphics × 9 ZX7 pages** | **198** |
| **13 tracks × 1 page** | **13** |
| **3 scenes × 10 pages** | **30** |
| **TOTAL** | **298 pages** |

**298 > 256** → не влезает. На ~40 pages overshoot.

---

## Оптимизированный layout с on-demand stream (ВЛЕЗАЕТ)

Идея: загруженным в RAM **одновременно** держится только **текущий** level (canvas + track) + текущая scene. Все остальные levels/scenes лежат в ZX7-compressed форме на тех же физических pages, и runtime swap'ает их при переходе.

Wait — на TS-Config все pages **уже в RAM одновременно** (4 MB всё доступно через banking). Нет понятия «загружен / не загружен» как на disk-based системах. Все 256 pages сразу в SDRAM.

То есть **on-demand stream не помогает** — все ZX7-compressed данные должны жить в RAM физически.

Реальная оптимизация:
1. **Tracks ZX7-pack 2 per page** (7K + 7K = 14K < 16K): 13 tracks / 2 = **7 pages** вместо 13.
2. **Скомпрессировать tracks**: добавить `track_NN_zx7.bin` в pipeline (currently track stored uncompressed).
3. **Стратегически выбрать какие graphics сжимать тоже сильнее** (например, статичные splash screens — RLE/Z3 вместо ZX7 если плотнее).

После оптимизации:

| Группа | Pages |
|---|---:|
| Code (main0/main1) | 3 |
| Sprites/atlases | 26 |
| Palettes | 1 |
| Runtime workspace | 27 |
| 22 graphics × 9 ZX7 pages | 198 |
| 13 tracks ZX7-packed × 0.5 page | **7** |
| 3 scenes × 10 pages | 30 |
| **TOTAL** | **~292 pages** |

Всё ещё > 256. Главный пожиратель — **22 × 9 = 198 pages на canvases**. Это **76% memory budget на одни картинки фонов**.

Реальная оптимизация-2:
1. **Уменьшить canvas footprint** — currently 9 pages × 144KB raw. Если canvas будет **stored в 6-7 pages** (более плотная ZX7-compression благодаря per-level palette quantization), это даёт **22 × 7 = 154 pages**.
2. **Share decor pages** (sky/pyramid/decorations) между levels того же stage.

| Группа (после оптимизации canvas) | Pages |
|---|---:|
| Code + sprites + palettes + workspace + misc | 57 |
| 22 canvases × 7 pages (ZX7-tight) | **154** |
| 13 tracks packed | 7 |
| 3 scenes × 8 pages | 24 |
| **TOTAL** | **~242 pages** |

**Влезает в 256 pages** с запасом 14 pages.

---

## Предлагаемое page mapping

Текущее (раскладка-66-pages):
```
#02      main1.bin                        [code + data + TrackData INCBIN]
#05      main0.bin                        [code]
#06..#09 frog_p0..p3.bin                  [frog sprite tiles]
#0A      page_a.bin                       [balls sprite atlas]
#0B      page_b.bin                       [skull/destroy atlas]
#0C      level preview (tsu_p0)           [LS preview sprite data]
#0D      page_d.bin                       [LVLINTRO atlas, restored on InitGame]
#10..#18 boot_black_canvas_page.bin       [9 pages boot canvas]
#19..#1C sky_atlas_p0..p3                 [4 pages sky]
#29..#2C pyramid_overlay_p0..p3           [4 pages pyramid]
#40..#45 balls_dma_even_0..5              [6 pages balls DMA even]
#46..#47 killzone_top, killzone_bot       [2 pages killzone]
#48..#4D balls_dma_odd_0..5               [6 pages balls DMA odd]
#4E..#4F dispname_atlas_a, _b             [2 pages dispname text]
#50      gameover_text_atlas               [1 page]
#51      level_intro_text_atlas            [1 page]
#52..#53 level_01_preview_p0, _p1         [2 pages level preview tiles]
#54..#5C [runtime only] LS scene decoded canvas (9 pages from #70..#78 ZX7)
#60      track_overflow.bin                [TrackData spillover]
#61      runtime palettes (frog/cursor/balls/bg/gameover/balls_dma)
#70..#78 scene_levelsel_canvas_p0..p8_zx7  [9 pages LS scene compressed]
#80..#88 level_01_canvas_p0..p8_zx7       [9 pages level1 canvas compressed]
```

Свободно для будущего:
```
#1D..#28 (12 pages) — для Start Screen / More Games (если используют sky-pyramid pattern)
#2D..#3F (19 pages) — общий пул для levels (graphics 02..04 + tracks)
#62..#6F (14 pages) — для button atlases, scene-specific
#79..#7F (7 pages)  — для extra scenes ZX7
#89..#FF (119 pages) — для levels 02..22 canvases + tracks
```

### Предлагаемое расширенное mapping (full game)

```
=== Static (code + sprites + system) ===
#02       main1.bin              [16K — нужно освободить от TrackData INCBIN]
#05       main0.bin              [16K — code]
#06..#09  frog_p0..p3            [4 pages — frog sprite]
#0A..#0B  balls + skull atlases  [2 pages]
#0C..#0D  level preview + LVLINTRO atlas
#10..#18  boot canvas            [9 pages]
#19..#1C  sky atlas              [4 pages — может быть shared между LS/Start/MG]
#29..#2C  pyramid overlay        [4 pages]
#40..#4D  balls DMA + killzone   [14 pages]
#4E..#4F  dispname atlas         [2 pages]
#50..#51  gameover + lvlintro text [2 pages]
#52..#53  level preview tiles    [2 pages]
#60       runtime palette extras
#61       runtime palettes pool

Subtotal static: ~54 pages

=== Per-scene (LS / Start / More Games) ===
#70..#78  Level Select scene ZX7 (9 pages)
#79..#81  Start Screen scene ZX7 (9 pages)
#82..#8A  More Games scene ZX7 (9 pages)
#62..#63  Level Select buttons atlas (2 pages, scene-specific)
#64..#65  Start Screen buttons (2 pages)
#66..#67  More Games buttons (2 pages)

Subtotal scenes: ~33 pages

=== Per-level (22 unique graphics × 7 pages compressed-tight) ===
#8B..#93  level_01 canvas ZX7 (7 pages, tight)
#94..#9C  level_02 canvas ZX7
...
#FB..#103 level_22 canvas ZX7
(22 × 7 = 154 pages)

Subtotal canvases: 154 pages

=== Tracks (13 unique, packed 2-per-page) ===
#104..#10A  tracks_01_02_zx7, tracks_03_04_zx7, ..., tracks_13_alone (7 pages)

Subtotal tracks: 7 pages

=== Reserved ===
#10B..#FF (5 pages) — резерв для audio, animations, debug

=== Runtime workspace (decoded buffers, not in spgbld) ===
#20..#28  Canvas B (9 pages) — runtime decoded current scene
#30..#38  Golden (9 pages) — pristine current level for blits
#54..#5C  LS scene decoded (если на LS scene)

Workspace: 27 pages (runtime, не в .spg)

TOTAL: 54 + 33 + 154 + 7 + 5 = 253 pages allocated в .spg
       + 27 runtime workspace = 280 used. Но workspace **shared** с static pages.
```

Реально 253 pages в .spg, + workspace mapping динамически.

---

## Архитектурные изменения для реализации

### Шаг 1: Освободить main1.bin от TrackData INCBIN
Сейчас `INCBIN level_01.bin` пишет 10596 байт в `#969C..#BFFF` (slot 2 page #02). Это:
- Фиксирует main1.bin в зависимость от **конкретного** level (нельзя сменить track без пересборки).
- Перетирает auto-allocated labels данных, если код растёт.

Решение: TrackData как **отдельная page** (`Block = #4000, #02, code.bin` + `Block = #4000, #03, track_data.bin`). Runtime PAGE3 → нужная track page при чтении.

### Шаг 2: Per-level track storage
Каждый track в свою (или половину) page. Runtime PAGE3 switch при level start. Build pipeline:
```
src/Python/make_track.py level_N.txt → level_N.bin → level_N_zx7.bin → page #X
```

### Шаг 3: Per-scene pages (LS/Start/MoreGames)
Каждый scene уже имеет свой ZX7-stream pool. Просто добавить блоки:
```
Block = #4000, #79..#81, start_screen_canvas_pN_zx7.bin
Block = #4000, #82..#8A, more_games_canvas_pN_zx7.bin
```

### Шаг 4: Per-level canvas pages
22 unique graphics × 7 (tight) или 9 (current) pages. Прямое расширение текущей схемы.

### Шаг 5: Sym layout refactor
- DirX/Y, CosTab, SinTab, Levels* tables → **перед** INCLUDE level_select.asm в main asm (низкие адреса).
- Palette INCBIN-дубликаты → удалить (они уже на page #61).
- TrackData INCBIN → переехать в отдельную page или INCBIN в SAVEBIN-block.

---

## Что отдать Codex'у на 19:00

Этот документ — **scope/план**. Конкретный refactor требует:
1. Создать `make_track_compressed.py` (ZX7 pack tracks).
2. Расширить `spgbld.ini` с per-level/per-scene blocks.
3. Переписать `LevelSelect_GotoGame` чтобы загружать track из назначенной page (с decompression если ZX7).
4. Удалить `INCBIN level_01.bin` в main1 в пользу dynamic page mapping.
5. Сделать **scene loader pattern** (общая функция: `LoadSceneFromZX7Pages(start_page, dst_canvas)`).

Codex может это сделать осознанно сразу. До 19:00 я **не трогаю** — остаюсь на baseline `2026-05-15_sfile_isolation`.
