/* Fat Chip GB - HATS NOISE: a kit's hats and cymbals on the noise channel (v0.17) */
#pragma bank 2
#include "engine.h"

/* slot -> recipe + 1 (CL HAT, OP HAT, CRASH, RIDE, SHAKER) */
static const uint8_t is_hat[DRUM_SLOTS] = { 0, 0, 0, 0, 0, 0, 1, 0, 2, 0, 3, 4, 5, 0, 0, 0, 0, 0 };
/* NR43 (clock; bit 3 = the short "metallic" LFSR), envelope pace,
 * length (64 - n) / 256 s or 0 = until the envelope ends, frames it owns the channel */
static const uint8_t hat_nr43[5] = { 0x00, 0x00, 0x12, 0x09, 0x00 };
static const uint8_t hat_pace[5] = { 1, 2, 5, 3, 0 };
static const uint8_t hat_len[5] = { 54, 0, 0, 0, 50 };
static const uint8_t hat_frames[5] = { 3, 30, 75, 45, 4 };
uint8_t noise_drum;            /* frames the noise channel still belongs to a hat */

/* 1 if the slot is a hat (and it played) */
uint8_t noise_hat(uint8_t slot, uint8_t vel) BANKED {
    voice_t *no = &voice[V_NOI];
    uint8_t h = is_hat[slot], vol;
    if (!h) return 0;
    h--;
    vol = vel_vol(vel, patch[V_DRM][P_LEVEL]);
    if (!vol) return 1;
    if (no->env_stage != ENV_IDLE) {      /* the hat takes the noise channel */
        no->env_stage = ENV_IDLE;
        no->note = NO_NOTE;
        no->nheld = 0;
    }
    click_left = 0;
    no->out_period = 0xFFFF;              /* (its next note writes NR43 again) */
    NR41_REG = hat_len[h];
    NR42_REG = (uint8_t)(vol << 4) | hat_pace[h];
    NR43_REG = hat_nr43[h];
    NR44_REG = hat_len[h] ? 0xC0 : 0x80;
    noise_drum = hat_frames[h];
    return 1;
}

/* v0.18: while a tremolo runs (synth.c trem_tick), a channel silent for
   DAC_OFF_AFTER frames has its DAC switched off (one small step, once), so
   the master volume's steps don't move its DC (the clicks on hardware) */
#define DAC_OFF_AFTER 10
uint8_t idle_frames[4];        /* frames each channel has been silent */
static const uint16_t dac_reg[4] = { 0xFF12, 0xFF17, 0xFF1A, 0xFF21 };   /* NR12 NR22 NR30 NR42 */
void idle_dacs(void) BANKED {
    uint8_t v, idle;
    for (v = 0; v < 4; v++) {
        if (v == V_WAV) idle = (voice[V_WAV].env_stage == ENV_IDLE && wave_owner == WO_NONE && !st_active);
        else if (v == V_NOI) idle = (voice[V_NOI].env_stage == ENV_IDLE && !noise_drum && !click_left);
        else idle = (voice[v].env_stage == ENV_IDLE);
        if (!idle) { idle_frames[v] = 0; continue; }
        if (idle_frames[v] < DAC_OFF_AFTER && ++idle_frames[v] == DAC_OFF_AFTER)
            *(volatile uint8_t *)dac_reg[v] = 0;
    }
}
