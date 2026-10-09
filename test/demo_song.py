#!/usr/bin/env python3
"""Render a short demo through the emulator -> test/out/demo.wav
Part A: wave-channel acid bass + noise hats + pulse lead/arp
Part B: ch5 drum kit (borrows the wave channel) + pulses
Part C: the wave channel says "hello game boy" over the beat
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from harness import GB  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), "..", "gbmidi.gb")
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)
STEP = 7  # frames per 16th note (~128 BPM)

PH = ["IY", "IH", "EH", "AE", "AA", "AO", "UH", "UW", "AH", "ER", "AX", "EY", "AY", "OW", "AW", "OY",
      "W", "Y", "R", "L", "M", "N", "NG", "S", "SH", "F", "TH", "HH", "Z", "ZH", "V", "DH",
      "P", "T", "K", "B", "D", "G", "CH", "JH", "--"]


def ph(name):
    return 36 + PH.index(name)


def play(gb, events, steps):
    """events: dict step -> list of (kind, ch, a, b)."""
    held = {}
    for s in range(steps):
        for ev in events.get(s, []):
            kind, ch = ev[0], ev[1]
            if kind == "n":
                n, vel, length = ev[2], ev[3], ev[4]
                if ch in held and ch != 4:
                    gb.off(ch, held[ch][0])
                gb.note(ch, n, vel)
                held[ch] = (n, s + length)
            elif kind == "cc":
                gb.cc(ch, ev[2], ev[3])
            elif kind == "pc":
                gb.pc(ch, ev[2])
        for ch, (n, end) in list(held.items()):
            if end == s + 1:
                gb.off(ch, n)
                del held[ch]
        gb.run(STEP)


def add(ev, step, item):
    ev.setdefault(step, []).append(item)


def main():
    gb = GB(ROM)
    gb.run(150)
    gb.clear_audio()

    # ---------------- part A (2 bars x2)
    ev = {}
    add(ev, 0, ("pc", 2, 4))          # ACID SWP
    add(ev, 0, ("pc", 0, 1))          # LEAD 25
    add(ev, 0, ("pc", 1, 2))          # PLUCK
    add(ev, 0, ("pc", 3, 0))          # HAT
    add(ev, 0, ("cc", 1, 10, 0))      # pluck panned left
    bass = [36, 36, 48, 36, 39, 36, 46, 36, 36, 36, 48, 36, 41, 39, 43, 46]
    arp = [60, 63, 67, 72]
    lead = {0: 72, 6: 75, 8: 74, 12: 70, 16: 72, 22: 79, 24: 77, 28: 75}
    for rep in range(2):
        base = rep * 32
        for i in range(32):
            add(ev, base + i, ("n", 2, bass[i % 16], 110, 1))
            add(ev, base + i, ("n", 3, 108 if i % 2 else 112, 70 if i % 2 else 110, 1))
            add(ev, base + i, ("n", 1, arp[i % 4] + (0 if i < 16 else -2), 90, 1))
            if i in lead:
                add(ev, base + i, ("n", 0, lead[i], 115, 5))
        add(ev, base, ("cc", 2, 74, 20 + rep * 60))
    play(gb, ev, 64)

    # ---------------- part B: drum kit on ch5
    ev = {}
    add(ev, 0, ("pc", 0, 4))          # BASS on pulse 1
    add(ev, 0, ("pc", 1, 3))          # PWM PAD
    add(ev, 0, ("cc", 1, 10, 64))
    kick, snare, hat = 36, 38, 42
    for rep in range(2):
        base = rep * 32
        for i in range(32):
            if i % 8 == 0 or i in (14, 30) and rep:
                add(ev, base + i, ("n", 4, kick, 127, 1))
            elif i % 8 == 4:
                add(ev, base + i, ("n", 4, snare, 120, 1))
            elif i % 2 == 0:
                add(ev, base + i, ("n", 4, hat, 90, 1))
            if i % 4 == 2:
                add(ev, base + i, ("n", 0, [36, 36, 41, 43][(i // 8) % 4], 120, 2))
        add(ev, base, ("n", 1, 63 if rep == 0 else 65, 100, 30))
    add(ev, 32, ("cc", 4, 70, 127))   # switch to CHIP kit for bar 2
    play(gb, ev, 64)

    # ---------------- part C: speech over the beat
    ev = {}
    add(ev, 0, ("cc", 4, 70, 0))
    add(ev, 0, ("pc", 2, 8))          # ROBOT (speech mode)
    add(ev, 0, ("cc", 2, 84, 50))
    words = [("HH", 1), ("EH", 2), ("L", 1), ("OW", 3), ("--", 1), ("G", 1), ("EY", 2), ("M", 2),
             ("B", 1), ("OY", 4)]
    s = 0
    for name, ln in words:
        add(ev, s, ("n", 2, ph(name), 120, ln))
        s += ln
    for i in range(32):
        if i % 8 == 0:
            add(ev, i, ("n", 3, 40, 127, 1))
        elif i % 2 == 0:
            add(ev, i, ("n", 3, 110, 80, 1))
        if i % 8 == 4:
            add(ev, i, ("n", 3, 70, 120, 1))
    play(gb, ev, 36)
    gb.run(30)

    path = os.path.join(OUT, "demo.wav")
    gb.save_wav(path)
    print("wrote", path)
    gb.stop()


if __name__ == "__main__":
    main()
