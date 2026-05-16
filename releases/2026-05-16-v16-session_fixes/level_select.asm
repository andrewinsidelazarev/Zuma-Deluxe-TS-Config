; ============================================================================
; LEVEL SELECT — экран выбора уровня (Scene=1).
;
;   LevelSelect_Init     — один раз: scene canvas → A + B, palette swap, draw dispname.
;   LevelSelect_Update   — клавиатура (O/P=stage ←/→, SPACE=PLAY).
;   LevelSelect_Render   — page swap (overlay в _Init или при O/P смене).
;   LevelSelect_GotoGame — Scene 1→0: restore level_01 canvas + palette.
; ============================================================================

LVLSEL_SRC_PAGE_BASE  EQU #54    ; spgbld pages #54..#5C (scene 360×288)
LVLSEL_BG_BACKUP_BASE EQU #30    ; level_01_canvas backup (для restore при PLAY)
LVLSEL_ZX7_PAGE_BASE  EQU #70    ; compressed scene_levelsel pages #70..#78
LVL01_ZX7_PAGE_BASE   EQU #80    ; compressed level_01 pages #80..#88
LVLSEL_SKY_PAGE_BASE   EQU #19   ; 4 pages: sky 480×100 stride 512 (visible 360w)
LVLSEL_PYR_PAGE_BASE   EQU #29   ; 4 pages: pyramid_overlay 360×100 stride 512
LVLSEL_SKY_BAND_H      EQU 100   ; высота анимированной зоны sky+pyramid
LVLSEL_SKY_MAX_SCROLL  EQU 120   ; sky 480 - canvas 360 = 120 px X-range
LVLSEL_BAND_BURST_LEN  EQU 180-1 ; DMALEN = 180 words (360 bytes) burst, S_ALGN→stride 512
LVLSEL_BTN_NONE        EQU #FF
LVLSEL_BTN_BACK        EQU 0
LVLSEL_BTN_PLAY        EQU 1
LVLSEL_BTN_NEXT        EQU 2
LVLSEL_BTN_STATE_EMPTY EQU 3
LVLSEL_BTN_DESC_BASE   EQU #0350
LVLSEL_BTN_SPAL        EQU 3
LVLSEL_BTN_Y           EQU 266
LVLSEL_BTN_H           EQU 24
LVLSEL_BACK_X          EQU 96
LVLSEL_PLAY_X          EQU 155
LVLSEL_NEXT_X          EQU 225
LVLSEL_BACK_W          EQU 56
LVLSEL_PLAY_W          EQU 64
LVLSEL_NEXT_W          EQU 56
; DEBUG/TEMP: PLAY hitbox is deliberately wider while hardware alignment is checked.
LVLSEL_BACK_HIT_X      EQU 76
LVLSEL_PLAY_HIT_X      EQU 138
LVLSEL_NEXT_HIT_X      EQU 230
LVLSEL_BACK_HIT_W      EQU 56
LVLSEL_PLAY_HIT_W      EQU 84
LVLSEL_NEXT_HIT_W      EQU 56
LVLSEL_BACK_TNUM       EQU 3096
LVLSEL_PLAY_TNUM       EQU 3608
LVLSEL_NEXT_TNUM       EQU 3800

; Dispname atlas — две page'а (page A=#4E rows 0-1, page B=#4F rows 2-3).
; Каждая строка stride = 512 байт (= canvas stride), height = 11 lines.
; Row stride within page = 11*512 = #1600.
LVLSEL_DISPNAME_PAGE_A EQU #4E
LVLSEL_DISPNAME_PAGE_B EQU #4F

LVLSEL_DISPNAME_X      EQU 108         ; (360-144)/2 = 108
LVLSEL_DISPNAME_Y      EQU 149         ; 11 lines = 149..159, все в page #14
LVLSEL_DISPNAME_H      EQU 11
LVLSEL_DISPNAME_DST_LO EQU #6C         ; ((149-128)*512 + 108) & 0xFF = 10860 = #2A6C
LVLSEL_DISPNAME_DST_HI EQU #2A
LVLSEL_DISPNAME_DST_PG_OFF EQU 4       ; CANVAS_*_PAGE_BASE + 4

; --- Preview level (TSU sprites над scene canvas) ---
; 5×4 спрайтов 32×32 = 160×128 px, занимает TSU pages #0C+#0D (sprite rows 0,1
; в #0C; rows 2,3 в #0D). При LevelSelect_Init LDIR copy из #52 → #0C, #53 → #0D.
; #0D перезаписывает LVLINTRO atlas — восстанавливается в LevelSelect_GotoGame.
; SPAL=0 → CRAM #00..#0F (32 bytes palette), не пересекается с cursor SPAL=1.
PREVIEW_SRC_PAGE_C    EQU #52    ; level 1 preview tiles (overlaid с mini-frog/kz)
PREVIEW_SRC_PAGE_D    EQU #53
PREVIEW_L2_PAGE_C     EQU #62    ; level 2 preview tiles
PREVIEW_L2_PAGE_D     EQU #63
PREVIEW_SPAL          EQU 0
PREVIEW_X             EQU 89          ; sprite area 192×120, точно матчит клики X=92..277 Y=140..259 (visible 186×120 с pad_X=3)
PREVIEW_Y             EQU 140
PREVIEW_COLS          EQU 3
PREVIEW_ROWS          EQU 15
PREVIEW_SPRITE_W      EQU 64
PREVIEW_SPRITE_H      EQU 8
; 45 sprites × 6 = 270 байт. От #0200 ends at #030E. Cursor at #03F8 (как раньше).
PREVIEW_DESC_BASE     EQU #0200
PREVIEW_NUM_SPRITES   EQU PREVIEW_COLS * PREVIEW_ROWS    ; 45

; Dispname TSU sprites — текст уровня поверх preview.
; SFILE Z-order (нижний адрес behind, верхний on top):
;   #0200..#030D preview (45)
;   #030E..#0353 (раньше здесь dispname — теперь перенесён на #0380)
;   #0350..#0367 buttons (Codex, 3)
;   #0368..#0373 mini-frog/kz (2)
;   #0380..#03C1 DISPNAME (11) — теперь LAST → рендерится поверх mini-frog/kz
;   #03F8.. CURSOR
DISPNAME_DESC_BASE    EQU #0380         ; перенесён после mini-sprites для top Z-order
DISPNAME_NUM_SPRITES  EQU 11
DISPNAME_SPAL         EQU 2
DISPNAME_X            EQU 96
DISPNAME_Y            EQU 145
DISPNAME_TNUM_BASE    EQU 3352          ; page #0C cy=4 cx=24 (3072+4*64+24)


; --- State ---
CurStageIdx:             DB 0    ; 0..12
LvlInStage:              DB 0
MaxUnlockedStage:        DB 12
LevelSelectKeyPrev:      DB 0
LevelSelectKeySpacePrev: DB 0
LevelSelectMousePrev:    DB 0
LevelSelectActionMask:   DB 0
LevelSelectHoverBtn:     DB LVLSEL_BTN_NONE
LevelSelectPressedBtn:   DB LVLSEL_BTN_NONE
SkyScrollOffset:         DB 0    ; 0..119, horizontal ping-pong scroll (sky 480w - canvas 360w)
SkyScrollDir:            DB 1    ; +1 / -1
SkyScrollTick:           DB 0    ; subdivider, инкрементируется каждый кадр


; ============================================================================
; LevelSelect_Init — DMA copy scene_levelsel pages → canvas A + B, palette swap,
; draw dispname для CurStageIdx=0.
; ============================================================================
LevelSelect_Init:
                    XOR A
                    LD (CurStageIdx), A
                    LD (LvlInStage), A
                    LD (LevelSelectKeyPrev), A
                    LD (LevelSelectKeySpacePrev), A
                    LD (LevelSelectMousePrev), A
                    LD (LevelSelectActionMask), A
                    LD (SkyScrollOffset), A
                    LD (SkyScrollTick), A
                    LD A, LVLSEL_BTN_NONE
                    LD (LevelSelectHoverBtn), A
                    LD (LevelSelectPressedBtn), A
                    LD A, 1 : LD (SkyScrollDir), A

                    ; --- Изоляция от Game: explicit SFILE clear #0200..#03FD (510 bytes).
                    ; Game→LS transition (или cold boot) может оставить stale chain/ball
                    ; descriptors с SPACT=1 в #0354..#03F7 — они рендерятся поверх LS scene.
                    ; Той же техникой что в InitGame (immediate-нулями, НЕ LDIR — read через
                    ; FM_EN отдаёт ROM, LDIR копирует ROM в SFILE = призраки).
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD HL, #0200
                    LD B, 255
.lsi_clr1:          LD (HL), 0 : INC HL : DJNZ .lsi_clr1
                    LD B, 255
.lsi_clr2:          LD (HL), 0 : INC HL : DJNZ .lsi_clr2    ; всего 510 байт #0200..#03FD
                    LD BC, FMADDR : XOR A : OUT (C), A

                    ; Depack level-select scene: compressed storage #70..#78
                    ; -> raw source #54..#5C, then copy to visible/shadow canvas.
                    LD A, LVLSEL_ZX7_PAGE_BASE
                    LD B, LVLSEL_SRC_PAGE_BASE
                    CALL UnpackZX7_9Pages
                    LD A, LVLSEL_SRC_PAGE_BASE
                    LD B, CANVAS_A_PAGE_BASE
                    CALL LsCopy9Pages
                    LD A, LVLSEL_SRC_PAGE_BASE
                    LD B, CANVAS_B_PAGE_BASE
                    CALL LsCopy9Pages

                    LD HL, LevelSelectPalette
                    CALL LsLoadCram128Palette

                    ; --- Preview level: tiles → TSU pages, palette → CRAM #00..#0F
                    LD A, PREVIEW_SRC_PAGE_C : LD B, #0C
                    CALL CopyAtlasToPage
                    LD A, PREVIEW_SRC_PAGE_D : LD B, #0D
                    CALL CopyAtlasToPage

                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD BC, PALSEL : XOR A : OUT (C), A
                    LD HL, LevelPreviewPalette
                    LD DE, #0000
                    LD BC, 32
                    LDIR
                    ; Dispname palette в SPAL=2 (CRAM #0040..#005F).
                    LD HL, DispnamePalette
                    LD DE, #0040
                    LD BC, 32
                    LDIR
                    ; Button palette is level-select-only SPAL=3 (CRAM #0060..#007F).
                    LD HL, LevelSelectButtonsPalette
                    LD DE, #0060
                    LD BC, 32
                    LDIR
                    ; Mini-frog/kz palette SPAL=4 (CRAM #0080..#009F), LS-only.
                    ; На GotoGame InitPalette перетирает balls SPAL=4 поверх.
                    LD HL, LevelSelectMiniPalette
                    LD DE, #0080
                    LD BC, 32
                    LDIR
                    LD BC, FMADDR : XOR A : OUT (C), A

                    CALL SetupPreviewSprites
                    CALL SetupDispnameSprites
                    CALL SetupLevelSelectButtonSprites
                    CALL SetupMiniFrogKzSprites

                    XOR A                                    ; CurStageIdx = 0
                    CALL LevelSelect_DrawDispnameByStage
                    RET


; ============================================================================
; LevelSelect_Update — обработка ввода.
; ============================================================================
LevelSelect_Update:
                    CALL HandleMouse                         ; обновить MouseAbsX/Y из порта
                    CALL LevelSelect_UpdateMouseButtons
                    LD BC, KEY_O
                    IN A, (C)
                    LD E, A
                    LD A, (LevelSelectKeyPrev)
                    LD D, A
                    LD A, E
                    LD (LevelSelectKeyPrev), A

                    ; O rising edge (prev bit1=1, cur bit1=0)
                    LD A, D : AND %00000010
                    JR Z, .lsu_check_p
                    LD A, E : AND %00000010
                    JR NZ, .lsu_check_p
                    LD A, (CurStageIdx)
                    OR A : JR Z, .lsu_check_p
                    DEC A
                    LD (CurStageIdx), A
                    CALL LevelSelect_RefreshLevelUI
                    CALL SetupLevelSelectButtonSprites
.lsu_check_p:
                    LD A, D : AND %00000001
                    JR Z, .lsu_check_space
                    LD A, E : AND %00000001
                    JR NZ, .lsu_check_space
                    LD A, (CurStageIdx)
                    LD B, A
                    LD A, (MaxUnlockedStage)
                    CP B
                    JR Z, .lsu_check_space
                    LD A, B
                    INC A
                    LD (CurStageIdx), A
                    CALL LevelSelect_RefreshLevelUI
                    CALL SetupLevelSelectButtonSprites
.lsu_check_space:
                    LD BC, KEY_SPACE
                    IN A, (C)
                    BIT 0, A
                    JR Z, .lsu_space_pressed
                    XOR A
                    LD (LevelSelectKeySpacePrev), A
                    RET
.lsu_space_pressed:
                    LD A, (LevelSelectKeySpacePrev)
                    OR A
                    RET NZ
                    LD A, 1
                    LD (LevelSelectKeySpacePrev), A
                    JP LevelSelect_GotoGame

; ============================================================================
; Mouse buttons: hover/pressed/click for BACK / PLAY / NEXT.
; Click fires on action release inside the same button.
; ============================================================================
LevelSelect_UpdateMouseButtons:
                    CALL LevelSelect_HitTestButtons
                    LD (LevelSelectHoverBtn), A

                    CALL LevelSelect_ReadActionDown
                    JR Z, .lsm_up
                    LD A, (LevelSelectMousePrev)
                    OR A
                    JR NZ, .lsm_down_cont
                    LD A, (LevelSelectHoverBtn)
                    LD (LevelSelectPressedBtn), A
                    CP LVLSEL_BTN_PLAY
                    JR Z, .lsm_click_play
.lsm_down_cont:
                    LD A, 1
                    LD (LevelSelectMousePrev), A
                    JP SetupLevelSelectButtonSprites
.lsm_up:
                    LD A, (LevelSelectMousePrev)
                    OR A
                    JR Z, .lsm_finish_up
                    LD A, (LevelSelectPressedBtn)
                    LD B, A
                    LD A, (LevelSelectHoverBtn)
                    CP B
                    JR NZ, .lsm_finish_up
                    LD A, B
                    CP LVLSEL_BTN_BACK
                    JR Z, .lsm_click_back
                    CP LVLSEL_BTN_PLAY
                    JR Z, .lsm_click_play
                    CP LVLSEL_BTN_NEXT
                    JR Z, .lsm_click_next
                    JR .lsm_finish_up
.lsm_click_back:
                    LD A, (CurStageIdx)
                    OR A
                    JR Z, .lsm_finish_up
                    DEC A
                    LD (CurStageIdx), A
                    CALL LevelSelect_RefreshLevelUI
                    JR .lsm_finish_up
.lsm_click_next:
                    LD A, (CurStageIdx)
                    LD B, A
                    LD A, (MaxUnlockedStage)
                    CP B
                    JR Z, .lsm_finish_up
                    LD A, B
                    INC A
                    LD (CurStageIdx), A
                    CALL LevelSelect_RefreshLevelUI
                    JR .lsm_finish_up
.lsm_click_play:
                    XOR A
                    LD (LevelSelectMousePrev), A
                    LD A, LVLSEL_BTN_NONE
                    LD (LevelSelectPressedBtn), A
                    ; Discard UpdateMouseButtons return → stack matches space path
                    ; (после GotoGame идём прямо в main loop, не в mid-routine Update
                    ; где keyboard polling работает с уже-Scene=0 state).
                    POP HL
                    JP LevelSelect_GotoGame
.lsm_finish_up:
                    XOR A
                    LD (LevelSelectMousePrev), A
                    LD A, LVLSEL_BTN_NONE
                    LD (LevelSelectPressedBtn), A
                    JP SetupLevelSelectButtonSprites

; Returns A=1/Z=0 when the selected action button is down, A=0/Z=1 on release.
; This is menu-local: unlike NormalizeMouseAction it must not keep buttons pressed.
LevelSelect_ReadActionDown:
                    LD BC, MOUSE_BTN
                    IN A, (C)
                    CPL
                    AND %00000011
                    LD E, A
                    LD A, (LevelSelectActionMask)
                    OR A
                    JR NZ, .lsrad_have_mask
                    LD A, E
                    OR A
                    RET Z
                    BIT 0, A
                    JR NZ, .lsrad_pick_bit0
                    LD A, %00000010
                    JR .lsrad_store_mask
.lsrad_pick_bit0:
                    LD A, %00000001
.lsrad_store_mask:
                    LD (LevelSelectActionMask), A
.lsrad_have_mask:
                    LD B, A
                    LD A, E
                    AND B
                    RET Z
                    LD A, 1
                    OR A
                    RET

LevelSelect_HitTestButtons:
                    LD HL, (MouseAbsY)
                    LD A, H
                    CP 1
                    JR NZ, .lsht_none
                    LD A, L
                    CP LOW(LVLSEL_BTN_Y)
                    JR C, .lsht_none
                    CP LOW(LVLSEL_BTN_Y + LVLSEL_BTN_H)
                    JR NC, .lsht_none

                    LD HL, (MouseAbsX)
                    LD A, H
                    OR A
                    JR NZ, .lsht_x_hi1
                    LD A, L
                    CP LVLSEL_BACK_HIT_X
                    JR C, .lsht_play
                    CP LVLSEL_BACK_HIT_X + LVLSEL_BACK_HIT_W
                    JR NC, .lsht_play
                    LD A, (CurStageIdx)
                    OR A
                    JR Z, .lsht_none
                    LD A, LVLSEL_BTN_BACK
                    RET
.lsht_play:
                    LD A, L
                    CP LVLSEL_PLAY_HIT_X
                    JR C, .lsht_next
                    CP LVLSEL_PLAY_HIT_X + LVLSEL_PLAY_HIT_W
                    JR NC, .lsht_next
                    LD A, LVLSEL_BTN_PLAY
                    RET
.lsht_next:
                    LD A, L
                    CP LVLSEL_NEXT_HIT_X
                    JR C, .lsht_none
                    JR .lsht_next_enabled
.lsht_x_hi1:
                    CP 1
                    JR NZ, .lsht_none
                    LD A, L
                    CP LOW(LVLSEL_NEXT_HIT_X + LVLSEL_NEXT_HIT_W)
                    JR NC, .lsht_none
.lsht_next_enabled:
                    LD A, (CurStageIdx)
                    LD B, A
                    LD A, (MaxUnlockedStage)
                    CP B
                    JR Z, .lsht_none
                    LD A, LVLSEL_BTN_NEXT
                    RET
.lsht_none:
                    LD A, LVLSEL_BTN_NONE
                    RET

; ============================================================================
; LevelSelect_Render — каждый кадр:
;   1. Blit sky с scroll → shadow canvas top 100 lines.
;   2. Blit pyramid overlay (transparency) → shadow canvas top 100 lines.
;   3. Swap visible/shadow.
;   4. Update cursor sprite + advance scroll counter.
; ============================================================================
LevelSelect_Render:
                    CALL BlitSkyToShadow
                    CALL BlitPyramidOverlayToShadow
                    LD A, (VisiblePageBase) : XOR #30 : LD (VisiblePageBase), A
                    LD A, (ShadowPageBase)  : XOR #30 : LD (ShadowPageBase), A
                    LD A, (VisiblePageBase) : LD BC, VPAGE : OUT (C), A
                    CALL UpdateCursorSprite
                    JP UpdateSkyScroll

; ============================================================================
; TSU level-select buttons. The graphics are packed into free cells of the
; level-select-only TSU pages #0C/#0D copied from #52/#53 during Init.
; ============================================================================
SetupLevelSelectButtonSprites:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    CALL SetupBackButtonSprite
                    CALL SetupPlayButtonSprite
                    CALL SetupNextButtonSprite
                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET

SetupBackButtonSprite:
                    LD HL, LVLSEL_BTN_DESC_BASE
                    LD A, (CurStageIdx)
                    OR A
                    JR Z, .sbb_disabled
                    LD A, LVLSEL_BTN_BACK
                    CALL LevelSelect_ButtonStateIndex
                    JR .sbb_state_ready
.sbb_disabled:
                    LD A, LVLSEL_BTN_STATE_EMPTY
.sbb_state_ready:
                    LD DE, LVLSEL_BACK_TNUM
                    LD B, 7
                    CALL LevelSelect_ButtonTnumByState
                    LD BC, LVLSEL_BACK_X
                    LD A, SPSIZ56
                    JP LevelSelect_WriteButtonDesc

SetupPlayButtonSprite:
                    LD HL, LVLSEL_BTN_DESC_BASE + 6
                    LD A, LVLSEL_BTN_PLAY
                    CALL LevelSelect_ButtonStateIndex
                    LD DE, LVLSEL_PLAY_TNUM
                    LD B, 8
                    CALL LevelSelect_ButtonTnumByState
                    LD BC, LVLSEL_PLAY_X
                    LD A, SPSIZ64
                    JP LevelSelect_WriteButtonDesc

SetupNextButtonSprite:
                    LD HL, LVLSEL_BTN_DESC_BASE + 12
                    LD A, (CurStageIdx)
                    LD C, A
                    LD A, (MaxUnlockedStage)
                    CP C
                    JR Z, .snb_disabled
                    LD A, LVLSEL_BTN_NEXT
                    CALL LevelSelect_ButtonStateIndex
                    JR .snb_state_ready
.snb_disabled:
                    LD A, LVLSEL_BTN_STATE_EMPTY
.snb_state_ready:
                    LD DE, LVLSEL_NEXT_TNUM
                    LD B, 7
                    CALL LevelSelect_ButtonTnumByState
                    LD BC, LVLSEL_NEXT_X
                    LD A, SPSIZ56
                    JP LevelSelect_WriteButtonDesc

; A=button id. Returns 0 idle, 1 hover, 2 pressed.
LevelSelect_ButtonStateIndex:
                    LD B, A
                    LD A, (LevelSelectPressedBtn)
                    CP B
                    JR Z, .lsbsi_pressed
                    LD A, (LevelSelectHoverBtn)
                    CP B
                    JR Z, .lsbsi_hover
                    XOR A
                    RET
.lsbsi_hover:
                    LD A, 1
                    RET
.lsbsi_pressed:
                    LD A, 2
                    RET

; A=state, DE=base TNUM, B=state step in cells. Returns DE=state TNUM.
LevelSelect_ButtonTnumByState:
                    OR A
                    RET Z
.lsbts_loop:
                    LD C, A
                    LD A, E
                    ADD A, B
                    LD E, A
                    LD A, D
                    ADC A, 0
                    LD D, A
                    LD A, C
                    DEC A
                    JR NZ, .lsbts_loop
                    RET

; HL=descriptor, DE=TNUM, BC=X, A=horizontal size. Y size is fixed 24.
LevelSelect_WriteButtonDesc:
                    LD (LsBtnTmpSize), A
                    LD A, LOW(LVLSEL_BTN_Y)
                    LD (HL), A : INC HL
                    LD A, HIGH(LVLSEL_BTN_Y) | SPACT | SPSIZ24
                    LD (HL), A : INC HL
                    LD A, C
                    LD (HL), A : INC HL
                    LD A, B
                    LD C, A
                    LD A, (LsBtnTmpSize)
                    OR C
                    LD (HL), A : INC HL
                    LD A, E
                    LD (HL), A : INC HL
                    LD A, D
                    AND #0F
                    OR LVLSEL_BTN_SPAL << 4
                    LD (HL), A
                    RET

LsBtnTmpSize: DB 0


; ============================================================================
; UpdateSkyScroll — horizontal ping-pong scroll, SkyScrollOffset 0..119.
; Каждый кадр SkyScrollTick++; каждые SKY_SCROLL_TICK кадров offset += Dir.
; На границах 0/MAX направление переворачивается.
; ============================================================================
SKY_SCROLL_TICK EQU 3            ; 1 px каждые 3 кадра ≈ 16 px/sec @50Hz

UpdateSkyScroll:
                    LD A, (SkyScrollTick)
                    INC A
                    CP SKY_SCROLL_TICK
                    JR C, .uss_save_tick
                    XOR A
                    LD (SkyScrollTick), A
                    LD A, (SkyScrollOffset)
                    LD B, A
                    LD A, (SkyScrollDir)
                    ADD A, B                             ; signed add (Dir = +1 / -1 = #FF)
                    LD (SkyScrollOffset), A
                    ; bounds: A=signed result. Если ≥ MAX или wrap (bit7=1) → invert Dir + clamp.
                    BIT 7, A
                    JR NZ, .uss_underflow
                    CP LVLSEL_SKY_MAX_SCROLL
                    RET C
                    ; overflow ≥ MAX → clamp + invert
                    LD A, LVLSEL_SKY_MAX_SCROLL - 1
                    LD (SkyScrollOffset), A
                    LD A, (SkyScrollDir) : NEG : LD (SkyScrollDir), A
                    RET
.uss_underflow:
                    XOR A
                    LD (SkyScrollOffset), A
                    LD A, (SkyScrollDir) : NEG : LD (SkyScrollDir), A
                    RET
.uss_save_tick:
                    LD (SkyScrollTick), A
                    RET


; ============================================================================
; BlitSkyToShadow — horizontal scroll sky band. Источник #38..#3B, 480w stride 512.
; Per-page-chunk DMA с burst=360 bytes; auto-stride S_ALGN advances 512 per line.
; ============================================================================
BlitSkyToShadow:
                    LD A, LVLSEL_SKY_PAGE_BASE       : LD (BS_SrcBase), A
                    LD A, (SkyScrollOffset)          : LD (BS_SrcX), A
                    LD A, (ShadowPageBase)           : LD (BS_DstPage), A
                    XOR A : LD (BS_Line), A
                    LD A, LVLSEL_SKY_BAND_H          : LD (BS_Lines), A
                    LD A, DMA_BLT_8BPP_MODE          : LD (BS_Mode), A   ; A_SZ=1 → stride 512 between bursts; sky без byte=0 → transparency не задействована
                    JP BlitSection


; ============================================================================
; BlitPyramidOverlayToShadow — статичный overlay с transparency (src=0 skip).
; Источник #3C..#3F, 360w stride 512. SrcX=0 (нет scroll).
; ============================================================================
BlitPyramidOverlayToShadow:
                    LD A, LVLSEL_PYR_PAGE_BASE       : LD (BS_SrcBase), A
                    XOR A                            : LD (BS_SrcX), A
                    LD A, (ShadowPageBase)           : LD (BS_DstPage), A
                    XOR A : LD (BS_Line), A
                    LD A, LVLSEL_SKY_BAND_H          : LD (BS_Lines), A
                    LD A, DMA_BLT_8BPP_MODE          : LD (BS_Mode), A
                    JP BlitSection


; ============================================================================
; BlitSection — per-page-chunk DMA band copy с horizontal X-offset.
; За 1 DMA call: до 32 линий (= 1 source page), burst LVLSEL_BAND_BURST_LEN+1
; words = 360 bytes (= visible 360w), auto-stride S_ALGN перешагивает 512 на
; следующую line внутри page.
;
; Inputs (memory):
;   BS_SrcBase  — page базы (например #38 для sky)
;   BS_SrcX     — horizontal X-offset внутри source line (0..119)
;   BS_DstPage  — стартовая canvas page
;   BS_Line     — стартовая линия в band (обычно 0)
;   BS_Lines    — сколько линий копировать (обычно 100)
;   BS_Mode     — DMA control byte
; ============================================================================
BlitSection:
.bsec_loop:
                    ; src_page = BS_SrcBase + (BS_Line / 32)
                    LD A, (BS_Line)
                    LD E, A
                    SRL A : SRL A : SRL A : SRL A : SRL A   ; A = BS_Line / 32 (0..3)
                    LD HL, BS_SrcBase
                    ADD A, (HL)
                    LD (BS_SrcPage), A
                    ; src_off = (BS_Line & 31) * 512 + BS_SrcX
                    LD A, E : AND 31
                    LD B, A                              ; B = BS_Line & 31 (0..31)
                    SLA A : LD H, A                      ; H = (BS_Line & 31) * 2
                    LD A, (BS_SrcX)                      ; A = SrcX (0..119)
                    LD L, A                              ; HL = (line_in_page << 9) | SrcX
                    LD (BS_SrcOff), HL
                    ; avail_in_src_page = 32 - (BS_Line & 31)
                    LD A, 32 : SUB B : LD (BS_AvailPg), A

                    ; dst_page = BS_DstPage + (BS_Line / 32)  (canvas line aligned с src line)
                    LD A, E
                    SRL A : SRL A : SRL A : SRL A : SRL A
                    LD HL, BS_DstPage
                    ADD A, (HL)
                    LD (BS_DstPageCur), A
                    ; dst_off = (BS_Line & 31) * 512  (X=0 в canvas)
                    LD A, E : AND 31
                    SLA A : LD H, A : LD L, 0
                    LD (BS_DstOff), HL

                    ; chunk = min(BS_AvailPg, BS_Lines)
                    LD A, (BS_AvailPg) : LD B, A
                    LD A, (BS_Lines)
                    CP B : JR NC, .bsec_chunk_done
                    LD B, A
.bsec_chunk_done:
                    LD A, B : LD (BS_Chunk), A

                    ; --- DMA setup ---
                    LD BC, FMADDR : XOR A : OUT (C), A
                    LD A, LVLSEL_BAND_BURST_LEN : LD BC, DMALEN : OUT (C), A   ; 180-1 = burst 360 bytes
                    LD A, (BS_Chunk) : DEC A : LD BC, DMANUM : OUT (C), A

                    LD A, (BS_SrcOff)   : LD BC, DMASADL : OUT (C), A
                    LD A, (BS_SrcOff+1) : LD BC, DMASADH : OUT (C), A
                    LD A, (BS_SrcPage)  : LD BC, DMASADX : OUT (C), A
                    LD A, (BS_DstOff)   : LD BC, DMADADL : OUT (C), A
                    LD A, (BS_DstOff+1) : LD BC, DMADADH : OUT (C), A
                    LD A, (BS_DstPageCur) : LD BC, DMADADX : OUT (C), A
                    LD A, (BS_Mode) : LD BC, DMACTR : OUT (C), A
.bsec_wait:
                    IN A, (C) : AND DMAWNR : JR NZ, .bsec_wait

                    ; advance
                    LD A, (BS_Chunk) : LD B, A
                    LD A, (BS_Line)  : ADD A, B : LD (BS_Line), A
                    LD A, (BS_Lines) : SUB B : LD (BS_Lines), A
                    JP NZ, .bsec_loop
                    RET


BS_SrcBase:     DB 0
BS_SrcX:        DB 0
BS_DstPage:     DB 0
BS_Line:        DB 0
BS_Lines:       DB 0
BS_Mode:        DB 0
BS_SrcPage:     DB 0
BS_SrcOff:      DW 0
BS_DstPageCur:  DB 0
BS_DstOff:      DW 0
BS_AvailPg:     DB 0
BS_Chunk:       DB 0


; ============================================================================
; LevelSelect_GotoGame — Scene=1→0. Restore level_01_canvas + palette + LVLINTRO atlas.
; ============================================================================
LevelSelect_GotoGame:
                    POP HL
                    LD (LevelLoadSavedRet), HL
                    LD (LevelLoadSavedSP), SP
                    LD SP, LevelLoadTempStackTop
                    DI                                   ; IRQ disabled — temp stack 256B мал для IM2 push'ей
                    LD A, 1 : LD (DebugStage), A
                    LD BC, VCONFIG : LD A, %11000110 : OUT (C), A  ; NOGFX=1 during scene load

                    LD A, 2 : LD (DebugStage), A
                    CALL SetupCurLevelPaging

                    ; Phase 4 proper: TrackData scratch в page #03 (там же stack — PAGE3
                    ; не меняется, stack stable). Source level N лежит в отдельной page:
                    ;   level 1 → page #65 (backup, идентичен #03 после spgbld)
                    ;   level 2 → page #04
                    ; CALL CopyAtlasToPage copies 16K из source→#03 во время NOGFX=1.
                    LD A, (CurStageIdx)
                    OR A
                    JR NZ, .lsg_l2_track
                    LD A, #65 : JR .lsg_track_copy   ; level 1 source
.lsg_l2_track:
                    LD A, #66                        ; level 2 source (moved from #04)
.lsg_track_copy:
                    LD B, #03
                    CALL CopyAtlasToPage

                    LD A, 3 : LD (DebugStage), A
                    LD A, (CurZx7Base)
                    LD B, LVLSEL_BG_BACKUP_BASE
                    CALL UnpackZX7_9Pages

                    LD A, 4 : LD (DebugStage), A
                    XOR A
                    LD (Scene), A
                    CALL InitPalette
                    LD A, 5 : LD (DebugStage), A
                    CALL InitGame
                    LD A, (CurStageIdx)
                    OR A
                    JR Z, .lsg_intro_ready
                    LD A, LVL02INTRO_ATLAS_SRC_PAGE
                    CALL CopyAtlasToPageD
.lsg_intro_ready:
                    LD A, 6 : LD (DebugStage), A
                    CALL OneTimeBlitKzToGolden

                    LD A, 7 : LD (DebugStage), A
                    LD A, LVLSEL_BG_BACKUP_BASE
                    LD B, CANVAS_A_PAGE_BASE
                    CALL LsCopy9Pages
                    LD A, 8 : LD (DebugStage), A
                    LD A, LVLSEL_BG_BACKUP_BASE
                    LD B, CANVAS_B_PAGE_BASE
                    CALL LsCopy9Pages
                    LD A, 9 : LD (DebugStage), A
                    CALL UpdateFrogSprite
                    CALL UpdatePreviewSprite
                    CALL UpdateBallSprites
                    CALL HideChainSprites
                    CALL UpdateExplodeSprites
                    CALL UpdateCursorSprite
                    CALL UpdateKzSkullSprite
                    CALL UpdateLevelIntroText
                    LD A, (VisiblePageBase) : LD BC, VPAGE : OUT (C), A
                    LD BC, VCONFIG : LD A, %11000010 : OUT (C), A
                    LD A, 99 : LD (DebugStage), A
                    LD SP, (LevelLoadSavedSP)
                    LD HL, (LevelLoadSavedRet)
                    PUSH HL
                    EI                                   ; restore IRQ перед RET
                    RET


; ============================================================================
; LevelSelect_RefreshLevelUI (Phase 4) — обновить preview tiles + dispname
; при смене CurStageIdx. NOGFX=1 на время blit, потом back to NOGFX=0.
; ============================================================================
LevelSelect_RefreshLevelUI:
                    LD BC, VCONFIG : LD A, %11000110 : OUT (C), A  ; NOGFX while TSU pages update
                    CALL LevelSelect_LoadCurStagePreview
                    CALL LoadCurStagePreviewPalette                  ; SPAL=0 палитра под уровень
                    LD A, (CurStageIdx)
                    CALL LevelSelect_DrawDispnameByStage
                    CALL SetupMiniFrogKzSprites                      ; пересчёт мини-frog/kz по новому CurStageIdx
                    LD BC, VCONFIG : LD A, %11000010 : OUT (C), A
                    RET

; ============================================================================
; LevelSelect_LoadCurStagePreview (Phase 4) — copy preview tiles в #0C/#0D
; на основе CurStageIdx. Уровень 1 → #52/#53, уровень 2 → #62/#63.
; ============================================================================
LevelSelect_LoadCurStagePreview:
                    LD A, (CurStageIdx)
                    OR A
                    JR NZ, .lcsp_lvl2
                    LD A, PREVIEW_SRC_PAGE_C : LD B, #0C : CALL CopyAtlasToPage
                    LD A, PREVIEW_SRC_PAGE_D : LD B, #0D : JP CopyAtlasToPage
.lcsp_lvl2:
                    LD A, PREVIEW_L2_PAGE_C  : LD B, #0C : CALL CopyAtlasToPage
                    LD A, PREVIEW_L2_PAGE_D  : LD B, #0D : JP CopyAtlasToPage

; ============================================================================
; SetupPreviewSprites — заполняет 20 TSU descriptors (DESC_CHAIN0..+119).
; Layout 5 cols × 4 rows, sprite 32×32, SPAL=0.
; TNUM base per row: 3072 (#0C cy=0), 3328 (#0C cy=4), 3584 (#0D cy=0), 3840 (#0D cy=4).
; ============================================================================
SetupPreviewSprites:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD HL, PREVIEW_DESC_BASE          ; #0200
                    LD IY, PreviewTnumBaseByRow

                    LD C, 0                            ; C = row (0..14)
.sps_row_loop:
                    LD B, 0                            ; B = col (0..2)
.sps_col_loop:
                    ; Y_L = PREVIEW_Y + row*8
                    LD A, C
                    ADD A, A : ADD A, A : ADD A, A     ; *8
                    ADD A, PREVIEW_Y
                    LD (HL), A : INC HL                ; Y_L
                    LD A, 0 : OR SPACT+SPSIZ8
                    LD (HL), A : INC HL                ; Y_H + ACT + SIZE8

                    ; X_L = PREVIEW_X + col*64; X_H bit 0 = carry (X[8])
                    LD A, B
                    ADD A, A : ADD A, A : ADD A, A : ADD A, A : ADD A, A : ADD A, A   ; *64
                    ADD A, PREVIEW_X
                    LD (HL), A : INC HL                ; X_L
                    LD A, 0
                    ADC A, A                           ; A = X[8] (carry)
                    OR SPSIZ64
                    LD (HL), A : INC HL                ; X_H + X[8] + SIZE64

                    ; TNUM = TnumBaseByRow[row] + col*8 (sprite 64 wide = 8 cells wide)
                    LD A, (IY+0)
                    LD E, A
                    LD A, (IY+1)
                    LD D, A                            ; DE = TNUM_BASE_ROW(row)
                    LD A, B
                    ADD A, A : ADD A, A : ADD A, A     ; A = col*8
                    ADD A, E : LD E, A
                    LD A, 0 : ADC A, D : LD D, A       ; DE = TNUM
                    LD (HL), E : INC HL                ; TNUM_L
                    LD A, D
                    AND #0F
                    OR PREVIEW_SPAL << 4
                    LD (HL), A : INC HL                ; TNUM_H + SPAL

                    INC B
                    LD A, B
                    CP PREVIEW_COLS
                    JR C, .sps_col_loop

                    INC IY : INC IY                    ; next row's TNUM base (DW)
                    INC C
                    LD A, C
                    CP PREVIEW_ROWS
                    JR C, .sps_row_loop

                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET

PreviewTnumBaseByRow:
                    ; page #0C TSU rows 0..7 (cy*64 + 3072), затем page #0D rows 0..6 (cy*64 + 3584)
                    DW 3072, 3136, 3200, 3264, 3328, 3392, 3456, 3520
                    DW 3584, 3648, 3712, 3776, 3840, 3904, 3968


; ============================================================================
; SetupDispnameSprites — 11 TSU sprite 16×24, текст dispname поверх preview.
; ============================================================================
SetupDispnameSprites:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD HL, DISPNAME_DESC_BASE
                    LD B, 0
.sds_loop:
                    LD (HL), DISPNAME_Y : INC HL
                    LD A, SPACT+SPSIZ24
                    LD (HL), A : INC HL

                    LD A, B
                    ADD A, A : ADD A, A : ADD A, A : ADD A, A    ; *16
                    ADD A, DISPNAME_X
                    LD (HL), A : INC HL
                    LD A, 0
                    ADC A, A
                    OR SPSIZ16
                    LD (HL), A : INC HL

                    LD A, B : ADD A, A                     ; A = col*2
                    ADD A, LOW(DISPNAME_TNUM_BASE)
                    LD (HL), A : INC HL
                    LD A, 0
                    ADC A, HIGH(DISPNAME_TNUM_BASE)
                    AND #0F
                    OR DISPNAME_SPAL << 4
                    LD (HL), A : INC HL

                    INC B
                    LD A, B
                    CP DISPNAME_NUM_SPRITES
                    JR C, .sds_loop

                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET


LevelPreviewPalette:
                    INCBIN "level_01_preview_pal.bin"

LevelPreviewPaletteL2:
                    INCBIN "level_02_preview_pal.bin"

; ============================================================================
; LoadCurStagePreviewPalette — загрузить SPAL=0 палитру (32 байта, CRAM #0000..#001F)
; preview sprites под текущий CurStageIdx. Меняет вид preview-тайлов чтобы соответствовать
; цветовой схеме bg уровня (раньше всегда показывался level 1 preview palette).
; Вызывается из LevelSelect_Init и LevelSelect_RefreshLevelUI при PREV/NEXT.
; ============================================================================
LoadCurStagePreviewPalette:
                    LD A, (CurStageIdx)
                    OR A
                    LD HL, LevelPreviewPalette
                    JR Z, .lcspp_apply
                    LD HL, LevelPreviewPaletteL2
.lcspp_apply:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD BC, PALSEL : XOR A : OUT (C), A
                    LD DE, #0000
                    LD BC, 32
                    LDIR
                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET

DispnamePalette:
                    INCBIN "level_01_dispname_pal.bin"

LevelSelectButtonsPalette:
                    INCBIN "level_select_buttons_pal.bin"

LevelSelectMiniPalette:
                    INCBIN "level_01_preview_mini_pal.bin"


; ============================================================================
; SetupMiniFrogKzSprites — 2 TSU sprite 32×32 поверх preview level.
; Позиции вычисляются из per-level game-coordinates frog/killzone (LevelMiniCfg),
; затем трансформируются game→preview-screen через PreviewScale routine.
; Раньше были hardcoded final screen-coords (level 1 only) — теперь работает для
; любого уровня из таблицы LevelMiniCfg, индексируемой CurStageIdx.
;
; Преобразование game→preview-screen:
;   Game canvas 360×288 → crop (X 36..324, Y 53..234) = 288×181 → visible 178×112
;   at screen (96, 145). Scale = 178/288 ≈ 0.618 ≈ 5/8 (точность ±1.1%, ≈3 px на 288).
;   screen_X = (game_X - 36) * 5/8 + 96 - 16   (-16 = top-left 32×32 sprite)
;   screen_Y = (game_Y - 53) * 5/8 + 145 - 16
; ============================================================================
LVLSEL_MINI_DESC_BASE  EQU LVLSEL_BTN_DESC_BASE + 18    ; после 3 button descriptors
LVLSEL_MINI_TNUM_FROG  EQU 3829    ; page #0D cy=3 cx=53
LVLSEL_MINI_TNUM_KZ    EQU 3833    ; page #0D cy=3 cx=57
LVLSEL_MINI_SPAL       EQU 4
LVLSEL_MINI_HALF       EQU 16      ; 32×32 sprite half-size

PREVIEW_GAME_OX        EQU 36      ; X-origin (crop start) в game-canvas координатах
PREVIEW_GAME_OY        EQU 53      ; Y-origin (crop start)
PREVIEW_SCREEN_OX      EQU 96      ; X top-left preview-area на экране (TSU)
PREVIEW_SCREEN_OY      EQU 145     ; Y top-left preview-area

; Per-level game-space centers (4 байта на уровень: frog_cx, frog_cy, kz_cx, kz_cy).
; frog center game = (FROG_INIT_X+32, FROG_INIT_Y+32) для 64×64 frog top-left + half.
; kz center = TrackData[CurTrackNumPoints-1] для каждого уровня (read из track .bin).
LevelMiniCfg:
                    ; Level 0 (= Level 1): frog (184,140), kz (115,130)
                    DB 184, 140, 115, 130
                    ; Level 1 (= Level 2): frog same (player slot), kz (64,146) = level_02 track end
                    DB 184, 140,  64, 146

; --- runtime scratch (level config snapshot) ---
TmpMiniFCX:         DB 0
TmpMiniFCY:         DB 0
TmpMiniKCX:         DB 0
TmpMiniKCY:         DB 0

; ============================================================================
; PreviewScaleGameToTop — convert single game coord to sprite top-left.
; In:   A = game coord (byte), B = game origin, C = preview screen origin.
; Out:  A = top-left screen coord = (game - B) * 5/8 + C - LVLSEL_MINI_HALF.
; Preserves: HL, IX, IY. Clobbers: BC, DE, AF.
; ============================================================================
PreviewScaleGameToTop:
                    PUSH HL
                    SUB B                          ; A = game - origin
                    LD H, 0 : LD L, A
                    LD D, H : LD E, L              ; DE = (game - origin)
                    ADD HL, HL                     ; ×2
                    ADD HL, HL                     ; ×4
                    ADD HL, DE                     ; ×5
                    SRL H : RR L
                    SRL H : RR L
                    SRL H : RR L                   ; ÷8 → HL = (game - origin) * 5/8
                    LD A, L
                    ADD A, C                       ; + screen origin
                    SUB LVLSEL_MINI_HALF           ; top-left = center - 16
                    POP HL
                    RET

SetupMiniFrogKzSprites:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A

                    ; --- Read per-level game coords из LevelMiniCfg[CurStageIdx] ---
                    LD A, (CurStageIdx)
                    ADD A, A : ADD A, A            ; A = idx * 4
                    LD HL, LevelMiniCfg
                    LD D, 0 : LD E, A
                    ADD HL, DE                     ; HL = &cfg[idx]
                    LD A, (HL) : LD (TmpMiniFCX), A : INC HL
                    LD A, (HL) : LD (TmpMiniFCY), A : INC HL
                    LD A, (HL) : LD (TmpMiniKCX), A : INC HL
                    LD A, (HL) : LD (TmpMiniKCY), A

                    LD HL, LVLSEL_MINI_DESC_BASE

                    ; --- Mini-frog descriptor (32×32, SPAL=4) ---
                    LD A, (TmpMiniFCY)
                    LD B, PREVIEW_GAME_OY : LD C, PREVIEW_SCREEN_OY
                    CALL PreviewScaleGameToTop     ; A = mini-frog top-left Y
                    LD (HL), A : INC HL                                       ; Y_L
                    LD A, SPACT | SPSIZ32
                    LD (HL), A : INC HL                                       ; Y_H+ACT+SH
                    LD A, (TmpMiniFCX)
                    LD B, PREVIEW_GAME_OX : LD C, PREVIEW_SCREEN_OX
                    CALL PreviewScaleGameToTop     ; A = mini-frog top-left X
                    LD (HL), A : INC HL                                       ; X_L
                    LD A, SPSIZ32
                    LD (HL), A : INC HL                                       ; X_H+SW
                    LD (HL), LOW(LVLSEL_MINI_TNUM_FROG) : INC HL              ; TNUM_L
                    LD A, HIGH(LVLSEL_MINI_TNUM_FROG) & #0F
                    OR LVLSEL_MINI_SPAL << 4
                    LD (HL), A : INC HL                                       ; TNUM_H+SPAL

                    ; --- Mini-killzone descriptor (32×32) ---
                    LD A, (TmpMiniKCY)
                    LD B, PREVIEW_GAME_OY : LD C, PREVIEW_SCREEN_OY
                    CALL PreviewScaleGameToTop
                    LD (HL), A : INC HL                                       ; Y_L
                    LD A, SPACT | SPSIZ32
                    LD (HL), A : INC HL
                    LD A, (TmpMiniKCX)
                    LD B, PREVIEW_GAME_OX : LD C, PREVIEW_SCREEN_OX
                    CALL PreviewScaleGameToTop
                    LD (HL), A : INC HL                                       ; X_L
                    LD A, SPSIZ32
                    LD (HL), A : INC HL
                    LD (HL), LOW(LVLSEL_MINI_TNUM_KZ) : INC HL
                    LD A, HIGH(LVLSEL_MINI_TNUM_KZ) & #0F
                    OR LVLSEL_MINI_SPAL << 4
                    LD (HL), A
                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET


; ============================================================================
; LsCopy9Pages / LsCopyNPages — DMA copy N pages × 16K. A=src_base, B=dst_base,
; (C=count для NPages; 9Pages = тонкая обёртка с C=9).
; ============================================================================
LsCopy9Pages:
                    LD C, 9
LsCopyNPages:
                    LD (LsCopySrc), A
                    LD A, B : LD (LsCopyDst), A
                    LD A, C : LD (LsCopyCnt), A
                    LD BC, FMADDR : XOR A : OUT (C), A
                    LD A, 256-1 : LD BC, DMALEN : OUT (C), A
                    LD A, 32-1  : LD BC, DMANUM : OUT (C), A
LsCopyLoop:
                    XOR A : LD BC, DMASADL : OUT (C), A
                    XOR A : LD BC, DMASADH : OUT (C), A
                    LD A, (LsCopySrc) : LD BC, DMASADX : OUT (C), A
                    XOR A : LD BC, DMADADL : OUT (C), A
                    XOR A : LD BC, DMADADH : OUT (C), A
                    LD A, (LsCopyDst) : LD BC, DMADADX : OUT (C), A
                    LD A, DMA_BLT_8BPP_MODE : LD BC, DMACTR : OUT (C), A
LsCopyWait:         IN A, (C)
                    AND DMAWNR
                    JR NZ, LsCopyWait
                    LD A, (LsCopySrc) : INC A : LD (LsCopySrc), A
                    LD A, (LsCopyDst) : INC A : LD (LsCopyDst), A
                    LD A, (LsCopyCnt) : DEC A : LD (LsCopyCnt), A
                    JR NZ, LsCopyLoop
                    RET
LsCopySrc: DB 0
LsCopyDst: DB 0
LsCopyCnt: DB 0


; ============================================================================
; LsLoadCram128Palette — HL = pointer (256 bytes) → CRAM #0100..#01FF.
; ============================================================================
LsLoadCram128Palette:
                    LD BC, FMADDR : LD A, FM_EN : OUT (C), A
                    LD BC, PALSEL : XOR A : OUT (C), A
                    LD DE, #0100
                    LD BC, 256
                    LDIR
                    LD BC, FMADDR : XOR A : OUT (C), A
                    RET


; ============================================================================
; LevelSelect_DrawDispnameByStage — A = stage_idx (0..12).
; 1) Restore clean scene fragment в text region (= clear old text).
; 2) DMA blit new dispname row.
; В обе canvas pages (A+B).
; ============================================================================
LevelSelect_DrawDispnameByStage:
                    LD HL, DispnameStageRowTable
                    LD E, A : LD D, 0
                    ADD HL, DE
                    LD A, (HL)
                    LD (DispnameCurRow), A

                    LD A, CANVAS_A_PAGE_BASE + LVLSEL_DISPNAME_DST_PG_OFF
                    LD (DispnameDstPage), A
                    CALL ClearDispnameArea
                    LD A, (DispnameCurRow)
                    CALL DrawDispnameRow

                    LD A, CANVAS_B_PAGE_BASE + LVLSEL_DISPNAME_DST_PG_OFF
                    LD (DispnameDstPage), A
                    CALL ClearDispnameArea
                    LD A, (DispnameCurRow)
                    JP DrawDispnameRow


; ============================================================================
; ClearDispnameArea — DMA copy scene fragment из source page (#54+pg_off)
; → canvas page (DispnameDstPage), без transparency. Восстанавливает чистый
; scene background в text region (для clear перед new text).
; ============================================================================
ClearDispnameArea:
                    LD BC, FMADDR : XOR A : OUT (C), A
                    LD A, 256-1 : LD BC, DMALEN : OUT (C), A
                    LD A, 11-1  : LD BC, DMANUM : OUT (C), A

                    LD A, LVLSEL_SRC_PAGE_BASE + LVLSEL_DISPNAME_DST_PG_OFF
                    LD BC, DMASADX : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_LO : LD BC, DMASADL : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_HI : LD BC, DMASADH : OUT (C), A

                    LD A, (DispnameDstPage)
                    LD BC, DMADADX : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_LO : LD BC, DMADADL : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_HI : LD BC, DMADADH : OUT (C), A

                    ; 8BPP_MODE с transparency: scene не имеет байт=0 (idx 128..255),
                    ; → ведёт себя как full copy. NOTRANSP_MODE (#B1) без ASZ-бита
                    ; видимо делает только 1 line вместо DMANUM+1.
                    LD A, DMA_BLT_8BPP_MODE : LD BC, DMACTR : OUT (C), A
.cda_wait:          IN A, (C) : AND DMAWNR : JR NZ, .cda_wait
                    RET


; ============================================================================
; DrawDispnameRow — A = row_idx (0..3). Один DMA blit (11 lines × 512 stride):
;   row 0..1 → src page #4E, offset 0 / #1600
;   row 2..3 → src page #4F, offset 0 / #1600
;   dst = canvas page, byte_offset = #2A6C (X=108, Y=149).
;   burst = 256 words (512 bytes per line), num = 11 lines.
;   DMA_BLT_8BPP_MODE: src=0 транспаренси.
; ============================================================================
DrawDispnameRow:
                    ; A = row 0..3 — обнаруживаем page и индекс внутри page
                    CP 2
                    JR C, .ddr_page_a
                    LD B, LVLSEL_DISPNAME_PAGE_B
                    SUB 2
                    JR .ddr_page_set
.ddr_page_a:
                    LD B, LVLSEL_DISPNAME_PAGE_A
.ddr_page_set:
                    ; A = индекс row внутри page (0 или 1); B = src page
                    LD C, A                                  ; сохранить
                    LD A, B : LD (DispnameSrcPage), A
                    LD A, C                                  ; A = row within page (0/1)
                    OR A
                    JR Z, .ddr_off_zero
                    LD HL, #1600                             ; row 1: offset 5632
                    JR .ddr_off_set
.ddr_off_zero:
                    LD HL, 0
.ddr_off_set:
                    LD (DispnameSrcOff), HL

                    LD BC, FMADDR : XOR A : OUT (C), A
                    LD A, 256-1 : LD BC, DMALEN : OUT (C), A
                    LD A, 11-1  : LD BC, DMANUM : OUT (C), A

                    LD A, (DispnameSrcPage)
                    LD BC, DMASADX : OUT (C), A
                    LD A, (DispnameSrcOff)   : LD BC, DMASADL : OUT (C), A
                    LD A, (DispnameSrcOff+1) : LD BC, DMASADH : OUT (C), A

                    LD A, (DispnameDstPage)
                    LD BC, DMADADX : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_LO : LD BC, DMADADL : OUT (C), A
                    LD A, LVLSEL_DISPNAME_DST_HI : LD BC, DMADADH : OUT (C), A

                    LD A, DMA_BLT_8BPP_MODE : LD BC, DMACTR : OUT (C), A
.ddr_wait:          IN A, (C) : AND DMAWNR : JR NZ, .ddr_wait
                    RET


DispnameSrcPage:  DB 0
DispnameSrcOff:   DW 0
DispnameDstPage:  DB 0
DispnameCurRow:   DB 0


; ============================================================================
; Палитра для scene level select — 128 colors CRAM. Грузится в #0100..#01FF.
; ============================================================================
LevelSelectPalette:
                    INCBIN "scene_levelsel_canvas_pal.bin"


; ============================================================================
; stage_to_row mapping (13 байт): stage_idx (0..12) → atlas row (0..3).
; row 0,1 в page #4E; row 2,3 в page #4F. Offset row*5632 byte (=#1600).
; ============================================================================
DispnameStageRowTable: INCBIN "dispname_stage_row.bin"


; ============================================================================
; Таблицы уровней (сгенерированы gen_levels_tables.py).
; ============================================================================
LevelsGraphicsTable:    INCBIN "levels/graphics_table.bin"
LevelsSettingsTable:    INCBIN "levels/settings_table.bin"
LevelsStagePairs:       INCBIN "levels/stage_pairs.bin"
LevelsStageTable:       INCBIN "levels/stage_table.bin"
LevelsDispnames:        INCBIN "levels/dispnames.bin"
LevelsDispnameOffsets:  INCBIN "levels/dispname_offsets.bin"
