/* Fat Chip GB user interface (bank 1)
 *
 * HOME   : five channel cards with live meters.  Up/Down pick a channel,
 *          Left/Right step through saved patches, A edits, SELECT = patches,
 *          START auditions.
 * EDIT   : LSDJ-style parameter list. Up/Down move, Left/Right change,
 *          hold A + Left/Right for big steps. Bottom line shows the CC number.
 * PATCH  : 16 slots. A loads, SELECT saves (then name it), B goes back.
 * NAME   : on-screen keyboard. A types, B deletes, START saves, SELECT cancels.
 *
 * Screens are redrawn a few rows per frame so MIDI is never starved.
 */
#pragma bank 1
#include <string.h>
#include "engine.h"
#include "gen/font.h"

extern const uint8_t shape_names[];
extern const uint8_t dual_names[];
extern const uint8_t kit_names[];
extern const uint8_t phoneme_names[];
void patch_slot_name(uint8_t type, uint8_t slot, uint8_t *out) BANKED;

#define SCR_HOME 0
#define SCR_EDIT 1
#define SCR_PATCH 2
#define SCR_NAME 3
#define SCR_SETUP 4
#define SCR_MON 5
#define SETUP_ITEMS 9 /* SHIFT ALL, 5 voice channels, VELOCITY, SCREEN OFF, MONITOR */
#define SI_VEL 6
#define SI_SCREEN 7
#define SI_MON 8

#define ROWS 18
#define EDIT_FIRST 2
#define EDIT_ROWS 15

static uint8_t screen, prev_screen;
static uint8_t sel;            /* selected voice */
static uint8_t dirty[ROWS];
static uint8_t line[20];

static uint8_t plist[24], pcount, ecur, escroll, plist_mode;
static uint8_t shown_val[24];
static uint8_t meter_shown[NUM_VOICES];
static uint8_t note_shown[NUM_VOICES];
static uint8_t act_shown;

static uint8_t pcur;           /* patch screen cursor */
static uint8_t kx, ky, npos;   /* name keyboard */
static uint8_t nbuf[PATCH_NAME_LEN];
static uint8_t flash;          /* frames to show a message on the help row */
static const char *flash_msg;

static uint8_t keys, keys_prev, rep;
static uint8_t scur, setup_changed;
static uint8_t sel_pending, lcd_off;
static uint16_t mon_shown;
static uint8_t clip[PATCH_SIZE];
static uint8_t clip_type = 0xFF;
static void go(uint8_t s);
static uint8_t audition;       /* note being auditioned + 1 */

/* ------------------------------------------------------------------ text helpers */
static void lclear(void) {
    memset(line, 0, 20); /* tile 0 = space */
}

static void lput(uint8_t x, const char *s, uint8_t base) {
    while (*s && x < 20) {
        uint8_t c = (uint8_t)*s++;
        if (c >= 'a' && c <= 'z') c -= 32;
        line[x++] = (c >= 32 && c < 96) ? (uint8_t)(c - 32 + base) : base;
    }
}

static void lputn(uint8_t x, const uint8_t *s, uint8_t n, uint8_t base) {
    while (n-- && x < 20) {
        uint8_t c = *s++;
        line[x++] = (c >= 32 && c < 96) ? (uint8_t)(c - 32 + base) : base;
    }
}

static uint8_t lnum(uint8_t x, int16_t v, uint8_t base) {
    char b[7];
    uint8_t i = 0, j;
    char tmp[6];
    uint8_t n = 0;
    uint16_t u;
    if (v < 0) {
        b[i++] = '-';
        u = (uint16_t)(-v);
    } else {
        u = (uint16_t)v;
    }
    do {
        tmp[n++] = '0' + (u % 10);
        u /= 10;
    } while (u);
    for (j = 0; j < n; j++) b[i++] = tmp[n - 1 - j];
    b[i] = 0;
    lput(x, b, base);
    return x + i;
}

static uint8_t lsigned(uint8_t x, int16_t v, uint8_t base) {
    if (v > 0) {
        lput(x, "+", base);
        x++;
    }
    return lnum(x, v, base);
}

static const char note_letters[] = "C C#D D#E F F#G G#A A#B ";

static uint8_t lnote(uint8_t x, uint8_t n, uint8_t base) {
    uint8_t k = (n % 12) << 1;
    line[x++] = (uint8_t)(note_letters[k] - 32 + base);
    if (note_letters[k + 1] == '#') line[x++] = (uint8_t)('#' - 32 + base);
    return lnum(x, (int16_t)(n / 12) - 1, base);
}

static void lflush(uint8_t y) {
    set_bkg_tiles(0, y, 20, 1, line);
}

static void dirty_all(void) {
    memset(dirty, 1, ROWS);
}

/* ------------------------------------------------------------------ names / labels */
static const char *const type_short[NUM_VOICES] = { "PU1", "PU2", "WAV", "NOI", "DRM" };
static const char *const type_long[NUM_VOICES] = { "PULSE 1", "PULSE 2", "WAVE", "NOISE", "DRUMS" };
static const char *const vel_names[4] = { "LINEAR", "SOFT", "HARD", "FIXED" };
static const char *const mode_names[WM_COUNT] = { "SYNTH", "PULSE", "TRI", "DUAL", "DRUMS", "SPEECH", "SING" };
static const char *const duty_names[4] = { "12.5%", "25%", "50%", "75%" };
static const char *const pan_names[3] = { "LEFT", "CENTER", "RIGHT" };
static const char *const lfo_names[5] = { "TRI", "SAW DN", "SAW UP", "SQUARE", "RANDOM" };
static const char *const dest_pulse[3] = { "PITCH", "DUTY", "PAN" };
static const char *const dest_wave[3] = { "PITCH", "TIMBRE", "PAN" };
static const char *const dest_noise[2] = { "PITCH", "PAN" };

static const char *param_label(uint8_t v, uint8_t p) {
    uint8_t t = voice_type[v];
    uint8_t mode = patch[v][P_MODE];
    switch (p) {
    case P_LEVEL: return "LEVEL";
    case P_PAN: return "PAN";
    case P_SHAPE:
        if (t == VT_PULSE) return "DUTY";
        if (t == VT_NOISE) return "WIDTH";
        if (t == VT_DRUM) return "KIT";
        if (mode == WM_PULSE) return "DUTY";
        return mode == WM_DUAL ? "CHORD" : "SHAPE";
    case P_TIMBRE:
        if (t == VT_DRUM) return "PITCH";
        return (mode == WM_SPEECH || mode == WM_SING) ? "SPEED" : "TIMBRE";
    case P_MODE: return "MODE";
    case P_ATTACK: return "ATTACK";
    case P_DECAY: return "DECAY";
    case P_RELEASE: return "RELEASE";
    case P_GLIDE: return "GLIDE";
    case P_BEND: return "BEND RNG";
    case P_DETUNE: return "DETUNE";
    case P_PENV_AMT: return "PITCH ENV";
    case P_PENV_TIME: return "P.ENV TIME";
    case P_SWEEP: return "SWEEP";
    case P_LFO_SHAPE: return "LFO WAVE";
    case P_LFO_RATE: return "LFO RATE";
    case P_LFO_DEPTH: return "LFO DEPTH";
    case P_LFO_DEST: return "LFO DEST";
    case P_LFO_DELAY: return "LFO DELAY";
    case P_SPLIT: return "DRUM SPLIT";
    case P_SPEECH_PITCH: return "VOICE PCH";
    case P_PHONEME: return "PHONEME";
    case P_LEGATO: return "LEGATO";
    }
    return "?";
}

/* writes the value text of param p at column x */
static void lvalue(uint8_t x, uint8_t v, uint8_t p, uint8_t base) {
    uint8_t t = voice_type[v];
    uint8_t val = patch[v][p];
    uint8_t mode = patch[v][P_MODE];
    switch (p) {
    case P_PAN: lput(x, pan_names[val > 2 ? 1 : val], base); return;
    case P_SHAPE:
        if (t == VT_PULSE) lput(x, duty_names[val & 3], base);
        else if (t == VT_NOISE) lput(x, val ? "SHORT" : "LONG", base);
        else if (t == VT_DRUM) lputn(x, &kit_names[(uint16_t)val * 6], 6, base);
        else if (mode == WM_PULSE) lput(x, duty_names[(val >> 2) & 3], base);
        else if (mode == WM_DUAL) lputn(x, &dual_names[(uint16_t)(val & 15) * 6], 6, base);
        else lputn(x, &shape_names[(uint16_t)(val & 15) * 6], 6, base);
        return;
    case P_TIMBRE:
        if (t == VT_DRUM) lsigned(x, (int16_t)val - 12, base);
        else lnum(x, val, base);
        return;
    case P_MODE: lput(x, mode_names[val >= WM_COUNT ? 0 : val], base); return;
    case P_DECAY:
        if (!val) { lput(x, "HOLD", base); return; }
        break;
    case P_RELEASE:
        if (!val) { lput(x, "CUT", base); return; }
        break;
    case P_GLIDE:
    case P_LFO_DEPTH:
        if (!val) { lput(x, "OFF", base); return; }
        break;
    case P_BEND:
        x = lnum(x, val, base);
        lput(x + 1, "SEMI", base);
        return;
    case P_DETUNE: lsigned(x, (int16_t)val - 32, base); return;
    case P_PENV_AMT:
        if (val == 24) { lput(x, "OFF", base); return; }
        x = lsigned(x, (int16_t)val - 24, base);
        lput(x + 1, "SEMI", base);
        return;
    case P_SWEEP:
        if (!val) lput(x, "OFF", base);
        else if (val < 8) { lput(x, "DOWN", base); lnum(x + 5, val, base); }
        else { lput(x, "UP", base); lnum(x + 3, val - 7, base); }
        return;
    case P_LFO_SHAPE: lput(x, lfo_names[val > 4 ? 0 : val], base); return;
    case P_LFO_DEST:
        if (t == VT_PULSE) lput(x, dest_pulse[val > 2 ? 0 : val], base);
        else if (t == VT_WAVE) lput(x, (val == LD_TIMBRE && mode == WM_PULSE) ? "PWM" : dest_wave[val > 2 ? 0 : val], base);
        else lput(x, dest_noise[val & 1], base);
        return;
    case P_SPLIT:
        if (!val) { lput(x, "OFF", base); return; }
        lput(x, "<", base);
        lnote(x + 1, val, base);
        return;
    case P_SPEECH_PITCH: lnote(x, val, base); return;
    case P_LEGATO: lput(x, val ? "ON" : "OFF", base); return;
    case P_PHONEME:
        x = lnum(x, val, base);
        lputn(x + 1, &phoneme_names[(uint16_t)val * 2], 2, base);
        return;
    }
    lnum(x, val, base);
}

/* ------------------------------------------------------------------ param list */
static const uint8_t order_pulse[] = { P_LEVEL, P_PAN, P_SHAPE, P_ATTACK, P_DECAY, P_RELEASE, P_GLIDE, P_LEGATO,
                                       P_BEND, P_DETUNE, P_PENV_AMT, P_PENV_TIME, P_SWEEP, P_LFO_SHAPE, P_LFO_RATE,
                                       P_LFO_DEPTH, P_LFO_DEST, P_LFO_DELAY, 0xFF };
static const uint8_t order_wave[] = { P_MODE, P_SHAPE, P_TIMBRE, P_SPEECH_PITCH, P_PHONEME, P_LEVEL, P_PAN,
                                      P_ATTACK, P_DECAY, P_RELEASE, P_GLIDE, P_LEGATO, P_BEND, P_DETUNE, P_PENV_AMT,
                                      P_PENV_TIME, P_LFO_SHAPE, P_LFO_RATE, P_LFO_DEPTH, P_LFO_DEST,
                                      P_LFO_DELAY, P_SPLIT, 0xFF };

static void build_plist(void) {
    uint8_t t = voice_type[sel];
    uint8_t mode = patch[sel][P_MODE];
    const uint8_t *o = (t == VT_WAVE) ? order_wave : order_pulse;
    uint8_t i, p;
    pcount = 0;
    if (t == VT_DRUM) {
        plist[0] = P_SHAPE;
        plist[1] = P_TIMBRE;
        plist[2] = P_LEVEL;
        plist[3] = P_PAN;
        pcount = 4;
    } else {
        for (i = 0; (p = o[i]) != 0xFF; i++) {
            if (param_max[t][p] == NA) continue;
            if (sel == V_PU2 && p == P_SWEEP) continue;
            if (t == VT_WAVE) {
                if (mode == WM_DRUMS && (p == P_SHAPE || p == P_TIMBRE || p == P_SPLIT)) continue;
                if ((mode == WM_SPEECH || mode == WM_SING || mode == WM_TRI) && p == P_SHAPE) continue;
                if ((mode == WM_PULSE || mode == WM_TRI) && p == P_TIMBRE) continue;
                if (p == P_SPEECH_PITCH && mode != WM_SPEECH) continue;
                if (p == P_PHONEME && mode != WM_SING) continue;
                if (p == P_LEGATO && (mode == WM_SPEECH || mode == WM_SING || mode == WM_DRUMS)) continue;
            }
            plist[pcount++] = p;
        }
    }
    plist_mode = mode;
    if (ecur >= pcount) ecur = pcount - 1;
    memset(shown_val, 0xFF, sizeof(shown_val));
}

/* ------------------------------------------------------------------ row renderers */
static void draw_header(const char *title) {
    uint8_t i;
    for (i = 0; i < 20; i++) line[i] = T_INVBLANK;
    lput(1, title, T_INV);
}

static void meter_tiles(uint8_t x, uint8_t level) {
    uint8_t px = level << 1, k, f;
    for (k = 0; k < 4; k++) {
        f = (px > 8) ? 8 : px;
        line[x + k] = T_METER + f;
        px -= f;
    }
}

static void home_card_summary(uint8_t v) {
    uint8_t *pp = patch[v];
    uint8_t t = voice_type[v];
    uint8_t x = 3;
    if (t == VT_PULSE) {
        lput(x, duty_names[pp[P_SHAPE] & 3], T_DIM);
        x += 6;
    } else if (t == VT_WAVE) {
        uint8_t m = pp[P_MODE];
        lput(x, mode_names[m >= WM_COUNT ? 0 : m], T_DIM);
        x += 7;
        if (m == WM_PULSE) lput(x - 1, duty_names[(pp[P_SHAPE] >> 2) & 3], T_DIM);
        else if (m == WM_SYNTH) lputn(x - 1, &shape_names[(uint16_t)(pp[P_SHAPE] & 15) * 6], 6, T_DIM);
        else if (m == WM_DUAL) lputn(x - 1, &dual_names[(uint16_t)(pp[P_SHAPE] & 15) * 6], 6, T_DIM);
        else if (m == WM_SING) lputn(x - 1, &phoneme_names[(uint16_t)pp[P_PHONEME] * 2], 2, T_DIM);
        if (pp[P_SPLIT] && m != WM_DRUMS) lput(13, "S", T_DIM);
    } else if (t == VT_NOISE) {
        lput(x, pp[P_SHAPE] ? "SHORT" : "LONG", T_DIM);
    } else {
        lput(x, "KIT", T_DIM);
        lputn(x + 4, &kit_names[(uint16_t)pp[P_SHAPE] * 6], 6, T_DIM);
    }
    if (t != VT_DRUM && voice[v].env_stage != ENV_IDLE && voice[v].note != NO_NOTE) {
        lnote(15, voice[v].note, 0);
    }
    note_shown[v] = (voice[v].env_stage != ENV_IDLE) ? voice[v].note : NO_NOTE;
}

static void draw_home_row(uint8_t y) {
    lclear();
    if (y == 0) {
        draw_header("FAT CHIP GB");
        line[19] = midi_activity ? T_NOTE : T_INVBLANK;
        act_shown = midi_activity ? 1 : 0;
    } else if (y >= 2 && y <= 16) {
        uint8_t v = (y - 2) / 3, r = (y - 2) % 3;
        if (r == 0) {
            uint8_t base = (v == sel) ? T_INV : 0;
            uint8_t i;
            if (v == sel) for (i = 0; i < 15; i++) line[i] = T_INVBLANK;
            line[0] = (v == sel) ? (uint8_t)('>' - 32 + T_INV) : 0;
            if (midi_ch[v] == CH_OFF) lput(1, "--", base);
            else lnum(midi_ch[v] < 9 ? 2 : 1, midi_ch[v] + 1, base);
            lput(4, type_short[v], base);
            lputn(8, &patch[v][PATCH_NAME_OFS], PATCH_NAME_LEN, base);
            meter_tiles(16, voice[v].meter);
            meter_shown[v] = voice[v].meter;
        } else if (r == 1) {
            home_card_summary(v);
        }
    } else if (y == 17) {
        if (flash) lput(1, flash_msg, 0);
        else lput(0, "A:EDIT SEL:PAT B:CH", T_DIM);
    }
    lflush(y);
}

static void draw_edit_row(uint8_t y) {
    lclear();
    if (y == 0) {
        draw_header("");
        lnum(1, sel + 1, T_INV);
        lput(3, type_long[sel], T_INV);
        lputn(11, &patch[sel][PATCH_NAME_OFS], PATCH_NAME_LEN, T_INV);
    } else if (y >= EDIT_FIRST && y < EDIT_FIRST + EDIT_ROWS) {
        uint8_t idx = escroll + (y - EDIT_FIRST);
        if (idx < pcount) {
            uint8_t p = plist[idx];
            uint8_t on = (idx == ecur);
            if (on) {
                uint8_t i;
                for (i = 0; i < 11; i++) line[i] = T_INVBLANK;
                line[0] = (uint8_t)('>' - 32 + T_INV);
            }
            lput(1, param_label(sel, p), on ? T_INV : T_DIM);
            lvalue(12, sel, p, 0);
            shown_val[idx] = patch[sel][p];
        }
        if (y == EDIT_FIRST && escroll) line[19] = (uint8_t)('^' - 32);
        if (y == EDIT_FIRST + EDIT_ROWS - 1 && escroll + EDIT_ROWS < pcount) line[19] = (uint8_t)('V' - 32 + T_DIM);
    } else if (y == 17) {
        if (flash) {
            lput(1, flash_msg, 0);
        } else if (ecur < pcount) {
            lput(0, "CC", T_DIM);
            lnum(2, param_cc[plist[ecur]], T_DIM);
            lput(7, "A+<>:FAST", T_DIM);
        }
    }
    lflush(y);
}

static void draw_patch_row(uint8_t y) {
    uint8_t name[PATCH_NAME_LEN];
    lclear();
    if (y == 0) {
        draw_header("PATCHES");
        lput(9, type_long[sel], T_INV);
    } else if (y >= 1 && y <= 16) {
        uint8_t s = y - 1;
        uint8_t on = (s == pcur);
        uint8_t base = on ? T_INV : 0;
        if (on) {
            uint8_t i;
            for (i = 0; i < 20; i++) line[i] = T_INVBLANK;
            line[0] = (uint8_t)('>' - 32 + T_INV);
        }
        if (s < 10) {
            lnum(1, 0, base);
            lnum(2, s, base);
        } else {
            lnum(1, s, base);
        }
        patch_slot_name(voice_type[sel], s, name);
        lputn(4, name, PATCH_NAME_LEN, base);
        if (s == patch_slot[sel]) lput(14, "*", base);
    } else if (y == 17) {
        if (flash) lput(1, flash_msg, 0);
        else lput(0, "A:LOAD SEL:SAVE B:<", T_DIM);
    }
    lflush(y);
}

static const char kb_chars[5][9] = {
    { 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I' },
    { 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R' },
    { 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '-' },
    { '0', '1', '2', '3', '4', '5', '6', '7', '8' },
    { '9', '.', '!', '?', '#', '+', '/', ' ', 0 },
};

static void draw_name_row(uint8_t y) {
    lclear();
    if (y == 0) {
        draw_header("SAVE TO SLOT");
        if (pcur < 10) lnum(14, 0, T_INV);
        lnum(pcur < 10 ? 15 : 14, pcur, T_INV);
    } else if (y == 3) {
        uint8_t i;
        lput(2, "NAME", T_DIM);
        line[7] = (uint8_t)('[' - 32);
        for (i = 0; i < PATCH_NAME_LEN; i++) {
            uint8_t c = nbuf[i];
            line[8 + i] = (uint8_t)(c - 32 + (i == npos ? T_INV : 0));
        }
        line[16] = (uint8_t)(']' - 32);
    } else if (y >= 6 && y <= 14 && !(y & 1)) {
        uint8_t r = (y - 6) >> 1, c;
        for (c = 0; c < 9; c++) {
            uint8_t ch = (uint8_t)kb_chars[r][c];
            uint8_t on = (r == ky && c == kx);
            uint8_t tile;
            if (ch == ' ') tile = T_SPACE;
            else if (ch == 0) tile = T_BACKSP;
            else tile = (uint8_t)(ch - 32 + (on ? T_INV : 0));
            if (on) line[1 + c * 2] = (ch && ch != ' ') ? T_INVBLANK : T_ARROW;
            line[2 + c * 2] = tile;
        }
    } else if (y == 16) {
        lput(0, "A:TYPE  B:DELETE", T_DIM);
    } else if (y == 17) {
        lput(0, "START:SAVE SEL:EXIT", T_DIM);
    }
    lflush(y);
}

/* ------------------------------------------------------------------ setup (MIDI channels) */
static uint8_t setup_base(void) {
    /* returns base channel (0-11) if voices are on consecutive channels, else 0xFF */
    uint8_t v;
    if (midi_ch[0] > 11) return 0xFF;
    for (v = 1; v < NUM_VOICES; v++)
        if (midi_ch[v] != midi_ch[0] + v) return 0xFF;
    return midi_ch[0];
}

static void draw_setup_row(uint8_t y) {
    lclear();
    if (y == 0) {
        draw_header("SETUP");
        lput(15, "V" VERSION_STR, T_INV);
    } else if (y >= 2 && y < 2 + SETUP_ITEMS) {
        uint8_t i = y - 2;
        uint8_t on = (i == scur);
        if (on) {
            uint8_t k;
            for (k = 0; k < 11; k++) line[k] = T_INVBLANK;
            line[0] = (uint8_t)('>' - 32 + T_INV);
        }
        if (i == 0) {
            uint8_t b = setup_base();
            lput(1, "SHIFT ALL", on ? T_INV : T_DIM);
            if (b == 0xFF) lput(12, "CUSTOM", 0);
            else {
                uint8_t x = lnum(12, b + 1, 0);
                lput(x, "-", 0);
                lnum(x + 1, b + 5, 0);
            }
        } else if (i == SI_VEL) {
            lput(1, "VELOCITY", on ? T_INV : T_DIM);
            lput(12, vel_names[vel_curve & 3], 0);
        } else if (i == SI_SCREEN) {
            lput(1, "SCREEN OFF", on ? T_INV : T_DIM);
            lput(12, "A:GO", 0);
        } else if (i == SI_MON) {
            lput(1, "MIDI MONITOR", on ? T_INV : T_DIM);
            lput(14, "A:GO", 0);
        } else {
            uint8_t v = i - 1;
            lput(1, type_long[v], on ? T_INV : T_DIM);
            if (midi_ch[v] == CH_OFF) lput(12, "OFF", 0);
            else {
                lput(12, "CH", 0);
                lnum(15, midi_ch[v] + 1, 0);
            }
        }
    } else if (y == 12) {
        lput(1, "SAME CH = LAYERED", T_DIM);
    } else if (y == 14) {
        lput(1, "ARDUINOBOY:KEEP 1-5", T_DIM);
    } else if (y == 15) {
        lput(1, "AND SET THE SHIFT", T_DIM);
    } else if (y == 16) {
        lput(1, "IN THE ARDUINOBOY", T_DIM);
    } else if (y == 17) {
        lput(0, "<>:CHANGE  B:BACK", T_DIM);
    }
    lflush(y);
}

static void handle_setup(uint8_t k) {
    uint8_t old = scur;
    if (k & J_UP && scur) scur--;
    if (k & J_DOWN && scur + 1 < SETUP_ITEMS) scur++;
    if (old != scur) {
        dirty[2 + old] = 1;
        dirty[2 + scur] = 1;
    }
    if (k & (J_LEFT | J_RIGHT)) {
        int8_t d = (k & J_LEFT) ? -1 : 1;
        uint8_t v;
        if (scur == SI_VEL) {
            vel_curve = (vel_curve + 4 + d) & 3;
        } else if (scur == SI_SCREEN || scur == SI_MON) {
            /* A activates */
        } else if (scur == 0) {
            uint8_t b = setup_base();
            int8_t nb = (b == 0xFF) ? 0 : (int8_t)b + d;
            if (nb < 0) nb = 0;
            if (nb > 11) nb = 11;
            panic_all();
            for (v = 0; v < NUM_VOICES; v++) midi_ch[v] = (uint8_t)nb + v;
        } else {
            v = scur - 1;
            /* cycle 1..16, OFF */
            panic_all();
            midi_ch[v] = (uint8_t)((midi_ch[v] + CH_OFF + 1 + d) % (CH_OFF + 1));
        }
        setup_changed = 1;
        for (v = 0; v < SETUP_ITEMS; v++) dirty[2 + v] = 1;
    }
    if (k & J_A) {
        if (scur == SI_SCREEN) {
            lcd_off = 1;
            DISPLAY_OFF;
        } else if (scur == SI_MON) {
            mon_shown = mon_count - 1;
            go(SCR_MON);
        }
    }
    if (k & J_B) {
        if (setup_changed) setup_save();
        setup_changed = 0;
        go(SCR_HOME);
    }
}

/* ------------------------------------------------------------------ MIDI monitor */
static void lhex(uint8_t x, uint8_t b) {
    static const char hx[] = "0123456789ABCDEF";
    line[x] = (uint8_t)(hx[b >> 4] - 32);
    line[x + 1] = (uint8_t)(hx[b & 15] - 32);
}

static void draw_mon_row(uint8_t y) {
    lclear();
    if (y == 0) {
        draw_header("MIDI MONITOR");
    } else if (y == 1) {
        lput(0, "CH MSG  DATA     VOX", T_DIM);
    } else if (y >= 2 && y < 2 + MON_LINES) {
        uint8_t age = y - 2;
        if (age < mon_count) {
            uint8_t *m = mon_msg[(mon_head + MON_LINES - age) % MON_LINES];
            uint8_t st = m[0], ch = st & 15, v, base = age ? 0 : T_INV;
            if (!age) {
                uint8_t i;
                for (i = 0; i < 20; i++) line[i] = T_INVBLANK;
            }
            lnum(ch < 9 ? 1 : 0, ch + 1, base);
            switch (st & 0xF0) {
            case 0x90:
                lput(3, m[2] ? "ON" : "OFF", base);
                lnote(8, m[1], base);
                if (m[2]) lnum(13, m[2], base);
                break;
            case 0x80: lput(3, "OFF", base); lnote(8, m[1], base); break;
            case 0xB0: lput(3, "CC", base); lnum(8, m[1], base); lnum(13, m[2], base); break;
            case 0xC0: lput(3, "PROG", base); lnum(8, m[1], base); break;
            case 0xE0:
                lput(3, "BEND", base);
                lsigned(8, (int16_t)((((uint16_t)m[2] << 7) | m[1]) - 8192), base);
                break;
            case 0xD0: lput(3, "PRES", base); lnum(8, m[1], base); break;
            case 0xA0: lput(3, "PAT", base); lnum(8, m[1], base); break;
            }
            for (v = 0; v < NUM_VOICES && midi_ch[v] != ch; v++) {}
            lput(17, v < NUM_VOICES ? type_short[v] : "--", base);
        }
    } else if (y == 15) {
        uint8_t i;
        lput(0, "RAW", T_DIM);
        for (i = 0; i < 5; i++) lhex(4 + i * 3, mon_raw[(mon_raw_head + 2 + i) % 6]);
    } else if (y == 16) {
        lput(0, "MESSAGES", T_DIM);
        lnum(9, (int16_t)(mon_count & 0x7FFF), 0);
    } else if (y == 17) {
        lput(0, "--:UNMAPPED  B:BACK", T_DIM);
    }
    lflush(y);
}

static void draw_row(uint8_t y) {
    switch (screen) {
    case SCR_HOME: draw_home_row(y); break;
    case SCR_EDIT: draw_edit_row(y); break;
    case SCR_PATCH: draw_patch_row(y); break;
    case SCR_SETUP: draw_setup_row(y); break;
    case SCR_MON: draw_mon_row(y); break;
    default: draw_name_row(y); break;
    }
}

/* ------------------------------------------------------------------ screen switching */
static void go(uint8_t s) {
    prev_screen = screen;
    screen = s;
    if (s == SCR_EDIT) build_plist();
    dirty_all();
}

static void show_flash(const char *msg) {
    flash_msg = msg;
    flash = 90;
    dirty[17] = 1;
}

static void audition_stop(void) {
    if (audition) {
        note_off(sel, audition - 1);
        audition = 0;
    }
}

static void audition_start(void) {
    uint8_t n = 60;
    if (sel == V_DRM) n = 36;
    else if (sel == V_WAV && patch[V_WAV][P_MODE] == WM_SPEECH) n = 40; /* AA */
    else if (sel == V_WAV && patch[V_WAV][P_MODE] == WM_DRUMS) n = 36;
    note_on(sel, n, 110);
    audition = n + 1;
}

/* ------------------------------------------------------------------ input */
static uint8_t read_keys(void) {
    uint8_t newp, dirs;
    keys = joypad();
    newp = keys & (uint8_t)~keys_prev;
    /* SELECT acts on release, so it can also be a modifier (SELECT+A/B/START) */
    if (newp & J_SELECT) sel_pending = 1;
    if ((keys & J_SELECT) && (newp & (uint8_t)~J_SELECT)) sel_pending = 0;
    newp &= (uint8_t)~J_SELECT;
    if (!(keys & J_SELECT) && (keys_prev & J_SELECT) && sel_pending) {
        newp |= J_SELECT;
        sel_pending = 0;
    }
    dirs = keys & (J_UP | J_DOWN | J_LEFT | J_RIGHT);
    if (dirs && dirs == (keys_prev & (J_UP | J_DOWN | J_LEFT | J_RIGHT))) {
        if (++rep >= 18) {
            rep = 14;
            newp |= dirs;
        }
    } else {
        rep = 0;
    }
    keys_prev = keys;
    return newp;
}

static void edit_change(int8_t dir) {
    uint8_t p = plist[ecur];
    uint8_t max = param_max[voice_type[sel]][p];
    int16_t v = patch[sel][p];
    int16_t step = 1;
    if (keys & J_A) {
        if (p == P_SPLIT || p == P_SPEECH_PITCH) step = 12;
        else if (max >= 24) step = 4;
        else if (max >= 8) step = 2;
    }
    if (p == P_SHAPE && voice_type[sel] == VT_WAVE && patch[sel][P_MODE] == WM_PULSE) {
        v = (v & ~3) + dir * 4; /* four duty zones of 4 */
        if (v > 15) v = 12;
    } else {
        v += dir * step;
    }
    if (v < 0) v = 0;
    if (v > max) v = max;
    if ((uint8_t)v != patch[sel][p]) param_set(sel, p, (uint8_t)v);
}

static void paste_sound(void) {
    uint8_t t = voice_type[sel], p, val, m;
    if (clip_type == 0xFF) {
        show_flash("NOTHING COPIED");
        return;
    }
    for (p = 0; p < NUM_PARAMS; p++) {
        m = param_max[t][p];
        if (m == NA || param_max[clip_type][p] == NA) continue;
        if (t != clip_type && (p == P_SHAPE || p == P_TIMBRE || p == P_MODE)) continue;
        val = clip[p];
        param_set(sel, p, val > m ? m : val);
    }
    memcpy(&patch[sel][PATCH_NAME_OFS], &clip[PATCH_NAME_OFS], PATCH_NAME_LEN);
    voice_refresh(sel);
    dirty[2 + sel * 3] = 1;
    dirty[3 + sel * 3] = 1;
    show_flash("PASTED");
}

static void handle_home(uint8_t k) {
    uint8_t old = sel;
    if (k & J_UP) sel = sel ? sel - 1 : NUM_VOICES - 1;
    if (k & J_DOWN) sel = (sel + 1) % NUM_VOICES;
    if (old != sel) {
        audition_stop();
        dirty[2 + old * 3] = 1;
        dirty[2 + sel * 3] = 1;
    }
    if (k & (J_LEFT | J_RIGHT)) {
        uint8_t s = patch_slot[sel];
        s = (k & J_LEFT) ? (s - 1) & 15 : (s + 1) & 15;
        patch_load(sel, s);
        dirty[2 + sel * 3] = 1;
        dirty[3 + sel * 3] = 1;
    }
    if ((keys & J_SELECT) && (k & J_B)) {
        memcpy(clip, patch[sel], PATCH_SIZE);
        clip_type = voice_type[sel];
        show_flash("COPIED");
    } else if ((keys & J_SELECT) && (k & J_A)) {
        paste_sound();
    } else if (k & J_A) go(SCR_EDIT);
    else if (k & J_B) {
        audition_stop();
        go(SCR_SETUP);
    }
    else if (k & J_SELECT) {
        pcur = patch_slot[sel];
        go(SCR_PATCH);
    }
}

static void handle_edit(uint8_t k) {
    uint8_t old = ecur;
    if (k & J_UP && ecur) ecur--;
    if (k & J_DOWN && ecur + 1 < pcount) ecur++;
    if (old != ecur) {
        if (ecur < escroll) {
            escroll = ecur;
            dirty_all();
        } else if (ecur >= escroll + EDIT_ROWS) {
            escroll = ecur - EDIT_ROWS + 1;
            dirty_all();
        } else {
            dirty[EDIT_FIRST + old - escroll] = 1;
            dirty[EDIT_FIRST + ecur - escroll] = 1;
        }
        dirty[17] = 1;
    }
    if (k & J_LEFT) edit_change(-1);
    if (k & J_RIGHT) edit_change(1);
    if (k & J_B) {
        audition_stop();
        go(SCR_HOME);
    } else if (k & J_SELECT) {
        pcur = patch_slot[sel];
        go(SCR_PATCH);
    }
}

static void handle_patch(uint8_t k) {
    uint8_t old = pcur;
    if (k & J_UP) pcur = (pcur - 1) & 15;
    if (k & J_DOWN) pcur = (pcur + 1) & 15;
    if (k & J_LEFT) pcur = (pcur - 8) & 15;
    if (k & J_RIGHT) pcur = (pcur + 8) & 15;
    if (old != pcur) {
        dirty[1 + old] = 1;
        dirty[1 + pcur] = 1;
    }
    if (k & J_A) {
        uint8_t prev = patch_slot[sel];
        patch_load(sel, pcur);
        dirty[1 + prev] = 1;
        dirty[1 + pcur] = 1;
        dirty[0] = 1;
        show_flash("LOADED");
    } else if (k & J_SELECT) {
        uint8_t i;
        memcpy(nbuf, &patch[sel][PATCH_NAME_OFS], PATCH_NAME_LEN);
        if (!memcmp(nbuf, "INIT    ", PATCH_NAME_LEN)) memset(nbuf, ' ', PATCH_NAME_LEN);
        npos = 0;
        for (i = 0; i < PATCH_NAME_LEN; i++)
            if (nbuf[i] != ' ') npos = i + 1;
        if (npos > PATCH_NAME_LEN - 1) npos = PATCH_NAME_LEN - 1;
        kx = ky = 0;
        go(SCR_NAME);
    } else if (k & J_B) {
        go(prev_screen == SCR_EDIT ? SCR_EDIT : SCR_HOME);
    }
}

static void handle_name(uint8_t k) {
    uint8_t oy = ky;
    if (k & J_UP) ky = ky ? ky - 1 : 4;
    if (k & J_DOWN) ky = (ky + 1) % 5;
    if (k & J_LEFT) kx = kx ? kx - 1 : 8;
    if (k & J_RIGHT) kx = (kx + 1) % 9;
    if (k & (J_UP | J_DOWN | J_LEFT | J_RIGHT)) {
        dirty[6 + oy * 2] = 1;
        dirty[6 + ky * 2] = 1;
    }
    if (k & J_A) {
        uint8_t ch = (uint8_t)kb_chars[ky][kx];
        if (ch == 0) {
            k |= J_B;
        } else {
            nbuf[npos] = ch;
            if (npos < PATCH_NAME_LEN - 1) npos++;
            dirty[3] = 1;
        }
    }
    if (k & J_B) {
        if (nbuf[npos] == ' ' && npos) npos--;
        nbuf[npos] = ' ';
        dirty[3] = 1;
    }
    if (k & J_START) {
        memcpy(&patch[sel][PATCH_NAME_OFS], nbuf, PATCH_NAME_LEN);
        patch_save(sel, pcur);
        go(SCR_PATCH);
        prev_screen = SCR_HOME;
        show_flash("SAVED!");
    } else if (k & J_SELECT) {
        go(SCR_PATCH);
    }
}

/* ------------------------------------------------------------------ public */
void ui_init(void) BANKED {
    DISPLAY_OFF;
    BGP_REG = 0xE4;
    LCDC_REG = LCDCF_OFF | LCDCF_BG8000 | LCDCF_BG9800 | LCDCF_BGON;
    load_ui_tiles();
    fill_bkg_rect(0, 0, 32, 32, 0);
    screen = SCR_HOME;
    prev_screen = SCR_HOME;
    sel = 0;
    memset(meter_shown, 0xFF, sizeof(meter_shown));
    memset(note_shown, 0xFE, sizeof(note_shown));
    {
        uint8_t y;
        for (y = 0; y < ROWS; y++) draw_row(y);
    }
    memset(dirty, 0, ROWS);
    SHOW_BKG;
    DISPLAY_ON;
}

void ui_tick(void) BANKED {
    uint8_t k = read_keys();
    uint8_t budget, y, v;

    if (lcd_off) {
        if (midi_activity) midi_activity--;
        ui_dirty_params = 0;
        if (k) { /* any button wakes the screen */
            lcd_off = 0;
            DISPLAY_ON;
            dirty_all();
        }
        return;
    }

    /* START auditions the selected channel (hold to sustain) */
    if ((keys & J_SELECT) && (k & J_START)) {
        audition = 0;
        panic_all();
        show_flash("PANIC: ALL OFF");
        k = 0;
    }
    if ((k & J_START) && screen != SCR_NAME) audition_start();
    if (audition && !(keys & J_START)) audition_stop();

    switch (screen) {
    case SCR_HOME: handle_home(k); break;
    case SCR_EDIT: handle_edit(k); break;
    case SCR_PATCH: handle_patch(k); break;
    case SCR_SETUP: handle_setup(k); break;
    case SCR_MON:
        if (k & J_B) go(SCR_SETUP);
        break;
    default: handle_name(k); break;
    }

    if (flash && !--flash) dirty[17] = 1;
    if (midi_activity) midi_activity--;

    /* live updates from MIDI */
    if (screen == SCR_HOME) {
        if ((midi_activity ? 1 : 0) != act_shown) dirty[0] = 1;
        for (v = 0; v < NUM_VOICES; v++) {
            uint8_t n = (voice[v].env_stage != ENV_IDLE) ? voice[v].note : NO_NOTE;
            if (ui_dirty_params & (1 << v)) {
                dirty[2 + v * 3] = 1;
                dirty[3 + v * 3] = 1;
            }
            if (n != note_shown[v]) dirty[3 + v * 3] = 1;
            if (voice[v].meter != meter_shown[v] && !dirty[2 + v * 3]) {
                /* meters: just the four tiles */
                meter_tiles(0, voice[v].meter);
                set_bkg_tiles(16, 2 + v * 3, 4, 1, line);
                meter_shown[v] = voice[v].meter;
            }
        }
        ui_dirty_params = 0;
    } else if (screen == SCR_EDIT) {
        if (ui_dirty_params & (1 << sel)) {
            uint8_t i;
            if (patch[sel][P_MODE] != plist_mode) {
                build_plist();
                dirty_all();
            } else {
                for (i = 0; i < pcount; i++) {
                    if (shown_val[i] != patch[sel][plist[i]] && i >= escroll && i < escroll + EDIT_ROWS)
                        dirty[EDIT_FIRST + i - escroll] = 1;
                }
                dirty[0] = 1;
            }
        }
        ui_dirty_params = 0;
    } else {
        ui_dirty_params = 0;
        if (screen == SCR_MON && mon_count != mon_shown) {
            mon_shown = mon_count;
            for (y = 2; y < 2 + MON_LINES; y++) dirty[y] = 1;
            dirty[15] = 1;
            dirty[16] = 1;
        }
    }

    /* redraw a few dirty rows per frame */
    budget = 4;
    for (y = 0; y < ROWS && budget; y++) {
        if (dirty[y]) {
            dirty[y] = 0;
            draw_row(y);
            budget--;
            midi_poll();
        }
    }
}
