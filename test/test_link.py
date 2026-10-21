#!/usr/bin/env python3
"""Link test screen: counters for bytes, notes, clock, SysEx.

Sends the same bursts as the web page (ReeveHunter.github.io/fatchip/linktest)
and checks the Game Boy counts what the page says it should.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
fails = 0
CH = 15  # MIDI channel 16: no voice listens there by default, so the test is silent


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    fails += 0 if cond else 1


def u16(gb, name):
    lo, hi = gb.var(name, 2)
    return lo | (hi << 8)


def u8(gb, name):
    return gb.var(name)


# ---- the bursts (keep in step with linktest/index.html)
def burst_notes():
    out = []
    for i in range(64):
        n = 36 + (i % 24)
        out += [0x90 | CH, n, 100, 0x80 | CH, n, 0]
    return out


def burst_clock():
    return [0xFA] + [0xF8] * 96 + [0xFC]


def burst_clock_between():
    out = []
    for i in range(32):
        n = 48 + (i % 12)
        out += [0xF8, 0x90 | CH, n, 100, 0xF8, 0x80 | CH, n, 0]
    return out


def burst_clock_inside():
    out = []
    for i in range(32):
        n = 48 + (i % 12)
        out += [0x90 | CH, 0xF8, n, 100, 0x80 | CH, n, 0xF8, 0]
    return out


def sysex(payload):
    return [0xF0, 0x7D, 0x46, 0x43] + payload + [0xF7]


def burst_sysex_short():
    return sysex([1, 2, 3, 4])


def burst_sysex_long():
    return sysex(list(range(128)))


def burst_sysex_1k():
    return sysex([(i * 7) & 0x7F for i in range(1024)])


def send(gb, data):
    """Feed bytes at roughly the real link rate (one byte per ~500 us, about
    33 per frame) instead of all at once, which would overflow the 256-byte
    receive buffer in a way real hardware never does."""
    for i in range(0, len(data), 32):
        gb.midi(*data[i:i + 32])
        gb.run(1)


def sx_len_sum(msg):
    data = msg[1:-1]
    return len(data), sum(data) & 0xFF


for f in glob.glob(ROM + ".ram"):
    os.remove(f)
gb = GB(ROM)
gb.run(120)

# counters start at zero
check("counters zero at boot", u16(gb, "_lt_bytes") == 0 and u16(gb, "_lt_noteon") == 0)

# notes
b = burst_notes()
send(gb, b)
gb.run(120)
check("notes: 64 note-ons", u16(gb, "_lt_noteon") == 64, u16(gb, "_lt_noteon"))
check("notes: bytes", u16(gb, "_lt_bytes") == len(b), f"{u16(gb, '_lt_bytes')} vs {len(b)}")
check("notes: no stray data", u16(gb, "_lt_stray") == 0)

# clock
send(gb, burst_clock())
gb.run(60)
check("clock: 96 F8", u16(gb, "_lt_clock") == 96, u16(gb, "_lt_clock"))
check("clock: start/stop", u8(gb, "_lt_start") == 1 and u8(gb, "_lt_stop") == 1)

# clock between and inside messages: notes must all survive
send(gb, burst_clock_between())
send(gb, burst_clock_inside())
gb.run(120)
check("clock between/inside: 64 more note-ons", u16(gb, "_lt_noteon") == 128, u16(gb, "_lt_noteon"))
check("clock between/inside: 128 more clocks", u16(gb, "_lt_clock") == 96 + 128, u16(gb, "_lt_clock"))
check("clock between/inside: no stray data", u16(gb, "_lt_stray") == 0)

# sysex
for name, burst in (("short", burst_sysex_short()), ("long", burst_sysex_long()), ("1k", burst_sysex_1k())):
    send(gb, burst)
    gb.run(200)
    want_len, want_sum = sx_len_sum(burst)
    check(f"sysex {name}: length {want_len}", u16(gb, "_lt_sx_len") == want_len, u16(gb, "_lt_sx_len"))
    check(f"sysex {name}: sum {want_sum:02X}", u8(gb, "_lt_sx_sum") == want_sum, f"{u8(gb, '_lt_sx_sum'):02X}")
check("sysex: 3 starts, 3 ends", u8(gb, "_lt_sx_start") == 3 and u8(gb, "_lt_sx_end") == 3)

# sysex must not upset normal playing afterwards
gb.note(0, 60, 100)
gb.run(10)
check("note after sysex still plays", gb.mem(0xFF26) & 0x01, hex(gb.mem(0xFF26)))
gb.off(0, 60)
gb.run(10)

# a dropped status byte shows up as stray data (F7 outside a sysex cancels
# running status, so the next data bytes have no status to belong to)
gb.midi(0xF7, 60, 100)
gb.run(10)
check("stray data counted", u16(gb, "_lt_stray") == 2, u16(gb, "_lt_stray"))

# stress: twice the real link rate, no bytes may be lost
def send_fast(gb, data, per_frame=66):
    for i in range(0, len(data), per_frame):
        gb.midi(*data[i:i + per_frame])
        gb.run(1)


before = u16(gb, "_lt_bytes")
stress = burst_sysex_1k() + burst_notes() + burst_clock_inside()
send_fast(gb, stress)
gb.run(60)
got = (u16(gb, "_lt_bytes") - before) & 0xFFFF
check("stress at 2x link rate: every byte processed", got == len(stress), f"{got} of {len(stress)}")
check("stress: sysex intact", u16(gb, "_lt_sx_len") == 1027, u16(gb, "_lt_sx_len"))

# screen: Setup (B) -> down to LINK TEST -> A
gb.press("b")
for _ in range(9):
    gb.press("down")
gb.press("a")
gb.run(30)
gb.screenshot(os.path.join(OUT, "link_test.png"))
gb.press("a")  # reset
gb.run(10)
check("A resets counters", u16(gb, "_lt_bytes") == 0 and u16(gb, "_lt_noteon") == 0)
send(gb, burst_sysex_short())
gb.run(30)
gb.screenshot(os.path.join(OUT, "link_test_after_sysex.png"))

gb.stop()
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
