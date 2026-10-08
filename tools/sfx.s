; =============================================================================
; BB-LAN self-extracting loader (used by tools/pack.py)
; =============================================================================
; PRG layout (load $0801):
;   BASIC "10 SYS2061" -> stub: copy unpacker (+raw tail) to $0200, jump there
;   unpacker ($0200): with all RAM banked in ($01=$34)
;     1. move compressed blob up so it ends at BLOB_END
;     2. LZ-decompress forward to $0400 (in place, pack.py checks overlap)
;     3. copy the raw tail bytes (if any) behind the output
;     4. $01=$35, jump to ENTRY
;
; Stream format:
;   $00-$7F  literal run, n+1 bytes follow
;   $80-$FF  match, length (t & $7F)+3, followed by 16-bit distance (lo, hi)
;   Decoding stops when dst reaches OUT_END (no end marker).
;
; Constants passed with -D: ENTRY, BLOB_END, OUT_END, CLEN, TAIL_LEN
; =============================================================================

src     = $02
dst     = $04
mptr    = $06
cnt     = $08

OUT_START = $0400

.segment "LOADADDR"
        .word   $0801

.segment "STUB"
        .word   basic_end
        .word   10
        .byte   $9E, "2061", 0
basic_end:
        .word   0

        sei
        lda     #$0B                    ; blank screen while unpacking
        sta     $D011
        ldx     #0
@copy:  lda     __UNPACK_LOAD__,x
        sta     __UNPACK_RUN__,x
        lda     __UNPACK_LOAD__ + $100,x
        sta     __UNPACK_RUN__ + $100,x
        inx
        bne     @copy
        jmp     unpack

.import __UNPACK_LOAD__, __UNPACK_RUN__, __BLOB_LOAD__

.segment "UNPACK"
unpack:
        lda     #$34
        sta     $01

        ; --- 1. move blob up: [BLOB_LOAD, +CLEN) -> [BLOB_END-CLEN, BLOB_END)
        ; full pages from the top down, then the remainder at the bottom
        lda     #<(__BLOB_LOAD__ + CLEN - $100)
        sta     src
        lda     #>(__BLOB_LOAD__ + CLEN - $100)
        sta     src+1
        lda     #<(BLOB_END - $100)
        sta     dst
        lda     #>(BLOB_END - $100)
        sta     dst+1
        ldx     #>CLEN
        beq     @rest
@page:  ldy     #$FF
@pb:    lda     (src),y
        sta     (dst),y
        dey
        cpy     #$FF
        bne     @pb
        dec     src+1
        dec     dst+1
        dex
        bne     @page
@rest:
.if <CLEN <> 0
        lda     #<__BLOB_LOAD__
        sta     src
        lda     #>__BLOB_LOAD__
        sta     src+1
        lda     #<(BLOB_END - CLEN)
        sta     dst
        lda     #>(BLOB_END - CLEN)
        sta     dst+1
        ldy     #<CLEN - 1
@rb:    lda     (src),y
        sta     (dst),y
        dey
        cpy     #$FF
        bne     @rb
.endif

        ; --- 2. decompress
        lda     #<(BLOB_END - CLEN)
        sta     src
        lda     #>(BLOB_END - CLEN)
        sta     src+1
        lda     #<OUT_START
        sta     dst
        lda     #>OUT_START
        sta     dst+1
loop:
        lda     dst+1
        cmp     #>OUT_END
        bne     @go
        lda     dst
        cmp     #<OUT_END
        beq     done
@go:    ldy     #0
        lda     (src),y
        bmi     match

        sta     cnt                     ; literal: cnt = len-1
        inc     src
        bne     @l0
        inc     src+1
@l0:    ldy     #0
@lit:   lda     (src),y
        sta     (dst),y
        iny
        cpy     cnt
        bcc     @lit
        beq     @lit
        tya                             ; src += len
        clc
        adc     src
        sta     src
        bcc     advance
        inc     src+1
        jmp     advance

match:
        and     #$7F
        clc
        adc     #2
        sta     cnt                     ; cnt = len-1
        iny
        sec
        lda     dst
        sbc     (src),y
        sta     mptr
        iny
        lda     dst+1
        sbc     (src),y
        sta     mptr+1
        lda     src                     ; src += 3
        clc
        adc     #3
        sta     src
        bcc     @m0
        inc     src+1
@m0:    ldy     #0
@mc:    lda     (mptr),y
        sta     (dst),y
        iny
        cpy     cnt
        bcc     @mc
        beq     @mc

advance:                                ; dst += y
        tya
        clc
        adc     dst
        sta     dst
        bcc     loop
        inc     dst+1
        jmp     loop

done:
        ; --- 3. raw tail
.if TAIL_LEN > 0
        ldy     #0
@t:     lda     tail,y
        sta     OUT_END,y
        iny
        cpy     #TAIL_LEN
        bne     @t
.endif
        ; --- 4. start the game
        lda     #$35
        sta     $01
        jmp     ENTRY

tail:
        .incbin "sfx-tail.bin"

.segment "BLOB"
        .incbin "sfx-blob.bin"
