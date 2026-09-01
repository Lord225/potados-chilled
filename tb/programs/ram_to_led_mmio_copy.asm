; Copy RAM[0..5] to LED PWM MMIO registers 0x8000..0x8005.
; The testbench deliberately supplies RAM contents before this program runs.

LI R2, 0x0000
LI SP, 0x0100
CALL show_array
HALT

show_array:
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

    RET
