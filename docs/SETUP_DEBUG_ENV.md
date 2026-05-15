# Отладка кода для Z80-совместимых ретро-компьютеров с помощью ИИ-агента

Документ описывает методологию динамической отладки для ИИ-агентов, работающих над проектами под Z80-совместимые ретро-платформы (ZX Spectrum, ZX Evolution / TS-Config, Pentagon, VDAC2/FT812 над TS-Config, и т. п.). Содержит **4 уровня глубины эмуляции**, обоснование когда какой уровень нужен, и worked example для ZX Evolution / TS-Config в приложении.

---

## 0. Постановка проблемы

Стандартный workflow разработки для Z80-ретро выглядит так:

```
asm-исходник → assembler (sjasmplus/pasmo/...) → linker/packer (spgbld/hobeta/...) → image (.spg/.tap/.trd/...) → эмулятор (Unreal Speccy/Fuse/...) → видимый результат + дампы
```

Разработчик-человек запускает эмулятор сам и видит результат глазами. **ИИ-агент** в этом цикле упирается в фундаментальное ограничение: **у ИИ нет прямого доступа к ресурсам эмулятора**:

- Не может сам нажать «запустить» в Unreal Speccy и увидеть, что происходит.
- Не может прочитать live дамп памяти после произвольного количества кадров.
- Не может поставить breakpoint и инспектировать state on-the-fly.
- Не может запустить, прокликать GUI, дойти до конкретного game-state и пощупать переменную.

Всё, что ИИ получает от эмулятора — это **посредничество человека**: «запусти», «пришли скриншот», «сделай дамп», «скажи, что увидел». Это **статичный feedback** с задержкой в десятки секунд на каждую итерацию. Для логических багов (порядок init, целостность стека, layout-overflow, регрессии после рефакторинга) такая обратная связь слишком слабая и слишком дорогая.

**Решение** — построить вокруг проекта **стек эмуляций нарастающей глубины**, чтобы ИИ-агент мог большую часть отладки сделать **сам**, без выхода на железо/Unreal через посредника. Финальная проверка на «железе» остаётся, но включается только в самом конце.

---

## 1. Четыре уровня глубины эмуляции

### Уровень 1 — скриншоты и статичные дампы памяти

**Что это:** Человек запускает эмулятор, играет до интересующего момента, делает скриншот и/или дамп памяти, шлёт ИИ.

**Что даёт ИИ:**
- Финальный визуальный результат (картинка) — для проверки эстетики/UX.
- Снимок состояния в один момент времени (дамп) — для проверки конкретных байтов в RAM/VRAM/CRAM/etc.

**Ограничения:**
- Статика. Чтобы получить состояние **до** и **после** какого-то события — нужны два прогона человеком, два дампа.
- Высокая стоимость итерации (десятки секунд + внимание человека).
- Не работает для редких/race условий — пока человек воспроизведёт нужный момент, иногда уходит десяток попыток.
- ИИ не может сам поставить probe в произвольной точке выполнения.

**Когда применим:** финальная проверка визуала, sanity-check «хотя бы запускается», первичное воспроизведение симптома.

### Уровень 2 — Python-симулятор технического задания (gameplay model)

**Что это:** Python-программа, которая **воспроизводит логику задачи** (например, физику цепочки шаров) **в Python**, без эмуляции Z80. Алгоритмы и формулы те же, что планируется реализовать на ассемблере, но язык — Python.

**Что даёт ИИ:**
- Полный контроль над симуляцией: можно вызвать любую функцию, проинспектировать любую переменную, поставить breakpoint в Python-отладчике.
- Быстрая итерация: запуск миллисекунды, рефакторинг секунды.
- Удобная визуализация (matplotlib, tkinter) — chain в окне, frog движущийся за курсором.
- Стохастическое тестирование: прогон 50+ random scenarios для проверки инвариантов.

**Ограничения — главное:**
- **Python ≠ Z80.** Симулятор работает на 64-bit арифметике с автоматическим расширением, у него нет понятия carry-flag, signed-vs-unsigned 8-bit, banking, self-modifying code.
- Баги класса «carry лишний раз сбросило», «signed compare через unsigned SBC», «PUSH в banking-switch» — Python-симулятор **не поймает в принципе**, потому что этих понятий в нём нет.
- Соответствие Python ↔ asm нужно проверять руками; легко разойтись после рефакторинга.

**Когда применим:** прототипирование алгоритмов до asm; проверка ИДЕЙ (не реализаций) на корректность; UX-эксперименты (параметры физики, скорости, decay).

**Anti-pattern:** «В Python работает, значит на Z80 заработает». Не значит.

### Уровень 3 — эмуляция железа на Python (chip emulator + ports)

**Что это:** Python-программа, которая реализует **сам процессор Z80** (instruction set, регистры, флаги) и **периферию платформы** (страничная память, порты ввода-вывода, специальные регистры). Не отдельный gameplay, а полный stack «процессор + железо».

**Готовые компоненты:** есть несколько публичных Python-реализаций Z80 — `kosarev/z80` (нативный C++, через pip), `cburbridge/python-z80` (pure-Python), и др.

**Что даёт ИИ:**
- Z80-точную семантику: carry, half-carry, signed/unsigned, banking, IRQ.
- Возможность загрузить **тот же** assembled .bin/.spg/.tap, что пойдёт на железо, и исполнить его инструкция за инструкцией.
- Catches Z80-специфические баги (которые Python-симулятор не видит).

**Ограничения:**
- Сам по себе chip emulator знает только «процессор + 64KB RAM + порты». Не знает специфику ВАШЕЙ платформы: какой порт что делает, какие страницы есть, как работает видео.
- Without периферии — модель неполная. Загрузить .spg в голый Z80 эмулятор обычно невозможно: нужен SPG-loader, paging, mapped ports, специальные регионы памяти типа CRAM/SFILE.

**Когда применим:** короткие unit-style тесты алгоритмов на чистом Z80 без сильной зависимости от периферии (математика, обработка массивов, разворачивание битов).

### Уровень 4 — Harness (chip emulator + проектная обвязка)

**Что это:** **Самый глубокий уровень.** Берём chip emulator (Уровень 3) и **достраиваем вокруг него**:

1. **Memory model** платформы (страничная память, банкование, специальные регионы типа CRAM/SFILE/Tilemap).
2. **Mocks для портов** ввода-вывода (видео-регистры, DMA-status, mouse, keyboard, RTC).
3. **Loader** для проектного image-формата (.spg, .tap, .trd) — кладёт байты файлов в нужные страницы памяти ровно так же, как делает реальное железо/эмулятор при загрузке.
4. **Sym-table integration** — парсит таблицу символов от ассемблера, чтобы можно было вызывать функции **по имени**, не по адресу.
5. **API для ИИ** — `emu.call("MyFunction")`, `emu.get_byte(addr)`, `emu.snapshot_sfile()`, и т. п. — высокоуровневые операции для написания тестов.

**Что даёт ИИ:**
- **Динамический цикл отладки** без посредника. ИИ пишет Python-тест, запускает, читает байты результата, формулирует следующую гипотезу.
- **Pre-inject state**: «представь, что игра только что закончилась с такой-то цепью» → залить SFILE байтами → вызвать функцию → проверить, как обработала.
- **First-divergence detection** для регрессий: snapshot state в good baseline, тот же snapshot в bad — diff даёт **первый расходящийся байт**.
- **Stack integrity tracking**: sentinel-байты на границе, min-SP за весь прогон, баланс SP до/после CALL.
- **Trace-режим**: лог каждой инструкции, видно в какой именно строке state расходится с ожиданием.

**Ограничения:**
- Видео-rasterizer (превращение descriptors/tilemaps в пиксели) обычно НЕ моделируется — это много работы и редко нужно для логических багов.
- Точный пиксель-clock, race условия видео-обновлений — частично через t-state count, точнее на железе.
- DMA-engine (если есть на платформе) — обычно проще mock'нуть как «всегда idle», чем точно эмулировать.

**Когда применим:** **по умолчанию** для любой логической отладки. Static disasm подтверждает «байты собрались правильно», harness — «эти байты на runtime делают правильную вещь». Вместе они закрывают почти весь класс багов, которые на Уровнях 1–2 ловятся медленно или вообще не воспроизводятся.

---

## 2. Динамический цикл отладки

С harness'ом (Уровень 4) ИИ-агент получает SOP, который **не требует выхода на железо** для большинства итераций. Базовая схема SOP для регрессий:

1. **Зафиксировать артефакты:** GOOD baseline + BAD build + точный symptom + минимальный repro.
2. **Разделить ресурсы и код:** byte-diff собранных images. Если отличаются только code pages — баг в логике (шаг 4). Если данные — pipeline (шаг 3).
3. **Transform/pipeline verify:** harness прогоняет **существующий** asm-декомпрессор/упаковщик на bad-данных, output сравнивается с golden reference. Не переписывать на Python — выполнять реальный asm-код в harness.
4. **Runtime state:** найти **первый момент**, где state расходится с expected. В harness — поставить probes (snapshot CRAM/SFILE/registers) в keypoints, найти точку расхождения.
5. **Минимальный fix:** harness red → harness green → metal. До фикса тест падает, после — проходит. **Только потом** сборка идёт на железо/Unreal как финальный sanity-check.

**Главное правило:** rejected hypothesis обязана иметь причину в виде **байта, состояния или трассы**. «Не похоже» не считается. Harness даёт байты и трассы в виде Python output — без необходимости открывать GUI отладчика или просить человека сделать дамп.

**Цикл итерации:**
- Уровень 1 (скриншот): десятки секунд + внимание человека.
- Уровень 4 (harness): миллисекунды, ИИ-агент сам.

Если задача 100 итераций — разница 1000× по времени и денежной стоимости работы агента.

---

## 3. Что обычно нужно скачать/установить

Минимальный стек инструментов для построения 4-уровневой пирамиды на любой Z80-платформе:

| Уровень | Инструмент | Тип | Установка |
|---|---|---|---|
| 0 (build) | **Ассемблер** для Z80 | OS binary | sjasmplus / pasmo / z80asm — обычно standalone .exe |
| 0 (pack) | **Linker/packer** проектного формата | OS binary | Платформо-зависимо: spgbld для TS-Config, hobeta для TR-DOS, etc |
| 1 | **Эмулятор платформы** | OS binary | Unreal Speccy (ZX/TS-Config), Fuse, ZX-Spin, vAmos, RetroVirtualMachine |
| 2–3 | **Python 3.10+** | runtime | python.org installer |
| 2 | **Pillow, numpy, matplotlib** (для визуальных симуляторов) | pip | `pip install Pillow numpy matplotlib` |
| 3 | **Z80 chip emulator на Python** | pip / source | `pip install z80` (kosarev — native) **или** скопировать `cburbridge/python-z80` как pure-Python lib |
| 4 | **Harness под конкретную платформу** | пишется самостоятельно | см. ниже шаблон |
| (опц.) | **Visual Studio Build Tools** | OS toolchain | Только если `pip install z80` — для нативной компиляции |

### Шаблон harness под Z80-платформу

```python
from pathlib import Path
import sys
sys.path.insert(0, "path/to/python-z80/src")
from z80 import instructions, registers, util

class PlatformMemory:
    """64K address space + page bank table + специальные регионы платформы."""
    def __init__(self):
        self.physical = bytearray(NUM_PAGES * PAGE_SIZE)
        self.pages = [0, 0, 0, 0]   # default slot mapping
        # Платформо-специфичные банки:
        self.cram = bytearray(...)  # для TS-Config
        self.tilemap = bytearray(...)
        self.fm_en = False

    def read(self, addr):
        if self.fm_en and ...: return self.cram[...]
        return self.physical[self.pages[addr >> 14] * PAGE_SIZE + (addr & 0x3FFF)]

    def write(self, addr, value):
        # симметрично

class Emulator:
    def __init__(self, root):
        self.sym = parse_sym(root / "project.sym")
        self.mem = PlatformMemory()
        self.reg = registers.Registers()
        self.ins = instructions.InstructionSet(self.reg)
        self._load_image_blocks(root / "project.spg")  # SPG/TAP loader
        self.reg.SP = 0xC000
        self.reg.PC = self.sym.get("Start")
        self.min_sp = self.reg.SP

    def step(self):
        op = self.mem.read(self.reg.PC)
        ins, args = self.ins << op
        # ... execute ...
        if self.reg.SP < self.min_sp:
            self.min_sp = self.reg.SP   # max-depth tracking

    def call(self, addr, max_steps=200000):
        # CALL convention: push return-marker, set PC, step until return
        ...

    def out_port(self, port, value):
        # mock платформо-специфичных регистров
        if port == PAGE0_PORT: self.mem.pages[0] = value
        elif port == FMADDR_PORT: self.mem.fm_en = bool(value & FM_EN_BIT)
        # ...
```

Полный рабочий harness под TS-Config — ~400 строк Python. См. приложение для конкретного примера.

---

## 4. Приложение: ZX Evolution / TS-Config — worked example

Конкретные инструменты, пути и команды для платформы, которую мы используем в проектах Zuma TS-Conf и Zuma VDAC2 (FT812 over TS-Config).

### Инструменты

| Уровень | Инструмент | Источник | Расположение |
|---|---|---|---|
| 0 | **sjasmplus** | github.com/z00m128/sjasmplus | `c:\z80\tsconf_project\exe\sjasmplus\sjasmplus.exe` |
| 0 | **spgbld** | TS-Labs | `c:\z80\tsconf_project\exe\spgbld\spgbld.exe` |
| 1 | **Unreal Speccy** | unrealspeccy.org | `Desktop\unreal_x64\Unreal.exe` |
| 2 | **vdc_visual_emulator.py** | own (in repo) | `src/Python/vdc_visual_emulator.py` |
| 2 | **visual_emulator.py** | own | `src/Python/visual_emulator.py` |
| 2 | **full_vdc_simulation.py** | own (stochastic test) | `src/Python/full_vdc_simulation.py` |
| 3 | **kosarev/z80** | pypi | `pip install z80` (требует VS Build Tools) |
| 3 | **_z80_lib_cburbridge** | github.com/cburbridge/python-z80 | копия в `src/Python/_z80_lib_cburbridge/` |
| 4 | **zuma_ts_emulator.py** | own (this project) | `src/Python/zuma_ts_emulator.py` |
| 4 | **zuma_full_z80_emulator.py** | own (VDAC2 variant) | `src/Python/zuma_full_z80_emulator.py` |
| 4 | **zuma_z80_simulator.py** | own (kosarev-based, simpler) | `src/Python/zuma_z80_simulator.py` |

### TS-Config-специфика, которую harness должен моделировать

- **Страничная память:** 4 слота × 16 КБ. Порты `PAGE0..3` = `#10AF..#13AF` (low byte `0xAF`, high byte = register number `0x10..0x13`).
- **FM_EN bank:** порт `FMADDR = #15AF`, бит `#10` (`FM_EN`). При установке бита адреса `#0000..#03FF` идут в отдельные банки **CRAM** (`#0000..#01FF`, палитры) и **SFILE** (`#0200..#03FF`, дескрипторы TSU-спрайтов). При сбросе бита — обычная RAM.
- **PALSEL:** порт `#07AF` — селектор палитры.
- **Mouse:** Kempston-протокол через порты `#FBDF` (X), `#FFDF` (Y), `#FADF` (buttons).
- **RTC:** порт `#BFF7` — секунды в BCD.
- **DMA:** порты `#1AAF..#28AF`. В harness обычно mock'аются как «всегда idle» (`DMAWNR=0`), чтобы не повисать в DMA-wait loop. Реальный DMA-engine моделировать нужно только если конкретный баг в DMA.
- **VDAC2/FT812 (надстройка):** дополнительные порты `0x57`/`0x77` для SPI с FT812. В TS-Config-only проектах не нужны.

### Сборка проекта

```powershell
cd c:\z80\zuma
.\sjasmplus.exe zuma_new_spg.asm --lst=user.l --sym=zuma.sym
.\spgbld.exe -b spgbld.ini zuma.spg
```

После этого `main0.bin`, `main1.bin`, `zuma.sym`, `zuma.spg` готовы — harness может их грузить.

### Запуск harness (Уровень 4)

```powershell
cd c:\z80\zuma

# Test 1: SFILE isolation (pre-inject garbage, call LevelSelect_Init, verify zeroed)
python zuma_ts_emulator.py --test-isolation
# PASS: SFILE fully cleared (510/510 bytes zeroed, isolation works)

# Test 2: целостность стека — sentinel, SP balance, min-SP за прогон
python zuma_ts_emulator.py --test-stack --symbol InitPalette
# PASS: stack balanced, sentinel intact, depth within budget

# Общий вызов любой функции по имени из .sym
python zuma_ts_emulator.py --call InitPalette

# Полный trace (для глубокого debug — лог каждой инструкции)
python zuma_ts_emulator.py --call InitPalette --trace
```

### Финальная проверка (Уровень 1)

После harness PASS — sanity-check на «железе»:

```powershell
Start-Process "C:\Users\Администратор\Desktop\unreal_x64\Unreal.exe" "c:\z80\zuma\zuma.spg"
```

В `Unreal.ini` для Windows Server / headless VM: `driver=gdi`, `SoundDrv=none`, Renderer "Double size".

### Чек-лист «новый разработчик за час»

- [ ] Установить Python 3.12 + `pip install Pillow numpy`.
- [ ] Клонировать репо: `git clone https://github.com/andrewinsidelazarev/Zuma-Deluxe-TS-Config.git`.
- [ ] Скачать sjasmplus + spgbld (или взять из `c:\z80\tsconf_project\exe\`).
- [ ] Скачать Unreal Speccy.
- [ ] Собрать: `sjasmplus + spgbld → zuma.spg`. Проверить, что `zuma.sym` + `main1.bin` есть.
- [ ] Запустить `python src/Python/zuma_ts_emulator.py --test-isolation` — ожидаемо **PASS**.
- [ ] Запустить `python src/Python/zuma_ts_emulator.py --test-stack --symbol InitPalette` — ожидаемо **PASS**.
- [ ] Запустить Unreal с `zuma.spg` → увидеть начальный экран игры.
- [ ] Прочитать учебник: `docs/uchebnik/index.html` (глава 20 — про harness).

Если все пункты PASS — среда готова. Если на этапе harness что-то FAIL — это уже **диагностическая** информация: значит сборка отклонилась от baseline. Repro baseline копированием `*_baseline_*.{asm,spg,ini}` поверх current.

---

## 5. Резюме

Главная идея — **строить пирамиду эмуляций такой высоты, чтобы ИИ-агент мог большую часть отладки сделать сам**. На каждом уровне:

- **Уровень 1** (скриншот): редкий sanity-check, дорогая итерация.
- **Уровень 2** (Python-симулятор): прототип алгоритмов; **не доверять для Z80-семантики**.
- **Уровень 3** (chip emulator): unit-тесты алгоритмов на чистом Z80.
- **Уровень 4** (harness): **рабочий инструмент** для большинства итераций. Pre-inject state, runtime assertions, trace, stack integrity, first-divergence detection.

Без Уровня 4 ИИ-агент работает в режиме «угадай → собери → отправь человеку → подожди ответа». С Уровнем 4 — «гипотеза → тест → байт ответа → следующая гипотеза» в миллисекундной петле. Это и есть **динамический цикл отладки**, которого у ИИ изначально нет в Z80-ретро-разработке и который надо построить осознанно.
