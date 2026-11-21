#!/usr/bin/env python3
"""v0.13: tremolo on the master volume (NR50), from Fat Chip 64's globals:
CC 115 depth 0-15, 116 shape (TRI SINE SAW UP SAW DOWN SQUARE RANDOM PUMP
GATE x3), 117 sync (0 FREE, 1 BAR ... 1/32: locked to the tempo and the
downbeat), 118 / 119 the FREE rate (Hz x 100, MSB then LSB).
v0.18: the frame tick sets a target (nr50_tgt); the timer interrupt walks NR50
there a level at a time (no jumps: on hardware each NR50 step moves every
on DAC's DC, which clicked), and while a tremolo runs, channels silent for
ten frames have their DACs switched off."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info != "" else ""))
    fails += 0 if cond else 1


def nr50(gb, frames):           # the tremolo's level each frame (the target the volume walks to)
    out = []
    for _ in range(frames):
        gb.run(1)
        out.append(gb.var("_nr50_tgt") & 7)
    return out


gb = GB(ROM, sram=bytes(8192))
gb.run(150)
gb.cc(0, 102, 70)
gb.run(2)
check("no tremolo: the master volume full (NR50 0x77)", gb.mem(0xFF24) == 0x77, hex(gb.mem(0xFF24)))

# FREE, TRI, 2 Hz (200 = 1 x 128 + 72)
gb.cc(0, 116, 0)
gb.cc(0, 117, 0)
gb.cc(0, 118, 1)
gb.cc(0, 119, 72)
gb.cc(0, 115, 15)
v = nr50(gb, 90)
lows = [i for i in range(1, 90) if v[i] == 0 and v[i - 1] != 0]      # (each dip's start)
check("TRI, FREE 2 Hz, depth 15: the volume swings from full to nothing", max(v) == 7 and min(v) == 0, (min(v), max(v)))
check("... about every 30 frames (2 Hz)", len(lows) >= 2 and all(26 <= b - a <= 34 for a, b in zip(lows, lows[1:])), lows)
gb.cc(0, 115, 6)
v = nr50(gb, 60)
check("depth 6: a shallower swing (never below 4)", min(v) >= 4 and max(v) == 7 and min(v) < 7, (min(v), max(v)))

# SYNC 1/4 at 120 BPM: PUMP on every beat, from the downbeat
gb.cc(0, 115, 15)
gb.cc(0, 107, 30)
gb.cc(0, 108, 0)                              # 120 BPM
gb.cc(0, 116, 6)                              # PUMP
gb.cc(0, 117, 3)                              # 1/4
gb.run(20)
gb.cc(0, 109, 0)                              # downbeat
v = nr50(gb, 64)
check("PUMP, SYNC 1/4 at 120 BPM: ducked right after the downbeat ...", v[0] == 0 or v[1] == 0, v[:6])
check("... back to full by mid-beat, ducked again a beat later (30 frames)", v[20] == 7 and (v[30] == 0 or v[31] == 0), (v[18:22], v[28:33]))

# GATE X.X.XX.X: hard on / off only
gb.cc(0, 116, 7)
gb.cc(0, 117, 1)                              # 1 BAR: eighth notes
gb.run(4)
v = nr50(gb, 120)
check("GATE: only full or nothing", set(v) <= {0, 7} and set(v) == {0, 7}, sorted(set(v)))

nr = gb.var("_nr50_cur") & 7
check("GATE: the master volume walks there (between frames it's caught up with the target)",
      gb.var("_nr50_cur") == gb.var("_nr50_tgt") or abs(nr - (gb.var("_nr50_tgt") & 7)) <= 2, (hex(gb.var("_nr50_cur")), hex(gb.var("_nr50_tgt"))))
gb.cc(0, 115, 15)
gb.cc(0, 116, 4)                              # SQUARE: full <-> nothing
gb.cc(0, 117, 0)
gb.cc(0, 118, 0)
gb.cc(0, 119, 100)                            # 1 Hz
gb.run(40)
check("silent channels' DACs off while the tremolo runs (NR12 NR22 NR30 NR42 all 0)",
      gb.mem(0xFF12) == 0 and gb.mem(0xFF17) == 0 and (gb.mem(0xFF1A) & 0x80) == 0 and gb.mem(0xFF21) == 0,
      [hex(gb.mem(a)) for a in (0xFF12, 0xFF17, 0xFF1A, 0xFF21)])
gb.note(0, 60, 100)
gb.run(4)
check("... and a note still plays (its DAC back on)", gb.mem(0xFF12) != 0, hex(gb.mem(0xFF12)))
gb.off(0, 60)

gb.cc(0, 115, 0)
gb.run(3)
check("depth 0: full volume again", gb.mem(0xFF24) == 0x77, hex(gb.mem(0xFF24)))

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
