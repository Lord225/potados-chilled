; Exercise one request per cycle and the signed IMM6 displacement limits.
LLI R2, 64
LLI R3, 0x11
LLI R4, 0xA5

ST R3, [R2 - 32]
ST R4, [R2 + 31]
LD R5, [R2 - 32]
LD R6, [R2 + 31]
LD R7, [R2 - 32]
HALT
