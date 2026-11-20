#!/usr/bin/env python3
"""Fat Chip GB drum synthesis (no third-party samples), and the sample prep that
turns each sound into what Fat Chip GB plays (4-bit, 524288 / 48 = 10923 Hz).

Kits are modelled on the analogue machines' circuits (808, 909, CR-78) or
built from Game Boy-style square / LFSR noise (CHIP SQ, CHIP LFSR).

Sample-prep chains (LSDJ follows the recipe LSDJ kit makers use, little-scale /
chipmusic.org); Fat Chip GB's kits use LSDJ:
  CLEAN    low-cut 40 Hz, anti-alias, normalize, 4-bit
  LSDJ     low-cut 70 Hz, +4 dB mids, normalize, +6 dB into a soft limiter, 4-bit
  SMASHED  a fast 6:1 compressor, +12 dB drive (tanh), 4-bit
  DITHER   LSDJ, with +-1 LSB triangular dither before the 4-bit step
Every chain trims the tail below 1 LSB and fades the last 3 ms.

Used by gen_drums.py. The Kit Lab listening page was built from the same code.
"""
import numpy as np
from scipy.signal import lfilter, resample_poly

HI = 44100
GB = 524288 / 48                     # 10922.67 Hz
rng = np.random.default_rng(1989)
SLOTS = ["KICK", "RIM", "SNARE", "CLAP", "SNARE2", "LO TOM", "CL HAT", "MD TOM", "OP HAT",
         "HI TOM", "CRASH", "RIDE", "SHAKER", "COWBEL", "CLAVE", "ZAP", "BLIP", "BOOM"]


# ------------------------------------------------------------------ building blocks (44.1 kHz)
def tt(d):
    return np.arange(int(d * HI)) / HI


def ex(t, tau):
    return np.exp(-t / tau)


def noise(n):
    return rng.uniform(-1, 1, n)


def sweep(t, f0, f1, tau, wave="sin"):
    f = f1 + (f0 - f1) * np.exp(-t / tau)
    ph = np.cumsum(f) / HI
    if wave == "sq":
        return np.where(ph % 1 < 0.5, 1.0, -1.0)
    if wave == "pulse25":
        return np.where(ph % 1 < 0.25, 1.0, -1.0)
    if wave == "tri4":                                   # the Game Boy wave channel's stepped triangle
        tri = 1 - 4 * np.abs((ph % 1) - 0.5)
        return np.round((tri + 1) * 7.5) / 7.5 - 1
    return np.sin(2 * np.pi * ph)


def sq(f, t, duty=0.5):
    return np.where((f * t) % 1 < duty, 1.0, -1.0)


def biquad(x, kind, f, q=0.707, gain_db=0.0, sr=HI):
    w = 2 * np.pi * f / sr
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    A = 10 ** (gain_db / 40)
    if kind == "lp":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == "hp":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == "bp":
        b = [al, 0, -al]; a = [1 + al, -2 * c, 1 - al]
    elif kind == "peak":
        b = [1 + al * A, -2 * c, 1 - al * A]; a = [1 + al / A, -2 * c, 1 - al / A]
    else:
        raise ValueError(kind)
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x)


def reso(t, f, tau, phase=0.0):
    """a ringing resonator (the analogue machines' bridged-T voices)"""
    return np.sin(2 * np.pi * f * t + phase) * ex(t, tau)


METAL808 = [205.3, 304.4, 369.6, 522.7, 540.0, 800.0]   # the 808's six square oscillators


def metal(t, freqs=METAL808, duty=0.5):
    return sum(sq(f, t, duty) for f in freqs) / len(freqs)


def bursts(t, times, tau_b, tail_tau, tail_from):
    e = np.zeros(len(t))
    for d in times:
        i = t >= d
        e[i] = np.maximum(e[i], ex(t[i] - d, tau_b))
    i = t >= tail_from
    e[i] = np.maximum(e[i], 0.7 * ex(t[i] - tail_from, tail_tau))
    return e


def lfsr_noise(t, clock_hz, short=False):
    """the Game Boy noise channel: a 15-bit (or 7-bit 'metallic') LFSR stepped at clock_hz"""
    steps = int(t[-1] * clock_hz) + 2 if len(t) else 1
    reg = 0x7FFF
    bits = np.empty(steps)
    for i in range(steps):
        b = (reg ^ (reg >> 1)) & 1
        reg = (reg >> 1) | (b << 14)
        if short:
            reg = (reg & ~(1 << 6)) | (b << 6)
        bits[i] = 1.0 if (reg & 1) == 0 else -1.0
    return bits[np.minimum((t * clock_hz).astype(int), steps - 1)]


# ------------------------------------------------------------------ the kits
def kit_808():
    s, lab = {}, {}
    t = tt(0.65)
    s["KICK"] = (sweep(t, 98, 54, 0.012) * ex(t, 0.24) + 0.25 * biquad(noise(len(t)), "lp", 3000) * ex(t, 0.0015))
    t = tt(0.06)
    s["RIM"] = (reso(t, 1700, 0.007) + 0.6 * reso(t, 500, 0.01)) * 1.0
    t = tt(0.24)
    s["SNARE"] = (0.8 * reso(t, 238, 0.05) + 0.4 * reso(t, 476, 0.03) +
                  0.9 * biquad(noise(len(t)), "hp", 1800) * ex(t, 0.055))
    t = tt(0.3)
    s["CLAP"] = biquad(noise(len(t)), "bp", 1100, 1.2) * bursts(t, [0, 0.0105, 0.021, 0.0315], 0.004, 0.08, 0.034) * 2.2
    t = tt(0.16)
    s["SNARE2"] = 0.5 * reso(t, 330, 0.02) + biquad(noise(len(t)), "hp", 2500) * ex(t, 0.035)
    for name, f in [("LO TOM", 98), ("MD TOM", 142), ("HI TOM", 200)]:
        t = tt(0.32)
        s[name] = sweep(t, f * 1.12, f, 0.04) * ex(t, 0.13) + 0.08 * biquad(noise(len(t)), "lp", 2000) * ex(t, 0.03)
    t = tt(0.07)
    m = biquad(biquad(metal(t), "bp", 7100, 1.0), "hp", 6000)
    s["CL HAT"] = m * ex(t, 0.012) * 3
    t = tt(0.45)
    s["OP HAT"] = biquad(biquad(metal(t), "bp", 7100, 1.0), "hp", 6000) * ex(t, 0.16) * 3
    t = tt(0.8)
    s["CRASH"] = (biquad(metal(t), "bp", 3500, 1.5) * 0.7 + biquad(metal(t), "hp", 6500) * 1.2) * ex(t, 0.38) * 2
    t = tt(0.55)
    s["RIDE"] = biquad(metal(t, [r * 1.5 for r in METAL808]), "bp", 4500, 2.0) * ex(t, 0.25) * 2.5
    lab["RIDE"] = "CYMBAL 2"
    t = tt(0.05)
    s["SHAKER"] = biquad(noise(len(t)), "hp", 5000) * ex(t, 0.012) * 1.5
    lab["SHAKER"] = "MARACA"
    t = tt(0.28)
    cb = biquad(sq(540, t) + sq(800, t), "bp", 700, 3.0)
    s["COWBEL"] = cb * (0.6 * ex(t, 0.008) + 0.5 * ex(t, 0.1)) * 3
    t = tt(0.07)
    s["CLAVE"] = reso(t, 2500, 0.016)
    t = tt(0.2)
    s["ZAP"] = sweep(t, 2400, 120, 0.03) * ex(t, 0.07)
    t = tt(0.12)
    s["BLIP"] = reso(t, 1046.5, 0.05)
    lab["BLIP"] = "HI CONGA"
    s["BLIP"] = sweep(t, 360, 330, 0.02) * ex(t, 0.06)
    t = tt(1.2)
    s["BOOM"] = sweep(t, 70, 49, 0.05) * ex(t, 0.55)
    lab["BOOM"] = "LONG 808"
    return s, lab, "Roland TR-808 model: bridged-T kick and toms, two-tone snare, six-square metal hats and cymbal"


def kit_909():
    s, lab = {}, {}
    t = tt(0.45)
    k = sweep(t, 260, 52, 0.011) * ex(t, 0.17)
    click = biquad(noise(len(t)), "hp", 1500) * ex(t, 0.002)
    s["KICK"] = np.tanh(1.8 * (k + 0.5 * click)) / np.tanh(1.8)
    t = tt(0.08)
    s["RIM"] = (reso(t, 220, 0.012) + reso(t, 500, 0.01) + 0.6 * biquad(noise(len(t)), "hp", 3000) * ex(t, 0.004))
    t = tt(0.3)
    s["SNARE"] = (0.7 * sweep(t, 220, 180, 0.01) * ex(t, 0.04) + 0.4 * sweep(t, 400, 330, 0.01) * ex(t, 0.03) +
                  1.0 * biquad(noise(len(t)), "hp", 1200) * ex(t, 0.1))
    t = tt(0.34)
    s["CLAP"] = biquad(noise(len(t)), "bp", 1400, 1.0) * bursts(t, [0, 0.008, 0.016, 0.024], 0.004, 0.12, 0.027) * 2.2
    t = tt(0.2)
    s["SNARE2"] = 0.5 * sweep(t, 260, 220, 0.01) * ex(t, 0.03) + biquad(noise(len(t)), "hp", 2000) * ex(t, 0.05)
    for name, f in [("LO TOM", 80), ("MD TOM", 118), ("HI TOM", 165)]:
        t = tt(0.36)
        s[name] = (sweep(t, f * 1.5, f, 0.03) * ex(t, 0.16) + 0.25 * biquad(noise(len(t)), "bp", 1200, 0.7) * ex(t, 0.05))
    hatm = [263, 400, 421, 474, 587, 845]
    t = tt(0.08)
    s["CL HAT"] = biquad(0.6 * noise(len(t)) + 0.5 * metal(t, hatm), "hp", 7000) * ex(t, 0.018) * 3
    t = tt(0.5)
    s["OP HAT"] = biquad(0.6 * noise(len(t)) + 0.5 * metal(t, hatm), "hp", 7000) * ex(t, 0.2) * 3
    t = tt(0.9)
    s["CRASH"] = biquad(0.8 * noise(len(t)) + 0.4 * metal(t, [f * 2.3 for f in hatm]), "hp", 3500) * ex(t, 0.4) * 1.6
    t = tt(0.7)
    ride = sum(np.sin(2 * np.pi * f * t) for f in [2450, 3130, 3700, 4400, 5200]) / 5
    s["RIDE"] = (0.8 * ride + 0.3 * biquad(noise(len(t)), "hp", 5000)) * ex(t, 0.35) * 1.5
    t = tt(0.06)
    s["SHAKER"] = biquad(noise(len(t)), "hp", 4000) * np.sin(np.pi * np.clip(t / 0.06, 0, 1)) ** 2
    t = tt(0.24)
    s["COWBEL"] = biquad(sq(562, t) + sq(845, t), "bp", 760, 2.5) * (0.6 * ex(t, 0.006) + 0.5 * ex(t, 0.08)) * 3
    t = tt(0.07)
    s["CLAVE"] = reso(t, 2200, 0.02)
    t = tt(0.16)
    s["ZAP"] = sweep(t, 3200, 200, 0.02) * ex(t, 0.05)
    t = tt(0.14)
    s["BLIP"] = biquad(noise(len(t)), "bp", 6000, 3) * ex(t, 0.05) * 3
    lab["BLIP"] = "TICK"
    t = tt(1.0)
    s["BOOM"] = np.tanh(2.5 * sweep(t, 120, 42, 0.06) * ex(t, 0.4)) / np.tanh(2.5)
    lab["BOOM"] = "DIST KICK"
    return s, lab, "Roland TR-909 model: swept, clicky kick; noisy snare; bright clap; metallic hats and cymbals"


def kit_cr78():
    s, lab = {}, {}
    t = tt(0.28)
    s["KICK"] = reso(t, 66, 0.11) + 0.4 * reso(t, 132, 0.03)
    t = tt(0.06)
    s["RIM"] = reso(t, 880, 0.012) + 0.5 * reso(t, 1760, 0.006)
    t = tt(0.22)
    s["SNARE"] = 0.6 * reso(t, 330, 0.035) + 0.3 * reso(t, 520, 0.02) + biquad(noise(len(t)), "bp", 3000, 0.8) * ex(t, 0.06) * 1.3
    t = tt(0.32)
    scr = np.zeros(len(t))
    for i, d in enumerate(np.arange(0, 0.22, 0.018)):
        j = (t >= d) & (t < d + 0.012)
        scr[j] = 1.0 - 0.3 * i / 12
    s["CLAP"] = biquad(noise(len(t)), "bp", 2500, 2.0) * scr * 2
    lab["CLAP"] = "GUIRO"
    t = tt(0.2)
    jing = sum(np.sin(2 * np.pi * f * t) for f in [4100, 5300, 6700]) / 3
    s["SNARE2"] = (biquad(noise(len(t)), "hp", 4000) * 0.7 + 0.6 * jing) * ex(t, 0.06)
    lab["SNARE2"] = "TAMBOURINE"
    for name, f, tau, nm in [("LO TOM", 180, 0.09, "LO CONGA"), ("MD TOM", 255, 0.08, "HI CONGA"), ("HI TOM", 420, 0.06, "BONGO")]:
        t = tt(0.2)
        s[name] = reso(t, f, tau) + 0.15 * reso(t, f * 2.1, tau / 3)
        lab[name] = nm
    t = tt(0.06)
    g = np.clip((0.035 - t) / 0.008, 0, 1)
    s["CL HAT"] = biquad(noise(len(t)), "hp", 6500) * g * 1.4
    t = tt(0.3)
    s["OP HAT"] = biquad(noise(len(t)), "hp", 6000) * ex(t, 0.11) * 1.4
    t = tt(0.7)
    s["CRASH"] = (biquad(noise(len(t)), "bp", 5000, 0.9) + 0.4 * metal(t, [450, 640, 870, 1150])) * ex(t, 0.3) * 1.3
    lab["CRASH"] = "CYMBAL"
    t = tt(0.4)
    s["RIDE"] = (0.5 * metal(t, [700, 1080, 1420]) + 0.5 * biquad(noise(len(t)), "hp", 5500)) * ex(t, 0.18)
    lab["RIDE"] = "METAL BEAT"
    t = tt(0.05)
    s["SHAKER"] = biquad(noise(len(t)), "hp", 5000) * np.sin(np.pi * np.clip(t / 0.05, 0, 1)) ** 2 * 1.4
    lab["SHAKER"] = "MARACA"
    t = tt(0.12)
    s["COWBEL"] = reso(t, 800, 0.05) + 0.5 * reso(t, 1210, 0.03)
    t = tt(0.07)
    s["CLAVE"] = reso(t, 2500, 0.018)
    t = tt(0.1)
    s["ZAP"] = reso(t, 1046, 0.03) * (t < 0.02) + reso(t, 1046, 0.03) * 0.3
    lab["ZAP"] = "TICK"
    t = tt(0.12)
    s["BLIP"] = reso(t, 1320, 0.03)
    lab["BLIP"] = "BELL"
    t = tt(0.4)
    s["BOOM"] = reso(t, 55, 0.2)
    lab["BOOM"] = "LONG KICK"
    return s, lab, "Roland CR-78 model: soft ringing kick, tuned congas / bongos, guiro and tambourine, gated hats"


def kit_chip_sq():
    s, lab = {}, {}
    t = tt(0.3)
    s["KICK"] = sweep(t, 320, 44, 0.018, "sq") * ex(t, 0.1)
    t = tt(0.04)
    s["RIM"] = sq(1400, t, 0.25) * ex(t, 0.008)
    t = tt(0.2)
    s["SNARE"] = 0.6 * sweep(t, 500, 180, 0.01, "pulse25") * ex(t, 0.02) + noise(len(t)) * ex(t, 0.06)
    t = tt(0.22)
    s["CLAP"] = noise(len(t)) * bursts(t, [0, 0.012, 0.024], 0.005, 0.06, 0.03) * 1.5
    t = tt(0.14)
    s["SNARE2"] = sweep(t, 900, 300, 0.008, "pulse25") * ex(t, 0.012) * 0.5 + noise(len(t)) * ex(t, 0.03)
    for name, f in [("LO TOM", 110), ("MD TOM", 165), ("HI TOM", 247)]:
        t = tt(0.22)
        s[name] = sweep(t, f * 2, f, 0.02, "sq") * ex(t, 0.08)
    t = tt(0.05)
    s["CL HAT"] = biquad(noise(len(t)), "hp", 5000) * ex(t, 0.01) * 2
    t = tt(0.28)
    s["OP HAT"] = biquad(noise(len(t)), "hp", 5000) * ex(t, 0.09) * 2
    t = tt(0.55)
    s["CRASH"] = noise(len(t)) * ex(t, 0.2)
    t = tt(0.35)
    s["RIDE"] = (0.5 * noise(len(t)) + 0.5 * sq(733, t) * sq(1033, t)) * ex(t, 0.14)
    t = tt(0.07)
    s["SHAKER"] = biquad(noise(len(t)), "hp", 4000) * np.sin(np.pi * np.clip(t / 0.07, 0, 1)) ** 2
    t = tt(0.16)
    s["COWBEL"] = (sq(587, t) + sq(880, t)) / 2 * ex(t, 0.06)
    t = tt(0.05)
    s["CLAVE"] = sq(1975, t) * ex(t, 0.012)
    t = tt(0.22)
    s["ZAP"] = sweep(t, 3000, 80, 0.045, "sq") * ex(t, 0.09)
    t = tt(0.12)
    arp = np.where(t < 0.04, 1046.5, np.where(t < 0.08, 1318.5, 1568.0))
    s["BLIP"] = np.where((np.cumsum(arp) / HI) % 1 < 0.5, 1.0, -1.0) * ex(t, 0.08)
    t = tt(0.5)
    s["BOOM"] = sweep(t, 140, 34, 0.09, "sq") * ex(t, 0.22)
    return s, lab, "Square and pulse waves with white noise: punchy and buzzy"


def kit_chip_lfsr():
    s, lab = {}, {}
    t = tt(0.32)
    s["KICK"] = sweep(t, 240, 40, 0.02, "tri4") * ex(t, 0.12) + 0.3 * lfsr_noise(t, 8000) * ex(t, 0.004)
    t = tt(0.04)
    s["RIM"] = lfsr_noise(t, 30000, short=True) * ex(t, 0.01)
    t = tt(0.22)
    s["SNARE"] = 0.5 * sweep(t, 380, 190, 0.012, "tri4") * ex(t, 0.03) + lfsr_noise(t, 20000) * ex(t, 0.07)
    t = tt(0.24)
    s["CLAP"] = lfsr_noise(t, 16000) * bursts(t, [0, 0.01, 0.02], 0.004, 0.07, 0.025) * 1.3
    t = tt(0.16)
    s["SNARE2"] = lfsr_noise(t, 12000, short=True) * ex(t, 0.04)
    lab["SNARE2"] = "METAL SNR"
    for name, f in [("LO TOM", 98), ("MD TOM", 147), ("HI TOM", 220)]:
        t = tt(0.24)
        s[name] = sweep(t, f * 1.8, f, 0.025, "tri4") * ex(t, 0.1)
    t = tt(0.05)
    s["CL HAT"] = lfsr_noise(t, 60000) * ex(t, 0.01)
    t = tt(0.3)
    s["OP HAT"] = lfsr_noise(t, 60000) * ex(t, 0.1)
    t = tt(0.6)
    s["CRASH"] = lfsr_noise(t, 40000) * ex(t, 0.22)
    t = tt(0.4)
    s["RIDE"] = lfsr_noise(t, 50000, short=True) * ex(t, 0.16)
    lab["RIDE"] = "METAL RIDE"
    t = tt(0.07)
    s["SHAKER"] = lfsr_noise(t, 50000) * np.sin(np.pi * np.clip(t / 0.07, 0, 1)) ** 2
    t = tt(0.16)
    s["COWBEL"] = lfsr_noise(t, 4096 * 2, short=True) * ex(t, 0.06)
    lab["COWBEL"] = "BUZZ BELL"
    t = tt(0.05)
    s["CLAVE"] = lfsr_noise(t, 5000, short=True) * ex(t, 0.015)
    lab["CLAVE"] = "BUZZ CLAVE"
    t = tt(0.25)
    s["ZAP"] = lfsr_noise(t, 3000, short=True) * ex(t, 0.08) * np.sign(np.sin(2 * np.pi * 30 * t) + 1.01)
    t = tt(0.12)
    s["BLIP"] = sweep(t, 1568, 1568, 1, "tri4") * ex(t, 0.06)
    t = tt(0.55)
    s["BOOM"] = sweep(t, 110, 36, 0.08, "tri4") * ex(t, 0.25)
    return s, lab, "The Game Boy's own sounds: stepped 4-bit triangles and its LFSR noise (long and short 'metallic' modes)"


# ------------------------------------------------------------------ the chains (at the Game Boy rate)
def to_gb(x):
    """anti-alias and resample 44.1 kHz -> 10923 Hz (524288/48 = 44100 * 4096/16537.5 ~)"""
    return resample_poly(x, 2048, 8269)          # 44100 * 2048 / 8269 = 10922.5 Hz


def normalize(x):
    m = np.max(np.abs(x))
    return x / m if m > 0 else x


def compressor(x, thresh_db=-18, ratio=6.0, att=0.002, rel=0.06, sr=GB):
    a_att, a_rel = np.exp(-1 / (att * sr)), np.exp(-1 / (rel * sr))
    env = 0.0
    out = np.empty_like(x)
    th = 10 ** (thresh_db / 20)
    for i, v in enumerate(x):
        a = abs(v)
        env = a_att * env + (1 - a_att) * a if a > env else a_rel * env + (1 - a_rel) * a
        g = 1.0 if env <= th else (th * (env / th) ** (1 / ratio)) / env
        out[i] = v * g
    return out


def quant4(x, dither=False):
    x = np.clip(x, -1, 1)
    v = (x + 1) * 7.5
    if dither:
        v = v + (rng.uniform(-0.5, 0.5, len(v)) + rng.uniform(-0.5, 0.5, len(v)))
    return np.clip(np.round(v), 0, 15).astype(np.uint8)


def trim_fade(q):
    """drop the tail once it stays within 1 step of the middle, fade the last 3 ms"""
    d = np.abs(q.astype(int) * 2 - 15)
    loud = np.nonzero(d > 2)[0]
    end = min(len(q), (loud[-1] + 1 + int(0.003 * GB)) if len(loud) else 1, MAXS)
    q = q[:end].astype(float)
    nf = min(len(q), int(0.003 * GB))
    if nf > 1:
        q[-nf:] = 7.5 + (q[-nf:] - 7.5) * np.linspace(1, 0, nf)
    q = np.round(q).astype(np.uint8)
    pad = (-len(q)) % 32                             # whole 32-sample chunks, as the ROM stores them
    return np.concatenate([q, np.full(pad, 8, np.uint8)])


def chain(x, kind):
    x = x - np.mean(x)
    if kind == "CLEAN":
        x = biquad(x, "hp", 40, sr=GB)
        return trim_fade(quant4(normalize(x)))
    if kind in ("LSDJ", "DITHER"):
        x = biquad(x, "hp", 70, sr=GB)
        x = biquad(x, "peak", 1500, 0.8, 4.0, sr=GB)
        x = normalize(x) * 10 ** (6 / 20)
        x = np.tanh(x) / np.tanh(10 ** (6 / 20))
        return trim_fade(quant4(np.clip(x, -1, 1), dither=(kind == "DITHER")))
    if kind == "SMASHED":
        x = biquad(x, "hp", 60, sr=GB)
        x = compressor(normalize(x))
        x = normalize(x) * 10 ** (12 / 20)
        return trim_fade(quant4(np.tanh(x) / np.tanh(10 ** (12 / 20))))
    raise ValueError(kind)


MAXS = 255 * 32                                       # the ROM's per-sound limit: 255 chunks (0.75 s)
CHAINS = ["CLEAN", "LSDJ", "SMASHED", "DITHER"]
