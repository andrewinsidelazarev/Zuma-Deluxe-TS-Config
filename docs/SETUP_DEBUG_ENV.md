# Среда отладки Zuma (TS-Conf + VDAC2) — setup для нового разработчика

Инструкция написана для разработчика и его ИИ-агента с пустой памятью. Описывает все эмуляторы и симуляторы, использовавшиеся в проектах Zuma TS-Conf (`c:/z80/zuma/`) и Zuma VDAC2 (`Desktop/Zuma Deluxe VDAC2/`).

---

## 0. TL;DR — что у нас есть

| Инструмент | Платформа | Назначение | Скорость | Расположение |
|---|---|---|---|---|
| **`zuma_ts_emulator.py`** | TS-Conf | Z80 + страничная память + FM_EN bank (CRAM/SFILE) | ~30 мс на функцию | `c:/z80/zuma/` |
| **`zuma_full_z80_emulator.py`** | VDAC2 | Z80 + paging + FT812 SPI/RAM_G mock | ~30 мс | `Desktop/Zuma Deluxe VDAC2/Source/OTHER/` |
| **`zuma_z80_simulator.py`** | VDAC2 | kosarev/z80 flat 64K (быстрый, без paging) | ~1 мс | `Desktop/Zuma Deluxe VDAC2/Source/OTHER/` |
| **`vdc_visual_emulator.py`** | Cross-platform | Chain physics + tkinter visualization | real-time | `Desktop/Zuma Deluxe VDAC2/Source/OTHER/` |
| **`visual_emulator.py`** | Cross-platform | Frog/cursor tkinter prototyping (legacy) | real-time | `Desktop/Zuma Deluxe VDAC2/Source/OTHER/` |
| **`full_vdc_simulation.py`** | Cross-platform | Stochastic VDC test (50+ random runs) | секунды | `Desktop/Zuma Deluxe VDAC2/Source/OTHER/` |
| **Unreal x64** | TS-Conf + VDAC2 | Spectrum hardware emulator (финальный target) | real-time | `Desktop/unreal_x64/Unreal.exe` |

Z80 harness'ы используются для **байт-точной отладки логики** (порядок init, очистка памяти, целостность стека, layout overflow). Visual emulators — для **прототипирования параметров** до asm. Unreal — для финального sanity-check на «железе».

---

## 1. Системные требования

- **OS:** Windows 10/11 (тестировалось на Windows Server 2022). Linux/WSL2 тоже работает.
- **Python 3.12** (3.10+ должно работать, но проверено на 3.12). Установлен `pip`.
- **PowerShell** (Windows) или bash.
- **Git** (опционально, для clone репозиториев).

### Опциональные компоненты

- **Visual Studio Build Tools 2022** (Windows, C++ workload) — **только если** нужен `kosarev/z80` native build для `zuma_z80_simulator.py`. Если работаешь только с harness'ами на cburbridge — не нужен.
- **Unreal x64** — Spectrum emulator с поддержкой TS-Config и VDAC2. Скачать с unrealspeccy.org или взять у автора проекта.

---

## 2. Установка Python зависимостей

```powershell
# Базовый Python (PIL для visual emulators)
pip install Pillow numpy

# Опционально — kosarev/z80 (нужен только для zuma_z80_simulator.py).
# Требует VS Build Tools.
# В PowerShell сначала запустить vcvars64.bat (или vcvarsx86_amd64.bat для x64):
& "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
pip install z80
```

**Если `pip install z80` падает с ошибкой компиляции** — это не блокер. Pure-Python Z80 core лежит в проектах как `_z80_lib_cburbridge/` и не требует компиляции. Все основные harness'ы (`zuma_ts_emulator.py`, `zuma_full_z80_emulator.py`) используют именно его.

---

## 3. Структура проектов

### TS-Conf Zuma (`c:/z80/zuma/`)
```
c:/z80/zuma/
├── sjasmplus.exe              # ассемблер Z80 (= local copy of tool)
├── spgbld.exe                 # упаковщик .spg для TS-Config
├── zuma_new_spg.asm           # главный asm-файл (главный код игры)
├── level_select.asm           # модуль экрана выбора уровня
├── spgbld.ini                 # описание pages для .spg
├── zuma.spg                   # последняя сборка (target для Unreal)
├── zuma.sym                   # symbol table (нужна для harness)
├── main0.bin, main1.bin       # auto-generated assembled binaries
├── level_01.bin, frog_*.bin, balls*.bin, ...    # графика/тайлы/палитры
├── zuma_ts_emulator.py        # NEW: TS-Conf Z80 harness
└── _z80_lib_cburbridge/       # NEW: pure-Python Z80 core (copy from VDAC2)
```

Канонические опорные версии (baselines): `*_baseline_<date>_<descriptor>.{asm,spg,ini}`. Самая свежая — `2026-05-15_sfile_isolation`.

### VDAC2 Zuma (`Desktop/Zuma Deluxe VDAC2/`)
```
Desktop/Zuma Deluxe VDAC2/
├── Source/
│   ├── ASM/                   # asm-файлы (main.asm, VDC.asm, Frog.asm, Bullet.asm, MainLoop.asm)
│   └── OTHER/
│       ├── zuma_z80_simulator.py            # kosarev/z80 flat 64K
│       ├── zuma_full_z80_emulator.py        # cburbridge + paging + FT812
│       ├── vdc_visual_emulator.py           # chain physics tkinter
│       ├── visual_emulator.py               # frog tkinter
│       ├── full_vdc_simulation.py           # stochastic VDC test
│       ├── make_*.py                        # генераторы графики
│       └── _z80_lib_cburbridge/             # pure-Python Z80 core
├── Graphics/                  # PNG источники + конвертированные bin
├── Docs/
│   ├── uchebnik_tsconf_vdac2.md             # учебник по VDAC2
│   └── ft812_profiler_guide.md
├── spgbld_vdac2.ini           # описание pages для .spg
├── zuma_vdac2.spg             # последняя сборка
└── zuma_vdac2.sym             # symbol table
```

### Альтернатива: всё из TS-Conf GitHub репо

Все упомянутые эмуляторы и harness'ы также опубликованы в TS-Conf репо как референсные копии:

```
https://github.com/andrewinsidelazarev/Zuma-Deluxe-TS-Config/tree/main/src/Python/
├── zuma_ts_emulator.py
├── zuma_full_z80_emulator.py     # VDAC2 emulator (reference copy)
├── zuma_z80_simulator.py         # VDAC2 simple (reference copy)
├── vdc_visual_emulator.py        # chain physics tkinter
├── visual_emulator.py            # frog tkinter (reference copy)
├── full_vdc_simulation.py        # stochastic VDC test (reference copy)
└── _z80_lib_cburbridge/          # pure-Python Z80 core
```

Если работаешь только с TS-Conf — клонируй репо и всё нужное под рукой.

---

## 4. Сборка проекта (нужна, чтобы harness'ы могли работать)

Harness'ы читают `*.sym` и `main*.bin`, которые создаются при сборке asm. Если их нет — сначала собери проект.

### TS-Conf
```powershell
cd c:\z80\zuma
.\sjasmplus.exe zuma_new_spg.asm --lst=user.l --sym=zuma.sym
.\spgbld.exe -b spgbld.ini zuma.spg
```

После — `main0.bin`, `main1.bin`, `zuma.sym`, `zuma.spg` готовы.

### VDAC2
```powershell
cd "C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2"
.\build.cmd
```

(внутри `build.cmd` есть absolute пути к sjasmplus и spgbld из `c:\z80\tsconf_project\exe\`).

---

## 5. Запуск Z80 harness'ов

### TS-Conf — `zuma_ts_emulator.py`

```powershell
cd c:\z80\zuma

# Test 1: SFILE isolation (проверка, что LevelSelect_Init очищает stale Game descriptors)
python zuma_ts_emulator.py --test-isolation
# Ожидаемый результат: PASS: SFILE fully cleared (510/510 bytes zeroed, isolation works)

# Test 2: Целостность стека для любого symbol
python zuma_ts_emulator.py --test-stack --symbol InitPalette
# Выведет: SP balance, min SP (max stack used), sentinel intact

# Общий запуск: вызвать функцию и сообщить состояние
python zuma_ts_emulator.py --call InitPalette

# Полная трассировка (для глубокого debug — лог инструкций)
python zuma_ts_emulator.py --call InitPalette --trace
```

**Что внутри:** Pure-Python Z80 core (cburbridge) + TS-Config paging (`PAGE0..3` через `#10AF..#13AF`) + FM_EN bank model (CRAM `#0000..#01FF` + SFILE `#0200..#03FF` через `#15AF`) + Mouse `#FADF` + Kempston `#xx1F` + RTC `#BFF7` + DMA mock (always-idle, чтобы не висеть в DMA wait loop).

**Что НЕ моделируется:** TSU rendering (descriptors не превращаются в пиксели), DMA-engine (только статус DMAWNR=0 fake), точный display refresh timing. Для этого — Unreal.

### VDAC2 — `zuma_full_z80_emulator.py`

```powershell
cd "C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2"
python Source\OTHER\zuma_full_z80_emulator.py --call Core.VDC_Init
python Source\OTHER\zuma_full_z80_emulator.py --frames 100
```

**Что внутри:** То же что TS-Conf harness + FT812 RAM_G/RAM_DL/RAM_CMD mock через SPI ports (#57, #77).

**Use case:** проверка VDC physics, chain logic, palette transitions, regression testing. `--frames N` запустит N кадров `game_frame()` который вызывает `ZL_AimUpdate / Frog_Update / VDC_Update / Bullet_Update / Bullet_CheckCollision / ZL_DrawFrame`.

### VDAC2 — `zuma_z80_simulator.py` (быстрый, без paging)

```powershell
cd "C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2"
python Source\OTHER\zuma_z80_simulator.py
python Source\OTHER\test_tail_glitch.py   # specific scenario test
```

**Когда использовать:** короткие узкие тесты VDC логики без paging (всё в slot 2). Быстрее full emulator потому что нет paging overhead и FT812 mock.

**Требует:** `pip install z80` (kosarev/z80, native C extension). Если не установлен — используй `zuma_full_z80_emulator.py` с тем же эффектом.

---

## 6. Запуск visual emulators (chain physics, frog)

### `vdc_visual_emulator.py` — Chain physics

```powershell
cd "C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2\Source\OTHER"
python vdc_visual_emulator.py
```

Откроет tkinter окно с цепочкой шаров на треке. Стреляешь мышью, видишь chain physics, match-3, cascade. Используется для прототипирования параметров (CELL_SIZE, decay, gap behavior) **до** портирования в asm.

### `visual_emulator.py` — Frog tester (legacy)

```powershell
python visual_emulator.py
```

Старый frog/cursor prototyping tool. Использовался для калибровки rotation, hemisphere insert до asm-имплементации в Frog.asm.

### `full_vdc_simulation.py` — Stochastic test

```powershell
python full_vdc_simulation.py
```

Stochastic test 50+ random runs — проверка VDC invariants (no double-counted slots, chain length consistency). Используется как regression catch для VDC logic changes.

---

## 7. Запуск на «железе» — Unreal x64

После того как harness PASS, финальный sanity check на real-style hardware:

```powershell
# TS-Conf
Start-Process "C:\Users\Администратор\Desktop\unreal_x64\Unreal.exe" "c:\z80\zuma\zuma.spg"

# VDAC2
Start-Process "C:\Users\Администратор\Desktop\unreal_x64\Unreal.exe" "C:\Users\Администратор\Desktop\Zuma Deluxe VDAC2\zuma_vdac2.spg"
```

**Важно:** в `Unreal.ini` должен быть включён режим Renderer "Double size" (через `video=double`) и driver=gdi + SoundDrv=none для headless VM (Windows Server 2022).

---

## 8. SOP отладки регрессий

При любой регрессии (что-то работало, после изменений сломалось) применять 5-шаговый SOP:

1. **Зафиксировать артефакты:** GOOD baseline + BAD build + конкретный symptom + trigger (минимальный repro).
2. **Разделить ресурсы и код:** byte-diff SPG-файлов (через `spgbld -u` распаковать обе сборки и сравнить страницы). Если отличаются только code pages — идти к шагу 4. Если данные — шаг 3.
3. **Transform/pipeline verify:** прогнать существующий asm-декомпрессор (например `Dzx7Turbo`) на bad данных через harness, сравнить выход с golden reference.
4. **Runtime state:** найти **первый момент**, где state расходится с expected. Поставить probes через `--trace` или snapshot CRAM/SFILE/pages в keypoints.
5. **Минимальный fix:** harness red → green → железо. До фикса harness падает, после — проходит, ТОЛЬКО потом сборка на Unreal.

**Главное правило:** rejected hypothesis должна иметь причину в виде **байта, состояния или трассы**. «Не похоже» не считается. Harness даёт байты и трассы — используй.

Полная инструкция SOP — в memory ИИ-агента (`feedback_regression_binary_elimination_sop.md`, помечена ⭐⭐).

---

## 9. Архитектурные правила (память между сценами)

### Правило изоляции Level Select vs Game

**Level Select** (Scene=1) и **Game** (Scene=0) — отдельные функциональные модули с раздельной памятью. Shared только:
- декомпрессор (`Dzx7Turbo`),
- таблица счетов,
- минимальное время прохождения уровня,
- **логика управления** (мышь/клавиатура, `MouseBtnFireFlag`, `MouseBtnPrev`),
- **текущий уровень игры** (`CurStageIdx`, `LvlInStage`),
- **текущая сложность игры**,
- runtime palette page #61 (frog/cursor/balls/bg/gameover).

**Всё остальное — раздельное.** В TS-Conf физически невозможно дать LS и Game разные SPAL/SFILE/TSU pages одновременно (мало места). Изоляция **temporal** — через scene init/exit полную перезапись:
- `InitGame` (Game side): SFILE clear `#0200..#03FD` + `InitPalette` (CRAM #0000..#01FF из page #61) + LVLINTRO atlas restore в TSU page #0D.
- `LevelSelect_Init` (LS side): SFILE clear `#0200..#03FD` + LS palettes (preview SPAL=0 + dispname SPAL=2 + LevelSelectPalette в CRAM #0100..#01FF) + preview tiles LDIR в TSU pages #0C/#0D.

Anti-pattern: «На LS balls SPAL=4 не используется → используем её для buttons». **Запрещено.** Сцены не «одалживают» SPAL/page/descriptors друг у друга.

Полное правило — в memory `feedback_zuma_levelsel_game_isolation.md` (⭐⭐).

---

## 10. Базовые asm-конвенции TS-Conf (важно для harness)

- **Ports** TS-Conf — 16-bit с high byte register selector + `0xAF` low. Например `PAGE3 = #13AF`. В harness `out_port` смотрит low byte = `0xAF`, потом по high byte выбирает register.
- **FM_EN bank** — при `OUT #15AF, #10` любые `LD (HL),x` по адресам `#0000..#03FF` идут в CRAM/SFILE bank, не в RAM. После `OUT #15AF, 0` нормальный доступ восстанавливается. Это **обязательная** модель для harness — без неё clear SFILE loop пишет в обычную RAM, не в SFILE.
- **`Stack` в `spgbld.ini`** — определяет начальное SP. Обычно `0xC000` (TS-Conf, стек растёт вниз в slot 2).
- **Layout overflow** — частая проблема. TrackData с `ORG #969C` в slot 2 + INCBIN `level_01.bin` size 10596 bytes заполняет `#969C..#BFFF`. Auto-allocated labels кода/данных ДО `ORG #969C` обязаны помещаться `#8000..#969C` = ~5800 bytes. После добавления нового кода в `level_select.asm` или main asm — проверять `zuma.sym` на labels выше #969C.

---

## 11. Полезные шорткаты

```powershell
# Быстрая сборка + запуск Unreal (TS-Conf)
cd c:\z80\zuma
.\sjasmplus.exe zuma_new_spg.asm --sym=zuma.sym ; .\spgbld.exe -b spgbld.ini zuma.spg ; Start-Process "C:\Users\Администратор\Desktop\unreal_x64\Unreal.exe" "zuma.spg"

# Проверка labels > #969C (overlap detection)
Select-String "EQU 0x0000(96|97|98|99|9[A-F]|A|B)" zuma.sym | Sort-Object

# Byte-diff двух SPG (для bisect регрессий)
.\spgbld.exe -u zuma_good.spg ; .\spgbld.exe -u zuma_bad.spg
python -c "import glob; ..."   # см. шаблон в SOP
```

---

## 12. Дальнейшее чтение

- `Desktop/Zuma Deluxe/docs/Программирование для tsconfig.md` — учебник по TS-Config. Глава 20 — про harness.
- `Desktop/Zuma Deluxe/docs/uchebnik/index.html` — то же в HTML.
- `Desktop/Zuma Deluxe VDAC2/Docs/uchebnik_tsconf_vdac2.md` — учебник по VDAC2.
- `MEMORY.md` (memory ИИ-агента) — индекс всех memory-файлов с feedback/правилами проекта.

---

## 13. Чек-лист «новый разработчик за час»

- [ ] Установить Python 3.12 + Pillow + numpy.
- [ ] Получить копии проектов `c:/z80/zuma/` и `Desktop/Zuma Deluxe VDAC2/` (от автора или из git).
- [ ] Собрать TS-Conf: `sjasmplus + spgbld → zuma.spg`. Проверить, что `zuma.sym` и `main1.bin` существуют.
- [ ] Запустить `python c:\z80\zuma\zuma_ts_emulator.py --test-isolation` → ожидаемо PASS.
- [ ] Запустить `python c:\z80\zuma\zuma_ts_emulator.py --test-stack --symbol InitPalette` → ожидаемо PASS.
- [ ] Запустить Unreal с `zuma.spg` → увидеть Level Select экран.
- [ ] Прочитать память `feedback_regression_binary_elimination_sop.md` (SOP) и `feedback_zuma_levelsel_game_isolation.md` (правило изоляции).

Если все пункты PASS — среда готова. Если на этапе harness что-то FAIL — это уже **diagnostic** информация: значит сборка отклонилась от baseline. Repro baseline через копирование `*_baseline_2026-05-15_sfile_isolation.{asm,spg,ini}` поверх current.
