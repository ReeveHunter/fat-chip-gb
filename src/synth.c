/* Fat Chip GB sound engine (fixed bank 0) */
#include <string.h>
#include "engine.h"

voice_t voice[NUM_VOICES];
uint8_t patch[NUM_VOICES][PATCH_SIZE];
uint8_t patch_slot[NUM_VOICES];
uint8_t wave_owner;
uint8_t ui_dirty_params;

static uint8_t nr51_shadow;
static uint8_t wave_vol_out;   /* last NR32 code written by the synth side */
static uint8_t rnd_state = 0x5A;
static uint8_t tick_count;

/* Fat Chip globals */
uint8_t profile = PROFILE_DAW;
int16_t master_tune;
uint8_t tune_cc = 64, warble_amt, warble_spd = 40, latch;
uint16_t tempo32, clock24;
uint8_t beat_flash;
static uint8_t tempo_msb, beat_sub;
static uint32_t clock_acc;
uint8_t learn_voice = NO_NOTE, learn_param, learn_done;

/* warble: each pitched voice drifts toward its own random target, so voices
   wander apart like tape wow (that's the fatness). 8.8 semitone units. */
static int16_t wb_cur[3], wb_step[3];
static uint8_t wb_left[3];

#define REG(a) (*(volatile uint8_t *)(a))

/* per-voice register bases (pulse 1, pulse 2, -, noise) */
static const uint16_t env_reg[4] = { 0xFF12, 0xFF17, 0xFF1C, 0xFF21 };

static uint8_t rand8(void) {
    uint8_t x = rnd_state;
    x ^= x << 3;
    x ^= x >> 5;
    x ^= x << 1;
    if (!x) x = 0xA7;
    rnd_state = x;
    return x;
}

void bank_copy16(uint8_t bank, const uint8_t *src, uint8_t *dst) {
    uint8_t save = _current_bank;
    uint8_t i;
    SWITCH_ROM(bank);
    for (i = 0; i < 16; i++) dst[i] = src[i];
    SWITCH_ROM(save);
}

static uint8_t bank_read8(uint8_t bank, const uint8_t *src) {
    uint8_t save = _current_bank;
    uint8_t r;
    SWITCH_ROM(bank);
    r = *src;
    SWITCH_ROM(save);
    return r;
}

/* ------------------------------------------------------------------ pitch */
/* 8.8 semitone pitch -> pulse "period" (131072/f). Low notes fold up an octave
   until playable. */
static uint16_t pitch_to_period(int16_t p) {
    uint8_t n, f;
    uint16_t a, d;
    if (p < 0) p = 0;
    if (p > (127 << 8)) p = (127 << 8);
    n = (uint8_t)(p >> 8);
    f = (uint8_t)p;
    a = period_tbl[n];
    if (f && n < 127) {
        d = a - period_tbl[n + 1];
        /* round to the nearest period step (matters for fine tuning) */
        if (d < 256) a -= (d * f + 128) >> 8;
        else a -= ((d >> 4) * f + 8) >> 4;
    }
    return a;
}

static int16_t lfo_pitch_ofs(voice_t *vo, uint8_t depth) {
    return ((int16_t)vo->lfo_out * (int16_t)lfo_depth_tbl[depth]) >> 3;
}

static int16_t voice_pitch(uint8_t v) {
    voice_t *vo = &voice[v];
    uint8_t *pp = patch[v];
    int16_t p = vo->pitch + vo->bend + vo->penv;
    if (voice_type[v] != VT_NOISE) {
        p += ((int16_t)pp[P_DETUNE] - 32) << 2;
        p += master_tune;
        if (v < 3) p += wb_cur[v];
    }
    if (pp[P_LFO_DEST] == LD_PITCH && pp[P_LFO_DEPTH]) p += lfo_pitch_ofs(vo, pp[P_LFO_DEPTH]);
    return p;
}

static uint8_t vel_vol(uint8_t vel, uint8_t level) {
    uint16_t v = (((uint16_t)(vel >> 3) + 1) * ((uint16_t)level + 1)) >> 4;
    if (v > 15) v = 15;
    if (!v && vel && level) v = 1;
    return (uint8_t)v;
}

/* ------------------------------------------------------------------ envelope estimator */
static uint8_t env_step(voice_t *vo, uint8_t period) {
    uint16_t lim;
    if (!period) return 0;
    vo->env_acc += 275; /* 64 Hz hardware envelope clock / 59.73 Hz tick, x256 */
    lim = (uint16_t)period << 8;
    if (vo->env_acc >= lim) {
        vo->env_acc -= lim;
        return 1;
    }
    return 0;
}

static void hw_trigger(uint8_t v) {
    if (v == V_NOI) {
        REG(0xFF23) = 0x80;
    } else {
        uint16_t x = 2048 - voice[v].out_period;
        REG(env_reg[v] + 2) = 0x80 | (uint8_t)(x >> 8);
    }
}

static void hw_env(uint8_t v, uint8_t vol, uint8_t up, uint8_t period) {
    REG(env_reg[v]) = (vol << 4) | (up ? 0x08 : 0) | period;
}

/* ------------------------------------------------------------------ wave helpers */
static uint8_t wave_amp;

static void scale_wave_buf(uint8_t amp) {
    uint8_t i, b;
    const uint8_t *row;
    if (amp >= 15) return;
    row = &scale_lut[(uint16_t)amp << 4];
    for (i = 0; i < 16; i++) {
        b = wave_buf[i];
        wave_buf[i] = (row[b >> 4] << 4) | row[b & 15];
    }
}

/* PULSE mode: SHAPE 0-15 in four duty zones, like CC70 on the pulse channels */
static const uint8_t pulse_step[4] = { 3, 7, 15, 7 }; /* 12.5%, 25%, 50%, 75% (= inverted 25%) */
#define TRI_SHAPE 14 /* MORPH: step 5 is an exact triangle */
#define TRI_STEP 5

static uint8_t wave_timbre(void) {
    uint8_t *pp = patch[V_WAV];
    uint8_t mode = pp[P_MODE];
    int16_t t;
    if (mode == WM_TRI) return TRI_STEP;
    t = (mode == WM_PULSE) ? pulse_step[pp[P_SHAPE] >> 2] : pp[P_TIMBRE];
    if (pp[P_LFO_DEST] == LD_TIMBRE && pp[P_LFO_DEPTH])
        t += ((int16_t)voice[V_WAV].lfo_out * pp[P_LFO_DEPTH]) >> 8;
    if (t < 0) t = 0;
    if (t > 15) t = 15;
    return (uint8_t)t;
}

static void wave_set_freq_regs(uint16_t w) {
    uint16_t x = 2048 - w;
    wv_nr33 = (uint8_t)x;
    wv_nr34 = (uint8_t)(x >> 8);
}

/* wave-channel period for the current pitch (multiplied for dual-tone) */
static uint16_t wave_period(void) {
    uint8_t *pp = patch[V_WAV];
    uint16_t w = pitch_to_period(voice_pitch(V_WAV)) >> 1;
    uint8_t m = 1;
    if (pp[P_MODE] == WM_DUAL) m = dual_mult_tbl[pp[P_SHAPE] & 15];
    while (m > 1 && !(m & 1)) { /* powers of two: cheap */
        w <<= 1;
        m >>= 1;
    }
    if (m > 1) {
        while (w > 2047 / m) w >>= 1;
        w *= m;
    }
    while (w > 2047) w >>= 1;
    if (w < 1) w = 1;
    return w;
}

static uint8_t wave_vol_code(uint8_t e) {
    if (e >= 11) return 1;
    if (e >= 6) return 2;
    if (e >= 2) return 3;
    return 0;
}

static void wave_set_vol(uint8_t code) {
    if (code != wave_vol_out) {
        wave_vol_out = code;
        NR32_REG = code << 5;
    }
}

static void wave_load_synth(void) {
    voice_t *vo = &voice[V_WAV];
    uint8_t *pp = patch[V_WAV];
    uint8_t t = wave_timbre();
    uint8_t mode = pp[P_MODE];
    uint8_t shape = pp[P_SHAPE] & 15;
    const uint8_t *src = (mode == WM_DUAL) ? dual_waves : shape_waves;
    if (mode == WM_PULSE) shape = 0;      /* PULSE table: width (step+1)/32 */
    else if (mode == WM_TRI) shape = TRI_SHAPE;
    src += (((uint16_t)shape << 4) + t) << 4;
    bank_copy16(WAVES_BANK, src, wave_buf);
    scale_wave_buf(wave_amp);
    vo->out_period = wave_period();
    wave_set_freq_regs(vo->out_period);
    wave_commit();
    vo->out_timbre = t;
}

/* ------------------------------------------------------------------ speech */
#define UNVOICED_W 64 /* 2097152 / 64 = 32768 Hz sample rate */
static uint8_t phon_meta;

static void speech_vol(void) {
    voice_t *vo = &voice[V_WAV];
    uint8_t code = phon_meta & 3;
    if (code) {
        if (vo->env_vol < 11) code++;
        if (vo->env_vol < 6) code++;
        if (vo->env_vol < 2 || code > 3) code = 0;
    }
    wave_set_vol(code);
}

static void speech_load_frame(void) {
    voice_t *vo = &voice[V_WAV];
    uint16_t fi = speech_start[vo->phon] + vo->phon_frame;
    if (vo->phon_set) fi += SPEECH_SET_FRAMES;
    bank_copy16(SPEECH_BANK, speech_frames + (fi << 4), wave_buf);
    phon_meta = bank_read8(SPEECH_BANK, speech_meta + fi);
    scale_wave_buf(wave_amp);
    if (phon_meta & 0x80) {
        vo->out_period = UNVOICED_W;
    } else {
        vo->out_period = wave_period();
    }
    wave_set_freq_regs(vo->out_period);
    wave_commit();
    speech_vol();
}

static void speech_start_phoneme(uint8_t ph) {
    voice_t *vo = &voice[V_WAV];
    if (ph >= SPEECH_PHONEMES) ph = SPEECH_PHONEMES - 1;
    vo->phon = ph;
    vo->phon_pos = 0;
    vo->phon_frame = 0;
    vo->phon_set = (voice_pitch(V_WAV) >= (51 << 8)) ? 1 : 0;
    speech_load_frame();
}

static void speech_tick(void) {
    voice_t *vo = &voice[V_WAV];
    uint8_t f, cnt, hold;
    if (vo->phon == 0xFF) return;
    vo->phon_pos += 128 + ((uint16_t)patch[V_WAV][P_TIMBRE] << 4);
    f = vo->phon_pos >> 8;
    cnt = speech_count[vo->phon];
    if (f >= cnt) {
        hold = speech_hold[vo->phon];
        if (hold != 0xFF && vo->env_stage != ENV_IDLE) {
            uint8_t span = cnt - hold;
            f = hold + (uint8_t)((f - hold) % span);
            vo->phon_pos = ((uint16_t)f << 8) | (vo->phon_pos & 0xFF);
        } else {
            wave_set_vol(0);
            vo->phon = 0xFF;
            vo->env_stage = ENV_IDLE;
            vo->env_vol = 0;
            return;
        }
    }
    if (f != vo->phon_frame) {
        vo->phon_frame = f;
        speech_load_frame();
    } else {
        speech_vol();
        if (!(phon_meta & 0x80)) {
            uint16_t w = wave_period();
            if (w != vo->out_period) {
                vo->out_period = w;
                wave_set_freq_regs(w);
                NR33_REG = wv_nr33;
                NR34_REG = wv_nr34;
            }
        }
    }
}

/* ------------------------------------------------------------------ drums (sample stream) */
static void stream_stop(void) {
    st_active = 0;
    st_done = 0;
}

static void drum_hit(uint8_t note, uint8_t vel) {
    uint8_t *dp = patch[V_DRM];
    uint8_t slot = drum_note_map[note & 127];
    uint8_t idx, t, lvl, code, save, i;
    const uint8_t *src;
    uint16_t x;
    if (slot == 0xFF) return;
    idx = dp[P_SHAPE] * DRUM_SLOTS + slot;
    t = drum_tick_tbl[dp[P_TIMBRE] > 24 ? 24 : dp[P_TIMBRE]];
    lvl = vel_vol(vel, dp[P_LEVEL]);
    code = wave_vol_code(lvl);
    if (!code) return;
    x = 2048 - ((uint16_t)t << 2);

    __critical {
        st_active = 0;
        st_done = 0;
        st_nr34 = 0x80 | (uint8_t)(x >> 8);
        src = (const uint8_t *)drum_ptr[idx];
        save = _current_bank;
        SWITCH_ROM(drum_bank[idx]);
        NR30_REG = 0;
        for (i = 0; i < 16; i++) AUD3WAVE[i] = src[i];
        SWITCH_ROM(save);
        NR30_REG = 0x80;
        NR32_REG = code << 5;
        wave_vol_out = 0xFF; /* synth side must rewrite when it resumes */
        NR33_REG = (uint8_t)x;
        NR34_REG = st_nr34;
        st_bank = drum_bank[idx];
        st_ptr = (uint8_t *)(src + 16);
        st_left = drum_len[idx] - 1;
        TMA_REG = (uint8_t)(256 - t);
        TIMA_REG = (uint8_t)(256 - t);
        if (st_left) st_active = 1;
        else st_done = 1;
    }
    wave_owner = WO_DRUM;
    voice[V_DRM].meter = (vel >> 3) | 1;
}

/* called from the main loop when a sample ends */
void stream_finished(void) {
    voice_t *vo = &voice[V_WAV];
    uint8_t mode = patch[V_WAV][P_MODE];
    if (st_active) return;
    wave_owner = WO_NONE;
    if (vo->env_stage != ENV_IDLE && vo->note != NO_NOTE) {
        wave_owner = WO_SYNTH;
        wave_vol_out = 0xFF;
        vo->out_pan = 0xFF;
        if (mode == WM_SPEECH || mode == WM_SING) {
            if (vo->phon != 0xFF) speech_load_frame();
        } else if (mode != WM_DRUMS) {
            wave_load_synth();
            wave_set_vol(wave_vol_code(vo->env_vol));
        }
    } else {
        NR32_REG = 0;
        wave_vol_out = 0;
    }
}

/* ------------------------------------------------------------------ note start / stop */
static void hold_push(voice_t *vo, uint8_t n) {
    uint8_t i, j;
    for (i = 0; i < vo->nheld; i++) {
        if (vo->held[i] == n) {
            for (j = i; j + 1 < vo->nheld; j++) vo->held[j] = vo->held[j + 1];
            vo->nheld--;
            break;
        }
    }
    if (vo->nheld == 8) {
        for (j = 0; j < 7; j++) vo->held[j] = vo->held[j + 1];
        vo->nheld = 7;
    }
    vo->held[vo->nheld++] = n;
}

static void hold_remove(voice_t *vo, uint8_t n) {
    uint8_t i, j;
    for (i = 0; i < vo->nheld; i++) {
        if (vo->held[i] == n) {
            for (j = i; j + 1 < vo->nheld; j++) vo->held[j] = vo->held[j + 1];
            vo->nheld--;
            return;
        }
    }
}

static void pulse1_sweep(uint8_t s) {
    uint8_t r = 0;
    if (s >= 1 && s <= 7) {
        r = ((8 - s) << 4) | 0x08 | 2; /* pitch falls; higher = faster */
    } else if (s >= 8) {
        uint8_t k = s - 7, tm = (k >= 8) ? 1 : 9 - k;
        if (tm > 7) tm = 7;
        r = (tm << 4) | 2; /* pitch rises */
    }
    NR10_REG = r;
}

static void start_note(uint8_t v, uint8_t note, uint8_t vel, uint8_t retrig) {
    voice_t *vo = &voice[v];
    uint8_t *pp = patch[v];
    uint8_t type = voice_type[v];
    uint8_t mode = pp[P_MODE];
    int16_t base;
    uint8_t was_playing = (vo->env_stage != ENV_IDLE);

    vo->note = note;
    vo->vel = vel;
    vo->gate = 1;
    vo->sus_off = 0;

    if (type == VT_WAVE && mode == WM_SPEECH) base = (int16_t)pp[P_SPEECH_PITCH] << 8;
    else base = (int16_t)note << 8;

    vo->target = base;
    if (!(pp[P_GLIDE] && (was_playing || !retrig))) vo->pitch = base;
    if (!retrig) return; /* legato return to an older held note: pitch only */

    vo->penv = ((int16_t)pp[P_PENV_AMT] - 24) << 8;
    vo->lfo_phase = 0x4000;
    vo->lfo_wait = pp[P_LFO_DELAY] << 3;
    vo->env_acc = 0;
    vo->out_period = 0xFFFF;

    if (type == VT_WAVE) {
        stream_stop();
        wave_owner = WO_SYNTH;
        wave_amp = vel_vol(vel, pp[P_LEVEL]);
        vo->out_pan = 0xFF;
        if (pp[P_ATTACK]) {
            vo->env_vol = 0;
            vo->env_stage = ENV_ATTACK;
        } else {
            vo->env_vol = 15;
            vo->env_stage = ENV_DECAY;
        }
        wave_vol_out = 0xFF;
        if (mode == WM_SPEECH || mode == WM_SING) {
            uint8_t ph = (mode == WM_SING) ? pp[P_PHONEME] : (uint8_t)(note - SPEECH_NOTE_BASE);
            if (mode == WM_SPEECH && note < SPEECH_NOTE_BASE) ph = 0;
            speech_start_phoneme(ph);
        } else {
            wave_load_synth();
            wave_set_vol(wave_vol_code(vo->env_vol));
        }
        return;
    }

    /* pulse / noise: hardware envelope */
    {
        uint8_t vol = vel_vol(vel, pp[P_LEVEL]);
        int16_t p = voice_pitch(v);
        if (type == VT_NOISE) {
            int16_t n = (p + 128) >> 8;
            if (n < 0) n = 0;
            if (n > 127) n = 127;
            NR41_REG = 0;
            NR43_REG = noise_tbl[n] | (pp[P_SHAPE] ? 0x08 : 0);
            vo->out_period = (uint16_t)n | (pp[P_SHAPE] ? 0x100 : 0);
        } else {
            uint16_t per = pitch_to_period(p);
            while (per > 2047) per >>= 1;
            vo->out_period = per;
            REG(env_reg[v] - 1) = (pp[P_SHAPE] & 3) << 6; /* duty, length 0 */
            vo->out_duty = pp[P_SHAPE] & 3;
            REG(env_reg[v] + 1) = (uint8_t)(2048 - per);
            if (v == V_PU1) pulse1_sweep(pp[P_SWEEP]);
        }
        vo->env_target = vol;
        if (pp[P_ATTACK]) {
            vo->env_vol = 0;
            vo->env_stage = ENV_ATTACK;
            hw_env(v, 0, 1, pp[P_ATTACK]);
        } else {
            vo->env_vol = vol;
            vo->env_stage = ENV_DECAY;
            hw_env(v, vol, 0, pp[P_DECAY] ? pp[P_DECAY] : 0);
        }
        hw_trigger(v);
    }
}

static void release_voice(uint8_t v) {
    voice_t *vo = &voice[v];
    uint8_t *pp = patch[v];
    uint8_t rel = pp[P_RELEASE];
    vo->gate = 0;
    if (vo->env_stage == ENV_IDLE) return;
    if (voice_type[v] == VT_WAVE) {
        if (!rel) {
            vo->env_stage = ENV_IDLE;
            vo->env_vol = 0;
            vo->phon = 0xFF;
            if (wave_owner == WO_SYNTH) wave_set_vol(0);
        } else {
            vo->env_stage = ENV_RELEASE;
            vo->env_acc = 0;
        }
        return;
    }
    if (!rel || !vo->env_vol) {
        REG(env_reg[v]) = 0; /* DAC off: silent immediately */
        vo->env_stage = ENV_IDLE;
        vo->env_vol = 0;
    } else {
        hw_env(v, vo->env_vol, 0, rel);
        hw_trigger(v);
        vo->env_stage = ENV_RELEASE;
        vo->env_acc = 0;
    }
}

static uint8_t wave_note_is_drum(uint8_t note) {
    uint8_t *pp = patch[V_WAV];
    if (pp[P_MODE] == WM_DRUMS) return 1;
    return (pp[P_SPLIT] && note < pp[P_SPLIT]);
}

void note_on(uint8_t v, uint8_t note, uint8_t vel) {
    voice_t *vo;
    if (v >= NUM_VOICES) return;
    if (!vel) {
        note_off(v, note);
        return;
    }
    if (v == V_DRM) {
        drum_hit(note, vel);
        return;
    }
    if (v == V_WAV && wave_note_is_drum(note)) {
        drum_hit(note, vel);
        return;
    }
    vo = &voice[v];
    {
        uint8_t mode = patch[v][P_MODE];
        uint8_t legato = patch[v][P_LEGATO] && vo->nheld && vo->env_stage != ENV_IDLE &&
                         !(v == V_WAV && (mode == WM_SPEECH || mode == WM_SING));
        hold_push(vo, note);
        start_note(v, note, vel, !legato);
    }
}

void note_off(uint8_t v, uint8_t note) {
    voice_t *vo;
    if (v >= V_DRM) return;
    if (v == V_WAV && wave_note_is_drum(note)) return;
    vo = &voice[v];
    hold_remove(vo, note);
    if (note != vo->note) return;
    if (vo->nheld) {
        start_note(v, vo->held[vo->nheld - 1], vo->vel, 0);
        return;
    }
    if (vo->sustain || latch) {
        vo->sus_off = 1;
        return;
    }
    release_voice(v);
}

/* Latch: like sustain on every voice at once. */
void latch_set(uint8_t on) {
    uint8_t v;
    latch = on;
    if (on) return;
    for (v = 0; v < V_DRM; v++) {
        voice_t *vo = &voice[v];
        if (vo->sus_off && !vo->sustain && !vo->nheld) {
            vo->sus_off = 0;
            release_voice(v);
        }
    }
}

void global_cc(uint8_t cc, uint8_t val) {
    switch (cc) {
    case GCC_PROFILE:
        if (val == PROFILE_F) profile = PROFILE_FATCHIP;
        else if (val == PROFILE_D) profile = PROFILE_DAW;
        break;
    case GCC_TUNE:
        tune_cc = val;
        master_tune = ((int16_t)val - 64) << 1; /* 1 step = 0.78 cents */
        break;
    case GCC_WARBLE: warble_amt = val; break;
    case GCC_WSPEED: warble_spd = val; break;
    case GCC_TEMPO_MSB: tempo_msb = val; break;
    case GCC_TEMPO_LSB:
        tempo32 = ((uint16_t)tempo_msb << 7) | val;
        break;
    case GCC_DOWNBEAT:
        clock24 = 0;
        beat_sub = 0;
        clock_acc = 0;
        beat_flash = 6;
        break;
    case GCC_LATCH: latch_set(val >= 64); break;
    case GCC_PANIC:
        latch_set(0);
        panic_all();
        break;
    }
}

void all_notes_off(uint8_t v) {
    voice_t *vo = &voice[v];
    vo->nheld = 0;
    vo->sustain = 0;
    vo->sus_off = 0;
    if (v == V_DRM || (v == V_WAV && wave_owner == WO_DRUM)) {
        stream_stop();
        NR32_REG = 0;
        wave_vol_out = 0;
        wave_owner = WO_NONE;
        if (v == V_DRM) return;
    }
    if (vo->env_stage != ENV_IDLE) {
        uint8_t rel = patch[v][P_RELEASE];
        patch[v][P_RELEASE] = 0;
        release_voice(v);
        patch[v][P_RELEASE] = rel;
    }
    vo->note = NO_NOTE;
}

/* ------------------------------------------------------------------ CC / bend */
static void recalc_bend(uint8_t v) {
    voice_t *vo = &voice[v];
    vo->bend = (int16_t)(((int32_t)((int16_t)vo->bend_raw - 8192) * patch[v][P_BEND]) >> 5);
}

void pitch_bend(uint8_t v, uint16_t val) {
    if (v >= V_DRM) return;
    voice[v].bend_raw = val;
    recalc_bend(v);
}

void param_set(uint8_t v, uint8_t p, uint8_t val) {
    uint8_t old = patch[v][p];
    patch[v][p] = val;
    ui_dirty_params |= (uint8_t)(1 << v);
    if (p == P_BEND) recalc_bend(v);
    else if (p == P_MODE && old != val && v == V_WAV) all_notes_off(V_WAV);
}

void control_change(uint8_t v, uint8_t cc, uint8_t val) {
    uint8_t p, max, t;
    voice_t *vo = &voice[v];
    if (v >= NUM_VOICES) return;
    if (cc == 64) {
        vo->sustain = (val >= 64);
        if (!vo->sustain && !latch && vo->sus_off && !vo->nheld) {
            vo->sus_off = 0;
            release_voice(v);
        }
        return;
    }
    if (cc == 120 || cc == 123) {
        all_notes_off(v);
        return;
    }
    if (cc == 121) {
        vo->bend_raw = 8192;
        vo->bend = 0;
        return;
    }
    t = voice_type[v];
    for (p = 0; p < NUM_PARAMS; p++) {
        if (cc_for(p) != cc) continue;
        max = param_max[t][p];
        if (max == NA) return;
        if (param_direct[p]) val = (val > max) ? max : val;
        else val = (uint8_t)(((uint16_t)val * (max + 1)) >> 7);
        param_set(v, p, val);
        return;
    }
}

void voice_refresh(uint8_t v) {
    voice_t *vo = &voice[v];
    vo->out_period = 0xFFFF;
    vo->out_pan = 0xFF;
    vo->out_duty = 0xFF;
    vo->out_timbre = 0xFF;
    if (v < V_DRM) recalc_bend(v);
    ui_dirty_params |= (uint8_t)(1 << v);
}

/* ------------------------------------------------------------------ per-tick */
static void lfo_tick(voice_t *vo, uint8_t *pp) {
    uint16_t old = vo->lfo_phase;
    uint8_t ph;
    int8_t out;
    vo->lfo_phase += lfo_rate_tbl[pp[P_LFO_RATE]];
    ph = vo->lfo_phase >> 8;
    switch (pp[P_LFO_SHAPE]) {
    case LFO_TRI: out = (ph < 128) ? (int8_t)(ph * 2 - 128) : (int8_t)(127 - (ph - 128) * 2); break;
    case LFO_SAWD: out = (int8_t)(127 - ph); break;
    case LFO_SAWU: out = (int8_t)(ph - 128); break;
    case LFO_SQR: out = (ph < 128) ? 127 : -128; break;
    default:
        if (vo->lfo_phase < old) vo->lfo_rnd = rand8();
        out = (int8_t)vo->lfo_rnd;
        break;
    }
    if (vo->lfo_wait) {
        vo->lfo_wait--;
        out = 0;
    }
    vo->lfo_out = out;
}

static void glide_penv_tick(voice_t *vo, uint8_t *pp) {
    if (vo->pitch != vo->target) {
        int16_t d = vo->target - vo->pitch;
        uint8_t g = pp[P_GLIDE];
        int16_t s;
        if (!g) {
            vo->pitch = vo->target;
        } else {
            s = (int16_t)(((d >> 4) * (int16_t)glide_tbl[g]) >> 4);
            if (d > 0) {
                if (s < 8) s = 8;
                if (s > d) s = d;
            } else {
                if (s > -8) s = -8;
                if (s < d) s = d;
            }
            vo->pitch += s;
        }
    }
    if (vo->penv) {
        vo->penv = (int16_t)(((int32_t)vo->penv * penv_tbl[pp[P_PENV_TIME]]) >> 8);
        if (vo->penv > -16 && vo->penv < 16) vo->penv = 0;
    }
}

static uint8_t pan_bits(uint8_t ch, uint8_t pan) {
    /* ch 0..3 hardware channel; pan 0 L, 1 C, 2 R */
    uint8_t b = 0;
    if (pan != 2) b |= (uint8_t)(0x10 << ch);
    if (pan != 0) b |= (uint8_t)(0x01 << ch);
    return b;
}

static uint8_t voice_pan(uint8_t v) {
    voice_t *vo = &voice[v];
    uint8_t *pp = patch[v];
    uint8_t pan = pp[P_PAN];
    uint8_t dest_pan = (voice_type[v] == VT_NOISE) ? 1 : LD_PAN;
    if (v < V_DRM && pp[P_LFO_DEST] == dest_pan && pp[P_LFO_DEPTH]) {
        int16_t x = ((int16_t)vo->lfo_out * pp[P_LFO_DEPTH]) >> 6;
        if (x > 20) pan = 2;
        else if (x < -20) pan = 0;
    }
    return pan;
}

static void pulse_noise_tick(uint8_t v) {
    voice_t *vo = &voice[v];
    uint8_t *pp = patch[v];
    int16_t p;

    /* envelope estimate and attack -> decay hand-off */
    switch (vo->env_stage) {
    case ENV_ATTACK:
        if (env_step(vo, pp[P_ATTACK]) && vo->env_vol < 15) vo->env_vol++;
        if (vo->env_vol >= vo->env_target) {
            vo->env_stage = ENV_DECAY;
            vo->env_acc = 0;
            if (vo->env_target < 15 || pp[P_DECAY]) {
                hw_env(v, vo->env_target, 0, pp[P_DECAY] ? pp[P_DECAY] : 0);
                hw_trigger(v);
            }
        }
        break;
    case ENV_DECAY:
        if (pp[P_DECAY] && env_step(vo, pp[P_DECAY]) && vo->env_vol) {
            vo->env_vol--;
            if (!vo->env_vol) vo->env_stage = ENV_IDLE;
        }
        break;
    case ENV_RELEASE:
        if (env_step(vo, pp[P_RELEASE]) && vo->env_vol) {
            vo->env_vol--;
            if (!vo->env_vol) vo->env_stage = ENV_IDLE;
        }
        break;
    default:
        return;
    }

    p = voice_pitch(v);
    if (v == V_NOI) {
        int16_t n = (p + 128) >> 8;
        uint16_t key;
        if (n < 0) n = 0;
        if (n > 127) n = 127;
        key = (uint16_t)n | (pp[P_SHAPE] ? 0x100 : 0);
        if (key != vo->out_period) {
            vo->out_period = key;
            NR43_REG = noise_tbl[n] | (pp[P_SHAPE] ? 0x08 : 0);
        }
    } else {
        uint16_t per = pitch_to_period(p);
        uint8_t duty = pp[P_SHAPE] & 3;
        while (per > 2047) per >>= 1;
        if (per != vo->out_period) {
            uint16_t x = 2048 - per;
            vo->out_period = per;
            REG(env_reg[v] + 1) = (uint8_t)x;
            REG(env_reg[v] + 2) = (uint8_t)(x >> 8);
        }
        if (pp[P_LFO_DEST] == LD_TIMBRE && pp[P_LFO_DEPTH]) {
            int16_t d = (int16_t)duty + (((int16_t)vo->lfo_out * pp[P_LFO_DEPTH]) >> 10);
            if (d < 0) d = 0;
            if (d > 3) d = 3;
            duty = (uint8_t)d;
        }
        if (duty != vo->out_duty) {
            vo->out_duty = duty;
            REG(env_reg[v] - 1) = duty << 6;
        }
    }
}

static void wave_tick(void) {
    voice_t *vo = &voice[V_WAV];
    uint8_t *pp = patch[V_WAV];
    uint8_t mode = pp[P_MODE];

    switch (vo->env_stage) {
    case ENV_ATTACK:
        if (env_step(vo, pp[P_ATTACK]) && vo->env_vol < 15) vo->env_vol++;
        if (vo->env_vol >= 15) {
            vo->env_stage = ENV_DECAY;
            vo->env_acc = 0;
        }
        break;
    case ENV_DECAY:
        if (pp[P_DECAY] && env_step(vo, pp[P_DECAY]) && vo->env_vol) {
            vo->env_vol--;
            if (!vo->env_vol) vo->env_stage = ENV_IDLE;
        }
        break;
    case ENV_RELEASE:
        if (env_step(vo, pp[P_RELEASE]) && vo->env_vol) {
            vo->env_vol--;
            if (!vo->env_vol) vo->env_stage = ENV_IDLE;
        }
        break;
    default:
        if (wave_owner == WO_SYNTH) {
            wave_set_vol(0);
            vo->phon = 0xFF;
        }
        return;
    }
    if (wave_owner != WO_SYNTH) return;

    if (mode == WM_SPEECH || mode == WM_SING) {
        speech_tick();
        return;
    }
    if (wave_timbre() != vo->out_timbre) {
        wave_load_synth();
        wave_vol_out = 0xFF;
    } else {
        uint16_t w = wave_period();
        if (w != vo->out_period) {
            vo->out_period = w;
            wave_set_freq_regs(w);
            NR33_REG = wv_nr33;
            NR34_REG = wv_nr34;
        }
    }
    wave_set_vol(wave_vol_code(vo->env_vol));
}

static void warble_tick(void) {
    uint8_t v;
    for (v = 0; v < 3; v++) {
        if (wb_left[v]) {
            wb_left[v]--;
            wb_cur[v] += wb_step[v];
            continue;
        }
        {
            /* new target: random within +-depth, reached in a random-ish time */
            int16_t tgt = warble_amt ? (int16_t)(((int16_t)(int8_t)rand8() * warble_amt) >> 7) : 0;
            uint8_t len = 4 + (uint8_t)(((uint16_t)(127 - warble_spd) * 116) >> 7);
            len += rand8() & 7;
            wb_step[v] = (tgt - wb_cur[v]) / (int16_t)len;
            wb_left[v] = len;
            if (!wb_step[v]) wb_cur[v] = tgt;
        }
    }
}

/* 24 clocks per beat from the frame rate (59.73 Hz on a DMG):
   clocks per frame = BPM * 24 / 60 / 59.7275, done as BPM*32*10 / 47782. */
static void clock_tick(void) {
    if (!tempo32) return;
    clock_acc += (uint32_t)tempo32 * 10;
    while (clock_acc >= 47782UL) {
        clock_acc -= 47782UL;
        clock24++;
        if (++beat_sub >= 24) {
            beat_sub = 0;
            beat_flash = 6;
        }
    }
}

void synth_tick(void) {
    uint8_t v, nr51 = 0;
    tick_count++;
    warble_tick();
    clock_tick();
    if (beat_flash) beat_flash--;
    for (v = 0; v < V_DRM; v++) {
        voice_t *vo = &voice[v];
        uint8_t *pp = patch[v];
        lfo_tick(vo, pp);
        glide_penv_tick(vo, pp);
        if (v == V_WAV) wave_tick();
        else pulse_noise_tick(v);
        vo->meter = (vo->env_stage == ENV_IDLE) ? 0 : vo->env_vol;
    }
    if (voice[V_DRM].meter && (tick_count & 1)) voice[V_DRM].meter--;
    if (wave_owner == WO_DRUM) voice[V_WAV].meter = 0;

    nr51 |= pan_bits(0, voice_pan(V_PU1));
    nr51 |= pan_bits(1, voice_pan(V_PU2));
    nr51 |= pan_bits(2, wave_owner == WO_DRUM ? patch[V_DRM][P_PAN] : voice_pan(V_WAV));
    nr51 |= pan_bits(3, voice_pan(V_NOI));
    if (nr51 != nr51_shadow) {
        nr51_shadow = nr51;
        NR51_REG = nr51;
    }
}

void synth_init(void) {
    uint8_t v;
    memset(voice, 0, sizeof(voice));
    for (v = 0; v < NUM_VOICES; v++) {
        voice[v].note = NO_NOTE;
        voice[v].phon = 0xFF;
        voice[v].bend_raw = 8192;
        voice_refresh(v);
    }
    wave_owner = WO_NONE;
    st_active = 0;
    st_done = 0;

    NR52_REG = 0x80;
    NR50_REG = 0x77;
    NR51_REG = 0xFF;
    nr51_shadow = 0xFF;
    NR10_REG = 0;
    NR12_REG = 0;
    NR22_REG = 0;
    NR42_REG = 0;
    NR30_REG = 0;
    NR32_REG = 0;
    wave_vol_out = 0;

    TMA_REG = 208;
    TAC_REG = 0x07; /* timer on, 16384 Hz */
}
