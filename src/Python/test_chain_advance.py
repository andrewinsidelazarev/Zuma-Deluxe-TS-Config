"""
Headless test: симулируем игру в Python emulator (без GUI), считаем сколько кадров
chain advance'ится прежде чем застрянет, и где именно. Сравнить с asm-поведением.
"""
import sys
sys.path.insert(0, 'c:/z80/zuma')
from vdc_visual_emulator import VDCEngine, load_track, CELL_SIZE, MAX_SLOTS

track = load_track()
e = VDCEngine(track, seed=42)
e.s.balls_spawned = 0

prev_hsa = -1
prev_hsub = -1
stall_streak = 0
max_stall = 0
track_max_hsa = len(track) // CELL_SIZE - 1

for frame in range(20000):
    e.s.frame = frame
    e.try_spawn()
    e.move_chain()
    e.animate_chain()
    if e.s.hsa == prev_hsa and e.s.hsub == prev_hsub:
        stall_streak += 1
        max_stall = max(max_stall, stall_streak)
    else:
        stall_streak = 0
    prev_hsa, prev_hsub = e.s.hsa, e.s.hsub
    if frame % 1000 == 0:
        gaps = sum(1 for i in range(e.s.slots_len) if e.s.slots[i] >= 6)
        explod = sum(1 for f in e.s.exploding_frame[:e.s.slots_len] if f > 0)
        print(f"frame={frame:5d} hsa={e.s.hsa:3d}/{track_max_hsa} hsub={e.s.hsub:2d} "
              f"len={e.s.slots_len:3d} stalled={e.s.chain_stalled} freeze={e.s.chain_freeze_counter:2d} "
              f"gaps={gaps} explod={explod} max_stall={max_stall}")

print(f"\n=== FINAL ===")
print(f"frame={frame} hsa={e.s.hsa}/{track_max_hsa} len={e.s.slots_len} "
      f"stalled={e.s.chain_stalled} freeze={e.s.chain_freeze_counter}")
print(f"max consecutive stall (no hsa/hsub change) = {max_stall} frames")
print(f"head reached killzone (hsa==max)? {e.s.hsa == track_max_hsa}")
