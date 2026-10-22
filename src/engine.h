#ifndef ENGINE_H
#define ENGINE_H

#include <gb/gb.h>
#include <stdint.h>

#define VERSION_STR "0.6"

/* ------------------------------------------------------------------ voices */
#define V_PU1 0
#define V_PU2 1
#define V_WAV 2
#define V_NOI 3
#define V_DRM 4 /* MIDI ch 5: drum kit streamed on the wave channel */
#define NUM_VOICES 5

#define VT_PULSE 0
#define VT_WAVE 1
#define VT_NOISE 2
#define VT_DRUM 3

#define NO_NOTE 0xFF

/* ------------------------------------------------------------------ params */
enum {
    P_LEVEL = 0,
    P_PAN,
    P_SHAPE,  /* pulse duty / wave shape or chord / noise width / drum kit */
    P_TIMBRE, /* wave morph step / dual timbre / speech speed / drum pitch */
    P_MODE,   /* wave: SYNTH PULSE TRI DUAL DRUMS SPEECH SING */
    P_ATTACK,
    P_DECAY,
    P_RELEASE,
    P_GLIDE,
    P_BEND,
    P_DETUNE,
    P_PENV_AMT,
    P_PENV_TIME,
    P_SWEEP,
    P_LFO_SHAPE,
    P_LFO_RATE,
    P_LFO_DEPTH,
    P_LFO_DEST,
    P_LFO_DELAY,
    P_SPLIT,
    P_SPEECH_PITCH,
    P_PHONEME,
    P_LEGATO, /* overlapping notes glide/change pitch without retriggering */
    NUM_PARAMS
};

#define PATCH_SIZE 32
#define PATCH_NAME_OFS 24
#define PATCH_NAME_LEN 8

#define NA 0xFF /* parameter not used by this voice type */

#define WM_SYNTH 0
#define WM_PULSE 1  /* wave channel as a third pulse (duty from SHAPE) */
#define WM_TRI 2    /* plain 4-bit triangle */
#define WM_DUAL 3
#define WM_DRUMS 4
#define WM_SPEECH 5
#define WM_SING 6
#define WM_COUNT 7

#define LFO_TRI 0
#define LFO_SAWD 1
#define LFO_SAWU 2
#define LFO_SQR 3
#define LFO_RND 4

#define LD_PITCH 0
#define LD_TIMBRE 1 /* pulse: duty, wave: timbre */
#define LD_PAN 2    /* noise: dest 1 is pan */

extern const uint8_t param_cc[NUM_PARAMS]; /* default CC map (FAT CHIP profile) */
extern uint8_t cc_map[NUM_PARAMS];          /* user CC map (DAW profile) */
uint8_t cc_for(uint8_t p);                  /* CC that drives parameter p right now */
uint8_t cc_fixed_param(uint8_t p);          /* LEVEL, PAN, LFO DEPTH keep 7/10/1 */
uint8_t cc_reserved(uint8_t cc);            /* never learnable */
void cc_map_reset(void);
uint8_t cc_map_custom(void);

/* ------------------------------------------------------------------ Fat Chip globals
   Global CCs work on any channel a voice listens to and affect every voice.
   See docs/fatchip-protocol.md. */
#define PROFILE_DAW 0
#define PROFILE_FATCHIP 1
#define GCC_FIRST 102
#define GCC_PROFILE 102  /* 70 'F' = FAT CHIP, 68 'D' = DAW, other values ignored */
#define GCC_TUNE 103     /* master tune, 64 = 0, +-50 cents */
#define GCC_WARBLE 104   /* warble depth 0..127 (0 = off, 127 = +-50 cents) */
#define GCC_WSPEED 105   /* warble speed 0 (slow, ~2 s) .. 127 (fast) */
#define GCC_RESERVED 106 /* glitch amount, not yet */
#define GCC_TEMPO_MSB 107 /* tempo = BPM * 32 as 14 bits; applied when LSB arrives */
#define GCC_TEMPO_LSB 108
#define GCC_DOWNBEAT 109 /* any value: beat 1 of a bar is now */
#define GCC_LATCH 110    /* >= 64 holds every voice's notes */
#define GCC_PANIC 111    /* any value: all voices off, bends reset, latch off */
#define GCC_DISPLAY 112  /* 0 = screen on, 1 = screen off (follows Fat Chip 64's video mode) */
#define GCC_LAST 112
#define PROFILE_F 70
#define PROFILE_D 68
extern uint8_t profile;
extern int16_t master_tune;  /* 8.8 semitones */
extern uint8_t tune_cc, warble_amt, warble_spd, latch;
extern uint16_t tempo32;     /* BPM * 32, 0 = no tempo yet */
extern uint16_t clock24;     /* 24 per beat, reset by the downbeat CC */
extern uint8_t beat_flash;   /* frames left of the on-beat blink */
extern uint8_t display_req;  /* 0xFF = none, else GCC_DISPLAY value to apply */
void global_cc(uint8_t cc, uint8_t val);
void latch_set(uint8_t on);
/* MIDI learn (DAW profile, edit screen) */
extern uint8_t learn_voice, learn_param; /* learn_voice = NO_NOTE when idle */
extern uint8_t learn_done;
extern const uint8_t param_max[4][NUM_PARAMS];
extern const uint8_t param_direct[NUM_PARAMS];
extern const uint8_t voice_type[NUM_VOICES];

/* live patches, one per voice: NUM_PARAMS bytes of params + 8-char name */
extern uint8_t patch[NUM_VOICES][PATCH_SIZE];
extern uint8_t patch_slot[NUM_VOICES];

/* ------------------------------------------------------------------ voice state */
typedef struct {
    uint8_t note;      /* sounding note or NO_NOTE */
    uint8_t vel;
    uint8_t gate;      /* key down (or held by sustain) */
    uint8_t held[8];   /* note stack for last-note priority */
    uint8_t nheld;
    uint8_t sustain;   /* CC64 down */
    uint8_t sus_off;   /* note-off arrived while sustain down */
    int16_t pitch;     /* 8.8 semitones, current (glides toward target) */
    int16_t target;
    int16_t bend;      /* 8.8 offset */
    int16_t penv;      /* 8.8 pitch envelope offset */
    uint16_t bend_raw;
    uint16_t lfo_phase;
    int8_t lfo_out;
    uint8_t lfo_wait;
    uint8_t lfo_rnd;
    uint8_t env_vol;   /* estimated current volume 0..15 */
    uint8_t env_stage;
    uint16_t env_acc;
    uint8_t env_target;
    uint16_t out_period; /* last written period, 0xFFFF = force */
    uint8_t out_pan;
    uint8_t out_timbre;
    uint8_t out_duty;
    uint8_t meter;     /* UI activity meter 0..15 */
    /* wave speech */
    uint8_t phon;
    uint16_t phon_pos; /* 8.8 frame position */
    uint8_t phon_frame;
    uint8_t phon_set;
} voice_t;

#define ENV_IDLE 0
#define ENV_ATTACK 1
#define ENV_DECAY 2
#define ENV_RELEASE 3

extern voice_t voice[NUM_VOICES];

/* wave hardware ownership */
#define WO_NONE 0
#define WO_SYNTH 1
#define WO_DRUM 2
extern uint8_t wave_owner;

/* ------------------------------------------------------------------ asm (isr.s) */
extern uint8_t wave_buf[16];
extern uint8_t wv_nr33, wv_nr34;
extern volatile uint8_t rx_head, rx_tail;
extern volatile uint8_t st_active, st_done, st_bank, st_left, st_nr34;
extern uint8_t *volatile st_ptr;
void wave_commit(void);        /* load wave_buf into wave RAM and trigger */
void sio_isr(void);
void tim_isr(void);
#define RX_BUF ((volatile uint8_t *)0xDC00)

/* ------------------------------------------------------------------ engine API */
void synth_init(void);
void synth_tick(void);
void note_on(uint8_t v, uint8_t note, uint8_t vel);
void note_off(uint8_t v, uint8_t note);
void all_notes_off(uint8_t v);
void control_change(uint8_t v, uint8_t cc, uint8_t val);
void pitch_bend(uint8_t v, uint16_t val);
void param_set(uint8_t v, uint8_t p, uint8_t val); /* applies + marks UI dirty */
void voice_refresh(uint8_t v);                     /* re-apply patch to hardware */
void stream_finished(void);
void midi_poll(void);
void bank_copy16(uint8_t bank, const uint8_t *src, uint8_t *dst);

/* MIDI channel each voice listens to (0-15), CH_OFF = ignore. Several voices
   may share a channel to layer them. */
#define CH_OFF 16
extern uint8_t midi_ch[NUM_VOICES];
void panic_all(void);
void load_ui_tiles(void);
void load_dim_tiles(void);

/* global setup */
#define VEL_LINEAR 0
#define VEL_SOFT 1
#define VEL_HARD 2
#define VEL_FIXED 3
extern uint8_t vel_curve;

/* MIDI monitor (last messages, newest at mon_head) */
#define MON_LINES 12
extern uint8_t mon_msg[MON_LINES][3];
extern uint8_t mon_head;
extern uint16_t mon_count;
extern uint8_t mon_raw[6];
extern uint8_t mon_raw_head;

/* Link test (Setup > LINK TEST): counts what actually arrives over the link,
   so we can check whether SysEx, clock etc. get through the MIDI adapter. */
extern uint16_t lt_bytes, lt_noteon, lt_cc, lt_bend, lt_clock, lt_stray;
extern uint8_t lt_start, lt_cont, lt_stop, lt_sense;
extern uint8_t lt_sx_start, lt_sx_end, lt_sx_sum;
extern uint16_t lt_sx_len;
void link_test_reset(void);

extern volatile uint8_t vbl_flag;
extern uint8_t ui_dirty_params; /* bitmask of voices whose params changed */
extern uint8_t midi_activity;

/* tables (gen/tables.c, gen/drums.c, gen/speech_tbl.c) */
extern const uint16_t period_tbl[128];
extern const uint8_t noise_tbl[128];
extern const uint8_t scale_lut[256];
extern const uint16_t lfo_rate_tbl[32];
extern const uint8_t lfo_depth_tbl[32];
extern const uint8_t glide_tbl[16];
extern const uint8_t drum_tick_tbl[25];
extern const uint8_t penv_tbl[16];
extern const uint8_t dual_mult_tbl[16];
extern const uint8_t drum_note_map[128];
extern const uint8_t drum_bank[];
extern const uint16_t drum_ptr[];
extern const uint8_t drum_len[];
extern const uint16_t speech_start[];
extern const uint8_t speech_count[];
extern const uint8_t speech_hold[];
#define DRUM_SLOTS 18
#define DRUM_KITS 2
#define SPEECH_PHONEMES 41
#define SPEECH_SET_FRAMES 260
#define WAVES_BANK 2
#define SPEECH_BANK 7
#define SPEECH_NOTE_BASE 36

/* banked data (only touched through bank_copy16) */
extern const uint8_t shape_waves[];
extern const uint8_t dual_waves[];
extern const uint8_t speech_frames[];
extern const uint8_t speech_meta[];

/* ------------------------------------------------------------------ UI / patches (bank 1) */
void ui_init(void) BANKED;
void ui_tick(void) BANKED;
void patches_init(void) BANKED;
void patch_load(uint8_t v, uint8_t slot) BANKED;
void patch_save(uint8_t v, uint8_t slot) BANKED;
void setup_load(void) BANKED;
void setup_save(void) BANKED;
void save_enable(void) BANKED;
void save_disable(void) BANKED;
extern uint8_t save_on;   /* patches/setup in cart save RAM (off by default) */
extern uint8_t contrast;  /* 0 normal, 1 high: grey labels drawn black */

#endif
