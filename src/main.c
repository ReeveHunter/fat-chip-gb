/* Fat Chip GB (formerly gbmidi) - MIDI-controlled Game Boy synth
 * main loop + MIDI parser (fixed bank)
 */
#include <gb/gb.h>
#include <gb/isr.h>
#include "engine.h"
#include "gen/font.h"

ISR_VECTOR(VECTOR_SERIAL, sio_isr)
ISR_VECTOR(VECTOR_TIMER, tim_isr)

volatile uint8_t vbl_flag;
uint8_t midi_activity;

static uint8_t m_status, m_need, m_n, m_d0;

/* link test counters */
uint16_t lt_bytes, lt_noteon, lt_cc, lt_bend, lt_clock, lt_stray;
uint8_t lt_start, lt_cont, lt_stop, lt_sense;
uint8_t lt_sx_start, lt_sx_end, lt_sx_sum;
uint16_t lt_sx_len;
static uint8_t lt_in_sx, lt_sx_cursum;
static uint16_t lt_sx_curlen;

void link_test_reset(void) {
    lt_bytes = lt_noteon = lt_cc = lt_bend = lt_clock = lt_stray = 0;
    lt_start = lt_cont = lt_stop = lt_sense = 0;
    lt_sx_start = lt_sx_end = lt_sx_sum = 0;
    lt_sx_len = 0;
    lt_in_sx = 0;
}

static void vbl(void) {
    vbl_flag = 1;
}

uint8_t midi_ch[NUM_VOICES] = { 0, 1, 2, 3, 4 };
uint8_t vel_curve;
uint8_t mon_msg[MON_LINES][3];
uint8_t mon_head;
uint16_t mon_count;
uint8_t mon_raw[6];
uint8_t mon_raw_head;

static uint8_t apply_curve(uint8_t v) {
    uint16_t x;
    switch (vel_curve) {
    case VEL_SOFT:
        x = 127 - v;
        return (uint8_t)(127 - ((x * x) >> 7));
    case VEL_HARD:
        x = ((uint16_t)v * v) >> 7;
        return x ? (uint8_t)x : 1;
    case VEL_FIXED:
        return 127;
    }
    return v;
}

static void midi_dispatch(uint8_t st, uint8_t d0, uint8_t d1) {
    uint8_t ch = st & 0x0F;
    uint8_t v;
    /* compare-and-wrap: % compiles to a slow software divide on the SM83 */
    if (++mon_head >= MON_LINES) mon_head = 0;
    mon_msg[mon_head][0] = st;
    mon_msg[mon_head][1] = d0;
    mon_msg[mon_head][2] = d1;
    mon_count++;
    switch (st & 0xF0) {
    case 0x90: if (d1) lt_noteon++; break;
    case 0xB0: lt_cc++; break;
    case 0xE0: lt_bend++; break;
    }
    if ((st & 0xF0) == 0x90 && d1) d1 = apply_curve(d1);
    for (v = 0; v < NUM_VOICES; v++) {
        if (midi_ch[v] != ch) continue;
        midi_activity = 8;
        switch (st & 0xF0) {
        case 0x90: note_on(v, d0, d1); break;
        case 0x80: note_off(v, d0); break;
        case 0xB0: control_change(v, d0, d1); break;
        case 0xE0: pitch_bend(v, ((uint16_t)d1 << 7) | d0); break;
        case 0xC0: patch_load(v, d0 & 15); break;
        default: break;
        }
    }
}

void panic_all(void) {
    uint8_t v;
    for (v = 0; v < NUM_VOICES; v++) {
        all_notes_off(v);
        voice[v].bend_raw = 8192;
        voice[v].bend = 0;
    }
}

static void midi_byte(uint8_t b) {
    if (b & 0x80) {
        if (b >= 0xF8) {         /* realtime: count, keep running status */
            switch (b) {
            case 0xF8: lt_clock++; break;
            case 0xFA: lt_start++; break;
            case 0xFB: lt_cont++; break;
            case 0xFC: lt_stop++; break;
            case 0xFE: lt_sense++; break;
            }
            return;
        }
        if (b == 0xF0) {         /* sysex start */
            lt_sx_start++;
            lt_in_sx = 1;
            lt_sx_curlen = 0;
            lt_sx_cursum = 0;
            m_status = 0;
            return;
        }
        if (b == 0xF7 && lt_in_sx) { /* sysex end: keep its length and checksum */
            lt_sx_end++;
            lt_sx_len = lt_sx_curlen;
            lt_sx_sum = lt_sx_cursum;
        }
        lt_in_sx = 0;            /* any other status byte ends a sysex */
        if (b >= 0xF0) {         /* system common: cancel running status */
            m_status = 0;
            return;
        }
        m_status = b;
        m_n = 0;
        m_need = ((b & 0xE0) == 0xC0) ? 1 : 2; /* Cx, Dx take one data byte */
        return;
    }
    if (lt_in_sx) {
        lt_sx_curlen++;
        lt_sx_cursum += b;
        return;
    }
    if (!m_status) {
        lt_stray++;              /* data byte with no status: something was dropped */
        return;
    }
    if (m_n == 0) {
        m_d0 = b;
        if (m_need == 1) {
            midi_dispatch(m_status, b, 0);
            return;
        }
        m_n = 1;
        return;
    }
    m_n = 0;
    midi_dispatch(m_status, m_d0, b);
}

void midi_poll(void) {
    while (rx_tail != rx_head) {
        uint8_t b;
        rx_tail++;
        b = RX_BUF[rx_tail];
        lt_bytes++;
        if (++mon_raw_head >= 6) mon_raw_head = 0;
        mon_raw[mon_raw_head] = b;
        midi_byte(b);
    }
    if (st_done) {
        st_done = 0;
        stream_finished();
    }
}

static uint8_t div_last;
static uint16_t div_acc;

extern const uint8_t ui_tiles[];
void load_ui_tiles(void) {
    uint8_t save = _current_bank;
    SWITCH_ROM(FONT_BANK);
    set_bkg_data(0, UI_TILE_COUNT, ui_tiles);
    SWITCH_ROM(save);
}

void main(void) {
    disable_interrupts();
    rx_head = 0;
    rx_tail = 0;
    link_test_reset();
    synth_init();
    patches_init();
    setup_load();
    ui_init();

    add_VBL(vbl);
    SC_REG = 0x80; /* serial: external clock (Arduinoboy), armed */
    set_interrupts(VBL_IFLAG | TIM_IFLAG | SIO_IFLAG);
    enable_interrupts();

    while (1) {
        uint8_t tick = 0;
        midi_poll();
        if (LCDC_REG & LCDCF_ON) {
            div_last = DIV_REG;
            if (vbl_flag) {
                vbl_flag = 0;
                tick = 1;
            }
        } else {
            /* screen off: no VBlank interrupt, so pace ticks from DIV (16384 Hz) */
            uint8_t d = DIV_REG;
            div_acc += (uint8_t)(d - div_last);
            div_last = d;
            if (div_acc >= 274) {
                div_acc -= 274;
                tick = 1;
            }
        }
        if (tick) {
            synth_tick();
            midi_poll();
            ui_tick();
        }
    }
}
