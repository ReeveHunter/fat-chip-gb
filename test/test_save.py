#!/usr/bin/env python3
"""Save RAM is opt-in, Shift All keeps custom gaps, contrast swaps the label tiles.

The cart's save RAM is filled with a stand-in for another game's save (on a
multi-ROM cart, LSDJ's). With SAVE TO CART off (the default) it must come back
byte-for-byte unchanged, whatever the user does.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
fails = 0
SRAM_SIZE = 8192
SETUP_ITEMS = {"shift": 0, "pu2": 2, "contrast": 7, "save": 8}


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info != "" else ""))
    fails += 0 if cond else 1


def other_game_save():
    rnd = random.Random(1987)
    return bytes(rnd.randrange(256) for _ in range(SRAM_SIZE))


def boot(sram):
    gb = GB(ROM, sram=sram)
    gb.run(150)
    return gb


def sram_now(gb):
    """Cartridge save RAM bank 0, read straight from the emulated cart."""
    return bytes(gb.pb.memory[0, 0xA000:0xBFFF]) + bytes([gb.pb.memory[0, 0xBFFF]])


def goto_setup_item(gb, idx):
    gb.press("b")
    for _ in range(idx):
        gb.press("down")


# ---------------------------------------------------------------- default: never write
lsdj = other_game_save()
gb = boot(lsdj)
check("saving is off by default", gb.var("_save_on") == 0)
# do everything that used to write: change channels, leave setup, save a patch
goto_setup_item(gb, SETUP_ITEMS["pu2"])
gb.press("right")
gb.press("b")                       # leave setup (used to call setup_save)
gb.press("select"); gb.run(10)      # patch browser
gb.press("select"); gb.run(10)      # save to slot -> namer
gb.press("start"); gb.run(10)       # confirm name
gb.press("b"); gb.run(10)
check("other game's save untouched", sram_now(gb) == lsdj)
gb.pb.stop(save=False)

# old gbmidi marker is not treated as ours
old = bytearray(lsdj)
old[0:5] = b"GBMI\x02"
gb = boot(bytes(old))
check("old GBMI marker ignored (saving off)", gb.var("_save_on") == 0)
check("old marker save untouched", sram_now(gb) == bytes(old))
gb.pb.stop(save=False)

# ---------------------------------------------------------------- opt in, with a warning
gb = boot(lsdj)
goto_setup_item(gb, SETUP_ITEMS["save"])
gb.press("a"); gb.run(20)
gb.screenshot(os.path.join(OUT, "save_warning.png"))
check("warning shown, nothing written yet", sram_now(gb) == lsdj and gb.var("_save_on") == 0)
gb.press("b"); gb.run(10)           # cancel
check("cancel keeps saving off", gb.var("_save_on") == 0 and sram_now(gb) == lsdj)
gb.press("a"); gb.run(20)           # warning again
gb.press("a"); gb.run(20)           # turn on
on_ram = sram_now(gb)
check("turning on sets save_on", gb.var("_save_on") == 1)
check("turning on writes the marker", on_ram[0:10] == b"FATCHIPGB\x03", on_ram[0:10])
gb.run(10)
gb.screenshot(os.path.join(OUT, "setup_save_on.png"))
gb.pb.stop(save=False)

# reboot with that save: recognised, and setup changes now persist
gb = boot(on_ram)
check("reboot: saving still on", gb.var("_save_on") == 1)
goto_setup_item(gb, SETUP_ITEMS["shift"])
gb.press("right")
gb.press("b"); gb.run(10)                     # leave setup -> saved
saved = sram_now(gb)
gb.pb.stop(save=False)
gb = boot(saved)
check("with saving on, channel map survives reboot", gb.var("_midi_ch", 5) == [1, 2, 3, 4, 5], gb.var("_midi_ch", 5))
on_ram = saved
# turn it off again: only the marker changes
goto_setup_item(gb, SETUP_ITEMS["save"])
gb.press("a"); gb.run(10)
off_ram = sram_now(gb)
check("turning off clears the marker", off_ram[0:10] == bytes(10) and gb.var("_save_on") == 0)
check("turning off changes nothing else", off_ram[10:] == on_ram[10:])
gb.pb.stop(save=False)
gb = boot(off_ram)
check("reboot after off: saving off", gb.var("_save_on") == 0)
gb.pb.stop(save=False)

# ---------------------------------------------------------------- Shift All keeps custom gaps
gb = boot(lsdj)
ch = gb.sym["_midi_ch"]
for v, c in enumerate([10, 11, 13, 16, 14]):   # 16 = OFF (drum voice switched off here)
    gb.pb.memory[ch + v] = c
goto_setup_item(gb, SETUP_ITEMS["shift"])
gb.press("left")
got = [gb.pb.memory[ch + v] for v in range(5)]
check("shift down keeps gaps and OFF", got == [9, 10, 12, 16, 13], got)
gb.press("right"); gb.press("right")
got = [gb.pb.memory[ch + v] for v in range(5)]
check("shift up keeps gaps", got == [11, 12, 14, 16, 15], got)
gb.press("right")                               # top voice is already on 16: no change
got = [gb.pb.memory[ch + v] for v in range(5)]
check("shift stops at channel 16", got == [11, 12, 14, 16, 15], got)
for v, c in enumerate([0, 1, 2, 3, 4]):
    gb.pb.memory[ch + v] = c
gb.press("left")
got = [gb.pb.memory[ch + v] for v in range(5)]
check("shift stops at channel 1", got == [0, 1, 2, 3, 4], got)
gb.press("right")
got = [gb.pb.memory[ch + v] for v in range(5)]
check("contiguous block shifts as before", got == [1, 2, 3, 4, 5], got)
gb.pb.stop(save=False)

# ---------------------------------------------------------------- contrast
gb = boot(lsdj)
tile = lambda: bytes(gb.pb.memory[0x8800 + i] for i in range(16 * 40))  # label tiles 128..
before = tile()
goto_setup_item(gb, SETUP_ITEMS["contrast"])
gb.press("right"); gb.run(5)
check("contrast high swaps label tiles", gb.var("_contrast") == 1 and tile() != before)
gb.screenshot(os.path.join(OUT, "setup_contrast_high.png"))
gb.press("right"); gb.run(5)
check("contrast normal restores them", gb.var("_contrast") == 0 and tile() == before)
check("contrast doesn't write save RAM", sram_now(gb) == lsdj)
gb.pb.stop(save=False)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
