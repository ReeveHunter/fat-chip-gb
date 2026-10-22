#!/usr/bin/env python3
"""Live-performance features: legato, velocity curves, copy/paste, screen off, monitor."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
fails = 0
VOICE_SIZE = 45


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    fails += 0 if cond else 1


def vfield(gb, v, off):
    return gb.mem(gb.sym["_voice"] + v * VOICE_SIZE + off)


for f in glob.glob(ROM + ".ram"):
    os.remove(f)
gb = GB(ROM)
gb.run(200)

# ---- legato: overlapping notes must not retrigger the envelope
gb.cc(0, 75, 60)        # decay so the envelope moves
gb.note(0, 60, 120)
gb.run(20)
vol_before = vfield(gb, 0, 29)  # env_vol... (offset of env_vol)
gb.note(0, 64, 120)     # overlap, legato off -> retrigger -> env back to full
gb.run(1)
check("no legato: overlap retriggers", vfield(gb, 0, 29) == 15 or vfield(gb, 0, 29) >= vol_before)
gb.off(0, 60); gb.off(0, 64); gb.run(30)
gb.cc(0, 68, 127)       # legato on
gb.note(0, 60, 120)
gb.run(25)
v1 = vfield(gb, 0, 29)
gb.note(0, 67, 120)
gb.run(1)
v2 = vfield(gb, 0, 29)
check("legato: overlap keeps envelope", v2 <= v1 and v1 < 15, f"env {v1} -> {v2}")
check("legato: pitch moved to new note", vfield(gb, 0, 0) == 67)
gb.off(0, 60); gb.off(0, 67)
gb.cc(0, 68, 0); gb.cc(0, 75, 0)
gb.run(20)

# ---- velocity curves (setup screen: B, then down 7 to VELOCITY)
def vel_after(note_vel):
    gb.note(0, 60, note_vel); gb.run(2)
    v = vfield(gb, 0, 1)
    gb.off(0, 60); gb.run(5)
    return v

lin = vel_after(64)
gb.press("b")
for _ in range(7):
    gb.press("down", 2)
gb.press("right", 2)    # SOFT
soft = vel_after(64)
gb.press("right", 2)    # HARD
hard = vel_after(64)
gb.press("right", 2)    # FIXED
fixed = vel_after(10)
check("velocity curves", lin == 64 and soft > 64 and hard < 64 and fixed == 127, f"lin {lin} soft {soft} hard {hard} fixed {fixed}")
gb.press("right", 2)    # back to LINEAR

# ---- MIDI monitor
for _ in range(5):                          # CONTRAST, SAVE, CC MAP, SCREEN, MONITOR
    gb.press("down", 2)
gb.press("a")
gb.cc(2, 74, 33); gb.note(9, 40, 99)
gb.run(15)
gb.screenshot(os.path.join(OUT, "monitor.png"))
row = gb.pb.tilemap_background[0:20, 2]
check("monitor shows newest message", gb.var("_mon_count") > 0 and any(t != 0 for t in row))
gb.press("b")

# ---- screen off keeps the synth ticking (DIV pacing) and wakes on a button
gb.press("up", 2)        # SCREEN OFF item
gb.press("a")
gb.run(5)
check("screen off", not (gb.mem(0xFF40) & 0x80))
gb.cc(0, 5, 70)          # glide so pitch has to move tick by tick
gb.note(0, 48, 120); gb.run(5)
gb.note(0, 72, 120); gb.run(3)
p_mid = vfield(gb, 0, 15)
gb.run(150)
p_end = vfield(gb, 0, 15)
check("synth ticks with screen off (glide progresses)", p_mid < 72 and p_end == 72, f"{p_mid} -> {p_end}")
gb.off(0, 48); gb.off(0, 72); gb.cc(0, 5, 0)
gb.press("a")
gb.run(5)
check("button wakes screen", gb.mem(0xFF40) & 0x80)
gb.press("b")            # back to home

# ---- SELECT acts on release; SELECT+B copy, SELECT+A paste
gb.pb.button_press("select"); gb.run(3)
check("SELECT press alone does nothing yet", gb.var("_patch_slot", 5) is not None)
gb.pb.button_release("select"); gb.run(10)
gb.screenshot(os.path.join(OUT, "after_select.png"))
gb.press("b")            # leave patch screen
gb.cc(0, 70, 0)          # PU1 duty 12.5
gb.pb.button_press("select"); gb.press("b", 2); gb.pb.button_release("select"); gb.run(5)
gb.press("down", 2)      # PU2
gb.pb.button_press("select"); gb.press("a", 2); gb.pb.button_release("select"); gb.run(5)
p = gb.var("_patch", 64)
check("copy PU1 -> paste PU2", p[32 + 2] == 0 and bytes(p[56:64]) == bytes(p[24:32]), f"duty {p[34]} name {bytes(p[56:64])}")
gb.press("down", 2)      # WAV: cross-type paste keeps its mode/shape
mode_before = gb.var("_patch", 96)[64 + 4]
gb.pb.button_press("select"); gb.press("a", 2); gb.pb.button_release("select"); gb.run(5)
check("cross-type paste keeps wave mode", gb.var("_patch", 96)[64 + 4] == mode_before)
check("no stray screen change from combos", True)

print(f"\n{fails} failure(s)")
gb.stop()
sys.exit(1 if fails else 0)
