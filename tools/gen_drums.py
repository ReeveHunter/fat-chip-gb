#!/usr/bin/env python3
"""Synthesize the drum kits (original sounds, no third-party samples).

Each kit lives in its own ROM bank. Samples are 4-bit, packed two per byte,
padded to whole 32-sample chunks (16 bytes) so the timer ISR can stream them
one wave-RAM load at a time.

Outputs src/gen/drums.c (+ drums_kitN.c per bank) and docs/drums/*.wav previews.
"""
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from cgen import c_array, c_strings, header, pack_nibbles  # noqa: E402

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "src", "gen")
PREV = os.path.join(HERE, "..", "docs", "drums")
os.makedirs(OUT, exist_ok=True)
os.makedirs(PREV, exist_ok=True)

DRUM_T = 48
SR = 524288 / DRUM_T  # ~10923 Hz
FIRST_BANK = 3
rng = np.random.default_rng(1989)

# sound slots shared by all kits (index -> name); note map below
SLOTS = ["KICK", "RIM", "SNARE", "CLAP", "SNARE2", "LO TOM", "CL HAT", "MD TOM", "OP HAT",
         "HI TOM", "CRASH", "RIDE", "SHAKER", "COWBEL", "CLAVE", "ZAP", "BLIP", "BOOM"]
NOTE_MAP = {
    35: 0, 36: 0, 37: 1, 38: 2, 39: 3, 40: 4, 41: 5, 43: 5, 42: 6, 44: 6, 45: 7, 47: 7,
    46: 8, 48: 9, 50: 9, 49: 10, 57: 10, 51: 11, 59: 11, 53: 11, 54: 12, 70: 12, 69: 12,
    56: 13, 75: 14, 76: 14, 77: 14, 60: 15, 61: 16, 62: 17,
}


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def env_exp(t, tau):
    return np.exp(-t / tau)


def sweep_sine(t, f0, f1, tau):
    f = f1 + (f0 - f1) * np.exp(-t / tau)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph)


def noise(n):
    return rng.uniform(-1, 1, n)


def hp(x, a=0.85):
    y = np.zeros_like(x)
    prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x)
        prev_x = v
        y[i] = prev_y
    return y


def lp(x, a=0.5):
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def bp(x, f, q=4.0):
    # simple biquad band-pass
    w = 2 * np.pi * f / SR
    alpha = np.sin(w) / (2 * q)
    b0, b2 = alpha, -alpha
    a0, a1, a2 = 1 + alpha, -2 * np.cos(w), 1 - alpha
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        o = (b0 * v + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1 = x1, v
        y2, y1 = y1, o
        y[i] = o
    return y


def sq(ph):
    return np.where((ph % 1.0) < 0.5, 1.0, -1.0)


# ------------------------------------------------------------------ kit 0: "808"
def kit_808():
    s = {}
    t = tt(0.42)
    s["KICK"] = sweep_sine(t, 160, 46, 0.03) * env_exp(t, 0.13) * 1.1 + \
        0.3 * noise(len(t)) * env_exp(t, 0.003)
    t = tt(0.05)
    s["RIM"] = (np.sin(2 * np.pi * 1700 * t) * 0.7 + np.sin(2 * np.pi * 460 * t) * 0.5) * env_exp(t, 0.008)
    t = tt(0.22)
    s["SNARE"] = (sweep_sine(t, 240, 180, 0.02) * env_exp(t, 0.05) * 0.8 +
                  hp(noise(len(t)), 0.7) * env_exp(t, 0.07) * 0.9)
    t = tt(0.25)
    n = hp(noise(len(t)), 0.6)
    e = np.zeros(len(t))
    for k, d in enumerate([0.0, 0.011, 0.022]):
        idx = t >= d
        e[idx] = np.maximum(e[idx], env_exp(t[idx] - d, 0.006 if k < 2 else 0.06))
    s["CLAP"] = bp(n, 1100, 1.5) * e * 2.0
    t = tt(0.18)
    s["SNARE2"] = (sweep_sine(t, 330, 220, 0.01) * env_exp(t, 0.03) * 0.6 +
                   hp(noise(len(t)), 0.8) * env_exp(t, 0.045))
    for name, f0, f1 in [("LO TOM", 130, 85), ("MD TOM", 190, 125), ("HI TOM", 270, 180)]:
        t = tt(0.3)
        s[name] = sweep_sine(t, f0, f1, 0.05) * env_exp(t, 0.11) + 0.2 * noise(len(t)) * env_exp(t, 0.004)
    t = tt(0.06)
    s["CL HAT"] = hp(noise(len(t)), 0.95) * env_exp(t, 0.014)
    t = tt(0.38)
    s["OP HAT"] = hp(noise(len(t)), 0.95) * env_exp(t, 0.12)
    t = tt(0.7)
    metal = sum(sq(f * t) for f in [205.3, 304.4, 369.6, 522.7, 540.0, 800.0])
    s["CRASH"] = hp(0.6 * noise(len(t)) + 0.15 * metal, 0.9) * env_exp(t, 0.25)
    t = tt(0.5)
    s["RIDE"] = hp(0.35 * noise(len(t)) + 0.3 * sum(sq(f * t) for f in [430, 640, 1010]) / 3, 0.9) * env_exp(t, 0.2)
    t = tt(0.1)
    s["SHAKER"] = hp(noise(len(t)), 0.93) * np.sin(np.pi * np.clip(t / 0.1, 0, 1)) ** 2
    t = tt(0.22)
    cb = bp(sq(540 * t) + sq(800 * t), 670, 2.5)
    s["COWBEL"] = cb * (0.6 * env_exp(t, 0.01) + 0.6 * env_exp(t, 0.09)) * 2
    t = tt(0.06)
    s["CLAVE"] = np.sin(2 * np.pi * 2500 * t) * env_exp(t, 0.012)
    t = tt(0.2)
    s["ZAP"] = sq(np.cumsum(1800 * np.exp(-t / 0.03) + 60) / SR) * env_exp(t, 0.08)
    t = tt(0.09)
    s["BLIP"] = sq(np.cumsum(np.where(t < 0.03, 1046.5, 1568.0)) / SR) * env_exp(t, 0.05)
    t = tt(0.7)
    s["BOOM"] = sweep_sine(t, 90, 38, 0.08) * env_exp(t, 0.3) * 1.2
    return s


# ------------------------------------------------------------------ kit 1: "CHIP" (crunchy)
def crush(x, levels=6):
    x = np.clip(x, -1, 1)
    return np.round((x + 1) / 2 * (levels - 1)) / (levels - 1) * 2 - 1


def kit_chip():
    s = {}
    t = tt(0.3)
    s["KICK"] = crush(sq(np.cumsum(220 * np.exp(-t / 0.025) + 50) / SR) * env_exp(t, 0.09), 8)
    t = tt(0.04)
    s["RIM"] = crush(sq(1200 * t) * env_exp(t, 0.01))
    t = tt(0.2)
    s["SNARE"] = crush(sq(np.cumsum(400 * np.exp(-t / 0.01) + 160) / SR) * env_exp(t, 0.02) * 0.7 +
                       noise(len(t)) * env_exp(t, 0.06), 8)
    t = tt(0.2)
    e = np.where(t < 0.01, 1, 0) + np.where((t > 0.016) & (t < 0.026), 1, 0) + env_exp(np.maximum(t - 0.03, 0), 0.05) * (t > 0.03)
    s["CLAP"] = crush(noise(len(t)) * e, 6)
    t = tt(0.15)
    s["SNARE2"] = crush(noise(len(t)) * env_exp(t, 0.035), 4)
    for name, f0 in [("LO TOM", 110), ("MD TOM", 165), ("HI TOM", 247)]:
        t = tt(0.24)
        s[name] = crush(sq(np.cumsum(f0 * (1 + 0.8 * np.exp(-t / 0.03))) / SR) * env_exp(t, 0.08), 6)
    t = tt(0.05)
    s["CL HAT"] = crush(hp(noise(len(t)), 0.9) * env_exp(t, 0.012), 4)
    t = tt(0.3)
    s["OP HAT"] = crush(hp(noise(len(t)), 0.9) * env_exp(t, 0.09), 4)
    t = tt(0.6)
    s["CRASH"] = crush(noise(len(t)) * env_exp(t, 0.2), 4)
    t = tt(0.4)
    s["RIDE"] = crush((0.5 * noise(len(t)) + 0.5 * sq(733 * t) * sq(1033 * t)) * env_exp(t, 0.15), 6)
    t = tt(0.08)
    s["SHAKER"] = crush(hp(noise(len(t)), 0.9) * np.sin(np.pi * t / 0.08) ** 2, 4)
    t = tt(0.18)
    s["COWBEL"] = crush((sq(587 * t) + sq(880 * t)) / 2 * env_exp(t, 0.07), 6)
    t = tt(0.05)
    s["CLAVE"] = crush(sq(1975 * t) * env_exp(t, 0.012), 6)
    t = tt(0.25)
    s["ZAP"] = crush(sq(np.cumsum(2500 * np.exp(-t / 0.05) + 80) / SR) * env_exp(t, 0.1), 6)
    t = tt(0.12)
    arp = np.where(t < 0.04, 1046.5, np.where(t < 0.08, 1318.5, 1568.0))
    s["BLIP"] = crush(sq(np.cumsum(arp) / SR) * env_exp(t, 0.08), 6)
    t = tt(0.6)
    s["BOOM"] = crush(sq(np.cumsum(120 * np.exp(-t / 0.1) + 35) / SR) * env_exp(t, 0.25), 8)
    return s


KITS = [("808", kit_808), ("CHIP", kit_chip)]


def to4(x):
    x = np.asarray(x, dtype=float)
    m = np.abs(x).max()
    if m > 0:
        x = x / m
    # soft knee so 4-bit headroom is used well
    x = np.tanh(1.3 * x) / np.tanh(1.3)
    q = np.clip(np.round((x + 1) * 7.5), 0, 15).astype(int)
    pad = (-len(q)) % 32
    q = np.concatenate([q, np.full(pad, 8)])
    # fade final chunk toward centre to avoid a click when the DAC turns off
    return q.tolist()


def write_wav(path, q):
    # preview: 4-bit levels -> 16-bit PCM at SR (rounded)
    data = ((np.array(q) - 7.5) / 7.5 * 20000).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(round(SR)))
        w.writeframes(data.tobytes())


def main():
    note_map = [0xFF] * 128
    for n, i in NOTE_MAP.items():
        note_map[n] = i

    common = header()
    common += f"#define DRUM_SLOTS {len(SLOTS)}\n"
    common += c_array("drum_note_map", note_map)
    sbank, soff, slen = [], [], []
    banks = {}  # bank -> bytes
    bank = FIRST_BANK
    banks[bank] = []
    for k, (kname, fn) in enumerate(KITS):
        sounds = fn()
        total = 0
        for name in SLOTS:
            q = to4(sounds[name])
            write_wav(os.path.join(PREV, f"{k}_{kname}_{name.replace(' ', '_')}.wav"), q)
            packed = pack_nibbles(q)
            chunks = len(packed) // 16
            assert chunks < 256, (name, chunks)
            if len(banks[bank]) + len(packed) > 16384:
                bank += 1
                banks[bank] = []
            sbank.append(bank)
            soff.append(0x4000 + len(banks[bank]))
            slen.append(chunks)
            banks[bank] += packed
            total += len(packed)
        print(f"kit {kname}: {total} bytes")
    for b, blob in banks.items():
        src = header(b)
        src += c_array(f"drum_bank{b}_data", blob)
        open(os.path.join(OUT, f"drums_bank{b}.c"), "w").write(src)
    print("drum banks", list(banks))
    common += f"#define DRUM_KITS {len(KITS)}\n"
    common += f"#define DRUM_LAST_BANK {bank}\n"
    common += c_array("drum_bank", sbank)
    common += c_array("drum_ptr", soff, "uint16_t", 8, "0x{:04X}")
    common += c_array("drum_len", slen)
    open(os.path.join(OUT, "drums.c"), "w").write(common)

    src = header(1)
    src += c_strings("kit_names", [n for n, _ in KITS], 6)
    src += c_strings("drum_slot_names", SLOTS, 6)
    open(os.path.join(OUT, "drum_names.c"), "w").write(src)


if __name__ == "__main__":
    main()
