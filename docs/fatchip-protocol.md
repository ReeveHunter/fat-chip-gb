# Fat Chip GB ↔ Fat Chip 64: MIDI protocol (v0.07)

This is the contract a Fat Chip controller (Fat Chip 64, or a future web controller) uses to drive Fat Chip GB. Everything here is plain channel MIDI: tested on Reeve's rig (Teensyboy Pro, mGB mode, DMG), the link passes notes, CCs, pitch bend and program change, but **not MIDI clock and not SysEx**.

## 1. Channels

| Voice | Default channel | Notes |
|---|---|---|
| Pulse 1 | 1 | Hardware sweep |
| Pulse 2 | 2 | |
| Wave | 3 | Synth / Pulse / Tri / Dual / Drums / Speech / Sing (CC71) |
| Noise | 4 | |
| Drums | 5 | Sample kit on the wave channel (takes it over briefly) |

- Each voice is **mono**. In the DAW profile: last-note priority. In the FAT CHIP profile a note-on replaces the voice's note outright (no held-note stack), so a lost note-off can't resurface later. Several voices can share a channel (unison layers).
- Channels are set on the Game Boy (Setup). Fat Chip 64's Game Boy profile must use the same block; default base channel 1. (The MidiNES usually sits on 2–6, so Reeve will move one of them; keep the base configurable on both sides.)
- **Use a channel the adapter passes.** A Teensyboy Pro in mGB mode did not pass channel 16. Its firmware (an Arduinoboy fork) maps MIDI channels to Game Boy channels; the default map is 1–15 → 1–15, and it forwards **every** mapped channel, the MidiNES's too, so NES traffic shares the Game Boy link's budget (§6).

## 2. Startup / resync sequence

The link is one-way, so the controller can't ask the Game Boy anything. Send this **at startup and on every panic**, on the Pulse 1 channel (any voice's channel works):

1. CC 102 = 70 → FAT CHIP profile (the header shows **FC**; the default CC map is forced).
2. CC 111 = 0 → panic (all voices off, bends reset, latch off).
3. CC 103 master tune, CC 104/105 warble, CC 107/108 tempo, then CC 109 downbeat on the next bar line.
4. Per voice: Program Change to pick its role patch, CC 7 level, and anything else the role needs.

## 3. Global CCs (102–112)

Accepted on **any channel a voice listens to**, applied once to every voice. In the DAW profile they work too (they're undefined CCs in General MIDI), and they can't be learned onto parameters.

| CC | Name | Values |
|---|---|---|
| 102 | Profile | 70 (`F`) = FAT CHIP, 68 (`D`) = DAW; anything else is ignored |
| 103 | Master tune | 64 = 0; each step = 0.78 cents; 0 → −50 c, 127 → +49 c. Synthcart match: **19 (−35 c)** |
| 104 | Warble depth | 0 = off … 127 = ±50 cents. Each pitched voice (pulses, wave) drifts to its own random targets, so voices wander apart: tape wow and fatness |
| 105 | Warble speed | 0 = slow (~2 s per drift) … 127 = fast (~4 frames) |
| 106 | *(reserved: glitch amount)* | not implemented yet |
| 107 | Tempo MSB | Tempo = **BPM × 32** as 14 bits (MSB = bits 7–13) |
| 108 | Tempo LSB | Bits 0–6; the new tempo applies when the LSB arrives. 120 BPM = 3840 → MSB 30, LSB 0. Synthcart 149.81 BPM = 4794 → MSB 37, LSB 58 |
| 109 | Downbeat | Any value: "beat 1 of a bar is now". Resets the Game Boy's clock phase. Send once per bar; it corrects drift |
| 110 | Latch | ≥ 64 = hold every voice's notes after note-off (like sustain on all voices); < 64 releases them |
| 111 | Panic | Any value: all voices off, bends reset, latch off |
| 112 | Display | 0 = screen on, 1 = screen off (no LCD buzz; the synth keeps running). Fat Chip 64 sends it when its own video mode changes. Values 2+ reserved (visualizer) |

The Game Boy's tempo clock runs at 24 steps per beat from its frame rate (59.73 Hz on a DMG; with the screen off it paces from the DIV timer at ~59.80 Hz, 0.1% fast), so the once-per-bar downbeat matters. Nothing uses the clock yet except the beat blink in the home header; the arpeggiator and glitch will.

## 4. Per-voice CCs

In the FAT CHIP profile the map is fixed to these defaults (same CC = same idea on every voice). Full ranges are in the README's MIDI implementation table.

| CC | Parameter | CC | Parameter |
|---|---|---|---|
| 1 | LFO depth | 77 | LFO wave |
| 5 | Glide | 78 | LFO destination |
| 7 | Level | 79 | LFO delay |
| 10 | Pan | 80 | Pitch envelope amount |
| 64 | Sustain | 81 | Pitch envelope time |
| 68 | Legato | 82 | Sweep (pulse 1) |
| 70 | Shape (duty / wave / chord / kit) | 83 | Drum split note |
| 71 | Wave mode | 84 | Speech pitch |
| 72 | Release | 85 | Bend range (0–24) |
| 73 | Attack | 86 | Phoneme (sing mode) |
| 74 | Timbre | 94 | Fine detune (±50 cents) |
| 75 | Decay | 120/123 | All notes off |
| 76 | LFO rate | 121 | Reset bend |

Program Change n (0–15) loads that voice's saved slot n.

## 5. Pitch and tuning

- Pitch bend per voice, range set by CC 85 (default 2 semitones). With range 2, one bend unit is 1/256 semitone internally, far finer than the hardware.
- The **hardware** is the limit: a Game Boy pulse at A4 (440 Hz) moves in steps of about 6 cents (A2 ≈ 1.5 cents, A5 ≈ 12 cents). The engine rounds to the nearest step. For just intonation and fine tuning, the Game Boy is best below about A4; give very high, finely tuned parts to the SID.
- All pitch offsets (bend, detune, master tune, warble, glide, pitch envelope) are summed in 8.8 semitones and converted once.

## 6. Bandwidth (measured)

On Reeve's Teensyboy Pro, **1 message per 2 ms sustained arrived clean; 1 per 1 ms lost messages** (the adapter's buffer overflows; the Game Boy itself keeps up at twice the link rate). Rules for the controller:

- Budget ~500 messages/s to the Game Boy; plan for ~400.
- Queue Game Boy-bound messages separately and drain them no faster than the budget.
- Coalesce bends and CCs (only the latest value per voice/CC is worth sending).
- Spread a chord's note-ons a couple of ms apart.
- Use running status.
- Let the Game Boy do motion locally (warble, LFOs, and later arps and glitch) rather than streaming it.

## 7. What not to send

- **No SysEx**: the adapter drops F0/F7 but can leak the data bytes, which could be misread as notes.
- **No MIDI clock / start / stop**: stripped by the adapter; use CC 107–109.
- No CC 102 values other than 70/68 (reserved for future profiles).
