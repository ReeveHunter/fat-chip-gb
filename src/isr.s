; gbmidi - interrupt handlers and wave RAM loader (fixed bank)
;
; sio_isr : one MIDI byte per serial interrupt (Arduinoboy clocks us, external clock)
; tim_isr : streams 32-sample chunks of drum samples into wave RAM
; wave_commit : DMG-safe wave RAM load (DAC off, copy, DAC on, retrigger)

        .module isr

        SB      = 0x01
        SC      = 0x02
        NR30    = 0x1A
        NR33    = 0x1D
        NR34    = 0x1E
        RX_PAGE = 0xDC

        .globl  __current_bank

        .area   _DATA
_rx_head::      .ds 1
_rx_tail::      .ds 1
_st_active::    .ds 1
_st_done::      .ds 1
_st_bank::      .ds 1
_st_left::      .ds 1
_st_nr34::      .ds 1
_st_ptr::       .ds 2
_wave_buf::     .ds 16
_wv_nr33::      .ds 1
_wv_nr34::      .ds 1

        .area   _CODE

; ------------------------------------------------------------------ serial
_sio_isr::
        push    af
        push    hl
        ld      a,(_rx_head)
        inc     a
        ld      (_rx_head),a
        ld      l,a
        ld      h,#RX_PAGE
        ldh     a,(SB)
        ld      (hl),a
        ld      a,#0x80         ; re-arm: external clock, start
        ldh     (SC),a
        pop     hl
        pop     af
        reti

; ------------------------------------------------------------------ timer: sample stream
_tim_isr::
        push    af
        ld      a,(_st_active)
        or      a
        jr      z,9$
        push    bc
        push    hl
        ldh     a,(__current_bank)
        push    af
        ld      a,(_st_bank)
        ld      (#0x2000),a
        ld      hl,#_st_ptr
        ld      a,(hl+)
        ld      h,(hl)
        ld      l,a
        xor     a
        ldh     (NR30),a        ; DAC off -> wave RAM safely writable on DMG
        ld      c,#0x30
        .rept   16
        ld      a,(hl+)
        ldh     (c),a
        inc     c
        .endm
        ld      a,#0x80
        ldh     (NR30),a
        ld      a,(_st_nr34)
        ldh     (NR34),a        ; retrigger
        ld      a,l
        ld      (_st_ptr),a
        ld      a,h
        ld      (_st_ptr+1),a
        pop     af
        ld      (#0x2000),a     ; restore caller's ROM bank
        ld      hl,#_st_left
        dec     (hl)
        jr      nz,8$
        xor     a
        ld      (_st_active),a
        inc     a
        ld      (_st_done),a
8$:
        pop     hl
        pop     bc
9$:
        pop     af
        reti

; ------------------------------------------------------------------ wave_commit
; Loads _wave_buf into wave RAM, writes NR33/NR34 (with trigger).
_wave_commit::
        di
        ld      hl,#_wave_buf
        xor     a
        ldh     (NR30),a
        ld      c,#0x30
        .rept   16
        ld      a,(hl+)
        ldh     (c),a
        inc     c
        .endm
        ld      a,#0x80
        ldh     (NR30),a
        ld      a,(_wv_nr33)
        ldh     (NR33),a
        ld      a,(_wv_nr34)
        or      #0x80
        ldh     (NR34),a
        ei
        ret
