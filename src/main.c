/* gbmidi - MIDI-controlled Game Boy synth
 * main loop + MIDI parser (fixed bank)
 */
#include <gb/gb.h>
#include <gb/isr.h>
#include "engine.h"

ISR_VECTOR(VECTOR_SERIAL, sio_isr)
ISR_VECTOR(VECTOR_TIMER, tim_isr)

volatile uint8_t vbl_flag;
uint8_t midi_activity;

static uint8_t m_status, m_need, m_n, m_d0;

static void vbl(void) {
    vbl_flag = 1;
}

uint8_t midi_ch[NUM_VOICES] = { 0, 1, 2, 3, 4 };

static void midi_dispatch(uint8_t st, uint8_t d0, uint8_t d1) {
    uint8_t ch = st & 0x0F;
    uint8_t v;
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
        if (b >= 0xF8) return;   /* realtime: ignore, keep running status */
        if (b >= 0xF0) {         /* sysex / common: cancel running status */
            m_status = 0;
            return;
        }
        m_status = b;
        m_n = 0;
        m_need = ((b & 0xE0) == 0xC0) ? 1 : 2; /* Cx, Dx take one data byte */
        return;
    }
    if (!m_status) return;
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
        rx_tail++;
        midi_byte(RX_BUF[rx_tail]);
    }
    if (st_done) {
        st_done = 0;
        stream_finished();
    }
}

void main(void) {
    disable_interrupts();
    rx_head = 0;
    rx_tail = 0;
    synth_init();
    patches_init();
    setup_load();
    ui_init();

    add_VBL(vbl);
    SC_REG = 0x80; /* serial: external clock (Arduinoboy), armed */
    set_interrupts(VBL_IFLAG | TIM_IFLAG | SIO_IFLAG);
    enable_interrupts();

    while (1) {
        midi_poll();
        if (vbl_flag) {
            vbl_flag = 0;
            synth_tick();
            midi_poll();
            ui_tick();
        }
    }
}
