#!/usr/bin/env python3
"""v0.15: CC 91 LFO SYNC (per voice, not saved): 0 FREE (LFO RATE), 1 BAR ...
1/32: the voice's LFO steps from the tempo (CC 107 / 108) and goes back to
its start on the downbeat (CC 109) when the division fits a bar."""
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


def u16(gb, name, i=0):
    a = gb.sym[name] + 2 * i
    return gb.mem(a) | gb.mem(a + 1) << 8


gb = GB(ROM, sram=bytes(8192))
gb.run(150)
gb.cc(0, 102, 70)
gb.cc(0, 91, 3)                                  # 1/4, no tempo yet
gb.run(3)
check("no tempo yet: FREE (no SYNC step)", u16(gb, "_lfo_sinc") == 0, u16(gb, "_lfo_sinc"))
gb.cc(0, 107, 30)
gb.cc(0, 108, 0)                                 # 120 BPM
gb.run(3)
want = 65536 * 2 / 59.7275                       # 1/4 at 120 BPM: 2 Hz
check("120 BPM, 1/4: a cycle a beat (2 Hz)", abs(u16(gb, "_lfo_sinc") - want) / want < 0.01, (u16(gb, "_lfo_sinc"), round(want)))
gb.cc(0, 1, 100)
gb.note(0, 60)
gb.run(17)
gb.cc(0, 109, 0)                                 # downbeat
gb.run(1)
ph = gb.mem(gb.sym["_voice"] + 24) | gb.mem(gb.sym["_voice"] + 25) << 8   # voice_t.lfo_phase
check("the downbeat: the LFO back at its start (0x4000, a step on)", 0x4000 <= ph <= 0x4000 + 2 * u16(gb, "_lfo_sinc"), hex(ph))
gb.cc(0, 91, 0)
gb.run(2)
check("CC 91 0: FREE again", u16(gb, "_lfo_sinc") == 0, u16(gb, "_lfo_sinc"))
check("... the other voices weren't touched", gb.var("_lfo_sync", 3)[1:] == [0, 0], gb.var("_lfo_sync", 3))

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
