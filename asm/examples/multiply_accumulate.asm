; Compute (3 * 4) + (5 * 6) = 42.
; NOPs currently avoid unresolved pipeline RAW hazards.

.section code, 0x0000
    LLI R2, 3
    NOP
    NOP
    NOP

    LLI R3, 4
    NOP
    NOP
    NOP

    MUL R4, R2, R3
    NOP
    NOP
    NOP

    LLI R5, 5
    NOP
    NOP
    NOP

    LLI R6, 6
    NOP
    NOP
    NOP

    MUL R7, R5, R6
    NOP
    NOP
    NOP

    ADD R2, R4, R7
    NOP
    NOP
    NOP
    HALT
