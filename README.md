# gbmidi (working title)

A MIDI sound module for the original Game Boy (DMG), in the spirit of
[mGB](https://github.com/trash80/mGB). Every sound channel is played live from
your DAW over an Arduinoboy, with no tracker. The wave channel has extra modes:
a morphing wavetable synth, dual-tone/chord waves, a sampled drum kit, and
LSDJ-style allophone speech you can sing with.

*Name TBD. Rename the repo/ROM whenever.*

```
 GBMIDI   MIDI SYNTH ♪
>1 PU1 LEAD 25   ▬▬▬
   25%            C4
 2 PU2 PLUCK     ▬
 3 WAV ACID SWP  ▬▬▬▬
   SYNTH ACID     C2
 4 NOI HAT
 5 DRM 808 KIT   ▬▬
```

## Quick start

1. Flash `gbmidi.gb` to your cart. It's MBC1 + 8 KB battery SRAM, 256 KB.
2. Set the Arduinoboy to **mGB mode** (mode 5 / LED 5). It forwards MIDI
   channels 1–5 to the Game Boy by default.
3. In Logic, point tracks at MIDI channels 1–5:

| MIDI ch | Game Boy voice |
|---|---|
| 1 | Pulse 1 (has hardware sweep) |
| 2 | Pulse 2 |
| 3 | Wave: Synth / Pulse / Tri / Dual / Drums / Speech / Sing modes |
| 4 | Noise |
| 5 | Drum kit (sampled, plays on the wave channel) |

Ch 3 and ch 5 share the wave hardware. A drum hit on ch 5 briefly takes over
the channel. When the sample ends, a note still held on ch 3 comes back. This
gives you a drum track and a wave-synth track at the same time, which is the
usual LSDJ trade-off.

> Tip: don't send MIDI clock to the Arduinoboy port. The Arduinoboy drops the
> byte after a real-time message, which can lose note velocities.

## Setup screen

Press **B** on the home screen. Changes are saved to the cart when you leave
the screen.

- **Channels:** each voice can listen on any MIDI channel 1–16,
or be set to **OFF**. **SHIFT ALL** moves the whole block of five at once
(1–5, 2–6, … 12–16). The home screen shows each voice's channel number.
- **Velocity:** LINEAR, SOFT (low velocities play louder), HARD (you have to
  dig in), or FIXED (every note at full level).
- **Screen off:** press A to switch the LCD off, which removes the faint LCD
  buzz on a DMG and saves battery. The synth keeps running normally. Press any
  button to wake the screen.
- **MIDI monitor:** press A to see the last 12 messages as they arrive. It
  shows channel, type, note or value, and which voice (if any) is listening,
  plus the raw bytes and a message counter. Use it to check the Arduinoboy link
  before blaming anything else.

Two or more voices on the **same channel play together** (layering). For
example, put Pulse 1 and Pulse 2 on one channel and detune one of them for a
fat unison lead, or stack Pulse + Tri for a thick bass.

> **With an Arduinoboy, leave these at 1–5.** The Arduinoboy's mGB mode
> doesn't pass MIDI channels through. It picks the five channels set in its own
> configuration and always renumbers them 1–5 before they reach the Game Boy.
> To move the Game Boy to, say, MIDI 6–10, change the mGB channels in the
> Arduinoboy (Arduinoboy Editor or its config SysEx). The in-ROM map is for
> adapters that pass channels straight through, and for layering or
> switching voices off.

## Controls on the Game Boy

**Home screen**: one card per channel, with patch name, live level meter, and
the note currently playing.

| Button | Action |
|---|---|
| Up / Down | choose channel |
| Left / Right | step to previous / next saved patch (instant) |
| A | edit the channel's parameters |
| SELECT | patch browser (load / save / name) |
| START (hold) | audition the channel without MIDI |
| B | setup: MIDI channels, velocity curve, screen off, MIDI monitor |
| SELECT + B | copy the selected channel's sound |
| SELECT + A | paste it onto the selected channel |
| SELECT + START | panic: every voice off, bends reset (works on any screen) |

SELECT on its own acts when you *release* it, so it can double as a modifier.

Copy and paste between the two pulses copies everything. Between different
voice types (say Pulse → Wave) it copies the shared settings (envelope, glide,
LFO, pitch envelope and so on) and keeps the target's own shape and mode.

**Edit screen**: a scrolling parameter list. The bottom line shows the CC
number for the highlighted parameter, so you can map it in Logic.

| Button | Action |
|---|---|
| Up / Down | move |
| Left / Right | change value |
| hold A + Left / Right | big steps (an octave for note parameters) |
| B | back |
| SELECT | patch browser |

Only the parameters that apply are listed. For example, PHONEME appears only in
Sing mode, and SWEEP only on Pulse 1.

**Patch browser**: 16 slots per voice type (pulse, wave, noise, drum). Both
pulse channels share the same bank. **A** loads a slot. **SELECT** saves the
current sound to that slot and opens the namer. **B** goes back.

**Namer**: an on-screen keyboard. **A** types a character, **B** deletes,
**START** saves, **SELECT** cancels.

Patches live in battery SRAM. On first boot the bank is filled with factory
presets.

## MIDI implementation

Notes, velocity, pitch bend, sustain (CC64) and Program Change work on every
channel. **Program Change n** loads saved slot *n* (0–15) for that channel.
CC 120/123 is all-notes-off and CC 121 resets bend. Mono voices use
last-note priority: release the top note and the previous held note returns
without a retrigger.

Every parameter below is also a CC. The same CC number means the same idea on
every channel. CCs edit the live sound (the screen updates too), and SELECT →
save stores it.

| CC | Parameter | Pulse | Wave | Noise | Drum (ch5) |
|---|---|---|---|---|---|
| 1 | LFO depth (mod wheel) | ✓ | ✓ | ✓ | |
| 5 | Glide time | ✓ | ✓ | ✓ | |
| 7 | Level | ✓ | ✓ | ✓ | ✓ |
| 10 | Pan (L / C / R) | ✓ | ✓ | ✓ | ✓ |
| 70 | Shape | duty 12.5/25/50/75% | wave shape · duty in Pulse · chord in Dual | width long/short | kit (808 / CHIP) |
| 71 | Mode | | Synth · Pulse · Tri · Dual · Drums · Speech · Sing | | |
| 72 | Release (0 = cut) | ✓ | ✓ | ✓ | |
| 73 | Attack (0 = instant) | ✓ | ✓ | ✓ | |
| 74 | Timbre | | morph step / chord timbre / speech speed | | pitch ±12 |
| 75 | Decay (0 = hold) | ✓ | ✓ | ✓ | |
| 76 | LFO rate (0.08–24 Hz) | ✓ | ✓ | ✓ | |
| 77 | LFO wave: tri, saw↓, saw↑, square, random | ✓ | ✓ | ✓ | |
| 78 | LFO destination | pitch / duty / pan | pitch / timbre (PWM in Pulse) / pan | pitch / pan | |
| 79 | LFO delay (fade-in after note) | ✓ | ✓ | ✓ | |
| 80 | Pitch envelope amount (±24 semitones, 64 = off) | ✓ | ✓ | ✓ | |
| 81 | Pitch envelope time | ✓ | ✓ | ✓ | |
| 82 | Sweep (hardware, pulse 1 only) | ✓ | | | |
| 83 | Drum split: notes below this play drums (value = note, 0 = off) | | ✓ | | |
| 84 | Speech pitch (value = note) | | ✓ | | |
| 85 | Pitch-bend range (0–24 semitones) | ✓ | ✓ | ✓ | |
| 86 | Phoneme for Sing mode (value = index) | | ✓ | | |
| 94 | Fine detune (±50 cents) | ✓ | ✓ | | |
| 68 | Legato on/off (≥64 = on) | ✓ | ✓ | ✓ | |

**Legato** is saved per patch. When it's on, a note played while another is
still held changes the pitch without restarting the envelope (it glides if
GLIDE is set), which is good for acid lines and smooth leads.

Scaled CCs map 0–127 across the parameter's range. CCs 83, 84 and 86 take the
value directly.

### Wave modes (CC71)

- **Synth**: 16 wave shapes, each a 16-step morph table swept by **Timbre**
  (CC74). An LFO aimed at *timbre* gives LSDJ-style PWM and filter sweeps.
  Shapes: PULSE (PWM), SAW LP, SQR LP, ACID (resonant), FOLD, ORGAN (drawbars),
  SYNC, FM 1:1, FM 1:2, VOX (vowel morph), PHASE, RING, CRUSH, NOISE, MORPH
  (sine→tri→saw→square), HARM (single harmonic).
- **Pulse**: the wave channel becomes a third pulse ("PU3"). **Shape** (CC70)
  picks the duty with the same ranges as the pulse channels: 12.5 / 25 / 50 /
  75 %. Set the LFO destination to *timbre* (shown as PWM) for smooth pulse-width
  modulation through 16 widths, which the real pulse channels can't do.
- **Tri**: a plain 4-bit stepped triangle, the classic chiptune bass and lead
  tone. It has no shape or timbre settings.
- **Dual**: chord waves built from simple integer ratios. **Shape** (CC70)
  picks the interval and **Timbre** picks the tone, from sine to square. The
  note you play is the root. Intervals: octave, 12th, 2 octaves, fifth, fourth,
  maj 3rd, min 3rd, maj 6th, min 7th, power (1-5-8), major triad (4:5:6),
  "minor~" (6:7:9, a bluesy septimal minor), sus4, dom7 (4:5:6:7), octave
  stack, major+octave. A true 10:12:15 minor triad doesn't fit in 32 samples,
  hence the "~".
- **Drums**: the whole keyboard plays the drum kit, with the same map as ch 5.
- **Speech**: each note is one allophone (map below), spoken at **Speech
  pitch** (CC84). Pitch bend and the LFO give it intonation. **Timbre** sets
  the talking speed. Vowels, nasals and fricatives sustain while the key is
  held, so you sequence words in the piano roll.
- **Sing**: the note sets the pitch and **Phoneme** (CC86) picks the sound, so
  the Game Boy can sing a melody on "AA", "OO", "MM" and so on.

**Drum split** (CC83) works in Synth, Dual, Speech and Sing. Notes below the
split note play drums (using the ch 5 kit settings) and notes above play the
synth.

### Drum map (ch 5, wave Drums mode, and below the split)

| Note | Sound | Note | Sound |
|---|---|---|---|
| 35, 36 | Kick | 48, 50 | High tom |
| 37 | Rim | 49, 57 | Crash |
| 38 | Snare | 51, 53, 59 | Ride |
| 39 | Clap | 54, 69, 70 | Shaker |
| 40 | Snare 2 | 56 | Cowbell |
| 41, 43 | Low tom | 75–77 | Clave |
| 42, 44 | Closed hat | 60 | Zap |
| 45, 47 | Mid tom | 61 | Blip |
| 46 | Open hat | 62 | Boom (long sub) |

There are two kits, **808** and **CHIP** (crunchy, square-based), selected by
CC70 on ch 5. Samples are 4-bit at ~10.9 kHz and were synthesized from scratch
by `tools/gen_drums.py`, so there are no third-party samples. CC74 on ch 5
repitches the kit by ±12 semitones.

### Allophones (Speech mode: note → sound)

| Note | # | Sound | as in |
|---|---|---|---|
| C2 (36) | 0 | IY | beet |
| C#2 (37) | 1 | IH | bit |
| D2 (38) | 2 | EH | bet |
| D#2 (39) | 3 | AE | bat |
| E2 (40) | 4 | AA | father |
| F2 (41) | 5 | AO | bought |
| F#2 (42) | 6 | UH | book |
| G2 (43) | 7 | UW | boot |
| G#2 (44) | 8 | AH | but |
| A2 (45) | 9 | ER | bird |
| A#2 (46) | 10 | AX | about |
| B2 (47) | 11 | EY | bait |
| C3 (48) | 12 | AY | bite |
| C#3 (49) | 13 | OW | boat |
| D3 (50) | 14 | AW | bout |
| D#3 (51) | 15 | OY | boy |
| E3 (52) | 16 | W | wet |
| F3 (53) | 17 | Y | yes |
| F#3 (54) | 18 | R | red |
| G3 (55) | 19 | L | let |
| G#3 (56) | 20 | M | man |
| A3 (57) | 21 | N | no |
| A#3 (58) | 22 | NG | sing |
| B3 (59) | 23 | S | sit |
| C4 (60) | 24 | SH | shoe |
| C#4 (61) | 25 | F | fan |
| D4 (62) | 26 | TH | thin |
| D#4 (63) | 27 | HH | hat |
| E4 (64) | 28 | Z | zoo |
| F4 (65) | 29 | ZH | measure |
| F#4 (66) | 30 | V | van |
| G4 (67) | 31 | DH | this |
| G#4 (68) | 32 | P | pat |
| A4 (69) | 33 | T | tap |
| A#4 (70) | 34 | K | cat |
| B4 (71) | 35 | B | bat |
| C5 (72) | 36 | D | dog |
| C#5 (73) | 37 | G | go |
| D5 (74) | 38 | CH | chin |
| D#5 (75) | 39 | JH | jam |
| E5 (76) | 40 | -- | (short pause) |
Example: "hello" = HH EH L OW = D#4, D2, G3, C#3 (notes 63, 38, 55, 49).

## How it works (and the DMG caveats)

- **MIDI in:** the serial interrupt stores each byte in a 256-byte ring
  buffer. The main loop parses it, including running status. The protocol is
  the plain MIDI stream the Arduinoboy's mGB mode sends.
- **Wave channel on a DMG:** wave RAM can only be rewritten safely with the
  channel's DAC switched off, so every reload goes DAC off → copy 16 bytes →
  DAC on → retrigger. Each reload makes a small click. You hear it on note-ons,
  when an LFO sweeps timbre, and at the ~60 Hz speech frame rate. LSDJ's wave
  synth and speech have the same character.
- **Drums** stream 32-sample chunks from ROM using a timer interrupt, the same
  approach LSDJ kits use.
- **Speech** is formant synthesis: each allophone is a sequence of
  single-cycle waveforms generated by `tools/gen_speech.py`. There are two
  sets, tuned for low and high voices, and the engine picks one from the
  pitch. Unvoiced sounds (s, sh, f, bursts) play at a fixed high rate with
  noise-shaped spectra.
- **Pulse/noise envelopes** use the hardware envelope. The engine tracks the
  level in software so attack→decay and release can take over from wherever
  the sound currently is.
- Everything is written to finish quickly so the serial interrupt is never
  held off long. The Arduinoboy sends a byte every 500 µs.

## Building

Needs [GBDK-2020](https://github.com/gbdk-2020/gbdk-2020/releases) 4.3+ and
Python 3 with numpy (plus Pillow for the preview images).

```sh
make GBDK_HOME=/path/to/gbdk          # builds gbmidi.gb
make gen                              # regenerate tables/samples/speech only
```

The generated C in `src/gen/` is checked in, so Python is only needed if you
change a generator.

| Path | What |
|---|---|
| `src/main.c` | init, main loop, MIDI parser |
| `src/synth.c` | sound engine: voices, envelopes, LFOs, wave modes, drum streaming, speech |
| `src/isr.s` | serial + timer interrupts, DMG-safe wave RAM loader |
| `src/params.c` | parameter ranges + CC map (shared by MIDI and UI) |
| `src/ui.c` | screens, input, incremental redraw (bank 1) |
| `src/patches.c` | SRAM patch storage, factory presets (bank 1) |
| `tools/gen_*.py` | generate pitch tables, wave shapes, drum kits, speech frames, font |
| `test/` | PyBoy emulator tests that inject MIDI into the serial interrupt (`test_engine.py`, `test_channels.py`, `test_live.py`) |

### Testing in an emulator

```sh
pip install pyboy numpy
python3 test/test_engine.py     # pitch/register/feature checks, writes test/out/*.wav
python3 test/demo_song.py       # renders test/out/demo.wav
```

PyBoy's unplugged link port always reads 0xFF, so the harness hooks the serial
interrupt and substitutes the MIDI bytes. Real-hardware timing still needs a
real Game Boy.

## Credits

- Inspired by [mGB](https://github.com/trash80/mGB) and
  [Arduinoboy](https://github.com/trash80/Arduinoboy) by Timothy Lamb (trash80).
  No mGB code is used.
- Font: [font8x8](https://github.com/dhepper/font8x8) by Daniel Hepper
  (public domain), thinned for the DMG screen.
- Built with [GBDK-2020](https://github.com/gbdk-2020/gbdk-2020).
