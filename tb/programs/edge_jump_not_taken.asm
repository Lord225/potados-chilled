LLI R2, 3
.space 3
LLI R3, 4
.space 3
JE R2, R3, target

LLI R4, 0x11
.space 3
HALT

target:
LLI R4, 0x2A
.space 3
HALT
