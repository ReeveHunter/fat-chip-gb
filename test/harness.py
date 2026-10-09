"""Emulator test harness: feeds MIDI bytes into the serial port the way an
Arduinoboy does, and records audio / screenshots / registers.

    from harness import GB
    gb = GB("gbmidi.gb")
    gb.midi(0x90, 60, 100); gb.run(30); gb.midi(0x80, 60, 0)
    gb.save_wav("out.wav")
"""
import os
import re
import wave
import warnings

import numpy as np

warnings.filterwarnings("ignore")
from pyboy import PyBoy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_symbols(noifile):
    syms = {}
    for line in open(noifile):
        m = re.match(r"DEF (\S+) 0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return syms


class GB:
    def __init__(self, rom, sram=None):
        self.rom = rom
        ram = None
        if sram is not None:
            import io
            ram = io.BytesIO(sram)
        self.pb = PyBoy(rom, window="null", sound_emulated=True, sound_sample_rate=48000,
                        cgb=False, no_input=False, ram_file=ram)
        self.pb.set_emulation_speed(0)
        self.sym = load_symbols(os.path.splitext(rom)[0] + ".noi")
        self.queue = []
        self.audio = []
        isr = self.sym["_sio_isr"]
        # PyBoy's unplugged link port always reads 0xFF, so we hook the ISR right
        # after it reads SB and substitute the MIDI byte into register A.
        self.pb.hook_register(0, isr + 14, self._in_isr, None)
        self.busy = False
        self.cur = None

    # ---------------------------------------------------------------- serial feed
    def _kick(self):
        if self.queue:
            self.cur = self.queue.pop(0)
            self.pb.memory[0xFF0F] = self.pb.memory[0xFF0F] | 0x08
            self.busy = True
        else:
            self.busy = False

    def _in_isr(self, ctx):
        if self.cur is not None:
            self.pb.register_file.A = self.cur
            self.cur = None
        self._kick()

    def midi(self, *data):
        self.queue.extend(data)
        if not self.busy:
            self._kick()

    def note(self, ch, n, vel=100):
        self.midi(0x90 | ch, n, vel)

    def off(self, ch, n):
        self.midi(0x80 | ch, n, 0)

    def cc(self, ch, c, v):
        self.midi(0xB0 | ch, c, v)

    def pc(self, ch, p):
        self.midi(0xC0 | ch, p)

    def bend(self, ch, v):
        self.midi(0xE0 | ch, v & 0x7F, (v >> 7) & 0x7F)

    # ---------------------------------------------------------------- run / capture
    def run(self, frames=1):
        for _ in range(frames):
            self.pb.tick(1, True, True)
            s = self.pb.sound.ndarray
            self.audio.append(np.array(s, dtype=np.int16).reshape(-1, 2).copy())

    def press(self, button, frames=3):
        self.pb.button_press(button)
        self.run(frames)
        self.pb.button_release(button)
        self.run(2)

    def mem(self, addr):
        return self.pb.memory[addr]

    def var(self, name, n=1):
        a = self.sym[name]
        return [self.pb.memory[a + i] for i in range(n)] if n > 1 else self.pb.memory[a]

    def regs(self):
        return {name: self.pb.memory[a] for name, a in [
            ("NR10", 0xFF10), ("NR11", 0xFF11), ("NR12", 0xFF12), ("NR13", 0xFF13), ("NR14", 0xFF14),
            ("NR21", 0xFF16), ("NR22", 0xFF17), ("NR23", 0xFF18), ("NR24", 0xFF19),
            ("NR30", 0xFF1A), ("NR32", 0xFF1C), ("NR33", 0xFF1D), ("NR34", 0xFF1E),
            ("NR42", 0xFF21), ("NR43", 0xFF22), ("NR44", 0xFF23), ("NR50", 0xFF24),
            ("NR51", 0xFF25), ("NR52", 0xFF26)]}

    def wave_ram(self):
        return [self.pb.memory[0xFF30 + i] for i in range(16)]

    def clear_audio(self):
        self.audio = []

    def samples(self):
        if not self.audio:
            return np.zeros((0, 2))
        return np.concatenate(self.audio).astype(np.float32)

    def save_wav(self, path):
        s = self.samples()
        m = np.abs(s).max() or 1
        d = (s / m * 28000).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(d.tobytes())

    def screenshot(self, path):
        self.pb.screen.image.save(path)

    def sram(self):
        return bytes(self.pb.memory[0, 0xA000:0xC000]) if False else None

    def stop(self):
        self.pb.stop(save=False)


def pitch_hz(samples, sr=48000):
    """Dominant frequency of a mono signal via autocorrelation-ish FFT peak."""
    x = samples - samples.mean()
    if np.abs(x).max() < 1e-6:
        return 0.0
    n = 1 << int(np.ceil(np.log2(len(x) * 4)))
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec[freqs < 30] = 0
    # harmonic product spectrum for robustness
    hps = spec.copy()
    for k in (2, 3):
        dec = spec[::k]
        hps[:len(dec)] *= dec
    return freqs[np.argmax(hps[: len(spec) // 3])]
