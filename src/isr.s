; Fat Chip GB - interrupt handlers and wave RAM loader (fixed bank)
;
; sio_isr : one MIDI byte per serial interrupt (Arduinoboy clocks us, external clock)
; tim_isr : streams 32-sample chunks of drum samples into wave RAM (two hits mixed)
; wave_commit : DMG-safe wave RAM load (DAC off, copy, DAC on, retrigger)

        .module isr

        SB      = 0x01
        SC      = 0x02
        NR30    = 0x1A
        NR50    = 0x24
        NR33    = 0x1D
        NR34    = 0x1E
        RX_PAGE = 0xDC
        MIXPAGE = 0xDB          ; drum_mixtab, copied here at start (synth_init)

        .globl  __current_bank

        .area   _DATA
_rx_head::      .ds 1
_rx_tail::      .ds 1
_st_active::    .ds 1
_st_done::      .ds 1
_st_busy::      .ds 1
_st_nr34::      .ds 1
_ds_bank::      .ds 2
_ds_left::      .ds 2
_ds_slot::      .ds 2
_ds_ptr::       .ds 4
_nxt_mask::     .ds 1
_nxt_buf::      .ds 32
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
; Two streams (two drum hits from the same kit), each a bank, a pointer and the
; chunks (32 samples) left. One stream playing: its next chunk goes straight from
; ROM into wave RAM, as cheap as a single sample stream. Both playing: _nxt_buf
; holds the next chunk already mixed, so the ISR only loads it, then turns
; interrupts back on (MIDI keeps coming) and mixes the chunk after it.
_tim_isr::
        push    af
        push    hl              ; v0.18: walk the master volume a step towards
        ld      hl,#_nr50_cur   ; the tremolo's target (both sides at once)
        ld      a,(_nr50_tgt)
        cp      (hl)
        jr      z,8$
        ld      a,(hl)
        jr      c,7$            ; (target below: down)
        add     a,#0x11
        jr      6$
7$:
        sub     #0x11
6$:
        ld      (hl),a
        ldh     (NR50),a
8$:
        pop     hl
        ld      a,(_st_active)
        or      a
        jr      z,9$
        ld      a,(_st_busy)
        or      a
        jr      nz,9$
        inc     a
        ld      (_st_busy),a
        push    bc
        push    de
        push    hl
        call    _drum_next
        ei
        call    _drum_mix       ; (only if both still play)
        xor     a
        ld      (_st_busy),a
        pop     hl
        pop     de
        pop     bc
9$:
        pop     af
        reti

; drum_next: play the next chunk: the mixed one if ready, else the one stream's
; straight from ROM. Ends the stream (st_active 0, st_done 1) after its last chunk.
_drum_next::
        ld      a,(_nxt_mask)
        or      a
        jr      z,1$
        xor     a
        ld      (_nxt_mask),a
        ld      hl,#_nxt_buf+1  ; (the mixed bytes are the odd ones)
        xor     a
        ldh     (NR30),a
        ld      c,#0x30
        .rept   16
        ld      a,(hl+)
        inc     hl
        ldh     (c),a
        inc     c
        .endm
        jr      5$
1$:
        ld      de,#_ds_left
        ld      a,(de)
        or      a
        jr      nz,2$
        inc     de              ; stream 1
        ld      a,(de)
        or      a
        jr      z,6$
2$:
        dec     a
        ld      (de),a
        ld      a,e
        sub     #<_ds_left      ; 0 or 1
        ld      c,a
        ld      b,#0
        ld      hl,#_ds_bank
        add     hl,bc
        ld      a,(hl)
        ld      hl,#_ds_ptr
        add     hl,bc
        add     hl,bc
        push    hl
        ld      b,a
        ldh     a,(__current_bank)
        ld      e,a
        ld      a,b
        ld      (#0x2000),a
        ld      a,(hl+)
        ld      h,(hl)
        ld      l,a
        xor     a
        ldh     (NR30),a
        ld      c,#0x30
        .rept   16
        ld      a,(hl+)
        ldh     (c),a
        inc     c
        .endm
        ld      a,e
        ld      (#0x2000),a     ; the caller's ROM bank
        ld      b,h
        ld      a,l
        pop     hl
        ld      (hl+),a
        ld      (hl),b
5$:
        ld      a,#0x80
        ldh     (NR30),a
        ld      a,(_st_nr34)
        ldh     (NR34),a        ; retrigger
        ld      a,(_ds_left)
        ld      b,a
        ld      a,(_ds_left+1)
        or      b
        ret     nz
        ld      a,(_nxt_mask)
        or      a
        ret     nz
6$:
        xor     a
        ld      (_st_active),a
        inc     a
        ld      (_st_done),a
        ret

; drum_mix: if both streams have a chunk left, mix them into _nxt_buf (stream 0
; in the even bytes, stream 1 in the odd ones, the result in the odd ones) and
; set _nxt_mask; else leave _nxt_mask 0
_drum_mix::
        ld      a,(_ds_left)
        or      a
        ret     z
        ld      a,(_ds_left+1)
        or      a
        ret     z
        ldh     a,(__current_bank)
        push    af
        ld      hl,#_ds_left
        dec     (hl)
        inc     hl
        dec     (hl)
        ld      a,(_ds_bank)
        ld      (#0x2000),a
        ld      hl,#_ds_ptr
        ld      de,#_nxt_buf
        call    copy16
        ld      a,(_ds_bank+1)
        ld      (#0x2000),a
        ld      hl,#_ds_ptr+2
        ld      de,#_nxt_buf+1
        call    copy16
        ; each byte holds two samples; the table adds two samples
        ld      hl,#_nxt_buf
        ld      d,#MIXPAGE
3$:
        .rept   2
        ld      a,(hl+)         ; A = [a0 a1]
        swap    a
        ld      c,a             ; S = [a1 a0]
        ld      a,(hl)          ; B = [b0 b1]
        xor     c
        ld      b,a             ; X = B ^ S
        and     #0x0F
        xor     c               ; [a1 b1]
        ld      e,a
        ld      a,(de)
        ld      (hl),a          ; (the low result, for a moment)
        ld      a,b
        and     #0xF0
        xor     c               ; [b0 a0] (the table is symmetric)
        ld      e,a
        ld      a,(de)
        swap    a
        or      (hl)
        ld      (hl+),a
        .endm
        ld      a,l
        cp      #<(_nxt_buf+32)
        jr      nz,3$
        ld      a,#3
        ld      (_nxt_mask),a
        pop     af
        ld      (#0x2000),a     ; the caller's ROM bank
        ret

; copy16: the 16 bytes at the stream pointer stored at (hl) -> every other byte
; from (de); the pointer advances
copy16:
        push    hl
        ld      a,(hl+)
        ld      h,(hl)
        ld      l,a
        .rept   16
        ld      a,(hl+)
        ld      (de),a
        inc     de
        inc     de
        .endm
        ld      b,h
        ld      a,l
        pop     hl
        ld      (hl+),a
        ld      (hl),b
        ret

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
