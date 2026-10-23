#!/usr/bin/env python3
"""Fat Chip integration: profile, global CCs (tune, warble, tempo, downbeat,
latch, panic), and the DAW profile's remappable CC map with MIDI learn."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
fails = 0
P_ATTACK, P_DECAY = 5, 6          # parameter indexes (engine.h)
CC_ATTACK, CC_DECAY = 73, 75


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info != "" else ""))
    fails += 0 if cond else 1


def u16(gb, name):
    lo, hi = gb.var(name, 2)
    return lo | (hi << 8)


def s16(gb, name):
    v = u16(gb, name)
    return v - 65536 if v >= 32768 else v


def pulse1_hz(gb):
    """Frequency registers are write-only, so read the engine's last written
    period (voice_t.out_period, offset 34): f = 131072 / period."""
    a = gb.sym["_voice"] + 34
    per = gb.mem(a) | (gb.mem(a + 1) << 8)
    return 131072 / per if per and per != 0xFFFF else 0.0


def sounding(gb, ch_bit):
    return bool(gb.mem(0xFF26) & ch_bit)


gb = GB(ROM, sram=bytes(8192))
gb.run(150)

# ---------------------------------------------------------------- profile
check("starts in DAW profile", gb.var("_profile") == 0)
gb.cc(0, 102, 70)
gb.run(5)
check("CC102=70 -> FAT CHIP", gb.var("_profile") == 1)
gb.cc(0, 102, 5)
gb.run(5)
check("other values ignored", gb.var("_profile") == 1)
gb.cc(6, 102, 68)                 # ch 7: no voice listens there
gb.run(5)
check("globals ignored on a channel no voice uses", gb.var("_profile") == 1)
gb.screenshot(os.path.join(OUT, "home_fatchip_profile.png"))
gb.cc(4, 102, 68)                 # ch 5 (drums) counts
gb.run(5)
check("CC102=68 on any voice's channel -> DAW", gb.var("_profile") == 0)

# ---------------------------------------------------------------- master tune
gb.note(0, 69, 120)               # A4 on pulse 1
gb.run(6)
f0 = pulse1_hz(gb)
gb.cc(0, 103, 19)                 # -35 cents (Synthcart's tuning)
gb.run(6)
f1 = pulse1_hz(gb)
cents = 1200 * math.log2(f1 / f0)
check("master tune -35 cents", abs(cents + 35.2) < 3, f"{cents:.1f} cents")
gb.cc(0, 103, 64)
gb.run(6)
check("master tune back to 0", abs(pulse1_hz(gb) - f0) < 0.5, f"{pulse1_hz(gb):.1f} vs {f0:.1f}")

# ---------------------------------------------------------------- warble
seen = set()
for _ in range(120):
    gb.run(1)
    seen.add(round(pulse1_hz(gb), 1))
check("no warble: pitch steady", len(seen) == 1, len(seen))
gb.cc(0, 104, 100)
gb.cc(0, 105, 100)
lo = hi = f0
for _ in range(240):
    gb.run(1)
    f = pulse1_hz(gb)
    lo, hi = min(lo, f), max(hi, f)
spread = 1200 * math.log2(hi / lo)
check("warble moves the pitch", spread > 10, f"{spread:.1f} cents spread")
check("warble stays within +-50 cents", spread < 101, f"{spread:.1f}")
gb.cc(0, 104, 0)
gb.run(300)
check("warble off settles back", abs(pulse1_hz(gb) - f0) < 0.5, f"{pulse1_hz(gb):.1f}")
gb.off(0, 69)
gb.run(10)

# ---------------------------------------------------------------- tempo + downbeat
bpm32 = 120 * 32
gb.cc(0, 107, bpm32 >> 7)
gb.cc(0, 108, bpm32 & 127)
gb.cc(0, 109, 0)                  # downbeat
gb.run(3)
start = u16(gb, "_clock24")
frames = 597                      # ~10 s on a DMG (59.7275 Hz)
gb.run(frames)
got = u16(gb, "_clock24") - start
want = 120 / 60 * 24 * frames / 59.7275
check("tempo 120: 24 clocks per beat", abs(got - want) <= 2, f"{got} vs {want:.1f}")
gb.screenshot(os.path.join(OUT, "home_beat.png"))
gb.cc(0, 109, 0)
gb.run(1)
check("downbeat resets the clock", u16(gb, "_clock24") <= 1, u16(gb, "_clock24"))

# ---------------------------------------------------------------- latch + panic
gb.cc(0, 72, 127)                 # long release so a note-off is audible as a fade
gb.cc(0, 110, 127)                # latch on
gb.note(0, 60, 120)
gb.run(5)
gb.off(0, 60)
gb.run(30)
check("latch holds after note-off", sounding(gb, 1) and gb.var("_latch") == 1)
gb.cc(0, 72, 0)                   # release 0 so the note-off is a cut
gb.cc(0, 110, 0)                  # latch off -> released
gb.run(20)
check("latch off releases", not sounding(gb, 1))
gb.cc(0, 110, 127)
gb.note(0, 60, 120); gb.note(1, 64, 120)
gb.run(5)
gb.cc(3, 111, 0)                  # panic on the noise voice's channel
gb.run(5)
check("panic CC silences every voice and clears latch",
      not sounding(gb, 3) and gb.var("_latch") == 0, hex(gb.mem(0xFF26)))

# ---------------------------------------------------------------- lost note-off
gb.cc(0, 102, 70)                 # FAT CHIP profile
gb.cc(0, 72, 0)                   # release 0: a note-off is a cut
gb.note(0, 60, 120); gb.run(3)
gb.note(0, 64, 120); gb.run(3)    # the note-off for 60 got lost on the way
gb.off(0, 64); gb.run(10)
check("FAT CHIP: a lost note-off doesn't bring the old note back", not sounding(gb, 1))
gb.cc(0, 102, 68)                 # DAW profile keeps last-note priority
gb.note(0, 60, 120); gb.run(3)
gb.note(0, 64, 120); gb.run(3)
gb.off(0, 64); gb.run(10)
check("DAW: releasing the top note returns to the held one", sounding(gb, 1))
gb.off(0, 60); gb.run(10)

# ---------------------------------------------------------------- display (CC 112)
gb.cc(0, 112, 1)
gb.run(5)
check("CC112=1 switches the screen off", not (gb.mem(0xFF40) & 0x80))
gb.note(0, 60, 100); gb.run(5)
check("synth keeps playing with the screen off", gb.mem(0xFF26) & 1)
gb.off(0, 60)
gb.cc(0, 112, 0)
gb.run(5)
check("CC112=0 switches it back on", gb.mem(0xFF40) & 0x80)

# ---------------------------------------------------------------- CC map + learn
def select_a(gb):
    gb.pb.button_press("select")
    gb.run(2)
    gb.press("a", 3)
    gb.pb.button_release("select")
    gb.run(3)


gb.press("a")                     # edit Pulse 1
gb.run(10)
select_a(gb)                      # learn on LEVEL: fixed
check("LEVEL can't be learned", gb.var("_learn_voice") == 0xFF)
for _ in range(3):
    gb.press("down")              # LEVEL, PAN, DUTY, ATTACK
select_a(gb)
check("learn armed on ATTACK", gb.var("_learn_voice") == 0 and gb.var("_learn_param") == P_ATTACK)
gb.run(5)
gb.screenshot(os.path.join(OUT, "edit_learn.png"))
gb.cc(0, 7, 90)                   # reserved CC: ignored, still learning
gb.run(3)
check("reserved CC doesn't learn", gb.var("_learn_voice") == 0)
gb.cc(0, CC_DECAY, 10)            # take decay's CC -> swap
gb.run(10)
cmap = gb.var("_cc_map", 23)
check("learned CC75 for ATTACK", cmap[P_ATTACK] == CC_DECAY, cmap[P_ATTACK])
check("DECAY swapped to ATTACK's old CC", cmap[P_DECAY] == CC_ATTACK, cmap[P_DECAY])
gb.screenshot(os.path.join(OUT, "edit_learned.png"))
patch = gb.sym["_patch"]
gb.cc(0, CC_DECAY, 127)
gb.run(3)
check("DAW: CC75 now drives ATTACK", gb.mem(patch + P_ATTACK) == 7, gb.mem(patch + P_ATTACK))
gb.cc(0, 102, 70)                 # FAT CHIP profile: default map
gb.cc(0, CC_ATTACK, 0)
gb.run(3)
check("FAT CHIP: default CC73 drives ATTACK", gb.mem(patch + P_ATTACK) == 0, gb.mem(patch + P_ATTACK))
select_a(gb)
check("no learning in FAT CHIP profile", gb.var("_learn_voice") == 0xFF)
gb.cc(0, 102, 68)
gb.press("b")                     # home
gb.press("b")                     # setup
for _ in range(10):               # CC MAP item
    gb.press("down")
gb.run(10)
gb.screenshot(os.path.join(OUT, "setup_fatchip.png"))
gb.press("a")
gb.run(5)
cmap = gb.var("_cc_map", 23)
check("Setup > CC MAP resets to defaults", cmap[P_ATTACK] == CC_ATTACK and cmap[P_DECAY] == CC_DECAY)
check("still no writes to save RAM", bytes(gb.pb.memory[0, 0xA000:0xBFFF]) == bytes(0x1FFF))

gb.stop()
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
