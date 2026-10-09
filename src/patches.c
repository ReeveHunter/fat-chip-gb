/* Patch storage in cartridge SRAM + factory presets (bank 1) */
#pragma bank 1
#include <string.h>
#include "engine.h"

#define SRAM_MAGIC_ADDR ((uint8_t *)0xA000)
#define SRAM_SLOTS ((uint8_t *)0xA010)
#define SLOTS_PER_TYPE 16
#define SRAM_VERSION 2

static const uint8_t magic[5] = { 'G', 'B', 'M', 'I', SRAM_VERSION };

/*  LVL PAN SHP TMB MOD ATK DEC REL GLD BND DET PEA PET SWP LSH LRT LDP LDS LDL SPL SPP PHO  pad pad  name */
#define PULSE_DEF 15, 1, 2, 0, 0, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0

static const uint8_t factory_pulse[][PATCH_SIZE] = {
    { 15, 1, 2, 0, 0, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'S', 'Q', 'U', 'A', 'R', 'E', ' ', ' ' },
    { 15, 1, 1, 0, 0, 0, 0, 3, 0, 2, 32, 24, 4, 0, 0, 16, 7, 0, 6, 0, 48, 0, 0, 0, 'L', 'E', 'A', 'D', ' ', '2', '5', ' ' },
    { 15, 1, 0, 0, 0, 0, 2, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'P', 'L', 'U', 'C', 'K', ' ', ' ', ' ' },
    { 13, 1, 2, 0, 0, 4, 0, 5, 0, 2, 32, 24, 4, 0, 0, 12, 31, 1, 0, 0, 48, 0, 0, 0, 'P', 'W', 'M', ' ', 'P', 'A', 'D', ' ' },
    { 15, 1, 2, 0, 0, 0, 4, 1, 0, 2, 32, 27, 1, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'B', 'A', 'S', 'S', ' ', ' ', ' ', ' ' },
    { 15, 1, 1, 0, 0, 0, 1, 1, 0, 2, 32, 36, 2, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'B', 'L', 'I', 'P', ' ', ' ', ' ', ' ' },
    { 15, 1, 2, 0, 0, 0, 3, 1, 0, 2, 32, 24, 4, 3, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'Z', 'A', 'P', 'P', 'E', 'R', ' ', ' ' },
    { 15, 1, 1, 0, 0, 0, 0, 3, 7, 2, 32, 24, 4, 0, 0, 18, 5, 0, 8, 0, 48, 0, 0, 0, 'G', 'L', 'I', 'D', 'E', ' ', ' ', ' ' },
};

static const uint8_t factory_wave[][PATCH_SIZE] = {
    { 15, 1, 0, 0, 2, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'T', 'R', 'I', 'A', 'N', 'G', 'L', 'E' },
    { 15, 1, 8, 0, 1, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'P', 'U', 'L', 'S', 'E', ' ', '3', ' ' },
    { 15, 1, 1, 12, 0, 0, 0, 3, 0, 2, 32, 24, 4, 0, 0, 16, 7, 0, 6, 0, 48, 0, 0, 0, 'S', 'A', 'W', ' ', 'L', 'E', 'A', 'D'},
    { 15, 1, 0, 8, 0, 0, 0, 1, 0, 2, 32, 24, 4, 0, 0, 9, 20, 1, 0, 0, 48, 0, 0, 0, 'P', 'W', 'M', ' ', 'B', 'A', 'S', 'S'},
    { 15, 1, 3, 6, 0, 0, 0, 1, 0, 2, 32, 24, 4, 0, 0, 7, 24, 1, 0, 0, 48, 0, 0, 0, 'A', 'C', 'I', 'D', ' ', 'S', 'W', 'P'},
    { 15, 1, 0, 0, 3, 0, 0, 3, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'O', 'C', 'T', 'A', 'V', 'E', 'S', ' '},
    { 15, 1, 10, 4, 3, 0, 0, 3, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'M', 'A', 'J', 'O', 'R', ' ', ' ', ' '},
    { 15, 1, 14, 3, 4, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'D', 'R', 'U', 'M', 'S', ' ', ' ', ' '},
    { 15, 1, 14, 8, 5, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'R', 'O', 'B', 'O', 'T', ' ', ' ', ' '},
    { 15, 1, 14, 8, 6, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 20, 5, 0, 10, 0, 48, 4, 0, 0, 'S', 'I', 'N', 'G', 'E', 'R', ' ', ' '},
    { 15, 1, 7, 2, 0, 0, 0, 3, 0, 2, 32, 24, 4, 0, 0, 6, 18, 1, 0, 0, 48, 0, 0, 0, 'F', 'M', ' ', 'W', 'O', 'B', ' ', ' '},
    { 15, 1, 0, 0, 0, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 48, 48, 0, 0, 0, 'S', 'P', 'L', 'I', 'T', ' ', ' ', ' '},
    { 15, 1, 14, 3, 0, 0, 0, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'S', 'O', 'F', 'T', ' ', 'T', 'R', 'I'},
};

static const uint8_t factory_noise[][PATCH_SIZE] = {
    { 15, 1, 0, 0, 0, 0, 1, 1, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'H', 'A', 'T', ' ', ' ', ' ', ' ', ' ' },
    { 15, 1, 0, 0, 0, 0, 2, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'S', 'N', 'A', 'R', 'E', ' ', ' ', ' ' },
    { 12, 1, 0, 0, 0, 3, 0, 5, 0, 2, 32, 24, 4, 0, 0, 4, 18, 0, 0, 0, 48, 0, 0, 0, 'W', 'I', 'N', 'D', ' ', ' ', ' ', ' ' },
    { 15, 1, 1, 0, 0, 0, 4, 2, 0, 2, 32, 24, 4, 0, 0, 14, 0, 0, 4, 0, 48, 0, 0, 0, 'M', 'E', 'T', 'A', 'L', ' ', ' ', ' ' },
};

static const uint8_t factory_drum[][PATCH_SIZE] = {
    { 15, 1, 0, 12, 0, 0, 0, 0, 0, 0, 32, 24, 0, 0, 0, 0, 0, 0, 0, 0, 48, 0, 0, 0, '8', '0', '8', ' ', 'K', 'I', 'T', ' ' },
    { 15, 1, 1, 12, 0, 0, 0, 0, 0, 0, 32, 24, 0, 0, 0, 0, 0, 0, 0, 0, 48, 0, 0, 0, 'C', 'H', 'I', 'P', ' ', 'K', 'I', 'T' },
};

static const uint8_t init_patch[PATCH_SIZE] = { PULSE_DEF, 'I', 'N', 'I', 'T', ' ', ' ', ' ', ' ' };

static uint8_t *slot_addr(uint8_t type, uint8_t slot) {
    return SRAM_SLOTS + (((uint16_t)type * SLOTS_PER_TYPE + (slot & 15)) << 5);
}

static void init_type(uint8_t type, const uint8_t *fac, uint8_t n) {
    uint8_t s;
    for (s = 0; s < SLOTS_PER_TYPE; s++) {
        uint8_t *dst = slot_addr(type, s);
        if (s < n) memcpy(dst, fac + (uint16_t)s * PATCH_SIZE, PATCH_SIZE);
        else memcpy(dst, init_patch, PATCH_SIZE);
        if (type == VT_DRUM && s >= n) {
            dst[P_SHAPE] = 0;
            dst[P_TIMBRE] = 12;
        }
        if (type == VT_WAVE && s >= n) dst[P_SHAPE] = 14;
    }
}

static void sram_format(void) {
    init_type(VT_PULSE, &factory_pulse[0][0], sizeof(factory_pulse) / PATCH_SIZE);
    init_type(VT_WAVE, &factory_wave[0][0], sizeof(factory_wave) / PATCH_SIZE);
    init_type(VT_NOISE, &factory_noise[0][0], sizeof(factory_noise) / PATCH_SIZE);
    init_type(VT_DRUM, &factory_drum[0][0], sizeof(factory_drum) / PATCH_SIZE);
    memcpy(SRAM_MAGIC_ADDR, magic, 5);
}

void patches_init(void) BANKED {
    uint8_t v;
    ENABLE_RAM;
    if (memcmp(SRAM_MAGIC_ADDR, magic, 5) != 0) sram_format();
    DISABLE_RAM;
    patch_load(V_PU1, 0);
    patch_load(V_PU2, 1);
    patch_load(V_WAV, 0);
    patch_load(V_NOI, 0);
    patch_load(V_DRM, 0);
    for (v = 0; v < NUM_VOICES; v++) voice_refresh(v);
}

void patch_load(uint8_t v, uint8_t slot) BANKED {
    uint8_t t, p, old_mode;
    if (v >= NUM_VOICES) return;
    t = voice_type[v];
    old_mode = patch[v][P_MODE];
    ENABLE_RAM;
    memcpy(patch[v], slot_addr(t, slot), PATCH_SIZE);
    DISABLE_RAM;
    for (p = 0; p < NUM_PARAMS; p++) {
        uint8_t m = param_max[t][p];
        if (m != NA && patch[v][p] > m) patch[v][p] = m;
    }
    for (p = PATCH_NAME_OFS; p < PATCH_SIZE; p++)
        if (patch[v][p] < 32 || patch[v][p] > 95) patch[v][p] = ' ';
    patch_slot[v] = slot & 15;
    if (v == V_WAV && patch[v][P_MODE] != old_mode) all_notes_off(V_WAV);
    voice_refresh(v);
}

void patch_save(uint8_t v, uint8_t slot) BANKED {
    if (v >= NUM_VOICES) return;
    ENABLE_RAM;
    memcpy(slot_addr(voice_type[v], slot), patch[v], PATCH_SIZE);
    DISABLE_RAM;
    patch_slot[v] = slot & 15;
}

/* global setup (MIDI channel map) */
#define SETUP_ADDR ((uint8_t *)0xA900)
static const uint8_t setup_magic[4] = { 'S', 'E', 'T', 1 };

void setup_load(void) BANKED {
    uint8_t v, c;
    ENABLE_RAM;
    if (!memcmp(SETUP_ADDR, setup_magic, 4)) {
        for (v = 0; v < NUM_VOICES; v++) {
            c = SETUP_ADDR[4 + v];
            midi_ch[v] = (c > CH_OFF) ? v : c;
        }
    }
    DISABLE_RAM;
}

void setup_save(void) BANKED {
    ENABLE_RAM;
    memcpy(SETUP_ADDR, setup_magic, 4);
    memcpy(SETUP_ADDR + 4, midi_ch, NUM_VOICES);
    DISABLE_RAM;
}

/* name of a stored slot, for the patch browser */
void patch_slot_name(uint8_t type, uint8_t slot, uint8_t *out) BANKED {
    uint8_t i, c;
    ENABLE_RAM;
    for (i = 0; i < PATCH_NAME_LEN; i++) {
        c = slot_addr(type, slot)[PATCH_NAME_OFS + i];
        out[i] = (c < 32 || c > 95) ? ' ' : c;
    }
    DISABLE_RAM;
}
