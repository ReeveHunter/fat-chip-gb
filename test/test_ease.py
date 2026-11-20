#!/usr/bin/env python3
"""v0.14: CC 90 EASED GLIDE (per voice, not saved): with glide on, a new note
is reached along an S curve over that many frames (it leaves gently, arrives
gently, takes exactly that long). Fat Chip 64 sends it in DRONE."""
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


def pitch(gb, v=0):
    a = gb.sym["_voice"] + v * 48 + 14                       # voice_t.pitch (8.8 semitones)
    p = gb.mem(a) | gb.mem(a + 1) << 8
    return (p - 65536 if p > 32767 else p) / 256


def glide(gb, ease):
    gb.cc(0, 90, ease)
    gb.note(0, 60)
    gb.run(10)
    gb.note(0, 72)                                           # (60 still sounding: it glides)
    seq = []
    for _ in range(90):
        gb.run(1)
        seq.append(pitch(gb))
    gb.off(0, 72)
    gb.off(0, 60)
    gb.run(40)
    return seq


def fresh():
    gb = GB(ROM, sram=bytes(8192))
    gb.run(150)
    gb.cc(0, 102, 70)
    gb.cc(0, 5, 127)                                         # glide on (slowest)
    gb.cc(0, 72, 127)
    gb.run(5)
    return gb


lin = glide(fresh(), 0)
ez = glide(fresh(), 60)
frac = lambda s, i: (s[i] - 60) / 12
check("pitch read right (a glide to 72 ends there)", abs(ez[-1] - 72) < 0.05, round(ez[-1], 2))
step = lambda s, i: s[i] - s[i - 1]
check("the usual glide rushes off: its biggest steps at the start", step(lin, 2) > step(lin, 30) > 0, (round(step(lin, 2), 3), round(step(lin, 30), 3)))
check("the eased one: its biggest in the middle", step(ez, 30) > step(ez, 3) and step(ez, 30) > step(ez, 57), (round(step(ez, 3), 3), round(step(ez, 30), 3), round(step(ez, 57), 3)))
check("EASED GLIDE 60 frames: leaves gently (under 20 % a quarter of the way in)", frac(ez, 14) < 0.2, round(frac(ez, 14), 2))
check("... half way at half time", 0.4 < frac(ez, 29) < 0.6, round(frac(ez, 29), 2))
check("... arrives gently (over 80 % three quarters in) and is there at 60 frames", frac(ez, 44) > 0.8 and abs(ez[60] - 72) < 0.01 and abs(ez[57] - 72) > 0.001,
      (round(frac(ez, 44), 2), round(ez[57], 3), round(ez[60], 3)))
check("... smooth: never steps back", all(b >= a - 1e-9 for a, b in zip(ez, ez[1:])))

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
