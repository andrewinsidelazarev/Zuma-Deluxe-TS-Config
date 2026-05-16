"""Compare game state snapshot after InitGame between two builds.

Run this twice: with baseline build active, save snapshot. Then apply refactor,
build, run again with --compare to diff against saved baseline snapshot.
"""
import sys, json, argparse
sys.path.insert(0, '_z80_lib_cburbridge/src')
from zuma_ts_emulator import ZumaTSEmulator

def snapshot(emu):
    """Take state snapshot of all gameplay vars."""
    sym = emu.sym
    s = {}
    s['sym_TrackData'] = sym['TrackData']
    s['sym_TRACK_NUM_POINTS'] = sym['TRACK_NUM_POINTS']
    s['sym_DirXTable'] = sym.get('DirXTable')
    s['sym_BallsPalette'] = sym.get('BallsPalette')
    # Memory snapshots at key addresses
    for name in ['Chain0_Slots', 'Chain0_SlotOffsets', 'FrogX', 'FrogY', 'KzCenterX', 'KzCenterY',
                 'ChainStalled', 'BallsSpawned', 'FrameCounter', 'BallTable', 'Scene']:
        if name not in sym: continue
        addr = sym[name]
        n = 70 if 'Slots' in name or 'Offsets' in name else (64 if name == 'BallTable' else 2)
        s[f'mem_{name}'] = bytes(emu.mem.read(addr+i) for i in range(n)).hex()
    # Read first 64 bytes of TrackData via PAGE3
    emu.mem.pages[3] = sym['TrackData'] >> 14  # high byte hint for page mapping
    # Restore PAGE3 to whatever runtime set
    s['final_PAGE3'] = emu.mem.pages[3]
    return s

ap = argparse.ArgumentParser()
ap.add_argument('--save', help='save snapshot to file')
ap.add_argument('--compare', help='compare against snapshot file')
args = ap.parse_args()

emu = ZumaTSEmulator()

# Run program from Start (Init code path including LS_Init + InitGame).
# That's too long — use direct call to InitGame instead.
# But InitGame expects PAGE3 etc. already set. Simulate that.
emu.mem.pages[3] = 0x03 if emu.sym['TrackData'] >= 0xC000 else 0x60  # heuristic
try:
    emu.call(emu.sym['InitGame'], max_steps=500000)
except Exception as e:
    print(f"InitGame error: {e} at PC=#{emu.reg.PC:04X}")

state = snapshot(emu)
print(f"=== State after InitGame (TrackData @ #{state['sym_TrackData']:04X}) ===")
for k, v in state.items():
    print(f"  {k}: {v}")

if args.save:
    open(args.save, 'w').write(json.dumps(state, indent=2))
    print(f"\nSaved to {args.save}")

if args.compare:
    other = json.loads(open(args.compare).read())
    print(f"\n=== Diff vs {args.compare} ===")
    diffs = 0
    for k in sorted(set(state.keys()) | set(other.keys())):
        a, b = state.get(k), other.get(k)
        if a != b:
            print(f"  {k}:")
            print(f"    current  = {a}")
            print(f"    baseline = {b}")
            diffs += 1
    if diffs == 0:
        print("  NO DIFFERENCES — states match byte-for-byte")
    else:
        print(f"\n{diffs} differences found")
