/* Parameter metadata shared by the MIDI handler (bank 0) and the UI (bank 1). */
#include <string.h>
#include "engine.h"

/* MIDI CC number for each parameter (same CC across channels) */
const uint8_t param_cc[NUM_PARAMS] = {
    7,  /* LEVEL */
    10, /* PAN */
    70, /* SHAPE  (duty / wave shape / noise width / drum kit) */
    74, /* TIMBRE (wave morph / speech speed / drum pitch) */
    71, /* MODE   (wave) */
    73, /* ATTACK */
    75, /* DECAY */
    72, /* RELEASE */
    5,  /* GLIDE */
    85, /* BEND range */
    94, /* DETUNE */
    80, /* PITCH ENV amount */
    81, /* PITCH ENV time */
    82, /* SWEEP (pulse 1) */
    77, /* LFO shape */
    76, /* LFO rate */
    1,  /* LFO depth (mod wheel) */
    78, /* LFO destination */
    79, /* LFO delay */
    83, /* SPLIT note (wave) */
    84, /* SPEECH pitch (wave) */
    86, /* PHONEME (wave, sing mode) */
    68, /* LEGATO (standard legato footswitch CC) */
    89, /* BEND SHAPE (v0.12: SLIDE / STEP, CLICK) */
};

/* user map (DAW profile); FAT CHIP profile always uses param_cc */
uint8_t cc_map[NUM_PARAMS];

uint8_t cc_fixed_param(uint8_t p) {
    return p == P_LEVEL || p == P_PAN || p == P_LFO_DEPTH;
}

/* standard CCs and the Fat Chip globals can't be learned */
uint8_t cc_reserved(uint8_t cc) {
    return cc == 1 || cc == 7 || cc == 10 || cc == 64 || cc >= 120 ||
           (cc >= GCC_FIRST && cc <= GCC_LAST);
}

uint8_t cc_for(uint8_t p) {
    return (profile == PROFILE_DAW) ? cc_map[p] : param_cc[p];
}

void cc_map_reset(void) {
    uint8_t p;
    for (p = 0; p < NUM_PARAMS; p++) cc_map[p] = param_cc[p];
    cc_lut_ok = 0;
}

/* CC -> parameter, a table rebuilt when the map or the profile changes (a search
 * of all the parameters cost ~1300 cycles a CC: Fat Chip 64's bursts backed up) */
uint8_t cc_lut_ok;
static uint8_t cc_lut_prof, cc_param[128];

uint8_t cc_to_param(uint8_t cc) {
    if (!cc_lut_ok || cc_lut_prof != profile) {
        uint8_t p = NUM_PARAMS;
        memset(cc_param, 0xFF, 128);
        while (p--) cc_param[cc_for(p) & 127] = p;   /* (the lowest parameter wins) */
        cc_lut_ok = 1;
        cc_lut_prof = profile;
    }
    return cc_param[cc & 127];
}

uint8_t cc_map_custom(void) {
    uint8_t p;
    for (p = 0; p < NUM_PARAMS; p++)
        if (cc_map[p] != param_cc[p]) return 1;
    return 0;
}

/* 1 = CC value is used directly (clamped), 0 = CC 0..127 scaled to 0..max */
const uint8_t param_direct[NUM_PARAMS] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1,
};

/*                         LVL PAN SHP TMB MOD ATK DEC REL GLD BND DET PEA PET SWP LSH LRT LDP LDS LDL SPL SPP PHO LEG BSH */
const uint8_t param_max[4][NUM_PARAMS] = {
    /* PULSE */ { 15, 2, 3, NA, NA, 7, 7, 7, 15, 24, 63, 48, 15, 15, 4, 31, 31, 2, 15, NA, NA, NA, 1, 13 },
    /* WAVE  */ { 15, 2, 15, 15, WM_COUNT - 1, 7, 7, 7, 15, 24, 63, 48, 15, NA, 4, 31, 31, 2, 15, 127, 127, SPEECH_PHONEMES - 1, 1, 13 },
    /* NOISE */ { 15, 2, 1, NA, NA, 7, 7, 7, 15, 24, NA, 48, 15, NA, 4, 31, 31, 1, 15, NA, NA, NA, 1, 9 },
    /* DRUM  */ { 15, 2, DRUM_KITS - 1, 24, 1, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA },
};

const uint8_t voice_type[NUM_VOICES] = { VT_PULSE, VT_PULSE, VT_WAVE, VT_NOISE, VT_DRUM };
