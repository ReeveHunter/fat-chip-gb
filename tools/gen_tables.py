#!/usr/bin/env python3
"""Generate pitch/noise/LFO tables (bank 0) and wave-synth shape tables (bank 2).

Outputs:
  src/gen/tables.c   - small engine tables, fixed bank
  src/gen/waves.c    - 16 morphing shapes x 16 steps, 16 dual-tone intervals x 16 timbres
  src/gen/names.c    - display names for shapes / intervals (UI bank)
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from cgen import c_array, c_strings, header, pack_nibbles, quantize4  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "src", "gen")
os.makedirs(OUT, exist_ok=True)

N = 32  # wave RAM samples
DRUM_T = 48  # drum sample rate = 524288 / DRUM_T Hz
t = np.arange(N) / N  # one cycle, phase 0..1


def midi_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# ---------------------------------------------------------------- engine tables
def period_table():
    # Pulse channel: f = 131072 / (2048 - x).  We store P = 131072/f (the "period").
    # Wave channel uses P/2.  Values > 2047 can't be played and are clamped in code.
    return [min(65535, int(round(131072 / midi_hz(n)))) for n in range(128)]


def noise_table():
    # Noise clock = 524288 / r / 2^(s+1), r = 0.5 for code 0.
    opts = []
    for s in range(14):
        for r in range(8):
            rr = 0.5 if r == 0 else r
            f = 524288 / rr / 2 ** (s + 1)
            opts.append((f, (s << 4) | r))
    # map MIDI 0..127 onto clock = 524288 * 2^((n-127)/12) (highest note = brightest)
    tbl = []
    for n in range(128):
        target = 524288 * 2 ** ((n - 127) / 12)
        best = min(opts, key=lambda o: abs(math.log(o[0] / target)))
        tbl.append(best[1])
    return tbl


def scale_lut():
    # scale_lut[amp*16 + s]: shrink sample s (0..15) toward the middle by amp/15
    out = []
    for amp in range(16):
        for s in range(16):
            v = 7.5 + (s - 7.5) * amp / 15.0
            out.append(int(round(v)) if amp else 8)
    return [min(15, max(0, v)) for v in out]


def lfo_rates():
    # 32 rates, 0.08 Hz .. 24 Hz, phase is 16-bit, ticked at 59.73 Hz
    out = []
    for i in range(32):
        f = 0.08 * (24 / 0.08) ** (i / 31)
        out.append(max(1, min(65535, int(round(f * 65536 / 59.73)))))
    return out


def lfo_depth_pitch():
    # LFO pitch depth in 1/16 semitone per full-scale (+-128) LFO output.
    # depth 0..31 -> 0 .. 12 semitones (192), curved for fine vibrato at low values
    return [int(round(192 * (d / 31) ** 2.2)) if d else 0 for d in range(32)]


def glide_frac():
    # fraction (/256) of remaining distance covered per tick; 0 = off
    out = [0]
    for g in range(1, 16):
        out.append(max(3, int(round(256 * 0.6 ** (g * 0.55)))))
    return out


def drum_ticks():
    # timer reload (16384 Hz clock) per drum pitch -12..+12 semitones; base 48 = 10923 Hz
    return [max(20, min(255, int(round(DRUM_T * 2 ** (-(p - 12) / 12))))) for p in range(25)]


def penv_coef():
    # pitch-envelope decay coefficient /256 per tick, time 0..15 (0 = very short)
    return [int(round(256 * math.exp(-1.0 / (1.5 * 1.35 ** i)))) for i in range(16)]


# ---------------------------------------------------------------- wave shapes
def additive(amps, phases=None):
    y = np.zeros(N)
    for h, a in enumerate(amps, start=1):
        if a == 0:
            continue
        ph = 0 if phases is None else phases[h - 1]
        y += a * np.sin(2 * np.pi * h * t + ph)
    return y


def norm(y):
    y = np.asarray(y, dtype=float)
    y = y - (y.max() + y.min()) / 2
    m = np.abs(y).max()
    return y / m if m > 1e-9 else y


def lpf_resp(h, cutoff, q):
    # 2-pole resonant low-pass magnitude at harmonic h for cutoff (in harmonics)
    w = h / cutoff
    return 1.0 / math.sqrt((1 - w * w) ** 2 + (w / q) ** 2)


def saw_amps(n=16):
    return [((-1) ** (h + 1)) / h for h in range(1, n + 1)]


def sqr_amps(n=16):
    return [(1 / h if h % 2 else 0) for h in range(1, n + 1)]


def tri_wave(ph):
    ph = ph % 1.0
    return np.where(ph < 0.5, 4 * ph - 1, 3 - 4 * ph)


def shape_steps():
    shapes = []
    names = []

    # 0 PULSE: width 1/32 .. 16/32
    names.append("PULSE")
    shapes.append([np.where(np.arange(N) < (i + 1), 1.0, -1.0) for i in range(16)])

    # 1 SAW low-pass sweep
    names.append("SAW LP")
    st = []
    for i in range(16):
        c = 0.8 * (18 / 0.8) ** (i / 15)
        st.append(additive([a * lpf_resp(h, c, 1.2) for h, a in enumerate(saw_amps(), 1)]))
    shapes.append(st)

    # 2 SQUARE low-pass sweep
    names.append("SQR LP")
    st = []
    for i in range(16):
        c = 0.8 * (18 / 0.8) ** (i / 15)
        st.append(additive([a * lpf_resp(h, c, 1.2) for h, a in enumerate(sqr_amps(), 1)]))
    shapes.append(st)

    # 3 ACID: saw with strong resonance
    names.append("ACID")
    st = []
    for i in range(16):
        c = 1.0 * (14 / 1.0) ** (i / 15)
        st.append(additive([a * lpf_resp(h, c, 5.0) for h, a in enumerate(saw_amps(), 1)]))
    shapes.append(st)

    # 4 FOLD: wavefolded triangle
    names.append("FOLD")
    st = []
    for i in range(16):
        g = 1 + i * 0.45
        y = tri_wave(t + 0.25) * g
        y = np.sin(np.pi / 2 * y)  # sine folder
        st.append(y)
    shapes.append(st)

    # 5 ORGAN: drawbars added one by one
    names.append("ORGAN")
    bars = [1, 2, 3, 4, 6, 8, 5, 10, 12, 16]
    st = []
    for i in range(16):
        amps = [0] * 16
        k = 1 + i * (len(bars) - 1) / 15
        for j, h in enumerate(bars):
            w = min(1.0, max(0.0, k - j))
            amps[h - 1] += w * (0.9 ** j)
        st.append(additive(amps))
    shapes.append(st)

    # 6 SYNC: hard sync saw, ratio 1..5
    names.append("SYNC")
    st = []
    for i in range(16):
        r = 1 + i * 4 / 15
        st.append(2 * ((t * r) % 1.0) - 1)
    shapes.append(st)

    # 7 FM 1:1
    names.append("FM 1:1")
    shapes.append([np.sin(2 * np.pi * t + (i * 0.45) * np.sin(2 * np.pi * t)) for i in range(16)])

    # 8 FM 1:2
    names.append("FM 1:2")
    shapes.append([np.sin(2 * np.pi * t + (i * 0.4) * np.sin(4 * np.pi * t)) for i in range(16)])

    # 9 VOX: vowel morph oo-oh-ah-eh-ee (formants evaluated at 150 Hz harmonics)
    names.append("VOX")
    vowels = [(300, 870, 2240), (500, 900, 2400), (730, 1090, 2440), (530, 1840, 2480), (270, 2290, 3010)]
    st = []
    for i in range(16):
        p = i / 15 * (len(vowels) - 1)
        a, b = int(math.floor(p)), min(len(vowels) - 1, int(math.floor(p)) + 1)
        fr = p - a
        F = [vowels[a][k] * (1 - fr) + vowels[b][k] * fr for k in range(3)]
        st.append(formant_wave(150, F, [80, 100, 140], [1.0, 0.6, 0.3]))
    shapes.append(st)

    # 10 PHASE: saw minus phase-shifted saw (PWM of saws)
    names.append("PHASE")
    st = []
    for i in range(16):
        d = (i + 1) / 34
        s1 = 2 * (t % 1.0) - 1
        s2 = 2 * ((t + d) % 1.0) - 1
        st.append(s1 - s2 + 0.3 * s1)
    shapes.append(st)

    # 11 RING: sine x sine at harmonic k
    names.append("RING")
    shapes.append([np.sin(2 * np.pi * t) * np.sin(2 * np.pi * (i + 1) * t) + 0.25 * np.sin(2 * np.pi * t)
                   for i in range(16)])

    # 12 CRUSH: sine quantized to fewer levels / samples
    names.append("CRUSH")
    st = []
    for i in range(16):
        levels = max(2, 16 - i)
        hold = 1 + i // 4
        y = np.sin(2 * np.pi * (np.floor(np.arange(N) / hold) * hold) / N)
        y = np.round((y + 1) / 2 * (levels - 1)) / (levels - 1) * 2 - 1
        st.append(y)
    shapes.append(st)

    # 13 NOISE: 16 seeded random waves (metallic / percussive)
    names.append("NOISE")
    rng = np.random.default_rng(80)
    st = []
    for i in range(16):
        y = rng.uniform(-1, 1, N)
        # smooth progressively less (darker -> brighter)
        k = max(1, 6 - i // 3)
        y = np.convolve(np.tile(y, 3), np.ones(k) / k, mode="same")[N:2 * N]
        st.append(y)
    shapes.append(st)

    # 14 MORPH: sine -> triangle -> saw -> square
    names.append("MORPH")
    shapes.append([morph_wave(i / 15) for i in range(16)])

    # 15 HARM: single harmonic h = 1..16 with a little fundamental
    names.append("HARM")
    shapes.append([np.sin(2 * np.pi * (i + 1) * t) + (0.35 * np.sin(2 * np.pi * t) if i else 0)
                   for i in range(16)])

    assert len(shapes) == 16
    return shapes, names


def morph_wave(x):
    """x 0..1: sine -> tri -> saw -> square."""
    sine = np.sin(2 * np.pi * t)
    tri = tri_wave(t + 0.25)
    saw = 2 * ((t + 0.5) % 1.0) - 1
    sqr = np.where(t < 0.5, 1.0, -1.0)
    seq = [sine, tri, saw, sqr]
    p = x * 3
    a = min(2, int(p))
    f = p - a
    return seq[a] * (1 - f) + seq[a + 1] * f


def formant_wave(f0, F, BW, A):
    amps = []
    for h in range(1, 17):
        fh = h * f0
        a = 0.0
        for Fi, Bi, Ai in zip(F, BW, A):
            a += Ai / math.sqrt(1 + ((fh - Fi) / (Bi / 2)) ** 2)
        a *= 1.0 / math.sqrt(h)  # glottal tilt
        amps.append(a)
    return additive(amps, phases=[-math.pi / 2] * 16)


# ---------------------------------------------------------------- dual tone
DUALS = [
    ("OCTAVE", [1, 2]),
    ("12TH", [1, 3]),
    ("2 OCT", [1, 4]),
    ("FIFTH", [2, 3]),
    ("FOURTH", [3, 4]),
    ("MAJ 3", [4, 5]),
    ("MIN 3", [5, 6]),
    ("MAJ 6", [3, 5]),
    ("MIN 7", [4, 7]),
    ("POWER", [2, 3, 4]),
    ("MAJOR", [4, 5, 6]),
    ("MINOR~", [6, 7, 9]),
    ("SUS 4", [6, 8, 9]),
    ("DOM 7", [4, 5, 6, 7]),
    ("OCTS", [1, 2, 4]),
    ("MAJ+8", [4, 5, 6, 8]),
]


def comp_wave(x, ph):
    """timbre 0..1 morph sine->tri->saw->square, evaluated at phases ph (cycles)."""
    ph = ph % 1.0
    sine = np.sin(2 * np.pi * ph)
    tri = tri_wave(ph + 0.25)
    saw = 2 * ((ph + 0.5) % 1.0) - 1
    sqr = np.where(ph < 0.5, 1.0, -1.0)
    seq = [sine, tri, saw, sqr]
    p = x * 3
    a = min(2, int(p))
    f = p - a
    return seq[a] * (1 - f) + seq[a + 1] * f


def dual_steps():
    out = []
    for name, ratios in DUALS:
        steps = []
        for i in range(16):
            y = np.zeros(N)
            for r in ratios:
                # weight the root a little louder so the pitch reads clearly
                w = 1.25 if r == ratios[0] else 1.0
                y += w * comp_wave(i / 15, t * r)
            steps.append(y)
        out.append(steps)
    return out


def to_bytes(wave):
    return pack_nibbles(quantize4(norm(wave)))


def main():
    # ---- engine tables (bank 0)
    src = header()
    src += c_array("period_tbl", period_table(), "uint16_t", 8, "{:5d}")
    src += c_array("noise_tbl", noise_table())
    src += c_array("scale_lut", scale_lut(), per_line=16, fmt="{:2d}")
    src += c_array("lfo_rate_tbl", lfo_rates(), "uint16_t", 8, "{:5d}")
    src += c_array("lfo_depth_tbl", lfo_depth_pitch(), fmt="{:3d}")
    src += c_array("glide_tbl", glide_frac(), fmt="{:3d}")
    src += c_array("drum_tick_tbl", drum_ticks(), fmt="{:3d}")
    src += c_array("penv_tbl", penv_coef(), fmt="{:3d}")
    src += c_array("dual_mult_tbl", [r[0] for _, r in DUALS], fmt="{:d}")
    open(os.path.join(OUT, "tables.c"), "w").write(src)

    # ---- wave data (bank 2)
    shapes, names = shape_steps()
    flat = []
    for st in shapes:
        for w in st:
            flat += to_bytes(w)
    dflat = []
    for st in dual_steps():
        for w in st:
            dflat += to_bytes(w)
    src = header(2)
    src += c_array("shape_waves", flat)
    src += c_array("dual_waves", dflat)
    open(os.path.join(OUT, "waves.c"), "w").write(src)

    # ---- names (UI bank 1)
    src = header(1)
    src += c_strings("shape_names", names, 6)
    src += c_strings("dual_names", [n for n, _ in DUALS], 6)
    open(os.path.join(OUT, "names.c"), "w").write(src)

    # preview image for humans
    try:
        from PIL import Image
        img = Image.new("L", (16 * 34, 32 * 18), 0)
        px = img.load()
        for si, st in enumerate(shapes + dual_steps()):
            for k, w in enumerate(st):
                q = quantize4(norm(w))
                for x in range(32):
                    y = 15 - q[x]
                    px[k * 34 + x, si * 18 + y] = 255
        img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
        img.save(os.path.join(os.path.dirname(__file__), "..", "docs", "waves_preview.png"))
    except ImportError:
        pass
    print("tables ok")


if __name__ == "__main__":
    main()
