/* Parameter metadata shared by the MIDI handler (bank 0) and the UI (bank 1). */
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
};

/* 1 = CC value is used directly (clamped), 0 = CC 0..127 scaled to 0..max */
const uint8_t param_direct[NUM_PARAMS] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
};

/*                         LVL PAN SHP TMB MOD ATK DEC REL GLD BND DET PEA PET SWP LSH LRT LDP LDS LDL SPL SPP PHO */
const uint8_t param_max[4][NUM_PARAMS] = {
    /* PULSE */ { 15, 2, 3, NA, NA, 7, 7, 7, 15, 24, 63, 48, 15, 15, 4, 31, 31, 2, 15, NA, NA, NA },
    /* WAVE  */ { 15, 2, 15, 15, 4, 7, 7, 7, 15, 24, 63, 48, 15, NA, 4, 31, 31, 2, 15, 127, 127, SPEECH_PHONEMES - 1 },
    /* NOISE */ { 15, 2, 1, NA, NA, 7, 7, 7, 15, 24, NA, 48, 15, NA, 4, 31, 31, 1, 15, NA, NA, NA },
    /* DRUM  */ { 15, 2, DRUM_KITS - 1, 24, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA },
};

const uint8_t voice_type[NUM_VOICES] = { VT_PULSE, VT_PULSE, VT_WAVE, VT_NOISE, VT_DRUM };
