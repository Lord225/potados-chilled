; Store an array in RAM, then copy it to the LED MMIO registers.
; RAM:  0x0000..0x0005
; LEDs: 0x8000..0x8005

LI R2, 0x0000
LI SP, 0x0100

LI R3, 0
ST R3, [R2 + 0]
LI R3, 100
ST R3, [R2 + 1]
LI R3, 148
ST R3, [R2 + 2]
LI R3, 200
ST R3, [R2 + 3]
LI R3, 255
ST R3, [R2 + 4]
LI R3, 32
ST R3, [R2 + 5]

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
