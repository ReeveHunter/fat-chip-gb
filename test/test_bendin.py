#!/usr/bin/env python3
"""v0.12: BEND IN's SHAPE and CLICK (CC 89, BEND SHAPE: bit 0 STEP, value >> 1
CLICK 1 SHORT / 2 LONG). STEP holds AMOUNT away for BEND TIME (17 ms - 1 s),
then jumps to the note; CLICK starts a pulse or wave note with a burst of
noise on the noise channel, while the noise voice is silent."""
import math
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


def semis(gb, v=0):
    """the pulse's sounding note from the engine's last written period (voice_t.out_period)"""
    a = gb.sym["_voice"] + 34 + v * gb_vsize
    per = gb.mem(a) | (gb.mem(a + 1) << 8)
    if not per or per == 0xFFFF:
        return None
    return 69 + 12 * math.log2(131072 / per / 440)


def noise_on(gb):
    return bool(gb.mem(0xFF26) & 0x08)


gb = GB(ROM, sram=bytes(8192))
gb.run(150)
gb_vsize = 0                                  # (voice 0 only)
gb.cc(0, 102, 70)
gb.cc(0, 80, 95)                              # BEND IN +12 (36 of 48: ceil(36 * 128 / 49))
gb.cc(0, 81, 64)                              # BEND TIME 8: STEP holds 12 frames (200 ms)
gb.cc(0, 89, 1)                               # STEP
gb.cc(0, 73, 0)
gb.cc(0, 75, 0)
gb.run(5)
check("CC 89 sets BEND SHAPE (taken as it is)", gb.var("_patch", 32)[23] == 1, gb.var("_patch", 32)[23])
gb.note(0, 60)
seq = []
for _ in range(24):
    gb.run(1)
    seq.append(semis(gb))
held = [s for s in seq[:10] if s is not None]
after = [s for s in seq[14:] if s is not None]
check("STEP: an octave up for the first 200 ms ...", held and all(abs(s - 72) < 0.3 for s in held), [round(s, 1) for s in held])
check("... then the note, at once (nothing in between)", after and all(abs(s - 60) < 0.3 for s in after)
      and all(abs(s - 72) < 0.3 or abs(s - 60) < 0.3 for s in seq if s is not None), [round(s, 1) for s in seq if s is not None])
gb.off(0, 60)
gb.run(30)

gb.cc(0, 89, 0)                               # SLIDE
gb.cc(0, 81, 64)
gb.note(0, 60)
seq = []
for _ in range(24):
    gb.run(1)
    seq.append(semis(gb))
mid = [s for s in seq if s is not None and 60.5 < s < 71.5]
check("SLIDE: it bends down through the notes in between, as before", len(mid) >= 3, len(mid))
gb.off(0, 60)
gb.run(30)

# CLICK SHORT: the noise channel, about 20 ms
gb.cc(0, 80, 63)                              # BEND IN 0: just the click
gb.cc(0, 89, 2)
gb.run(3)
gb.note(0, 60)
gb.run(1)
on1 = noise_on(gb)
gb.run(3)
check("CLICK SHORT: noise at the note's start, gone after about 20 ms", on1 and not noise_on(gb), (on1, noise_on(gb)))
gb.off(0, 60)
gb.run(20)

# CLICK LONG: as long as BEND TIME (12 frames)
gb.cc(0, 89, 4)
gb.cc(0, 81, 64)
gb.run(3)
gb.note(0, 60)
gb.run(8)
mid = noise_on(gb)
gb.run(8)
check("CLICK LONG: still sounding at 130 ms, gone by 270 ms (BEND TIME 200 ms)", mid and gb.mem(0xFF21) == 0, (mid, hex(gb.mem(0xFF21))))
gb.off(0, 60)
gb.run(20)

# the noise voice playing: no click (its sound is left alone)
gb.cc(3, 73, 0)
gb.cc(3, 75, 0)
gb.note(3, 60)
gb.run(5)
nr43 = gb.mem(0xFF22)
gb.cc(0, 89, 2)
gb.note(0, 64)
gb.run(2)
check("the noise voice playing: no click (its noise is left alone)", gb.mem(0xFF22) == nr43, (hex(nr43), hex(gb.mem(0xFF22))))
gb.off(3, 60)
gb.off(0, 64)
gb.run(30)

# v0.16: BEND SHAPE bit 3: BEND IN x 2 (up to 4 octaves)
gb.cc(0, 80, 127)                             # +24 (48 of 48)
gb.cc(0, 81, 64)
gb.cc(0, 89, 9)                               # STEP + x2: +48
gb.cc(0, 1, 0)
gb.run(3)
gb.note(0, 48)
seq = []
for _ in range(20):
    gb.run(1)
    seq.append(semis(gb))
held = [s for s in seq[:10] if s is not None]
check("STEP x2 (+24 doubled): four octaves up, held, then the note", held and all(abs(s - 96) < 0.3 for s in held) and abs(seq[-1] - 48) < 0.3,
      [round(x, 1) for x in seq if x is not None][:14])
gb.off(0, 48)
gb.run(30)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
