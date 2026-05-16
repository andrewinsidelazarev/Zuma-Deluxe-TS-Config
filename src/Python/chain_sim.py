#!/usr/bin/env python3
"""
Python re-implementation chain physics из zuma_new_spg.asm.
Воспроизводит rigid-body модель: ChainHeadT, ChainColors, ChainOffsets,
ChainStalled, CascadeState/Wait/Delay.

ВНИМАНИЕ: это моя интерпретация asm-логики. Если в asm есть баги,
Python их воспроизведёт. Цель — проверить high-level corner cases.
"""

# Константы (соответствуют EQU в asm)
BALL_DIAMETER       = 18
CELL_SIZE           = 32          # CHAIN_SPACING
CHAIN_SPACING       = CELL_SIZE   # legacy alias
MAX_CHAIN_BALLS     = 60
MAX_SLOTS_PER_CHAIN = MAX_CHAIN_BALLS
TRACK_NUM_POINTS    = 3096
FAST_ADVANCE        = 12
LEVEL_START_BALLS   = 35
LEVEL_REPEAT_BALLS  = 50
LEVEL_TOTAL_BALLS   = LEVEL_START_BALLS + LEVEL_REPEAT_BALLS

CASCADE_SLOWDOWN_DELAY = 10  # frames

GAP = -1  # generic GAP marker (legacy)
GAP_STOP    = -2   # = #FE в ASM, тает с tail-стороны (хвост подъезжает к голове)
GAP_CASCADE = -3   # = #FD в ASM, тает с head-стороны (голова катится к хвосту)
NUM_BALL_COLORS = 3
GAP_STEP_FRAMES = 32

def is_gap(v):
    return v < 0  # любой GAP-маркер (GAP, GAP_STOP, GAP_CASCADE)

# Тип signed-byte в asm для ChainOffsets. Эмулирую через -128..127 clamp.
def sat_byte_signed(v):
    if v > 127: return 127
    if v < -128: return -128
    return v


class ChainSim:
    def __init__(self):
        self.ChainHeadT       = 0
        self.ChainColors      = [0] * MAX_CHAIN_BALLS
        self.ChainOffsets     = [0] * MAX_CHAIN_BALLS  # signed byte
        self.ChainLen         = 0
        self.ChainStalled     = 0
        self.BallsSpawned     = 0
        self.FrameCounter     = 0
        self.CascadeState     = 0
        self.CascadeIdx       = 0
        self.CascadeWait      = 0
        self.CascadeDelay     = 0
        self.NextChainColor   = 0  # для spawn (используем 0..3 цикл для теста)

    def position(self, i):
        """Visual position шара i (по track t-индексам)."""
        return self.ChainHeadT - CHAIN_SPACING * i + self.ChainOffsets[i]

    def gap(self, i):
        """Зазор между шаром i-1 и i. Норма = CHAIN_SPACING."""
        if i <= 0: return CHAIN_SPACING
        return CHAIN_SPACING + self.ChainOffsets[i-1] - self.ChainOffsets[i]

    # ------------------------------------------------------------------
    # MoveChain — HeadT += 1 (либо реверс при cascade, либо стоп при stall)
    # ------------------------------------------------------------------
    def move_chain(self):
        if self.CascadeState != 0:
            # cascade reverse, но с delay для slowdown
            if self.CascadeDelay > 0:
                self.CascadeDelay -= 1
                return
            if self.ChainHeadT > 0:
                self.ChainHeadT -= 1
            return
        if self.ChainStalled != 0:
            return
        if self.ChainHeadT < TRACK_NUM_POINTS - 1:
            self.ChainHeadT += 1
        else:
            self.ChainHeadT = TRACK_NUM_POINTS - 1

    # ------------------------------------------------------------------
    # AnimateChain — decay ChainOffsets к 0. Скорость зависит от ChainStalled.
    # ------------------------------------------------------------------
    def animate_chain(self):
        if self.ChainLen == 0:
            self.ChainStalled = 0
            return
        step = 1 if self.ChainStalled else 4
        any_active = False
        for i in range(self.ChainLen):
            o = self.ChainOffsets[i]
            if o == 0:
                continue
            if o > 0:
                o -= step
                if o <= 0: o = 0
            else:
                o += step
                if o >= 0: o = 0
            self.ChainOffsets[i] = o
            if o != 0:
                any_active = True
        if not any_active:
            self.ChainStalled = 0

    # ------------------------------------------------------------------
    # SpawnChainBall — агрессивный loop: spawn пока есть место
    # Возвращает количество добавленных
    # ------------------------------------------------------------------
    def spawn_chain_ball(self):
        added = 0
        while self.ChainLen < MAX_CHAIN_BALLS:
            # idx = ChainLen, t = HeadT - SPACING * ChainLen, должно >= 0
            if self.ChainLen > 0:
                t = self.ChainHeadT - CHAIN_SPACING * self.ChainLen
                if t < 0:
                    break
            self.ChainColors[self.ChainLen] = self.NextChainColor
            self.NextChainColor = (self.NextChainColor + 1) % 4
            self.ChainLen += 1
            added += 1
        return added

    def try_spawn_and_count(self):
        prev = self.ChainLen
        self.spawn_chain_ball()
        added = self.ChainLen - prev
        self.BallsSpawned = min(255, self.BallsSpawned + added)
        return added

    # ------------------------------------------------------------------
    # InsertChainBall — игрок попал; вставка в TmpInsertIdx с TmpInsertColor
    # ------------------------------------------------------------------
    def insert_chain_ball(self, idx, color):
        if self.ChainLen >= MAX_CHAIN_BALLS:
            self.ChainLen -= 1  # drop-tail trick

        # shift right ChainColors[idx..len-1] → [idx+1..len]
        if idx < self.ChainLen:
            for i in range(self.ChainLen, idx, -1):
                self.ChainColors[i] = self.ChainColors[i-1]
                self.ChainOffsets[i] = self.ChainOffsets[i-1]
        self.ChainColors[idx] = color
        self.ChainOffsets[idx] = 0
        self.ChainLen += 1

        if self.ChainStalled:
            return  # stall: не трогаем HeadT и head_offsets

        # head_offsets[0..idx-1] -= SPACING
        for i in range(idx):
            self.ChainOffsets[i] = sat_byte_signed(self.ChainOffsets[i] - CHAIN_SPACING)

        # ChainHeadT += SPACING
        self.ChainHeadT = min(TRACK_NUM_POINTS - 1, self.ChainHeadT + CHAIN_SPACING)

    # ------------------------------------------------------------------
    # CheckMatch3 — найти run цвета через TmpInsertIdx с gap-check
    # Возвращает True если match произошёл
    # ------------------------------------------------------------------
    def check_match3(self, insert_idx):
        if insert_idx >= self.ChainLen:
            return False
        color = self.ChainColors[insert_idx]
        # scan left
        lb = insert_idx
        while lb > 0:
            if self.ChainColors[lb-1] != color:
                break
            # gap check: 32 + offset[lb-1] - offset[lb] ≤ 37
            if (CHAIN_SPACING + self.ChainOffsets[lb-1] - self.ChainOffsets[lb]) > CHAIN_SPACING + 5:
                break
            lb -= 1
        # scan right
        rb = insert_idx
        while rb < self.ChainLen - 1:
            if self.ChainColors[rb+1] != color:
                break
            if (CHAIN_SPACING + self.ChainOffsets[rb] - self.ChainOffsets[rb+1]) > CHAIN_SPACING + 5:
                break
            rb += 1
        count = rb - lb + 1
        if count < 3:
            return False

        # tail shift = SPACING * count, clamp count <= 4
        clamped = min(count, 4)
        shift = CHAIN_SPACING * clamped

        # default stop-mode → stall
        self.ChainStalled = 1

        # head_offsets[0..lb-1] = 0 (отменяем pending insert-animation)
        for i in range(lb):
            self.ChainOffsets[i] = 0

        # cascade detection: colors[lb-1] vs colors[rb+1]
        cascade = False
        if lb > 0 and rb + 1 < self.ChainLen:
            if self.ChainColors[lb-1] == self.ChainColors[rb+1]:
                cascade = True

        if cascade:
            # roll-back mode: half shift в tail (и потом MoveChain reverse)
            shift = shift // 2

        # ChainColors LDIR: colors[rb+1..len-1] → colors[lb..]
        copy_count = self.ChainLen - 1 - rb
        if copy_count > 0:
            for k in range(copy_count):
                # tail offsets after shift = old offsets[rb+1+k] - shift
                self.ChainColors[lb+k] = self.ChainColors[rb+1+k]
                self.ChainOffsets[lb+k] = sat_byte_signed(self.ChainOffsets[rb+1+k] - shift)

        # ChainLen -= count
        self.ChainLen -= count
        return True

    def schedule_cascade(self, match_left):
        """Если на стыке после match одинаковый цвет → cascade scheduled."""
        if match_left == 0 or match_left >= self.ChainLen:
            return
        if self.ChainColors[match_left-1] != self.ChainColors[match_left]:
            return
        # cascade detected
        self.CascadeIdx = match_left - 1
        self.CascadeState = 1
        self.CascadeDelay = CASCADE_SLOWDOWN_DELAY
        # CascadeWait = halfShift*2 (приближённо count*30 или count*15 после моего refactor)
        # В нашем asm: CascadeWait = TmpMatchHalfShift * 2. Используем shift estimate.
        self.CascadeWait = 60  # ≈ count*30 для count=2; точное значение зависит

    def process_cascade(self):
        if self.CascadeState == 0:
            return
        if self.CascadeWait > 0:
            self.CascadeWait -= 1
            return
        # trigger
        triggered = self.check_match3(self.CascadeIdx)
        if triggered:
            self.schedule_cascade(self.CascadeIdx)  # упрощение
        else:
            self.CascadeState = 0

    # ------------------------------------------------------------------
    # main loop tick
    # ------------------------------------------------------------------
    def tick(self):
        self.FrameCounter = (self.FrameCounter + 1) & 0xFF

        if self.BallsSpawned < LEVEL_START_BALLS:
            # fast phase
            for _ in range(FAST_ADVANCE):
                self.move_chain()
            self.animate_chain()
            self.try_spawn_and_count()
        else:
            # normal: move_chain каждые 2 кадра
            if (self.FrameCounter & 1) == 0:
                self.move_chain()
                self.animate_chain()
            if self.BallsSpawned < LEVEL_TOTAL_BALLS:
                if (self.FrameCounter & 63) == 0:
                    self.try_spawn_and_count()

        if self.CascadeState != 0:
            self.process_cascade()


# ==============================================================
# SLOT-ARRAY MODEL (новая физика)
#
# Каждая cell-позиция вдоль трека = slot k (целое 0..N-1). t-units = k * CELL_SIZE.
# Slots[k] хранит цвет (0..5) либо GAP (= -1, пусто).
# SlotOffsets[k] — signed sub-cell offset для smooth animation.
# HeadSlotAbs — абсолютный track-slot для Slots[0] (head).
# HeadSub — sub-cell progress (0..CELL_SIZE-1) общий для всей цепочки.
#
# t-position шара в Slots[k]:  (HeadSlotAbs - k) * CELL_SIZE + SlotOffsets[k] + HeadSub
#
# Match-3: window-3 scan по Slots[]. GAP блокирует match (s[k]==s[k+1]==s[k+2] && s[k]!=GAP).
# ==============================================================
class ChainSimSlots:
    """Slot-array model — соответствует ASM Chain0_Slots/SlotOffsets/HeadSlotAbs/HeadSub.

    На текущей итерации реализован только match-3 detection. Move/Animate/Insert и т.д.
    остаются в ChainSim (legacy) и синхронизируются через `from_legacy`. Это позволяет
    тестировать новую модель параллельно legacy и сверять результаты.
    """

    MAX_SLOTS = MAX_SLOTS_PER_CHAIN

    def __init__(self):
        self.Slots       = [GAP] * self.MAX_SLOTS
        self.SlotOffsets = [0] * self.MAX_SLOTS
        self.HeadSlotAbs = 0
        self.HeadSub     = 0
        self.SlotsLen    = 0

    @classmethod
    def from_legacy(cls, legacy):
        s = cls()
        s.HeadSlotAbs = legacy.ChainHeadT // CELL_SIZE
        s.HeadSub     = legacy.ChainHeadT %  CELL_SIZE
        s.SlotsLen    = legacy.ChainLen
        for k in range(legacy.ChainLen):
            s.Slots[k]       = legacy.ChainColors[k]
            s.SlotOffsets[k] = legacy.ChainOffsets[k]
        return s

    def t_of(self, k):
        """t-coord (= индекс в TrackData) для шара в Slots[k]."""
        return (self.HeadSlotAbs - k) * CELL_SIZE + self.SlotOffsets[k] + self.HeadSub

    def gap_to_prev(self, k):
        """Расстояние t между шаром k и k-1 минус CELL_SIZE (= 0 при норме)."""
        if k <= 0:
            return 0
        return self.SlotOffsets[k-1] - self.SlotOffsets[k]

    def detect_match3(self, idx):
        """Window scan вокруг idx. Возвращает (matched, lb, rb, count).
        Slots[idx] = центр (вставленный шар). Scan останавливается на:
          (1) разнице цветов, (2) GAP-маркере. Discrete logic — offsets visual only.
        """
        if idx >= self.SlotsLen:
            return (False, 0, 0, 0)
        color = self.Slots[idx]
        if color == GAP:
            return (False, 0, 0, 0)

        lb = idx
        while lb > 0:
            if self.Slots[lb-1] == GAP or self.Slots[lb-1] != color:
                break
            lb -= 1

        rb = idx
        while rb < self.SlotsLen - 1:
            if self.Slots[rb+1] == GAP or self.Slots[rb+1] != color:
                break
            rb += 1

        count = rb - lb + 1
        return (count >= 3, lb, rb, count)

    def schedule_cascade_scan(self):
        """Full chain scan для window-3 одного цвета (после match'а).
        Возвращает первый найденный (lb, rb, count) либо None."""
        for i in range(self.SlotsLen - 2):
            c = self.Slots[i]
            if c == GAP:
                continue
            if self.Slots[i+1] == c and self.Slots[i+2] == c:
                rb = i + 2
                while rb + 1 < self.SlotsLen and self.Slots[rb+1] == c:
                    rb += 1
                return (i, rb, rb - i + 1)
        return None

    # === Writers (отражают ASM в новом slot-array model) ===
    def insert(self, idx, color, stalled=False):
        """Insert at idx: shift_right массива, Slots[idx]=color, HSA+=1 (если не stalled)."""
        if self.SlotsLen >= self.MAX_SLOTS:
            self.SlotsLen -= 1
        if idx < self.SlotsLen:
            for j in range(self.SlotsLen, idx, -1):
                self.Slots[j]       = self.Slots[j-1]
                self.SlotOffsets[j] = self.SlotOffsets[j-1]
        self.Slots[idx]       = color
        self.SlotOffsets[idx] = 0
        self.SlotsLen += 1
        if not stalled:
            self.HeadSlotAbs = min(95, self.HeadSlotAbs + 1)

    def set_match_pending(self, lb, rb):
        """Set Slots[lb..rb] = GAP (pending compaction)."""
        for k in range(lb, rb + 1):
            self.Slots[k] = GAP
            self.SlotOffsets[k] = 0

    def compact_and_detect(self, lb, rb, count):
        """Shift_left массива на count + detect stop/cascade. Возвращает 'stop'|'cascade'|'edge'."""
        copy_count = self.SlotsLen - 1 - rb
        if copy_count > 0:
            for k in range(copy_count):
                self.Slots[lb + k]       = self.Slots[rb + 1 + k]
                self.SlotOffsets[lb + k] = self.SlotOffsets[rb + 1 + k]
        self.SlotsLen -= count
        # tail GAP fill
        for k in range(self.SlotsLen, self.SlotsLen + count):
            if k < self.MAX_SLOTS:
                self.Slots[k]       = GAP
                self.SlotOffsets[k] = 0

        # cascade/stop detect
        if lb == 0 or lb >= self.SlotsLen:
            return 'edge'
        if self.Slots[lb-1] == self.Slots[lb]:
            # CASCADE: HSA -= count (хвост стоит, голова прыгает)
            self.HeadSlotAbs = max(0, self.HeadSlotAbs - count)
            return 'cascade'
        return 'stop'

    def t_positions(self):
        """Список t-позиций активных шаров (None для GAP). Render-формула с HeadSub."""
        return [None if self.Slots[k] == GAP else (self.HeadSlotAbs - k) * CELL_SIZE + self.SlotOffsets[k] + self.HeadSub
                for k in range(self.SlotsLen)]


def sat_signed(v):
    if v > 127:  return 127
    if v < -128: return -128
    return v


class ChainSimASM(ChainSimSlots):
    """Цикл-точная эмуляция ASM-flow (Insert/MoveChain/AnimateChain/CompactAndDetectMode/ProcessCascade).

    Методы инвариантов и tick() — для random fuzz-теста.
    """

    COMPACT_DELAY  = 30
    STOP_FRAMES    = 30
    CASCADE_DELAY  = 10
    CASCADE_WAIT   = 60
    MOVE_PIX_RATE  = 1   # HeadSub++ каждый MoveChain call (попиксельно)
    FAST_ADVANCE   = 12
    LEVEL_FAST     = 35
    LEVEL_TOTAL    = 85

    def __init__(self):
        super().__init__()
        self.HeadSub      = 0
        self.ChainStalled = 0
        self.CompactTimer = 0
        self.StopTimer    = 0
        self.CascadeState = 0
        self.CascadeIdx   = 0
        self.CascadeWait  = 0
        self.CascadeDelay = 0
        self.FrameCounter = 0
        self.BallsSpawned = 0
        # сохранённые TmpMatch* (для отложенной compaction)
        self.PendingMatchLeft  = 0
        self.PendingMatchRight = 0
        self.PendingMatchCount = 0
        self.event_log = []

    def log(self, msg):
        self.event_log.append(f"[F{self.FrameCounter}] {msg}")

    # ----- writers -----
    def insert_ball(self, idx, color):
        if self.CompactTimer > 0:
            # force-close pending compaction
            self.compact_and_detect_mode()
            self.CompactTimer = 0
        # Force-clear все ongoing animations (decay/stall/cascade) — discrete snap
        for k in range(self.MAX_SLOTS):
            self.SlotOffsets[k] = 0
        self.ChainStalled = 0
        self.StopTimer    = 0
        self.CascadeState = 0
        self.CascadeWait  = 0
        self.CascadeDelay = 0

        if self.SlotsLen >= self.MAX_SLOTS:
            self.SlotsLen -= 1
        if idx < self.SlotsLen:
            for j in range(self.SlotsLen, idx, -1):
                self.Slots[j]       = self.Slots[j-1]
                self.SlotOffsets[j] = self.SlotOffsets[j-1]
        self.Slots[idx]       = color
        self.SlotOffsets[idx] = 0
        self.SlotsLen += 1
        # HSA += 1, head-half получает offset = -CELL_SIZE для smooth insert anim
        self.HeadSlotAbs = min(95, self.HeadSlotAbs + 1)
        for k in range(idx):
            self.SlotOffsets[k] = sat_signed(self.SlotOffsets[k] - CELL_SIZE)
        self.log(f"insert(idx={idx}, color={color}) → slots={self.Slots[:self.SlotsLen]}")

    def check_match3(self, idx):
        matched, lb, rb, count = self.detect_match3(idx)
        if not matched:
            return False
        for k in range(lb, rb + 1):
            self.Slots[k] = GAP
            self.SlotOffsets[k] = 0
        self.PendingMatchLeft  = lb
        self.PendingMatchRight = rb
        self.PendingMatchCount = count
        self.ChainStalled = 1
        self.CompactTimer = self.COMPACT_DELAY
        self.log(f"match-3 detected lb={lb}, rb={rb}, count={count}")
        return True

    def compact_and_detect_mode(self):
        lb = self.PendingMatchLeft
        rb = self.PendingMatchRight
        count = self.PendingMatchCount
        copy_count = self.SlotsLen - 1 - rb
        if copy_count > 0:
            for k in range(copy_count):
                self.Slots[lb + k]       = self.Slots[rb + 1 + k]
                self.SlotOffsets[lb + k] = self.SlotOffsets[rb + 1 + k]
        self.SlotsLen -= count
        for k in range(self.SlotsLen, self.SlotsLen + count):
            if k < self.MAX_SLOTS:
                self.Slots[k] = GAP
                self.SlotOffsets[k] = 0

        # detect mode
        if lb == 0 or lb >= self.SlotsLen:
            # edge — нет head или tail-half для cascade
            self.ChainStalled = 0
            self.log(f"compact (edge), slots={self.Slots[:self.SlotsLen]}")
            return
        if self.Slots[lb-1] == self.Slots[lb]:
            # CASCADE
            self.HeadSlotAbs = max(0, self.HeadSlotAbs - count)
            shift = min(count, 3) * CELL_SIZE
            for k in range(lb):
                self.SlotOffsets[k] = sat_signed(self.SlotOffsets[k] + shift)
            self.ChainStalled = 1
            self.CascadeState = 1
            self.CascadeWait = 1
            self.CascadeDelay = 0
            self.CascadeIdx = lb
            self.log(f"compact CASCADE → hsa={self.HeadSlotAbs}, slots={self.Slots[:self.SlotsLen]}")
        else:
            # STOP
            shift = min(count, 4) * CELL_SIZE
            for k in range(lb, self.SlotsLen):
                self.SlotOffsets[k] = sat_signed(self.SlotOffsets[k] - shift)
            self.StopTimer = self.STOP_FRAMES
            self.ChainStalled = 1
            self.log(f"compact STOP → slots={self.Slots[:self.SlotsLen]}, tail offsets[lb..]={self.SlotOffsets[lb:self.SlotsLen]}")

    def animate_chain(self):
        if self.CompactTimer > 0:
            self.CompactTimer -= 1
            if self.CompactTimer == 0:
                self.compact_and_detect_mode()
            return
        if self.StopTimer > 0:
            self.StopTimer -= 1
            return
        if self.SlotsLen == 0:
            self.ChainStalled = 0
            return
        step = 1 if self.ChainStalled else 4
        any_active = False
        for k in range(self.SlotsLen):
            o = self.SlotOffsets[k]
            if o == 0:
                continue
            if o > 0:
                o = max(0, o - step)
            else:
                o = min(0, o + step)
            self.SlotOffsets[k] = o
            if o != 0:
                any_active = True
        if not any_active:
            self.ChainStalled = 0

    def move_chain(self):
        if self.CascadeState != 0:
            return  # цепочка стоит во время cascade
        if self.ChainStalled:
            return
        self.HeadSub += self.MOVE_PIX_RATE
        if self.HeadSub >= CELL_SIZE:
            self.HeadSub -= CELL_SIZE
            self.HeadSlotAbs = min(95, self.HeadSlotAbs + 1)

    def process_cascade(self):
        if self.CascadeState == 0:
            return
        if self.ChainStalled:
            return  # ждём decay
        if self.CascadeWait > 0:
            self.CascadeWait -= 1
            return
        # trigger
        idx = self.CascadeIdx
        if idx >= self.SlotsLen:
            self.CascadeState = 0
            return
        if self.check_match3(idx):
            return  # pending установился
        self.CascadeState = 0

    def spawn_chain_ball(self, color):
        if self.SlotsLen >= self.MAX_SLOTS:
            return False
        if self.HeadSlotAbs < self.SlotsLen:
            return False
        self.Slots[self.SlotsLen] = color
        self.SlotOffsets[self.SlotsLen] = 0
        self.SlotsLen += 1
        return True

    def tick(self, color_seq=None):
        """Один кадр: spawn (по фазе), MoveChain, AnimateChain, ProcessCascade."""
        self.FrameCounter += 1
        if self.BallsSpawned < self.LEVEL_FAST:
            for _ in range(self.FAST_ADVANCE):
                self.move_chain()
            self.animate_chain()
            if color_seq is not None and self.spawn_chain_ball(color_seq.pop(0) if color_seq else 0):
                self.BallsSpawned = min(255, self.BallsSpawned + 1)
        else:
            if (self.FrameCounter & 1) == 0:
                self.move_chain()
                self.animate_chain()
            if self.BallsSpawned < self.LEVEL_TOTAL:
                if (self.FrameCounter & 63) == 0 and color_seq is not None:
                    if self.spawn_chain_ball(color_seq.pop(0) if color_seq else 0):
                        self.BallsSpawned = min(255, self.BallsSpawned + 1)
        if self.CascadeState != 0:
            self.process_cascade()

    # ----- инварианты -----
    def check_invariants(self):
        """Проверка после каждого критического действия. Возвращает list проблем."""
        issues = []
        # GAP только в хвосте после compaction
        first_gap = None
        for k in range(self.SlotsLen):
            if self.Slots[k] == GAP:
                first_gap = k
                break
        if first_gap is not None and self.CompactTimer == 0:
            # Когда CompactTimer=0, GAP внутри active range = баг
            issues.append(f"GAP at idx {first_gap} but CompactTimer=0 (active GAP without pending compaction)")
        # SlotsLen в пределах
        if self.SlotsLen < 0 or self.SlotsLen > self.MAX_SLOTS:
            issues.append(f"SlotsLen={self.SlotsLen} out of [0..{self.MAX_SLOTS}]")
        # HSA в пределах
        if self.HeadSlotAbs < 0 or self.HeadSlotAbs > 95:
            issues.append(f"HSA={self.HeadSlotAbs} out of [0..95]")
        # Cascade без stall и offsets — должен немедленно завершиться
        if self.CascadeState != 0 and self.ChainStalled == 0 and self.CascadeWait == 0 and self.CompactTimer == 0:
            # На след tick'е ProcessCascade trigger CheckMatch3. Если там нет match → CascadeState=0.
            # До тика — это transient state. Не флаг.
            pass
        return issues


# ==============================================================
# Сценарии
# ==============================================================
def scenario_fast_phase():
    """Подсчёт времени fast-фазы: ожидание 35 шаров."""
    s = ChainSim()
    frame = 0
    print("=== Fast-фаза (LEVEL_START_BALLS = 35) ===")
    while s.BallsSpawned < LEVEL_START_BALLS:
        s.tick()
        frame += 1
        if frame > 1000:
            print(f"  ABORT — превышено 1000 кадров; ChainLen={s.ChainLen}, BallsSpawned={s.BallsSpawned}")
            return
    print(f"  35 шаров заспавнено за {frame} кадров = {frame/50:.2f} сек на 50 fps")
    print(f"  ChainHeadT={s.ChainHeadT}, ChainLen={s.ChainLen}")


def scenario_single_insert_no_match():
    """Insert без match. Ожидание: head отъезжает на CHAIN_SPACING за ~8 тиков."""
    s = ChainSim()
    # Подготовка: цепочка из 5 шаров разных цветов (не вызовет match)
    s.ChainLen = 5
    s.ChainHeadT = 5 * CHAIN_SPACING
    s.ChainColors[:5] = [0, 1, 2, 3, 0]
    s.BallsSpawned = LEVEL_TOTAL_BALLS  # после spawn-фазы

    print("\n=== Insert без match ===")
    print(f"  до: HeadT={s.ChainHeadT}, head[0]_pos={s.position(0)}")
    s.insert_chain_ball(2, 4)  # цвет 4 в idx=2
    print(f"  после insert: HeadT={s.ChainHeadT} (+{CHAIN_SPACING}), head[0]_pos={s.position(0)}, offsets={s.ChainOffsets[:s.ChainLen]}")
    # не было match
    matched = s.check_match3(2)
    print(f"  match3: {matched} (ожидается False)")
    # decay anim
    for f in range(20):
        s.animate_chain()
        if all(o == 0 for o in s.ChainOffsets[:s.ChainLen]):
            print(f"  все offsets = 0 после {f+1} animate_chain ticks")
            break
    print(f"  финал: head[0]_pos={s.position(0)} (отъехал от {5*CHAIN_SPACING - 0}? см. delta)")


def scenario_match3_stop_mode():
    """Match-3 со стыком разных цветов → stop-mode. Head freeze, tail catch-up."""
    s = ChainSim()
    s.ChainLen = 7
    s.ChainHeadT = 7 * CHAIN_SPACING
    s.ChainColors[:7] = [0, 1, 1, 1, 2, 0, 1]
    #                    head 0,1,2 — match-3 zone (idx 1-3),
    #                    tail [4,5,6] = 2,0,1
    # На стыке (idx 0 vs idx 4 после shift): colors[0]=0, colors[1] (after shift = old[4]=2). Разные → stop.
    s.BallsSpawned = LEVEL_TOTAL_BALLS

    print("\n=== Match-3 stop-mode (разные на стыке) ===")
    print(f"  до match: ChainLen={s.ChainLen}, HeadT={s.ChainHeadT}")
    matched = s.check_match3(2)  # insert idx=2 (центр match)
    print(f"  matched={matched}, ChainLen={s.ChainLen}, ChainStalled={s.ChainStalled}")
    print(f"  ChainColors={s.ChainColors[:s.ChainLen]}")
    print(f"  ChainOffsets={s.ChainOffsets[:s.ChainLen]}")
    # tick несколько раз — head должен стоять
    init_headt = s.ChainHeadT
    init_pos_head = s.position(0)
    for f in range(50):
        s.tick()
    print(f"  через 50 кадров: HeadT={s.ChainHeadT} (delta={s.ChainHeadT-init_headt}), head[0]_pos={s.position(0)}")
    print(f"  Stalled={s.ChainStalled}, offsets={s.ChainOffsets[:s.ChainLen]}")
    # ожидание: HeadT не изменился пока stalled


def scenario_match3_cascade_mode():
    """Match-3 со стыком одинаковых → cascade roll-back."""
    s = ChainSim()
    s.ChainLen = 7
    s.ChainHeadT = 7 * CHAIN_SPACING
    s.ChainColors[:7] = [0, 1, 1, 1, 0, 2, 3]
    # head[0]=0, match=[1,2,3], tail=[4,5,6]=0,2,3
    # На стыке после shift: colors[lb-1]=colors[0]=0, colors[lb] (= old colors[4]) = 0. Одинаковые → cascade.
    s.BallsSpawned = LEVEL_TOTAL_BALLS

    print("\n=== Match-3 cascade-mode (одинаковые на стыке) ===")
    print(f"  до match: HeadT={s.ChainHeadT}, head[0]_pos={s.position(0)}")
    matched = s.check_match3(2)
    print(f"  matched={matched}, ChainLen={s.ChainLen}")
    print(f"  ChainColors={s.ChainColors[:s.ChainLen]}, Stalled={s.ChainStalled}")
    # schedule cascade
    s.schedule_cascade(1)  # match_left = 1
    print(f"  CascadeState={s.CascadeState}, CascadeWait={s.CascadeWait}, CascadeDelay={s.CascadeDelay}")
    init_headt = s.ChainHeadT
    init_head0 = s.position(0)
    # tick 30 кадров — head должен поехать назад
    for f in range(30):
        s.tick()
    print(f"  через 30 кадров: HeadT={s.ChainHeadT} (delta={s.ChainHeadT-init_headt}), head[0]_pos={s.position(0)} (delta={s.position(0)-init_head0})")
    print(f"  CascadeState={s.CascadeState}, CascadeWait={s.CascadeWait}")


def scenario_insert_during_stall():
    """Insert во время stall не должен двигать HeadT."""
    s = ChainSim()
    s.ChainLen = 7
    s.ChainHeadT = 7 * CHAIN_SPACING
    s.ChainColors[:7] = [0, 1, 1, 1, 2, 0, 1]
    s.BallsSpawned = LEVEL_TOTAL_BALLS
    s.check_match3(2)  # вызов stop-mode

    print("\n=== Insert во время stall ===")
    print(f"  до Insert: ChainStalled={s.ChainStalled}, HeadT={s.ChainHeadT}")
    headt_before = s.ChainHeadT
    s.insert_chain_ball(1, 5)  # вставка в head_half
    print(f"  после Insert: HeadT={s.ChainHeadT} (delta={s.ChainHeadT-headt_before}, ожидается 0)")
    print(f"  head_offsets[0]={s.ChainOffsets[0]} (ожидается 0)")


def scenario_overlap_check():
    """Проверка возможного overlap при множественных insert'ах в normal mode."""
    s = ChainSim()
    s.ChainLen = 5
    s.ChainHeadT = 5 * CHAIN_SPACING
    s.ChainColors[:5] = [0, 1, 2, 3, 0]
    s.BallsSpawned = LEVEL_TOTAL_BALLS

    print("\n=== Overlap при 3 быстрых insert'ах ===")
    s.insert_chain_ball(1, 4)
    s.insert_chain_ball(2, 5)
    s.insert_chain_ball(3, 4)
    print(f"  ChainOffsets={s.ChainOffsets[:s.ChainLen]}")
    # печать positions
    positions = [s.position(i) for i in range(s.ChainLen)]
    print(f"  positions={positions}")
    # gap check
    gaps = [positions[i-1] - positions[i] for i in range(1, s.ChainLen)]
    print(f"  gaps между соседями={gaps} (ожидается >={CHAIN_SPACING})")
    bad = [i for i, g in enumerate(gaps) if g < CHAIN_SPACING - 5]
    if bad:
        print(f"  ❌ overlap detected при индексах {bad}")
    else:
        print(f"  ✓ нет overlap")


# ==============================================================
# Сценарии для slot-array модели — сверка с legacy
# ==============================================================
def scenario_slots_match3_basic():
    """Базовая сверка: detect_match3 на slots vs check_match3 на legacy."""
    s = ChainSim()
    s.ChainLen = 5
    s.ChainHeadT = 5 * CHAIN_SPACING
    s.ChainColors[:5] = [2, 1, 1, 1, 2]   # match на idx 1..3

    slots = ChainSimSlots.from_legacy(s)
    matched, lb, rb, count = slots.detect_match3(2)
    print("\n=== Slot model: match-3 detection ===")
    print(f"  Slots: matched={matched}, lb={lb}, rb={rb}, count={count}")
    legacy_matched = s.check_match3(2)
    print(f"  Legacy.check_match3(2)={legacy_matched} (после legacy LDIR ChainLen={s.ChainLen})")


def scenario_slots_gap_blocks_match():
    """Имитация: после insert head-half имеет offset=-32 → physical gap >= 16,
    одинаковые цвета по обе стороны insert'а НЕ должны давать match."""
    slots = ChainSimSlots()
    slots.HeadSlotAbs = 5
    slots.HeadSub = 0
    slots.SlotsLen = 5
    slots.Slots[:5]       = [1, 1, 4, 1, 1]   # цвета совпадают, но 4 в центре
    slots.SlotOffsets[:5] = [-32, -32, 0, 0, 0]  # head-half отстаёт

    # Insert новый '1' в idx=2 (между 4 и tail-1's). Сейчас Slots[2] = 4 (центр).
    # Если бы centre было 1, scan слева наткнулся бы на gap (off[1]=-32, off[2]=0 →
    # off[1]-off[2]=-32 < 16 → gap-OK; но это neg, OK). Hmm — current legacy logic
    # actually allows match across head/tail после insert если colors совпадут.
    # Этот сценарий просто демонстрация.
    matched, lb, rb, count = slots.detect_match3(2)
    print("\n=== Slot model: gap blocks match? (демо) ===")
    print(f"  Slots={slots.Slots[:5]}, Offsets={slots.SlotOffsets[:5]}")
    print(f"  detect_match3(2): matched={matched}, lb={lb}, rb={rb}")


def scenario_slots_with_gap_marker():
    """Явный GAP-marker между шарами одного цвета — match НЕ должен срабатывать."""
    slots = ChainSimSlots()
    slots.HeadSlotAbs = 5
    slots.SlotsLen = 5
    slots.Slots[:5] = [1, GAP, 1, 1, 1]   # шар + GAP + три '1'

    matched, lb, rb, count = slots.detect_match3(3)
    print("\n=== Slot model: GAP-marker блокирует scan ===")
    print(f"  Slots={slots.Slots[:5]}")
    print(f"  detect_match3(3): matched={matched}, lb={lb}, rb={rb}, count={count}")
    print(f"  ожидается: matched=True (run [2,3,4]={slots.Slots[2:5]}), lb=2, rb=4")


def scenario_slots_cascade_scan():
    """Full chain scan для cascade detection."""
    slots = ChainSimSlots()
    slots.HeadSlotAbs = 7
    slots.SlotsLen = 7
    slots.Slots[:7] = [2, 0, 3, 3, 3, 1, 4]
    found = slots.schedule_cascade_scan()
    print("\n=== Slot model: schedule_cascade_scan ===")
    print(f"  Slots={slots.Slots[:7]}")
    print(f"  found={found} (ожидается (2, 4, 3))")


def scenario_cascade_full_flow():
    """Полный flow cascade: insert → match → pending → compact → cascade → re-match."""
    s = ChainSimSlots()
    # initial: [0, 1, 1, 0, 0, 0, 1, 0], hsa=7, len=8
    s.HeadSlotAbs = 7
    s.SlotsLen = 8
    s.Slots[:8] = [0, 1, 1, 0, 0, 0, 1, 0]
    print("\n=== CASCADE full flow (HD-style stack of same colors) ===")
    print(f"  init: hsa={s.HeadSlotAbs}, slots={s.Slots[:s.SlotsLen]}")

    # Insert color=1 at idx=3 (между slot 2 (color 1) и slot 3 (color 0))
    s.insert(3, 1)
    print(f"\n  after insert(3, color=1): hsa={s.HeadSlotAbs}, slots={s.Slots[:s.SlotsLen]}")
    # Detect at idx=3
    matched, lb, rb, count = s.detect_match3(3)
    print(f"  detect: matched={matched}, lb={lb}, rb={rb}, count={count}")
    assert matched, "match-3 expected"

    # Pending: Slots[lb..rb]=GAP
    s.set_match_pending(lb, rb)
    print(f"  PENDING (gap visible): slots={s.Slots[:s.SlotsLen]}")
    t_pos = s.t_positions()
    print(f"  t-позиции: {t_pos}")

    # Compaction после CompactTimer
    result = s.compact_and_detect(lb, rb, count)
    print(f"\n  COMPACT: slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}, result={result}")
    t_pos = s.t_positions()
    print(f"  t-позиции после compaction: {t_pos}")

    if result == 'cascade':
        # Schedule next CheckMatch3
        next_idx = lb
        matched2, lb2, rb2, count2 = s.detect_match3(next_idx)
        print(f"\n  CASCADE NEXT MATCH at idx={next_idx}: matched={matched2}, lb={lb2}, rb={rb2}, count={count2}")
        if matched2:
            s.set_match_pending(lb2, rb2)
            print(f"  PENDING: slots={s.Slots[:s.SlotsLen]}")
            result2 = s.compact_and_detect(lb2, rb2, count2)
            print(f"  COMPACT: slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}, result={result2}")


class ChainSimVDC:
    """Повторяет ASM VDC модель: GAP_STOP (тает с tail), GAP_CASCADE (тает с head)."""
    MAX_SLOTS = MAX_SLOTS_PER_CHAIN

    def __init__(self):
        self.Slots       = [GAP] * self.MAX_SLOTS
        self.SlotOffsets = [0] * self.MAX_SLOTS
        self.HeadSlotAbs = 50
        self.HeadSub     = 0
        self.SlotsLen    = 0
        self.GapStepCounter = 0
        self.MatchScanIdx = 0xFF
        self.TmpGapIdx = 0
        self.TmpInsertIdx = 0
        self.TmpInsertColor = 0
        self.TmpMatchLeft = 0
        self.TmpMatchRight = 0
        self.TmpMatchCount = 0
        self.TmpMatchColor = 0
        self.ChainStalled = 0
        self.events = []

    def log(self, msg):
        self.events.append(msg)

    def detect_match3(self, idx):
        if idx >= self.SlotsLen: return False
        color = self.Slots[idx]
        if color < 0 or color >= NUM_BALL_COLORS: return False
        lb = idx
        while lb > 0 and self.Slots[lb-1] == color:
            lb -= 1
        rb = idx
        while rb < self.SlotsLen-1 and self.Slots[rb+1] == color:
            rb += 1
        count = rb - lb + 1
        if count < 3: return False
        self.TmpMatchLeft = lb
        self.TmpMatchRight = rb
        self.TmpMatchCount = count
        self.TmpMatchColor = color
        return True

    def check_match3(self, idx):
        """ASM CheckMatch3: detect + apply GAP-marker."""
        self.TmpInsertIdx = idx
        if not self.detect_match3(idx):
            return False
        lb, rb, count = self.TmpMatchLeft, self.TmpMatchRight, self.TmpMatchCount
        # Cascade detection: Slots[lb-1] == Slots[rb+1] (если есть оба)
        marker = GAP_STOP
        if lb > 0 and rb+1 < self.SlotsLen:
            if self.Slots[lb-1] == self.Slots[rb+1]:
                marker = GAP_CASCADE
        for k in range(lb, rb+1):
            self.Slots[k] = marker
            self.SlotOffsets[k] = 0
        self.ChainStalled = 1
        self.log(f"match-3 detected lb={lb}, rb={rb}, count={count}, marker={'CASCADE' if marker==GAP_CASCADE else 'STOP'}")
        return True

    def insert_ball(self, idx, color):
        # shift_right массива от idx
        if self.SlotsLen >= self.MAX_SLOTS:
            self.SlotsLen -= 1
        if idx < self.SlotsLen:
            for j in range(self.SlotsLen, idx, -1):
                self.Slots[j] = self.Slots[j-1]
                self.SlotOffsets[j] = self.SlotOffsets[j-1]
        self.Slots[idx] = color
        self.SlotOffsets[idx] = 0
        self.SlotsLen += 1
        self.HeadSlotAbs = min(95, self.HeadSlotAbs + 1)
        self.log(f"insert(idx={idx}, color={color}) → slots={self.Slots[:self.SlotsLen]}")

    def do_gap_step(self):
        # Pass 1: STOP (last from tail-side)
        stop_idx = -1
        for k in range(self.SlotsLen-1, -1, -1):
            if self.Slots[k] == GAP_STOP:
                stop_idx = k
                break
        if stop_idx >= 0:
            # удалить slot stop_idx, shift_left от stop_idx+1
            for j in range(stop_idx, self.SlotsLen-1):
                self.Slots[j] = self.Slots[j+1]
                self.SlotOffsets[j] = self.SlotOffsets[j+1]
            self.SlotsLen -= 1
            # offsets shifted (slot stop_idx onwards) -= CELL_SIZE
            for j in range(stop_idx, self.SlotsLen):
                self.SlotOffsets[j] = sat_byte_signed(self.SlotOffsets[j] - CELL_SIZE)
            # Check if GAP_STOP полностью исчез
            any_stop = any(self.Slots[k] == GAP_STOP for k in range(self.SlotsLen))
            if not any_stop:
                self.MatchScanIdx = stop_idx
                self.log(f"GAP_STOP fully closed, MatchScanIdx={stop_idx}")
            self.TmpGapIdx = stop_idx

        # Pass 2: CASCADE (first from head-side)
        casc_idx = -1
        for k in range(self.SlotsLen):
            if self.Slots[k] == GAP_CASCADE:
                casc_idx = k
                break
        if casc_idx >= 0:
            # удалить slot casc_idx, shift_left от casc_idx+1
            for j in range(casc_idx, self.SlotsLen-1):
                self.Slots[j] = self.Slots[j+1]
                self.SlotOffsets[j] = self.SlotOffsets[j+1]
            self.SlotsLen -= 1
            self.HeadSlotAbs = max(0, self.HeadSlotAbs - 1)
            # offsets head-side (slot 0..casc_idx-1) += CELL_SIZE
            for j in range(casc_idx):
                self.SlotOffsets[j] = sat_byte_signed(self.SlotOffsets[j] + CELL_SIZE)
            # Check fully closed
            any_casc = any(self.Slots[k] == GAP_CASCADE for k in range(self.SlotsLen))
            if not any_casc:
                self.MatchScanIdx = casc_idx
                self.log(f"GAP_CASCADE fully closed, MatchScanIdx={casc_idx}")
            self.TmpGapIdx = casc_idx

    def scan_for_new_match(self):
        if self.MatchScanIdx == 0xFF:
            return
        start = max(0, self.MatchScanIdx - 2)
        self.MatchScanIdx = 0xFF
        if self.SlotsLen < 3:
            return
        max_start = self.SlotsLen - 3
        for k in range(start, min(start + 5, max_start + 1)):
            if k < 0 or k > max_start: continue
            c = self.Slots[k]
            if c < 0 or c >= NUM_BALL_COLORS: continue
            if self.Slots[k+1] == c and self.Slots[k+2] == c:
                self.log(f"ScanForNewMatch found run at idx={k}, calling check_match3({k+1})")
                self.check_match3(k+1)
                return
        self.log(f"ScanForNewMatch (start={start}) — no match found")

    def update_stall_by_gap(self):
        any_gap = any(is_gap(self.Slots[k]) for k in range(self.SlotsLen))
        any_off = any(self.SlotOffsets[k] != 0 for k in range(self.SlotsLen))
        self.ChainStalled = 1 if (any_gap or any_off) else 0

    def animate_chain(self):
        # decay offsets
        for k in range(self.SlotsLen):
            o = self.SlotOffsets[k]
            if o > 0: self.SlotOffsets[k] = max(0, o - 1)
            elif o < 0: self.SlotOffsets[k] = min(0, o + 1)
        # gap step counter
        self.GapStepCounter += 1
        if self.GapStepCounter >= GAP_STEP_FRAMES:
            self.GapStepCounter = 0
            self.do_gap_step()
            self.scan_for_new_match()
        self.update_stall_by_gap()

    def run_until_idle(self, max_frames=2000):
        f = 0
        while f < max_frames:
            self.animate_chain()
            f += 1
            any_gap = any(is_gap(self.Slots[k]) for k in range(self.SlotsLen))
            any_off = any(self.SlotOffsets[k] != 0 for k in range(self.SlotsLen))
            if not any_gap and not any_off and self.MatchScanIdx == 0xFF:
                break
        return f


def scenario_vdc_basic_cascade():
    """Простой cascade: insert между двумя одинаковыми цветами создаёт run-3 и
    cascade detection (соседи одного цвета). После closure new match-3."""
    s = ChainSimVDC()
    s.SlotsLen = 6
    s.Slots[:6] = [0, 0, 1, 0, 0, 2]   # head=slot0
    print("\n=== VDC: cascade chain (one match → after closure → another match) ===")
    print(f"  init: {s.Slots[:s.SlotsLen]}")
    # Insert color=1 at idx=2 → [0, 0, 1, 1, 0, 0, 2]
    # detect at idx=2: slots[2]=1, scan left lb=2, scan right rb=3, count=2. NO MATCH.
    # Better — insert цвет 1 at idx=3, between slot[2]=1 и slot[3]=0
    # Actually just match: setup [0, 0, 1, 1, 1, 0, 0, 2]
    s.SlotsLen = 8
    s.Slots[:8] = [0, 0, 1, 1, 1, 0, 0, 2]
    s.events.clear()
    s.check_match3(3)
    print(f"  after match: {s.Slots[:s.SlotsLen]}")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}")
    print(f"  events:")
    for e in s.events:
        print(f"    {e}")


def scenario_vdc_insert_in_visible_gap():
    """Insert игрока во время visible gap. NEW попадает в slots[idx], GAP остаётся."""
    s = ChainSimVDC()
    s.SlotsLen = 7
    s.Slots[:7] = [0, 1, GAP_STOP, GAP_STOP, GAP_STOP, 0, 2]
    print("\n=== VDC: Insert during visible gap ===")
    print(f"  init: {s.Slots[:s.SlotsLen]}")
    # Insert color=1 at idx=2 (между 1 и GAP_STOP): result [0, 1, 1, GAP_STOP, GAP_STOP, GAP_STOP, 0, 2]
    s.insert_ball(2, 1)
    print(f"  after insert: {s.Slots[:s.SlotsLen]}")
    s.check_match3(2)
    print(f"  after check_match3: {s.Slots[:s.SlotsLen]}")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}")
    for e in s.events:
        print(f"    {e}")


def scenario_vdc_two_gaps_simultaneously():
    """Два GAP-блока одновременно (STOP + CASCADE). Закрываются параллельно."""
    s = ChainSimVDC()
    s.SlotsLen = 13
    # head [0]=A, run STOP at [3..5] (color 1), run CASCADE at [9..10] (color 2)
    # cascade blocks: соседи [8]=2, [11]=2 → CASCADE
    # stop blocks: соседи [2]=A, [6]=B (разные) → STOP
    s.Slots[:13] = [0, 0, 1, GAP_STOP, GAP_STOP, GAP_STOP, 2, 1, 0, GAP_CASCADE, GAP_CASCADE, 0, 1]
    print("\n=== VDC: TWO GAPs simultaneously (STOP + CASCADE) ===")
    print(f"  init: {s.Slots[:s.SlotsLen]}")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}")
    for e in s.events[-10:]:
        print(f"    {e}")


def scenario_vdc_insert_at_gap_boundary():
    """Insert ровно на границе GAP-блока (idx=lb или idx=rb+1)."""
    s = ChainSimVDC()
    # chain: [0, 1, GAP_STOP, GAP_STOP, GAP_STOP, 1, 2]
    # Insert color 1 at idx=2 (= перед GAP). slots after shift: [0, 1, 1, GAP×3, 1, 2]
    s.SlotsLen = 7
    s.Slots[:7] = [0, 1, GAP_STOP, GAP_STOP, GAP_STOP, 1, 2]
    print("\n=== VDC: Insert at GAP head-boundary (color = soседа) ===")
    print(f"  init: {s.Slots[:s.SlotsLen]}")
    s.insert_ball(2, 1)
    print(f"  after insert: {s.Slots[:s.SlotsLen]}")
    s.check_match3(2)
    print(f"  after check_match3: {s.Slots[:s.SlotsLen]}")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}")
    for e in s.events:
        print(f"    {e}")


def scenario_vdc_long_chain_match_at_edge():
    """Match на самом начале/конце цепочки (edge cases для cascade detect)."""
    s = ChainSimVDC()
    # Match at slot 0..2 (no head-side neighbor)
    s.SlotsLen = 7
    s.Slots[:7] = [1, 1, 1, 0, 2, 0, 0]
    print("\n=== VDC: Match at HEAD edge (lb=0, no head neighbor) ===")
    s.events.clear()
    s.check_match3(1)
    print(f"  after check_match3: {s.Slots[:s.SlotsLen]}, expected GAP_STOP (no cascade detect)")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}")
    for e in s.events:
        print(f"    {e}")

    # Match at slot SlotsLen-3..SlotsLen-1 (no tail-side neighbor)
    s = ChainSimVDC()
    s.SlotsLen = 7
    s.Slots[:7] = [0, 2, 0, 0, 1, 1, 1]
    print("\n=== VDC: Match at TAIL edge (rb=last, no tail neighbor) ===")
    s.events.clear()
    s.check_match3(5)
    print(f"  after check_match3: {s.Slots[:s.SlotsLen]}")
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}")
    for e in s.events:
        print(f"    {e}")


def scenario_vdc_cascade_chain_3_levels():
    """Match → cascade → match → cascade → match. 3-уровневый cascade combo."""
    s = ChainSimVDC()
    # Цепочка специально такая, чтобы after first match cascade соседей был new run
    # init: [A, A, B, B, B, A, A, C] insert(2, B) → [A, A, B, B, B, B, A, A, C]
    # Wait: уже B,B,B в init.
    # Cleaner: [0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0] — insert match cascade chain.
    # init: [A=0, A=0, B=1, B=1, B=1, A=0, A=0, B=1, B=1, B=1, A=0]
    # after match at [2..4]: GAP_CASCADE (соседи 0=0). closure → [0,0,0,0,1,1,1,0]
    # next match [0..3] count=4 cascade or stop? соседи: [0..3] left=none, right=1. Edge → STOP.
    s = ChainSimVDC()
    s.SlotsLen = 11
    s.Slots[:11] = [0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0]
    print("\n=== VDC: 3-level cascade combo ===")
    s.events.clear()
    s.check_match3(3)
    f = s.run_until_idle()
    print(f"  resolved in {f} frames. final: {s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}")
    matches = [e for e in s.events if 'match-3 detected' in e]
    print(f"  total matches in chain: {len(matches)}")
    for e in s.events:
        print(f"    {e}")


def scenario_vdc_fuzz():
    """Fuzz: random insert at random idx, проверка инвариантов."""
    import random
    random.seed(7)
    print("\n=== VDC FUZZ: 30 runs of random insert + closure ===")
    issues = 0
    for run_idx in range(30):
        s = ChainSimVDC()
        n = random.randint(5, 12)
        s.SlotsLen = n
        for k in range(n):
            s.Slots[k] = random.randint(0, NUM_BALL_COLORS-1)
        # 3 random inserts
        for _ in range(3):
            idx = random.randint(0, s.SlotsLen)
            color = random.randint(0, NUM_BALL_COLORS-1)
            s.insert_ball(idx, color)
            s.check_match3(idx)
            f = s.run_until_idle(max_frames=3000)
            # invariants
            for k in range(s.SlotsLen):
                if s.Slots[k] in (GAP_STOP, GAP_CASCADE):
                    print(f"  RUN {run_idx}: GAP осталось в slots[{k}] после run_until_idle")
                    issues += 1
                    break
    print(f"  total issues: {issues}/30")


def scenario_random_run_after_match():
    """
    Edge case: после match-3 в одном месте, чейн перезагрузился, и ScheduleCascade
    нашёл случайный run >=3 в другом месте. Это валидное HD-поведение, но игроку
    выглядит как 'match без причины'.
    """
    s = ChainSimSlots()
    s.HeadSlotAbs = 14
    s.SlotsLen = 14
    # Цепочка с случайным run [9,10,11]=2,2,2 далеко от планируемого insert.
    s.Slots[:14] = [0, 1, 0, 1, 1, 1, 0, 1, 0, 2, 2, 2, 0, 1]
    print("\n=== Random run после match (выглядит как ложный match) ===")
    print(f"  init slots: {s.Slots[:s.SlotsLen]}")

    # Игрок выстрелил 1 в idx=4 → run [3..5]=1,1,1 → но был уже 1,1,1
    # Уже есть 3 единицы [3,4,5]. detect_match3(3) → должно lb=3,rb=5,count=3.
    matched, lb, rb, count = s.detect_match3(3)
    print(f"  detect at idx=3: matched={matched}, lb={lb}, rb={rb}, count={count}")
    s.set_match_pending(lb, rb)
    print(f"  PENDING: {s.Slots[:s.SlotsLen]}")

    # Полный scan для cascade detection (= ScheduleCascade в ASM)
    found = s.schedule_cascade_scan()
    print(f"  ScheduleCascade scan по Slots: found={found}")
    print(f"  → если found != None и не в зоне (lb..rb), это будет 'ложный match' для игрока")

    # Compaction — close gap из match-3
    result = s.compact_and_detect(lb, rb, count)
    print(f"  COMPACT: slots={s.Slots[:s.SlotsLen]}, result={result}")

    # После compaction, ScheduleCascade триггер: ProcessCascade на CascadeIdx из ScheduleCascade.
    # Если CascadeIdx указывает в run [9..11] (теперь по новому индексу [9-3..11-3]=[6..8]),
    # next CheckMatch3 на этом idx сработает — это и есть "ложный match".
    if found is not None:
        old_lb, old_rb, old_count = found
        # Идекс после compaction (если before run был справа от первого match'а)
        new_idx = old_lb - count if old_lb > rb else old_lb
        print(f"  После compaction run был [{old_lb}..{old_rb}] → новый idx={new_idx}")
        m2, lb2, rb2, c2 = s.detect_match3(new_idx + 1)  # центр
        print(f"  detect_match3 при ScheduleCascade trigger: matched={m2}, lb={lb2}, rb={rb2}, count={c2}")
        if m2:
            print(f"  ↑ ВТОРОЙ match сработает — для игрока это 'случайный match-3 без выстрела'")


def run_until_idle(s, max_frames=600, color_seq=None):
    """Прокручивает tick'и пока match-flow не завершится (CompactTimer=StopTimer=Cascade=0, all offsets=0).
    Возвращает кадры, snapshot, issues."""
    issues = []
    f0 = s.FrameCounter
    while s.FrameCounter - f0 < max_frames:
        s.tick(color_seq)
        problems = s.check_invariants()
        if problems:
            issues.extend([f"frame {s.FrameCounter}: {p}" for p in problems])
        all_zero = all(s.SlotOffsets[k] == 0 for k in range(s.SlotsLen))
        if (s.CompactTimer == 0 and s.StopTimer == 0 and s.CascadeState == 0
                and s.ChainStalled == 0 and all_zero):
            break
    return s.FrameCounter - f0, issues


def make_chain(slots_list, hsa=None):
    """Helper — построить chain с заданными slots[]."""
    s = ChainSimASM()
    s.HeadSlotAbs = hsa if hsa is not None else len(slots_list)
    s.SlotsLen = len(slots_list)
    for k, c in enumerate(slots_list):
        s.Slots[k] = c
    s.BallsSpawned = ChainSimASM.LEVEL_TOTAL  # spawn off
    return s


def analyze_v1_stop_simple():
    """Вариант 1: разные цвета на стыке → stop-mode, tail подъезжает."""
    print("\n=== ВАРИАНТ 1: STOP-mode (разные цвета на стыке) ===")
    s = make_chain([0, 1, 1, 2, 0, 1])  # insert color=1 at idx=2 → match [1,2] цвета 1
    s.insert_ball(2, 1)                   # → [0, 1, 1, 1, 2, 0, 1]
    s.check_match3(2)                     # match: lb=1, rb=3, count=3
    print(f"  до compaction: slots={s.Slots[:s.SlotsLen]}, gap visible")
    frames, issues = run_until_idle(s)
    print(f"  завершилось за {frames} кадров")
    print(f"  final slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}, sub={s.HeadSub}")
    print(f"  issues: {issues if issues else '(нет)'}")


def analyze_v2_cascade_simple():
    """Вариант 2: одинаковые на стыке → cascade-mode, head катится к хвосту."""
    print("\n=== ВАРИАНТ 2: CASCADE-mode (одинаковые на стыке) ===")
    # init: [A=0, A=0, B=1, B=1, B=1, A=0, A=0, X=2]
    # insert color=1 at idx=3 — но там уже 1 → match. Лучше построить конкретно:
    # [0, 0, 1, 1, 0, 1, 2] — после insert(2, 1): [0, 0, 1, 1, 1, 0, 1, 2]
    # match: lb=2,rb=4,count=3. После compaction: [0, 0, 0, 1, 2]. Stык: Slots[1]=0, Slots[2]=0 → CASCADE.
    s = make_chain([0, 0, 1, 1, 0, 1, 2])
    s.insert_ball(2, 1)
    s.check_match3(2)
    print(f"  match установлен: pending lb={s.PendingMatchLeft}, rb={s.PendingMatchRight}")
    frames, issues = run_until_idle(s, max_frames=1000)
    print(f"  завершилось за {frames} кадров")
    print(f"  final slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}")
    print(f"  cascade triggered next match? {len([e for e in s.event_log if 'match-3 detected' in e])} match'ей")
    print(f"  issues: {issues if issues else '(нет)'}")
    # Проверка: tail-шар должен сохранить свою t-позицию между insert и завершением
    # t изменения tail отслежим через event_log


def analyze_v1_recursive():
    """Вариант 1 рекурсивно: stop → после паузы случайно ещё match (от спавна) → stop."""
    print("\n=== ВАРИАНТ 1 РЕКУРСИВНО: серия stop-mode ===")
    # Цепочка с двумя независимыми runs одного цвета, разделёнными разноцветными.
    # После первого match (stop-mode), второй match не должен сработать автоматически —
    # он сработает только при выстреле или ScheduleCascade (отключена в нашей discrete model).
    s = make_chain([0, 1, 1, 2, 1, 1, 0, 2])   # один run [1,2] цвета 1, один [4,5] цвета 1
    s.insert_ball(2, 1)                          # → [0, 1, 1, 1, 2, 1, 1, 0, 2]
    s.check_match3(2)                            # match цвета 1, lb=1,rb=3,count=3
    frames1, issues1 = run_until_idle(s, max_frames=500)
    print(f"  match #1 завершён за {frames1} кадров. slots={s.Slots[:s.SlotsLen]}")
    # Сейчас [0, 2, 1, 1, 0, 2]. Run [2,3] цвета 1 — len=2, не match.
    # Симулируем второй insert игроком
    s.insert_ball(2, 1)
    s.check_match3(2)
    frames2, issues2 = run_until_idle(s, max_frames=500)
    print(f"  match #2 завершён за {frames2} кадров. slots={s.Slots[:s.SlotsLen]}")
    print(f"  total issues: {issues1 + issues2 if (issues1 or issues2) else '(нет)'}")


def analyze_v2_recursive():
    """Вариант 2 рекурсивно: cascade → cascade → cascade. HD-style combo."""
    print("\n=== ВАРИАНТ 2 РЕКУРСИВНО: цепочка cascade'ев ===")
    # Цепочка где после первого match'а cascade откроет ещё match, и т.д.
    # init: [0, 0, 0, 1, 1, 1, 0, 0, 0, 2]
    # insert color=1 at idx=4 — НЕ нужно, уже есть 3 единицы.
    # Try: [1, 0, 0, 2, 0, 0, 1, 2]
    # insert(0, 1) → [1, 1, 0, 0, 2, 0, 0, 1, 2]. detect at 0: only Slots[0]=1, Slots[1]=1, count=2. No match.
    # Лучше: [0, 0, 1, 1, 0, 0, 1, 0, 0, 2]
    # insert(2, 1): [0, 0, 1, 1, 1, 0, 0, 1, 0, 0, 2]. detect: lb=2,rb=4,count=3.
    # После compaction: [0, 0, 0, 0, 1, 0, 0, 2]. Stык: Slots[1]=0, Slots[2]=0 → cascade.
    # HSA -= 3. Slots[0..3]=0,0,0,0 → следующий match: lb=0,rb=3,count=4.
    # После compaction: [1, 0, 0, 2]. Edge — нет head-half. Cascade end.
    s = make_chain([0, 0, 1, 1, 0, 0, 1, 0, 0, 2])
    s.insert_ball(2, 1)
    s.check_match3(2)
    frames, issues = run_until_idle(s, max_frames=1500)
    matches = len([e for e in s.event_log if 'match-3 detected' in e])
    print(f"  завершилось за {frames} кадров, всего match'ей: {matches}")
    print(f"  final slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}")
    print(f"  cascade chain log:")
    for e in s.event_log[-10:]:
        print(f"    {e}")
    print(f"  issues: {issues if issues else '(нет)'}")


def analyze_combined_recursion():
    """Рекурсия комбинаций: cascade → stop, stop → cascade, etc."""
    print("\n=== РЕКУРСИЯ КОМБИНАЦИЙ ===")
    # cascade → stop:
    # initial: [0, 0, 1, 1, 0, 0, 2, 1, 0]
    # insert(2, 1): [0, 0, 1, 1, 1, 0, 0, 2, 1, 0]
    # match lb=2,rb=4. Compaction: [0, 0, 0, 0, 2, 1, 0]. Стык 1=0, 2=0 → CASCADE.
    # HSA -= 3. Slots[0..3]=0,0,0,0 → match lb=0,rb=3,count=4.
    # Compaction: [2, 1, 0]. Edge → no cascade.
    print("  Сценарий: CASCADE → еще match (edge) → завершение")
    s = make_chain([0, 0, 1, 1, 0, 0, 2, 1, 0])
    s.insert_ball(2, 1)
    s.check_match3(2)
    frames, issues = run_until_idle(s, 1500)
    print(f"    finish in {frames} frames. final slots={s.Slots[:s.SlotsLen]}")
    matches = [e for e in s.event_log if 'match-3 detected' in e]
    modes = [e for e in s.event_log if 'compact' in e.lower()]
    print(f"    matches: {len(matches)}, modes: {[m.split(' ')[2] for m in modes]}")
    print(f"    issues: {issues if issues else '(нет)'}")

    print("\n  Сценарий: STOP → новый insert → CASCADE")
    s = make_chain([0, 1, 1, 2, 0, 0])  # short chain
    s.insert_ball(2, 1)                 # match цвет 1
    s.check_match3(2)
    f1, _ = run_until_idle(s, 200)
    print(f"    после первого insert: {s.Slots[:s.SlotsLen]} (за {f1} кадров)")
    # Теперь Slots = [0, 2, 0, 0]. Соседи 0 == 0 в [2,3]. Insert 0 at idx=2 → match lb=2,rb=4,count=3.
    s.insert_ball(2, 0)
    s.check_match3(2)
    f2, _ = run_until_idle(s, 1500)
    print(f"    после второго insert: {s.Slots[:s.SlotsLen]} (за {f2} кадров)")


def analyze_fuzz_random():
    """Fuzz-test: random chain + random insert sequences. Логирует issues."""
    print("\n=== FUZZ-TEST: random sequences ===")
    import random
    random.seed(42)
    issues_per_run = []
    for run in range(20):
        # Random initial chain длины 6..15, цвета 0..2
        n = random.randint(6, 15)
        slots = [random.randint(0, 2) for _ in range(n)]
        s = make_chain(slots)
        all_issues = []
        # 5 случайных insert'ов
        for _ in range(5):
            idx = random.randint(0, s.SlotsLen)
            color = random.randint(0, 2)
            s.insert_ball(idx, color)
            s.check_match3(idx)
            _, iss = run_until_idle(s, max_frames=2000)
            all_issues.extend(iss)
        issues_per_run.append(len(all_issues))
        if all_issues:
            print(f"  RUN {run}: {len(all_issues)} issues:")
            for iss in all_issues[:3]:
                print(f"    {iss}")
    bad_runs = sum(1 for c in issues_per_run if c > 0)
    print(f"  total: {bad_runs}/{len(issues_per_run)} runs with issues")


def scenario_stop_mode():
    """Stop-mode: разные цвета на стыке после remove."""
    s = ChainSimSlots()
    s.HeadSlotAbs = 7
    s.SlotsLen = 8
    s.Slots[:8] = [0, 1, 1, 1, 2, 0, 1, 2]
    # Insert color=1 at idx=3 — даст match идущий до idx=2 (где 1, 1, 1).
    print("\n=== STOP mode (разные цвета на стыке) ===")
    print(f"  init: hsa={s.HeadSlotAbs}, slots={s.Slots[:s.SlotsLen]}")
    s.insert(3, 1)
    print(f"  after insert(3,1): slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}")
    matched, lb, rb, count = s.detect_match3(3)
    print(f"  detect: matched={matched}, lb={lb}, rb={rb}, count={count}")
    assert matched
    s.set_match_pending(lb, rb)
    result = s.compact_and_detect(lb, rb, count)
    print(f"  COMPACT: slots={s.Slots[:s.SlotsLen]}, hsa={s.HeadSlotAbs}, result={result}")
    print(f"  Ожидается 'stop' (Slots[lb-1]={s.Slots[lb-1]} vs Slots[lb]={s.Slots[lb] if lb < s.SlotsLen else 'EOF'})")


# ==============================================================
if __name__ == "__main__":
    scenario_fast_phase()
    scenario_single_insert_no_match()
    scenario_match3_stop_mode()
    scenario_match3_cascade_mode()
    scenario_insert_during_stall()
    scenario_overlap_check()
    # Slot-array
    scenario_slots_match3_basic()
    scenario_slots_gap_blocks_match()
    scenario_slots_with_gap_marker()
    scenario_slots_cascade_scan()
    scenario_cascade_full_flow()
    scenario_stop_mode()
    scenario_random_run_after_match()
    print("\n" + "=" * 60)
    print("VDC модель — полная эмуляция")
    print("=" * 60)
    scenario_vdc_basic_cascade()
    scenario_vdc_insert_in_visible_gap()
    scenario_vdc_two_gaps_simultaneously()
    scenario_vdc_insert_at_gap_boundary()
    scenario_vdc_long_chain_match_at_edge()
    scenario_vdc_cascade_chain_3_levels()
    scenario_vdc_fuzz()
    print("\n" + "=" * 60)
    print("РАСШИРЕННЫЙ АНАЛИЗ: варианты, рекурсии, комбинации")
    print("=" * 60)
    analyze_v1_stop_simple()
    analyze_v2_cascade_simple()
    analyze_v1_recursive()
    analyze_v2_recursive()
    analyze_combined_recursion()
    analyze_fuzz_random()
