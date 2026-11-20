#!/usr/bin/env python3
"""v0.10: Fat Chip sounds. CC 114 n plays Fat Chip 64's built-in sound n on the
whole Game Boy (pulse 1, pulse 2, wave) from the ROM's own copy of the CCs
(src/gen/fcsounds.c): the same patch as those CCs sent one by one, the sound's
name on each card. SELECT + LEFT / RIGHT on the home screen step through them.
The edit screen uses Fat Chip's names (BEND IN, VIBRATO / PWM / AUTOPAN)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
GEN = os.path.join(os.path.dirname(__file__), "..", "src", "gen", "fcsounds.c")
fails = 0
PATCH_SIZE, NAME = 32, 24


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info != "" else ""))
    fails += 0 if cond else 1


def table():
    src = open(GEN).read()
    ofs = [int(x) for x in re.search(r"fc_sound_ofs\[FC_SOUNDS_N\] = \{([^}]*)\}", src).group(1).split(",")]
    data = [int(x) for x in re.findall(r"\d+", re.search(r"fc_sound_data\[\d+\] = \{([^}]*)\}", src).group(1))]
    names = re.findall(r"/\* ([A-Z0-9 .]+) \*/", src.split("fc_sound_names")[1].split("};")[0])
    return ofs, data, names


def lists(data, o):
    out = []
    for _ in range(4):
        n = data[o]
        o += 1
        out.append([(data[o + 2 * k], data[o + 2 * k + 1]) for k in range(n)])
        o += 2 * n
    return out


def patches(gb):
    return gb.var("_patch", 5 * PATCH_SIZE)


ofs, data, names = table()
check("the table: Fat Chip 64's 19 built-in sounds", len(ofs) == 19 and names[0] == "FAT", (len(ofs), names[:3]))

for n in (0, 4, 13):
    a = GB(ROM, sram=bytes(8192))
    a.run(150)
    a.cc(0, 102, 70)                      # FAT CHIP profile
    a.cc(0, 114, n)
    a.run(10)
    b = GB(ROM, sram=bytes(8192))
    b.run(150)
    b.cc(0, 102, 70)
    chans = lists(data, ofs[n])
    for v in range(3):
        for cc, val in chans[v]:
            b.cc(v, cc, val)
            b.run(1)
    for cc, val in chans[3]:
        b.cc(0, cc, val)
    b.run(10)
    pa, pb = patches(a), patches(b)
    same = all(pa[v * PATCH_SIZE:v * PATCH_SIZE + NAME] == pb[v * PATCH_SIZE:v * PATCH_SIZE + NAME] for v in range(3))
    check(f"CC 114 {n} ({names[n]}): the same patch as its CCs one by one (pulse 1, pulse 2, wave)", same)
    nm = bytes(pa[NAME:NAME + 8]).decode("ascii", "replace")
    check(f"... the sound's name on the cards ({nm.strip()})", all(bytes(pa[v * PATCH_SIZE + NAME:v * PATCH_SIZE + NAME + 8]) == bytes(pa[NAME:NAME + 8])
                                                              for v in range(3)) and nm.strip() != "", nm)
    check("... the globals too (warble)", a.var("_warble_amt") == b.var("_warble_amt") and a.var("_fc_cur") == n,
          (a.var("_warble_amt"), b.var("_warble_amt"), a.var("_fc_cur")))
    check("... noise and drums untouched", pa[3 * PATCH_SIZE:] == pb[3 * PATCH_SIZE:])

a = GB(ROM, sram=bytes(8192))
a.run(150)
a.cc(0, 114, 200)
a.run(5)
check("CC 114 past the last sound: nothing", a.var("_fc_cur") == 255)
a.cc(5, 114, 1)
a.run(5)
check("CC 114 on a channel no voice listens to: nothing", a.var("_fc_cur") == 255)

# SELECT + RIGHT on the home screen: the next sound
g = GB(ROM, sram=bytes(8192))
g.run(150)
g.pb.button_press("select")
g.run(3)
g.press("right", 3)
g.pb.button_release("select")
g.run(10)
check("SELECT + RIGHT: a Fat Chip sound on the whole Game Boy", g.var("_fc_cur") == 18 or g.var("_fc_cur") == 0, g.var("_fc_cur"))
c0 = g.var("_fc_cur")
g.pb.button_press("select")
g.run(3)
g.press("right", 3)
g.pb.button_release("select")
g.run(10)
check("... again: the next", g.var("_fc_cur") == (c0 + 1) % 19, g.var("_fc_cur"))

# ---------------------------------------------------------------- v0.11: the status (CC 114 = 64 + n)
def name_of(g, v=0):
    return bytes(patches(g)[v * PATCH_SIZE + NAME:v * PATCH_SIZE + NAME + 8]).decode("ascii", "replace")


g = GB(ROM, sram=bytes(8192))                 # a Game Boy switched on late: DAW profile, its own channels
g.run(150)
check("power-on: DAW profile", g.var("_profile") == 0)
g.cc(3, 113, 74)                              # Fat Chip 64's status: the channels (any channel) ...
g.run(5)
g.cc(10, 114, 64 + 4)                         # ... then "on WHISTLE"
g.run(10)
ref = GB(ROM, sram=bytes(8192))
ref.run(150)
ref.cc(0, 102, 70)
ref.cc(0, 114, 4)
ref.run(10)
check("late power-on: the first status sets the FAT CHIP profile ...", g.var("_profile") == 1, g.var("_profile"))
check("... and plays the sound (as CC 114 4 would)", g.var("_fc_cur") == 4 and
      all(patches(g)[v * PATCH_SIZE:v * PATCH_SIZE + NAME] == patches(ref)[v * PATCH_SIZE:v * PATCH_SIZE + NAME] for v in range(3)),
      name_of(g))
before = patches(g)[:3 * PATCH_SIZE]
g.cc(10, 73, 127)                             # a live edit (pulse 1: attack)
g.run(5)
edited = patches(g)[:3 * PATCH_SIZE]
g.cc(10, 114, 64 + 4)
g.run(10)
check("synced: the status again doesn't undo a live edit", patches(g)[:3 * PATCH_SIZE] == edited and edited != before, (edited != before))
g.cc(10, 114, 64 + 13)
g.run(10)
p13 = patches(g)[:3 * PATCH_SIZE]
same = all(p13[v * PATCH_SIZE:v * PATCH_SIZE + NAME] == edited[v * PATCH_SIZE:v * PATCH_SIZE + NAME] for v in range(3))
check("synced: another sound's status only renames the cards (GLD BASS), the sound stays", same and name_of(g) == "GLD BASS"
      and name_of(g, 2) == "GLD BASS" and g.var("_fc_cur") == 13, name_of(g))
g.cc(10, 114, 127)
g.run(10)
check("status 127: a sound of Fat Chip 64's own: CUSTOM", name_of(g) == "CUSTOM  " and name_of(g, 1) == "CUSTOM  " and g.var("_fc_cur") == 255,
      name_of(g))

h = GB(ROM, sram=bytes(8192))                 # on at Fat Chip 64's startup: the profile CC marks it synced
h.run(150)
h.cc(0, 102, 70)
h.run(5)
p0 = patches(h)[:3 * PATCH_SIZE]
h.cc(0, 114, 64 + 4)
h.run(10)
check("after Fat Chip 64's startup (CC 102 heard), a status doesn't reload, just names",
      all(patches(h)[v * PATCH_SIZE:v * PATCH_SIZE + NAME] == p0[v * PATCH_SIZE:v * PATCH_SIZE + NAME] for v in range(3)) and name_of(h) == "WHISTLE ",
      name_of(h))

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
