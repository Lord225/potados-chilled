start:
LI SP, 0x0100
LI R2, 0x0000
LI R4, 0x8000

LLI R3, 255
ST R3, [R2 + 0]
LLI R3, 128
ST R3, [R2 + 1]
LLI R3, 32
ST R3, [R2 + 2]
LLI R3, 10
ST R3, [R2 + 3]
LLI R3, 1
ST R3, [R2 + 4]
LLI R3, 0
ST R3, [R2 + 5]
CALL show_array
CALL super_delay
CALL bubble_sort
CALL super_delay
CALL super_delay
CALL super_delay
CALL super_delay
JMP start

HALT

show_array:
    PUSH R4
    LI R4, 0x8000

    LD R3, [R2 + 0]
    ST R3, [R4 + 0]
    LD R3, [R2 + 1]
    ST R3, [R4 + 1]
    LD R3, [R2 + 2]
    ST R3, [R4 + 2]
    LD R3, [R2 + 3]
    ST R3, [R4 + 3]
    LD R3, [R2 + 4]
    ST R3, [R4 + 4]
    LD R3, [R2 + 5]
    ST R3, [R4 + 5]
    POP R4
    RET

bubble_sort:
    PUSH R4
    PUSH R5
    PUSH R6
    PUSH R7

    LI R4, 5              ; five outer passes

outer_pass:
    MOV R5, R2            ; pointer = array base
    ; LI R6, 5            ; five adjacent comparisons
    MOV R6, R4            ; number of comparisons = number of remaining passes


inner_pass:
    LD R3, [R5 + 0]       ; left value
    LD R7, [R5 + 1]       ; right value

    JAE R7, R3, no_swap   ; right >= left: already ordered

    ST R7, [R5 + 0]       ; otherwise swap them
    ST R3, [R5 + 1]

no_swap:
    CALL show_array
    CALL super_delay

    INC R5
    DEC R6
    JNE R6, ZERO, inner_pass

    DEC R4
    JNE R4, ZERO, outer_pass

    POP R7
    POP R6
    POP R5
    POP R4
    RET



delay:
    PUSH R4
    LI R4, 0xFFFF
delay_loop:
    DEC R4
    JNE R4, ZERO, delay_loop
    POP R4
    RET
super_delay:
    PUSH R4
    PUSH R7

    LI R4, 0x0020
super_delay_loop:
    CALL delay
    DEC R4
    JNE R4, ZERO, super_delay_loop

    POP R7
    POP R4
    RET

prank:
  LUI SP, 21
  LLI SP, 37
  RET



