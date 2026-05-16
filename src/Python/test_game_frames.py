"""Run InitGame + N UpdateGame frames in harness, snapshot chain state per frame.

Compares baseline vs refactored build by running same sequence on both.
"""
import sys, json, argparse
sys.path.insert(0, '_z80_lib_cburbridge/src')
from zuma_ts_emulator import ZumaTSEmulator


def snapshot_chain(emu):
    """Read chain physics state into a dict."""
    sym = emu.sym
    s = {}
    for name, n in [
        ('Chain0_Slots', 80),
        ('Chain0_SlotOffsets', 80),
        ('FrogX', 2), ('FrogY', 2), ('FrogAngle', 1),
        ('KzCenterX', 2), ('KzCenterY', 2),
        ('ChainStalled', 1), ('BallsSpawned', 1),
        ('FrameCounter', 1), ('GameState', 1),
        ('BallTable', 64),
    ]:
        if name not in sym: continue
        addr = sym[name]
        s[name] = bytes(emu.mem.read(addr+i) for i in range(n)).hex()
    s['_SP'] = emu.reg.SP
    s['_PC'] = emu.reg.PC
    s['_PAGE3'] = emu.mem.pages[3]
    return s


def run(num_frames, snapshot_file=None, compare_file=None):
    emu = ZumaTSEmulator()
    sym = emu.sym

    # Mock track page mapping based on TrackData location.
    if sym['TrackData'] >= 0xC000:
        emu.mem.pages[3] = 0x03
    else:
        # baseline: track in slot 2 main1.bin + spillover #60
        emu.mem.pages[3] = 0x60

    # Initialize state: InitGame
    print(f"[init] TrackData @ #{sym['TrackData']:04X}, PAGE3 init = #{emu.mem.pages[3]:02X}")
    try:
        emu.call(sym['InitGame'], max_steps=500000)
    except Exception as e:
        print(f"  InitGame: {e} at PC=#{emu.reg.PC:04X}")

    # Force GameState=0 (playing) to enter chain physics path in UpdateGame.
    emu.set_byte(sym['GameState'], 0)
    # Reset frame counter to 0.
    emu.set_byte(sym['FrameCounter'], 0)

    # Mock mouse — pos (180,144) center, no buttons pressed.
    if 'MouseAbsX' in sym:
        emu.set_word(sym['MouseAbsX'], 180)
        emu.set_word(sym['MouseAbsY'], 144)
    emu.input.mouse_buttons = 0x03  # both released

    frames = []
    frames.append({'frame': -1, 'state': snapshot_chain(emu)})

    for i in range(num_frames):
        try:
            emu.call(sym['UpdateGame'], max_steps=500000)
        except Exception as e:
            print(f"  UpdateGame frame {i}: {e} at PC=#{emu.reg.PC:04X}")
            break
        frames.append({'frame': i, 'state': snapshot_chain(emu)})

    print(f"\n[done] ran {len(frames)-1} frames")

    if snapshot_file:
        json.dump({'sym_TrackData': sym['TrackData'], 'frames': frames}, open(snapshot_file, 'w'))
        print(f"Saved → {snapshot_file}")

    if compare_file:
        other = json.load(open(compare_file))
        print(f"\n=== Diff vs {compare_file} ===")
        of = other['frames']
        for i, (a, b) in enumerate(zip(frames, of)):
            af, bf = a['frame'], b['frame']
            diffs = []
            for k in sorted(set(a['state'].keys()) | set(b['state'].keys())):
                ax, bx = a['state'].get(k), b['state'].get(k)
                if ax != bx:
                    # Skip _SP / _PC / _PAGE3 noise — focus on game state
                    if k in ('_SP', '_PC', '_PAGE3'):
                        continue
                    diffs.append((k, ax, bx))
            if diffs:
                print(f"\n  Frame {af}: {len(diffs)} divergent fields")
                for k, ax, bx in diffs[:5]:
                    print(f"    {k}:")
                    print(f"      current  = {ax}")
                    print(f"      baseline = {bx}")
                if len(diffs) > 5:
                    print(f"    ... and {len(diffs)-5} more")
                # FIRST DIVERGENCE — that's the bug onset
                return af, diffs
        print("\n  NO DIVERGENCE in chain state across all frames")
        return None, []
    return None, []


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=10)
    ap.add_argument('--save')
    ap.add_argument('--compare')
    args = ap.parse_args()
    run(args.frames, args.save, args.compare)
