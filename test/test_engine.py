#!/usr/bin/env python3
"""Engine tests in PyBoy. Run from repo root:  python3 test/test_engine.py
Writes listening examples to test/out/."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB, pitch_hz  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "fat-chip-gb.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    if not cond:
        fails += 1


def midi_hz(n):
    return 440 * 2 ** ((n - 69) / 12)


def near(f, target, cents=15):
    return f > 0 and abs(1200 * np.log2(f / target)) < cents


def cut(gb):
    for ch in range(5):
        gb.cc(ch, 123, 0)
    gb.run(3)


def boot():
    gb = GB(ROM)
    gb.run(150)  # boot ROM + init
    gb.clear_audio()
    return gb


def wave_freq(gb):
    x = gb.var("_wv_nr33") | ((gb.var("_wv_nr34") & 7) << 8)
    return 65536 / (2048 - x)


def pulse_freq(gb, ch=0):
    lo = 0xFF13 if ch == 0 else 0xFF18
    x = gb.mem(lo) | ((gb.var("_voice", 1) and 0) << 8)
    return x


def voice_field(gb, v, off, n=1):
    size = gb.sym["_voice"]  # base
    # voice_t size: compute from symbol spacing is fragile; use constant from engine.h layout
    VSIZE = VOICE_SIZE
    a = gb.sym["_voice"] + v * VSIZE + off
    return [gb.mem(a + i) for i in range(n)] if n > 1 else gb.mem(a)


VOICE_SIZE = None


def main():
    global VOICE_SIZE
    gb = boot()
    # voice_t size = distance between _voice and next symbol isn't reliable; derive from engine.h fields
    VOICE_SIZE = 45

    # ---- pulse 1 pitch
    for n in (45, 57, 69, 81):
        gb.clear_audio()
        gb.note(0, n, 120)
        gb.run(20)
        f = pitch_hz(gb.samples()[2000:, 0])
        check(f"pulse1 note {n}", near(f, midi_hz(n)), f"{f:.1f} Hz vs {midi_hz(n):.1f}")
        gb.off(0, n)
        gb.run(10)
    gb.save_wav(os.path.join(OUT, "pulse1.wav"))

    # ---- pulse 2 + duty CC
    gb.clear_audio()
    gb.note(1, 72, 120)
    gb.run(5)
    for duty, expect in ((0, 0), (40, 1), (70, 2), (120, 3)):
        gb.cc(1, 70, duty)
        gb.run(3)
        d = gb.mem(0xFF16) >> 6
        check(f"pulse2 duty cc {duty}", d == expect, f"NR21 duty {d}")
    f = pitch_hz(gb.samples()[2000:, 0])
    check("pulse2 C5", near(f, midi_hz(72)), f"{f:.1f}")
    gb.off(1, 72)
    gb.run(10)

    cut(gb)
    # ---- pitch bend (+2 semis default range)
    gb.note(0, 69, 120)
    gb.run(5)
    gb.bend(0, 16383)
    gb.run(5)
    gb.clear_audio()
    gb.run(15)
    f = pitch_hz(gb.samples()[1000:, 0])
    check("pitch bend up 2", near(f, midi_hz(71), 25), f"{f:.1f} vs {midi_hz(71):.1f}")
    gb.bend(0, 8192)
    gb.off(0, 69)
    gb.run(10)

    cut(gb)
    # ---- wave synth pitch
    for n in (45, 57, 69):
        gb.clear_audio()
        gb.note(2, n, 120)
        gb.run(20)
        f = pitch_hz(gb.samples()[2000:, 0])
        check(f"wave synth note {n}", near(f, midi_hz(n)), f"{f:.1f} vs {midi_hz(n):.1f}")
        gb.off(2, n)
        gb.run(8)

    # ---- wave shape sweep via CC74 (timbre) changes wave RAM
    gb.cc(2, 71, 0)  # SYNTH mode
    gb.cc(2, 70, 0)  # PULSE shape
    gb.note(2, 57, 127)
    gb.run(5)
    w1 = gb.var('_wave_buf', 16)
    gb.cc(2, 74, 127)
    gb.run(5)
    w2 = gb.var('_wave_buf', 16)
    check("wave timbre changes wave RAM", w1 != w2, f"{w1[:4]} -> {w2[:4]}")
    gb.off(2, 57)
    gb.run(5)

    # ---- PULSE mode (wave as a third pulse) and TRI mode
    gb.cc(2, 71, 20)   # mode 1 = PULSE
    for cc, width in ((0, 4), (40, 8), (70, 16)):
        gb.cc(2, 70, cc)
        gb.clear_audio()
        gb.note(2, 57, 127)
        gb.run(15)
        buf = gb.var("_wave_buf", 16)
        samples = [n for b in buf for n in (b >> 4, b & 15)]
        hi = sum(1 for x in samples if x > 8)
        f = pitch_hz(gb.samples()[1500:, 0])
        check(f"wave PULSE duty cc{cc}", hi == width and near(f, midi_hz(57)), f"high {hi}/32, {f:.1f} Hz")
        gb.off(2, 57)
        gb.run(5)
    gb.cc(2, 71, 40)   # mode 2 = TRI
    gb.clear_audio()
    gb.note(2, 45, 127)
    gb.run(15)
    buf = gb.var("_wave_buf", 16)
    samples = [n for b in buf for n in (b >> 4, b & 15)]
    diffs = {abs(samples[i + 1] - samples[i]) for i in range(31)}
    f = pitch_hz(gb.samples()[1500:, 0])
    check("wave TRI is a triangle", diffs <= {0, 1} and max(samples) == 15 and min(samples) == 0 and near(f, midi_hz(45)),
          f"{samples[:12]}.. {f:.1f} Hz")
    gb.save_wav(os.path.join(OUT, "wave_tri.wav"))
    gb.off(2, 45)
    gb.cc(2, 71, 0)
    gb.run(5)

    # ---- dual tone: MAJOR (4:5:6) -> channel plays root/4
    gb.cc(2, 71, 60)   # mode 3 = DUAL  (60*7>>7 = 3)
    gb.cc(2, 70, 10 * 8 + 4)  # shape 10 = MAJOR
    gb.run(2)
    check("wave mode = dual", gb.var("_patch", 96)[64 + 4] == 3, str(gb.var("_patch", 96)[64 + 4]))
    gb.clear_audio()
    gb.note(2, 64, 120)
    gb.run(25)
    wf = wave_freq(gb)
    check("dual MAJOR root/4", near(wf * 4, midi_hz(64), 10), f"wave {wf:.2f} Hz x4 = {wf * 4:.1f} vs {midi_hz(64):.1f}")
    gb.save_wav(os.path.join(OUT, "dual_major.wav"))
    gb.off(2, 64)
    gb.cc(2, 71, 0)
    gb.run(5)

    # ---- noise
    gb.note(3, 60, 120)
    gb.run(3)
    r = gb.regs()
    check("noise NR43 from table", r["NR43"] != 0 and (r["NR52"] & 8), f"NR43 {r['NR43']:02X} NR52 {r['NR52']:02X}")
    gb.off(3, 60)
    gb.run(10)

    # ---- drums on ch 5
    gb.clear_audio()
    for n in (36, 38, 42, 46, 36, 39):
        gb.note(4, n, 127)
        gb.run(12)
    gb.run(30)
    s = gb.samples()
    check("drum stream produced audio", np.abs(s).max() > 2, f"peak {np.abs(s).max()}")
    check("drum stream finished", gb.var("_st_active") == 0 and gb.var("_wave_owner") != 2,
          f"active {gb.var('_st_active')} owner {gb.var('_wave_owner')}")
    gb.save_wav(os.path.join(OUT, "drums_808.wav"))

    # chip kit
    gb.cc(4, 70, 127)
    gb.clear_audio()
    for n in (36, 42, 38, 42, 36, 36, 38, 46):
        gb.note(4, n, 127)
        gb.run(10)
    gb.run(30)
    gb.save_wav(os.path.join(OUT, "drums_chip.wav"))
    gb.cc(4, 70, 0)

    # ---- drum steals wave, synth resumes
    gb.clear_audio()
    gb.note(2, 57, 120)
    gb.run(10)
    gb.note(4, 42, 127)   # short closed hat
    gb.run(2)
    check("drum owns wave", gb.var("_wave_owner") == 2)
    gb.run(15)
    check("synth resumed after drum", gb.var("_wave_owner") == 1, f"owner {gb.var('_wave_owner')}")
    gb.off(2, 57)
    gb.run(10)
    gb.save_wav(os.path.join(OUT, "steal_resume.wav"))

    # ---- split on ch3: below C3 = drums
    gb.cc(2, 83, 48)
    gb.note(2, 36, 120)
    gb.run(2)
    check("split: low note -> drum", gb.var("_wave_owner") == 2)
    gb.run(30)
    gb.note(2, 60, 120)
    gb.run(3)
    check("split: high note -> synth", gb.var("_wave_owner") == 1)
    gb.off(2, 60)
    gb.cc(2, 83, 0)
    gb.run(10)

    # ---- speech
    gb.cc(2, 71, 100)  # mode 5 = SPEECH
    gb.cc(2, 84, 48)   # speech pitch C3
    gb.run(2)
    gb.clear_audio()
    names = ["HH", "EH", "L", "OW", "--", "W", "ER", "L", "D"]
    order = ["IY", "IH", "EH", "AE", "AA", "AO", "UH", "UW", "AH", "ER", "AX", "EY", "AY", "OW", "AW", "OY",
             "W", "Y", "R", "L", "M", "N", "NG", "S", "SH", "F", "TH", "HH", "Z", "ZH", "V", "DH",
             "P", "T", "K", "B", "D", "G", "CH", "JH", "--"]
    for nm in names:
        n = 36 + order.index(nm)
        gb.note(2, n, 120)
        gb.run(9 if nm in ("EH", "OW", "ER") else 6)
        gb.off(2, n)
    gb.run(20)
    s = gb.samples()
    check("speech produced audio", np.abs(s).max() > 2)
    gb.save_wav(os.path.join(OUT, "speech_hello_world.wav"))

    # sing mode: phoneme AA, melody
    gb.cc(2, 71, 120)  # mode 6 SING
    gb.cc(2, 86, order.index("AA"))
    gb.clear_audio()
    for n in (48, 52, 55, 60, 55, 52, 48):
        gb.note(2, n, 120)
        gb.run(12)
        gb.off(2, n)
        gb.run(2)
    gb.run(15)
    gb.save_wav(os.path.join(OUT, "sing_arpeggio.wav"))
    gb.cc(2, 71, 0)
    gb.run(5)

    # ---- glide
    gb.cc(0, 5, 70)
    gb.note(0, 57, 120)
    gb.run(10)
    gb.note(0, 69, 120)
    gb.run(2)
    p_mid = voice_field(gb, 0, 14, 2)
    gb.run(40)
    gb.off(0, 69)
    gb.off(0, 57)
    gb.cc(0, 5, 0)
    gb.run(10)
    print("    glide pitch sample", p_mid)

    # ---- LFO vibrato audible as pitch modulation
    gb.cc(0, 76, 80)
    gb.cc(0, 1, 90)
    gb.clear_audio()
    gb.note(0, 69, 120)
    gb.run(60)
    gb.off(0, 69)
    gb.cc(0, 1, 0)
    gb.run(10)
    gb.save_wav(os.path.join(OUT, "vibrato.wav"))

    # ---- program change loads patch name
    gb.pc(0, 5)
    gb.run(3)
    name = bytes(gb.var("_patch", 32)[24:32]).decode()
    check("program change loads patch 5", name.strip() == "BLIP", repr(name))
    gb.pc(0, 0)
    gb.run(3)

    # ---- running status (note on, then data pairs only)
    gb.midi(0x90, 60, 100, 64, 100, 67, 100)
    gb.run(3)
    held = voice_field(gb, 0, 3, 8)
    check("running status note stack", held[:3] == [60, 64, 67], str(held[:4]))
    gb.midi(0x80, 60, 0, 64, 0, 67, 0)
    gb.run(5)

    print("\n%d failure(s)" % fails)
    gb.stop()
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
