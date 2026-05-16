#!/usr/bin/env python3
"""Headless тест Game Over absorption. Прогоняет engine forward, логирует переходы states."""
import sys
sys.path.insert(0, 'C:/z80/zuma')
from vdc_visual_emulator import (
    VDCEngine, load_track, GAP_STOP, GAP_CASCADE, MAX_SLOTS, CELL_SIZE, NUM_BALL_COLORS, is_gap
)

track = load_track()
engine = VDCEngine(track, seed=42)
kx, ky = track[-1]
track_len = len(track)
print(f'track len={track_len} max_hsa={track_len//CELL_SIZE - 1} kz=({kx},{ky})')

absorb_threshold = 16
game_state = 0
absorb_count = 0
last_print = 0

def head_dist():
    if engine.s.slots_len == 0: return None
    head = engine.slot_pos(0)
    if head is None: return None
    return abs(head[0] - kx) + abs(head[1] - ky)

def absorb():
    s = engine.s
    if s.slots_len == 0: return
    for i in range(s.slots_len - 1):
        s.slots[i] = s.slots[i+1]
        s.offsets[i] = s.offsets[i+1]
        s.shot2[i] = s.shot2[i+1]
        s.last_render_pos[i] = s.last_render_pos[i+1]
        s.rollback_counter[i] = s.rollback_counter[i+1]
        s.exploding_frame[i] = s.exploding_frame[i+1]
        s.exploding_marker[i] = s.exploding_marker[i+1]
    s.slots_len -= 1
    s.hsa += 1

# Spawn fast (skip cooldowns) — fill chain fast
for frame in range(20000):
    if game_state == 0:
        if engine.s.balls_spawned < 60:
            engine.try_spawn()
        engine.move_chain()
        engine.animate_chain()
        engine.s.frame += 1
        d = head_dist()
        if d is not None and d < absorb_threshold:
            game_state = 1
            print(f'[F{frame:5d}] ⇒ STATE 1 (trigger absorption). dist={d}, hsa={engine.s.hsa}, slotsLen={engine.s.slots_len}')
    elif game_state == 1:
        for _ in range(12):
            engine.move_chain()
        engine.animate_chain()
        engine.s.frame += 1
        d = head_dist()
        if d is not None and d < absorb_threshold:
            absorb()
            absorb_count += 1
            if absorb_count <= 5 or absorb_count % 5 == 0:
                print(f'[F{frame:5d}] ABSORB #{absorb_count}, slotsLen={engine.s.slots_len}, hsa={engine.s.hsa}, dist_after={head_dist()}')
        if engine.s.slots_len == 0:
            game_state = 2
            print(f'[F{frame:5d}] ⇒ STATE 2 (all absorbed, chain empty). Total absorbs: {absorb_count}')
            break
    if frame - last_print >= 500 and game_state == 0:
        d = head_dist()
        print(f'[F{frame:5d}] state={game_state} slotsLen={engine.s.slots_len} hsa={engine.s.hsa} dist={d}')
        last_print = frame
else:
    print(f'[F{frame:5d}] TIMEOUT — did not reach state 2. game_state={game_state}, slotsLen={engine.s.slots_len}, hsa={engine.s.hsa}, dist={head_dist()}')
