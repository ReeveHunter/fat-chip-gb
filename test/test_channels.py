#!/usr/bin/env python3
"""MIDI channel mapping: shift-all, layering, OFF, SRAM persistence, panic."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    fails += 0 if cond else 1


def clean_ram():
    for f in glob.glob(ROM + ".ram") + glob.glob(os.path.splitext(ROM)[0] + ".ram"):
        os.remove(f)


clean_ram()
gb = GB(ROM)
gb.run(200)
check("default map 1-5", gb.var("_midi_ch", 5) == [0, 1, 2, 3, 4])
gb.press("b")
for _ in range(5):
    gb.press("right", 2)
check("shift all -> 6-10", gb.var("_midi_ch", 5) == [5, 6, 7, 8, 9], str(gb.var("_midi_ch", 5)))
gb.note(0, 69, 120)
gb.run(5)
check("ch1 now ignored", not (gb.mem(0xFF26) & 1))
gb.note(5, 69, 120)
gb.run(5)
check("ch6 plays pulse 1", gb.mem(0xFF26) & 1)
gb.off(5, 69)
gb.press("down", 2)
gb.press("down", 2)
gb.press("left", 2)
check("pulse 2 layered on ch6", gb.var("_midi_ch", 5)[:2] == [5, 5])
gb.press("down", 2)
for _ in range(9):          # wave: ch8 -> past 16 -> OFF
    gb.press("right", 2)
check("wave set OFF", gb.var("_midi_ch", 5)[2] == 16, str(gb.var("_midi_ch", 5)))
gb.press("b")
gb.run(10)
gb.note(5, 60, 120)
gb.run(5)
check("layer: both pulses sound", (gb.mem(0xFF26) & 3) == 3, hex(gb.mem(0xFF26)))
gb.press("select", 1)
gb.pb.button_press("select")
gb.press("start", 2)
gb.pb.button_release("select")
gb.run(5)
check("SELECT+START panic silences", (gb.mem(0xFF26) & 3) == 0, hex(gb.mem(0xFF26)))
gb.pb.stop(save=True)
gb2 = GB(ROM)
gb2.run(200)
check("map survives reboot (SRAM)", gb2.var("_midi_ch", 5) == [5, 5, 16, 8, 9], str(gb2.var("_midi_ch", 5)))
gb2.stop()
clean_ram()
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
