#!/usr/bin/env python3
"""Allophone speech data for the wave channel (original formant synthesis).

Each allophone is a short sequence of 32-sample single-cycle frames, played one
frame per video frame (~60 Hz). Voiced frames are played at the note pitch, so
the Game Boy can *sing*; unvoiced frames (s, sh, f, bursts) are played at a fixed
high rate with fresh random phases each frame.

Two frame sets are generated: one tuned for low voices (f0 ~110 Hz) and one for
higher voices (f0 ~220 Hz). The engine picks the set from the playing pitch.

Outputs src/gen/speech.c (bank SPEECH_BANK), src/gen/speech_names.c (UI bank),
docs/speech_preview.wav.
"""
import math
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from cgen import c_array, c_strings, header, pack_nibbles  # noqa: E402

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "src", "gen")
SPEECH_BANK = 7
N = 32
NOISE_RATE = 32768.0  # unvoiced frames: 32-sample loop -> harmonics of 1024 Hz
rng = np.random.default_rng(256)

# meta byte per frame
M_LEVEL_MASK = 0x03  # 1=100% 2=50% 3=25% (NR32 code), 0 = silent
M_UNVOICED = 0x80

# ---------------------------------------------------------------- phoneme specs
# vowels: (F1, F2, F3)
V = {
    "IY": (270, 2290, 3010), "IH": (390, 1990, 2550), "EH": (530, 1840, 2480),
    "AE": (660, 1720, 2410), "AA": (730, 1090, 2440), "AO": (570, 840, 2410),
    "UH": (440, 1020, 2240), "UW": (300, 870, 2240), "AH": (640, 1190, 2390),
    "ER": (490, 1350, 1690), "AX": (500, 1500, 2500),
}
BW = (90, 110, 170)

# Noise spectra: list of (center Hz, width Hz, gain)
NOISE = {
    "S": [(6500, 3000, 1.0)],
    "SH": [(3000, 1500, 1.0), (5000, 2000, 0.4)],
    "F": [(4000, 8000, 0.5)],
    "TH": [(6000, 8000, 0.45)],
    "HH": [(1500, 1200, 0.5), (2600, 1500, 0.35)],
    "BP": [(1000, 1500, 0.7)],   # P burst
    "BT": [(4500, 2500, 0.9)],   # T burst
    "BK": [(2000, 1200, 0.9)],   # K burst
    "BCH": [(3200, 2000, 1.0)],
}

# Segment types:
#   ("v", frames, F_start, F_end, amp_start, amp_end)       voiced, formants glide
#   ("n", frames, noise_key, amp_start, amp_end)            unvoiced
#   ("z", frames, F, noise_key, amp)                         voiced + noise (buzz)
#   ("s", frames)                                            silence
# hold = (first, last) frame indices looped while the note is held (None = one-shot)
PH = []


def ph(name, segs, hold="last"):
    PH.append((name, segs, hold))


def vowel(name, frames=6):
    F = V[name]
    ph(name, [("v", 2, F, F, 0.5, 1.0), ("v", frames - 2, F, F, 1.0, 1.0)])


def diph(name, a, b):
    ph(name, [("v", 2, a, a, 0.6, 1.0), ("v", 4, a, a, 1.0, 1.0), ("v", 6, a, b, 1.0, 1.0),
              ("v", 2, b, b, 1.0, 1.0)])


for v in ["IY", "IH", "EH", "AE", "AA", "AO", "UH", "UW", "AH", "ER", "AX"]:
    vowel(v)
diph("EY", (480, 1900, 2500), (330, 2200, 2900))
diph("AY", (730, 1090, 2440), (330, 2100, 2800))
diph("OW", (550, 900, 2400), (330, 800, 2250))
diph("AW", (730, 1100, 2440), (350, 850, 2250))
diph("OY", (570, 840, 2410), (330, 2100, 2800))
# semivowels / liquids (glide toward neutral)
ph("W", [("v", 3, (290, 610, 2150), (290, 610, 2150), 0.5, 0.7), ("v", 3, (290, 610, 2150), (450, 1000, 2300), 0.7, 0.9)])
ph("Y", [("v", 3, (260, 2070, 3020), (260, 2070, 3020), 0.5, 0.7), ("v", 3, (260, 2070, 3020), (400, 1800, 2600), 0.7, 0.9)])
ph("R", [("v", 3, (310, 1060, 1380), (310, 1060, 1380), 0.6, 0.8), ("v", 3, (310, 1060, 1380), (450, 1200, 1800), 0.8, 0.9)])
ph("L", [("v", 3, (310, 1050, 2880), (310, 1050, 2880), 0.6, 0.8), ("v", 3, (310, 1050, 2880), (450, 1200, 2600), 0.8, 0.9)])
# nasals (murmur)
ph("M", [("v", 5, (270, 1000, 2200), (270, 1000, 2200), 0.45, 0.5)])
ph("N", [("v", 5, (270, 1500, 2500), (270, 1500, 2500), 0.45, 0.5)])
ph("NG", [("v", 5, (270, 2000, 2700), (270, 2000, 2700), 0.4, 0.45)])
# fricatives
ph("S", [("n", 6, "S", 0.8, 0.9)])
ph("SH", [("n", 6, "SH", 0.8, 1.0)])
ph("F", [("n", 5, "F", 0.4, 0.45)])
ph("TH", [("n", 5, "TH", 0.35, 0.4)])
ph("HH", [("n", 4, "HH", 0.4, 0.5)])
ph("Z", [("z", 6, (270, 1800, 2500), "S", 0.7)])
ph("ZH", [("z", 6, (300, 1800, 2400), "SH", 0.7)])
ph("V", [("z", 5, (300, 1100, 2300), "F", 0.55)])
ph("DH", [("z", 4, (300, 1400, 2500), "TH", 0.5)])
# stops (one-shot): burst + aspiration / voice onset
ph("P", [("s", 1), ("n", 1, "BP", 0.9, 0.9), ("n", 2, "HH", 0.5, 0.3)], hold=None)
ph("T", [("s", 1), ("n", 1, "BT", 1.0, 1.0), ("n", 2, "S", 0.5, 0.3)], hold=None)
ph("K", [("s", 1), ("n", 1, "BK", 1.0, 1.0), ("n", 2, "HH", 0.6, 0.35)], hold=None)
ph("B", [("v", 1, (200, 900, 2200), (200, 900, 2200), 0.3, 0.3), ("n", 1, "BP", 0.5, 0.5),
         ("v", 2, (300, 1000, 2300), (450, 1100, 2400), 0.7, 0.9)], hold=None)
ph("D", [("v", 1, (200, 1600, 2600), (200, 1600, 2600), 0.3, 0.3), ("n", 1, "BT", 0.5, 0.5),
         ("v", 2, (300, 1700, 2600), (450, 1600, 2500), 0.7, 0.9)], hold=None)
ph("G", [("v", 1, (200, 1900, 2300), (200, 1900, 2300), 0.3, 0.3), ("n", 1, "BK", 0.6, 0.6),
         ("v", 2, (300, 1900, 2400), (450, 1500, 2400), 0.7, 0.9)], hold=None)
ph("CH", [("s", 1), ("n", 1, "BT", 0.9, 0.9), ("n", 4, "SH", 1.0, 0.7)], hold=None)
ph("JH", [("v", 1, (200, 1600, 2600), (200, 1600, 2600), 0.3, 0.3), ("n", 1, "BT", 0.5, 0.5),
          ("z", 4, (300, 1800, 2400), "SH", 0.7)], hold=None)
# a short pause (useful between words when sequencing)
ph("--", [("s", 2)], hold=None)


# ---------------------------------------------------------------- synthesis
def voiced_wave(f0, F, amp, buzz=0.0):
    amps = []
    for h in range(1, 17):
        fh = h * f0
        a = 0.0
        for Fi, Bi, gi in zip(F, BW, (1.0, 0.7, 0.35)):
            a += gi / math.sqrt(1 + ((fh - Fi) / (Bi / 2)) ** 2)
        a *= 1.0 / (h ** 0.6)
        amps.append(a)
    t = np.arange(N) / N
    y = np.zeros(N)
    for h, a in enumerate(amps, 1):
        y += a * np.sin(2 * np.pi * h * t - np.pi / 2 * h)  # roughly glottal phase
    y = y / (np.abs(y).max() + 1e-9)
    if buzz:
        y = y * (1 - buzz) + buzz * noise_wave(NOISE["S"], 1.0, f0)  # pitched hiss on top
    return y * amp


def noise_wave(spec, amp, base=NOISE_RATE / N):
    t = np.arange(N) / N
    y = np.zeros(N)
    for h in range(1, 17):
        fh = h * base
        g = 0.0
        for c, w, gain in spec:
            g += gain * math.exp(-0.5 * ((fh - c) / (w / 2)) ** 2)
        y += g * np.sin(2 * np.pi * h * t + rng.uniform(0, 2 * np.pi))
    m = np.abs(y).max()
    if m > 1e-9:
        y = y / m
    return y * amp


def encode(y, unvoiced):
    a = float(np.abs(y).max())
    if a < 0.04:
        return [0x88] * 16, 0
    if a > 0.5:
        level, gain = 1, 1.0
    elif a > 0.25:
        level, gain = 2, 2.0
    else:
        level, gain = 3, 4.0
    q = np.clip(np.round((y * gain + 1) * 7.5), 0, 15).astype(int).tolist()
    return pack_nibbles(q), level | (M_UNVOICED if unvoiced else 0)


def lerp(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def render_set(f0):
    frames, meta, table = [], [], []
    for name, segs, hold in PH:
        start = len(meta)
        for seg in segs:
            kind, n = seg[0], seg[1]
            for i in range(n):
                f = i / max(1, n - 1)
                if kind == "v":
                    F = lerp(seg[2], seg[3], f)
                    amp = seg[4] + (seg[5] - seg[4]) * f
                    b, m = encode(voiced_wave(f0, F, amp), False)
                elif kind == "n":
                    amp = seg[3] + (seg[4] - seg[3]) * f
                    b, m = encode(noise_wave(NOISE[seg[2]], amp), True)
                elif kind == "z":
                    b, m = encode(voiced_wave(f0, seg[2], seg[4], buzz=0.35), False)
                else:
                    b, m = [0x88] * 16, 0
                frames += b
                meta.append(m)
        count = len(meta) - start
        if hold == "last":
            # hold the last frame (or last 2 for noise, which alternate phases)
            hs = count - 2 if segs[-1][0] in ("n", "z") else count - 1
            he = count - 1
        else:
            hs = he = 0xFF
        table.append((start, count, hs, he))
    return frames, meta, table


def preview(frames, meta, table, f0, path):
    """Render a rough audio preview of 'hello world' style sequence."""
    sr = 32768
    out = []
    words = [["HH", "EH", "L", "OW"], ["--"], ["W", "ER", "L", "D"], ["--"],
             ["G", "EY", "M"], ["B", "OY"]]
    names = [p[0] for p in PH]
    for w in words:
        for p in w:
            st, cnt, hs, he = table[names.index(p)]
            seq = list(range(cnt)) + ([cnt - 1] * 4 if hs != 0xFF else [])
            for k in seq:
                i = st + k
                m = meta[i]
                lvl = {0: 0, 1: 1.0, 2: 0.5, 3: 0.25}[m & 3]
                b = frames[i * 16:(i + 1) * 16]
                s = []
                for byte in b:
                    s += [byte >> 4, byte & 15]
                cyc = (np.array(s) - 7.5) / 7.5 * lvl
                rate = NOISE_RATE / N if m & M_UNVOICED else f0
                n = int(sr / 59.73)
                idx = (np.arange(n) * rate * N / sr).astype(int) % N
                out.append(cyc[idx])
    data = (np.concatenate(out) * 20000).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def main():
    lo = render_set(110.0)
    hi = render_set(220.0)
    nframes = len(lo[1])
    assert len(hi[1]) == nframes
    frames = lo[0] + hi[0]
    meta = lo[1] + hi[1]
    size = len(frames) + len(meta)
    assert size < 16384 - 512, size
    src = header(SPEECH_BANK)
    src += c_array("speech_frames", frames)
    src += c_array("speech_meta", meta)
    open(os.path.join(OUT, "speech.c"), "w").write(src)

    # fixed-bank table so the engine can index without switching banks
    src = header()
    src += f"#define SPEECH_PHONEMES {len(PH)}\n#define SPEECH_SET_FRAMES {nframes}\n"
    src += c_array("speech_start", [t[0] for t in lo[2]], "uint16_t", 8, "{:4d}")
    src += c_array("speech_count", [t[1] for t in lo[2]], fmt="{:3d}")
    src += c_array("speech_hold", [t[2] for t in lo[2]], fmt="{:3d}")
    open(os.path.join(OUT, "speech_tbl.c"), "w").write(src)

    src = header(1)
    src += c_strings("phoneme_names", [p[0] for p in PH], 2)
    open(os.path.join(OUT, "speech_names.c"), "w").write(src)
    preview(*lo, 110.0, os.path.join(HERE, "..", "docs", "speech_preview_low.wav"))
    preview(*hi, 220.0, os.path.join(HERE, "..", "docs", "speech_preview_high.wav"))
    print(f"speech: {len(PH)} phonemes, {nframes} frames/set, {size} bytes in bank {SPEECH_BANK}")


if __name__ == "__main__":
    main()
