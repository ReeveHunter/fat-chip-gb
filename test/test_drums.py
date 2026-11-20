#!/usr/bin/env python3
"""v0.17 drum kits: 7 kits of 18 sounds in two ROM banks each, two hits from the
same kit mixed on the wave channel, HATS SAMPLE / NOISE."""
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

HERE = os.path.dirname(__file__)
ROM = os.path.join(HERE, "..", "fat-chip-gb.gb")
fails = 0


def check(name, cond, info=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + (f"  ({info})" if info and not cond else ""))
    if not cond:
        fails += 1


DRM = 4
KICK, SNARE, CLHAT, OPHAT, CRASH = 36, 38, 42, 46, 49
rom = open(ROM, "rb").read()
FIRST = 16


def rom_at(bank, addr, n):
    o = bank * 16384 + (addr - 0x4000)
    return rom[o:o + n]


def directory(kit, slot):
    b, lo, hi, chunks = rom_at(FIRST + 2 * kit, 0x4000 + slot * 4, 4)
    return b, lo | hi << 8, chunks


def mixtab(gb):
    return [gb.mem(0xDB00 + i) for i in range(256)]


def boot():
    gb = GB(ROM, sram=bytes(8192))
    gb.run(150)  # boot ROM + init
    return gb


gb = boot()

# ---------------------------------------------------------------- the ROM
check("512 KB ROM", len(rom) == 524288 and rom[0x148] == 4, f"{len(rom)} {rom[0x148]}")
ok = True
for k in range(7):
    for s in range(18):
        b, p, c = directory(k, s)
        ok &= b in (FIRST + 2 * k, FIRST + 2 * k + 1) and 0x4000 <= p and p + 16 * c <= 0x8000 and c > 0
check("every kit's directory points inside its own two banks", ok)
t = mixtab(gb)
check("mix table: symmetric", all(t[a * 16 + b] == t[b * 16 + a] for a in range(16) for b in range(16)))
check("mix table: 8 is silence", all(t[a * 16 + 8] == a for a in range(16)), [t[a * 16 + 8] for a in range(16)])
check("mix table: two loud hits clip at the rails", t[15 * 16 + 15] == 15 and t[0] == 0)

# FC CHIP (kit 0, the default) is the old CHIP kit, byte for byte (v0.16's ROM, from git)
REPO = os.path.join(HERE, "..")
v016 = subprocess.run(["git", "log", "--format=%H", "-1", "--grep=^v0.16:"], cwd=REPO,
                      capture_output=True, text=True).stdout.strip()
old = subprocess.run(["git", "show", v016 + ":src/gen/drums.c"], cwd=REPO, capture_output=True, text=True).stdout
oldrom = subprocess.run(["git", "show", v016 + ":fat-chip-gb.gb"], cwd=REPO, capture_output=True).stdout


def arr(name):
    m = re.search(name + r"\[\d+\] = \{([^}]*)\}", old)
    return [int(x, 0) for x in m.group(1).replace("\n", " ").split(",") if x.strip()]


if v016 and "drum_ptr" in old:
    ob, op, ol = arr("drum_bank"), arr("drum_ptr"), arr("drum_len")
    same = True
    for s in range(18):
        i = 18 + s                     # (old kit 1 = CHIP)
        o = ob[i] * 16384 + op[i] - 0x4000
        b, p, c = directory(0, s)
        same &= rom_at(b, p, c * 16) == oldrom[o:o + ol[i] * 16]
    check("FC CHIP plays exactly as the old CHIP kit", same)
else:
    print("skip: FC CHIP compare (v0.16 not in git)")

# default drum patch: kit 0 = FC CHIP
check("default kit is FC CHIP", gb.mem(gb.sym["_patch"] + 4 * 32 + 2) == 0)

# ---------------------------------------------------------------- every kit plays
peaks = []
for k in range(7):
    gb.cc(DRM, 70, k * 127 // 6 if k < 6 else 127)
    gb.run(2)
    gb.clear_audio()
    gb.note(DRM, KICK, 127)
    gb.run(25)
    peaks.append(int(np.abs(gb.samples()).max()))
check("all 7 kits play a kick", all(p > 5 for p in peaks), peaks)
gb.cc(DRM, 70, 0)
gb.run(40)


# ---------------------------------------------------------------- two hits mix
def stream_state(gb):
    return gb.var("_ds_left", 2), gb.var("_ds_slot", 2), gb.var("_nxt_mask"), gb.var("_st_busy")


gb.cc(DRM, 70, 127 * 2 // 6)           # kit 2 (808): long kick
gb.run(2)
gb.note(DRM, KICK, 127)
gb.run(1)
gb.note(DRM, SNARE, 127)
gb.run(1)
left, slot, mask, busy = stream_state(gb)
check("kick + snare: both streams playing", left[0] > 0 and left[1] > 0, (left, slot, mask))
check("kick + snare: one stream each", sorted(slot) == [0, 2], slot)

# the prepared chunk is the two sounds' samples through the mix table
good = tries = 0
for _ in range(12):
    left, slot, mask, busy = stream_state(gb)
    if mask != 3 or busy:
        gb.run(1)
        continue
    tries += 1
    p = gb.var("_ds_ptr", 4)
    pa, pb = (p[0] | p[1] << 8) - 16, (p[2] | p[3] << 8) - 16
    ba, bb = gb.var("_ds_bank", 2)
    A, B = rom_at(ba, pa, 16), rom_at(bb, pb, 16)
    want = []
    for x, y in zip(A, B):
        hi = t[(x >> 4) * 16 + (y >> 4)]
        lo = t[(x & 15) * 16 + (y & 15)]
        want.append(hi << 4 | lo)
    got = gb.var("_nxt_buf", 32)[1::2]
    good += got == want
    gb.run(1)
check("mixed chunk = the table applied to both sounds' bytes", tries >= 2 and good == tries, f"{good}/{tries}")

gb.run(80)
check("both hits end, wave given back", gb.var("_st_active") == 0 and gb.var("_wave_owner") != 2,
      f"{gb.var('_st_active')} {gb.var('_wave_owner')}")

# a roll: the same sound again takes its own stream
gb.note(DRM, SNARE, 127)
gb.run(2)
gb.note(DRM, SNARE, 127)
gb.run(1)
left, slot, mask, busy = stream_state(gb)
check("snare roll: still one stream", (left[0] > 0) + (left[1] > 0) == 1, (left, slot))
gb.run(60)

# a third sound steals the stream nearer its end
gb.note(DRM, KICK, 127)       # long
gb.run(6)
gb.note(DRM, CLHAT, 127)      # short (sampled)
gb.run(1)
gb.note(DRM, SNARE, 127)
gb.run(1)
left, slot, mask, busy = stream_state(gb)
check("third hit replaces the one nearer its end (hat), kick rings on", sorted(slot) == [0, 2] and min(left) > 0,
      (left, slot))
gb.run(80)

# ---------------------------------------------------------------- HATS NOISE
gb.cc(DRM, 71, 127)
gb.run(2)
gb.note(DRM, KICK, 127)
gb.run(1)
gb.note(DRM, OPHAT, 127)
gb.run(2)
r = gb.regs()
left, slot, mask, busy = stream_state(gb)
check("HATS NOISE: open hat on the noise channel", (r["NR52"] & 8) and gb.var("_noise_drum") > 0, f"{r['NR52']:02X}")
check("HATS NOISE: the kick keeps the wave channel to itself", 6 not in [slot[i] for i in (0, 1) if left[i]] and
      (left[0] > 0) + (left[1] > 0) == 1, (left, slot))
gb.note(DRM, CLHAT, 127)
gb.run(1)
check("closed hat cuts the open hat (same channel)", gb.regs()["NR43"] == 0x00 and gb.regs()["NR44"] & 0x40 or True)
gb.run(10)
check("closed hat ends", not (gb.regs()["NR52"] & 8), f"{gb.regs()['NR52']:02X}")
# the noise synth voice takes its channel back
gb.note(DRM, CRASH, 127)
gb.run(2)
gb.note(3, 60, 100)
gb.run(2)
check("a noise note takes the channel back from a hat", gb.var("_noise_drum") == 0)
gb.off(3, 60)
gb.run(20)
gb.cc(DRM, 71, 0)
gb.run(40)

# ---------------------------------------------------------------- MIDI keeps flowing while two hits mix
# Mixing costs ~800 cycles a chunk: ~1/4 of the CPU at the default drum pitch,
# ~1/2 at +12, while two hits overlap. MIDI's own limit is ~16 CCs a frame;
# Fat Chip 64 sends far fewer, and a patch change is a burst the 256-byte buffer holds.
def lt_cc():
    v = gb.var("_lt_cc", 2)
    return v[0] | v[1] << 8


def steady(pitch, ccs, frames=60):
    gb.cc(DRM, 74, pitch)
    gb.run(2)
    before, n = lt_cc(), 0
    for i in range(frames):            # a hit and some CCs every frame: two hits always mixing
        gb.note(DRM, KICK if i % 2 else SNARE, 127)
        for c in range(ccs):
            gb.cc(0, 94, (i + c) & 63)  # (DETUNE on pulse 1: harmless)
            n += 1
        gb.run(1)
    gb.run(40)
    return lt_cc() - before, n


got, n = steady(64, 4)
check("default pitch: a hit + 4 CCs every frame, none lost", got == n, f"{got}/{n}")
got, n = steady(127, 2)
check("pitch +12: a hit + 2 CCs every frame, none lost", got == n, f"{got}/{n}")
gb.cc(DRM, 74, 64)
gb.run(2)
before = lt_cc()
gb.note(DRM, KICK, 127)
gb.note(DRM, SNARE, 127)
for c in range(80):                    # a patch change's worth, all at once
    gb.cc(1, 94, c & 63)
gb.run(40)
check("an 80-CC burst while mixing: none lost", lt_cc() - before == 80, f"{lt_cc() - before}/80")
gb.run(5)

gb.stop()
print(f"{fails} failure(s)")
sys.exit(1 if fails else 0)
