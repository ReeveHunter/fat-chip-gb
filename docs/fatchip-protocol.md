# Fat Chip GB ↔ Fat Chip 64: MIDI protocol (v0.16)

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

0. CC 113 = 64 + n (any channel) → the voices move to the controller's block of channels.
1. CC 102 = 70 → FAT CHIP profile (the header shows **FC**; the default CC map is forced).
2. CC 111 = 0 → panic (all voices off, bends reset, latch off).
3. CC 103 master tune, CC 104/105 warble, CC 107/108 tempo, then CC 109 downbeat on the next bar line.
4. Per voice: Program Change to pick its role patch, CC 7 level, and anything else the role needs.

## 3. Global CCs (102–119)

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
| 113 | Channels | **Heard on any channel** (v0.08), unlike the others: **64 + n** moves the five voices to channels n+1 … n+5 (n = 0–11, so 64 = 1–5, 74 = 11–15). Other values are ignored. Held notes stop if the block changes. Not saved to the cart. Fat Chip 64 sends it first at startup, so the Game Boy's own channel setting doesn't matter |
| 114 | Fat Chip sound | (v0.10) **n** = Fat Chip 64's built-in sound n (0–18): pulse 1, pulse 2 and the wave take that sound's settings and name, and the warble is set, exactly as if Fat Chip 64 had sent its CCs (the ROM keeps a copy of them, `src/gen/fcsounds.c`, made by Fat Chip 64's `tools/gen_gb_sounds.py`). Noise and drums are untouched. Values past the last sound are ignored. Fat Chip 64 sends it in place of about 45 CCs when a built-in sound is chosen and nothing in play changes it; afterwards, edits are CCs as usual. **64 + n** (v0.11) is a status, "Fat Chip 64 is on sound n" (64 + 63 = 127: a sound of its own, shown as CUSTOM): Fat Chip 64 sends it after a sound sent as CCs (so also at the end of its startup; Fat Chip 64 v0.50 also sent it every 2 s, dropped in v0.52 because the steady traffic blinked the Teensyboy Pro). The first one after the Game Boy powers on (before any CC 102 = 70 or CC 114 n) also sets the FAT CHIP profile and plays sound n, so a Game Boy switched on late joins in; after that it only names the cards and never reloads, so live edits stay |
| 115 | Tremolo depth | (v0.13) 0–15: how much of the master volume (NR50) the tremolo takes; 0 = off (full volume). No clicks: NR50 needs no retrigger |
| 116 | Tremolo shape | 0 TRI, 1 SINE, 2 SAW UP, 3 SAW DOWN, 4 SQUARE, 5 RANDOM, 6 PUMP (ducked at the cycle's start, swells back), 7–9 GATE X.X.XX.X / XX.XX.X. / X..X..X. (eight steps a cycle) |
| 117 | Tremolo sync | 0 FREE (CC 118/119), 1 1 BAR, 2 1/2, 3 1/4, 4 1/8 dotted, 5 1/8, 6 1/8T, 7 1/16, 8 1/16T, 9 1/32: from the tempo (CC 107/108); the downbeat (CC 109) puts the cycle back to its start (not 1/8 dotted, which doesn't divide a bar) |
| 118 / 119 | Tremolo rate | FREE: Hz × 100 as 14 bits, MSB then LSB (taken when the LSB arrives) |

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
| 74 | Timbre | 87 | Release drop: semitones (0–24, 0 off; v0.09) |
| 75 | Decay | 88 | Release drop time (0–127 → 16 steps) |
| 76 | LFO rate | 89 | BEND SHAPE (v0.12): +1 STEP, +2 CLICK SHORT / +4 LONG, +8 BEND IN × 2 (v0.16) (as it is) |
| | | 90 | EASED GLIDE frames (v0.14, as it is; 0 = the usual glide): Fat Chip 64's DRONE |
| | | 91 | LFO SYNC (v0.15, as it is): 0 FREE, 1–9 a division (as CC 117) from the tempo, back to its start on the downbeat |
| | | 94 | Fine detune (±50 cents) |
| | | 120/123 | All notes off |
| | | 121 | Reset bend |

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
