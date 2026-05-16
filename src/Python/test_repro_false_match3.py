"""
Repro test для бага «ложный match-3»:
после взрыва 3 шаров одного цвета финализация (через EXPLOSION_FRAMES=14 кадров)
пишет GAP по СТАРОМУ индексу. Если в течение этих 14 кадров игрок успел сделать
insert левее exploding-блока, exploding_frame/exploding_marker массивы остаются
указывать на старые индексы, и финализация удаляет non-exploding шар по соседству.

Ожидаемое поведение (после fix):
  insert на idx_l < lb (левее exploding-блока) сдвигает exploding_frame/marker
  вместе с slots/offsets/shot2.

Запуск:
  python test_repro_false_match3.py        # demonstrate bug (current code)
  python test_repro_false_match3.py --fix  # с fix'ом — repro должен исчезнуть

Без fix'а: 1 невинный шар (цвет=другой) превращается в GAP.
С fix'ом:    только три exploding шара превращаются в GAP, остальные сохраняются.
"""
import sys
sys.path.insert(0, 'c:/z80/zuma')

from vdc_visual_emulator import VDCEngine, VDCState, EXPLOSION_FRAMES, GAP_STOP, GAP_CASCADE, NUM_BALL_COLORS, is_gap, MAX_SLOTS, CELL_SIZE, sat_signed

APPLY_FIX = '--fix' in sys.argv

# ---------- Monkey-patch для fix'а ----------
if APPLY_FIX:
    _orig_insert = VDCEngine.insert_at
    def insert_at_fixed(self, target_idx, color):
        s = self.s
        if s.slots_len >= MAX_SLOTS: return False
        if target_idx > s.slots_len: target_idx = s.slots_len
        if s.slots_len == 0:
            head_off = 0; tail_off = 0
        elif target_idx == 0:
            head_off = s.offsets[0]; tail_off = s.offsets[0]
        elif target_idx == s.slots_len:
            head_off = s.offsets[target_idx - 1]; tail_off = s.offsets[target_idx - 1]
        else:
            head_off = s.offsets[target_idx - 1]; tail_off = s.offsets[target_idx]
        new_offset = -CELL_SIZE // 2 + (head_off + tail_off) // 2
        for j in range(s.slots_len, target_idx, -1):
            s.slots[j] = s.slots[j-1]
            s.offsets[j] = s.offsets[j-1]
            s.shot2[j] = s.shot2[j-1]
            s.last_render_pos[j] = s.last_render_pos[j-1]
            s.rollback_counter[j] = s.rollback_counter[j-1]
            # FIX: shift exploding arrays вместе с slots
            s.exploding_frame[j] = s.exploding_frame[j-1]
            s.exploding_marker[j] = s.exploding_marker[j-1]
        s.slots[target_idx] = color
        s.offsets[target_idx] = sat_signed(new_offset)
        s.shot2[target_idx] = 1
        s.last_render_pos[target_idx] = None
        s.rollback_counter[target_idx] = 0
        s.exploding_frame[target_idx] = 0
        s.exploding_marker[target_idx] = GAP_STOP
        s.slots_len += 1
        if s.hsa < len(self.track) // CELL_SIZE - 1:
            s.hsa += 1
        for i in range(target_idx):
            s.offsets[i] = max(s.offsets[i] - CELL_SIZE, -CELL_SIZE)
        s.chain_freeze_counter = CELL_SIZE
        return self.check_match3(target_idx)
    VDCEngine.insert_at = insert_at_fixed

# ---------- Repro ----------
# Простой синтетический track: 100 cells × 32 px по горизонтали.
track = [(20 + i, 100) for i in range(100 * CELL_SIZE)]
e = VDCEngine(track, seed=42)
s = e.s

# Setup: 6 шаров в цепи. Цвета: 0,1,2,2,2,3
# (slot 0..5; slot 2..4 = цвет 2 = group для match)
COLORS = [0, 1, 2, 2, 2, 3]
for i, c in enumerate(COLORS):
    s.slots[i] = c
    s.offsets[i] = 0
s.slots_len = len(COLORS)
s.hsa = 50
s.hsub = 0

print(f"Initial chain: {s.slots[:s.slots_len]}")

# Триггерим match-3: добавляем ещё 1 шар цвета 2 рядом → group 4 шара? Нет, мы хотим именно 3.
# Просто принудительно вызовем check_match3 на slot 3 (центр группы 2-2-2):
s.shot2[3] = 1  # marker для detection
matched = e.check_match3(3)
print(f"After check_match3(3): matched={matched}")
print(f"  Slots:           {s.slots[:s.slots_len]}")
print(f"  ExplodingFrame:  {s.exploding_frame[:s.slots_len]}")
print(f"  ExplodingMarker: [{', '.join(hex(m) for m in s.exploding_marker[:s.slots_len])}]")

# В этот момент: exploding_frame[2..4]=1, slots[2..4] = colors всё ещё.
# Теперь СИМУЛИРУЕМ insert ЛЕВЕЕ exploding-блока (idx=1).
# Это критический момент: exploding_frame должно сдвинуться на 1 вправо.
print(f"\n--- Insert color=5 at idx=1 (левее exploding-блока) ---")
e.insert_at(1, 5)
print(f"  Slots:           {s.slots[:s.slots_len]}")
print(f"  ExplodingFrame:  {s.exploding_frame[:s.slots_len]}")
print(f"  ExplodingMarker: [{', '.join(hex(m) for m in s.exploding_marker[:s.slots_len])}]")

# Без fix: exploding_frame[2..4]=1, но slot 2 теперь = старое slots[1] = color 1 (НЕ exploding-цвет).
# Slots[3..5] = старые slots[2..4] = group цвета 2 (правильные exploding).
# Через EXPLOSION_FRAMES финализация сделает Slots[2..4] = GAP_STOP.
# Это значит slot 2 (= не должен взрываться, color 1) превратится в GAP — баг.

# Прокручиваем animate_chain до финализации
for fr in range(EXPLOSION_FRAMES + 2):
    e.animate_chain()

print(f"\n--- После финализации (EXPLOSION_FRAMES прошло) ---")
print(f"  Slots: {[hex(v) if v >= NUM_BALL_COLORS else v for v in s.slots[:s.slots_len]]}")
print(f"  ExplodingFrame: {s.exploding_frame[:s.slots_len]}")

# Проверка: какие индексы стали GAP?
gap_indices = [i for i in range(s.slots_len) if is_gap(s.slots[i])]
expected_color2_indices_after_insert = [3, 4, 5]  # старые 2,3,4 после shift_right на 1
print(f"\n  GAP indices: {gap_indices}")
print(f"  Expected (color=2 после shift): {expected_color2_indices_after_insert}")

if set(gap_indices) == set(expected_color2_indices_after_insert):
    print("\n[PASS] Финализация удалила правильные exploding-шары")
else:
    extra = set(gap_indices) - set(expected_color2_indices_after_insert)
    missed = set(expected_color2_indices_after_insert) - set(gap_indices)
    print(f"\n[FAIL] Ложный match-3 воспроизведён:")
    if extra:
        print(f"  Лишние GAP (НЕ должны были взорваться): {sorted(extra)}")
    if missed:
        print(f"  Пропущенные (ДОЛЖНЫ были взорваться): {sorted(missed)}")
