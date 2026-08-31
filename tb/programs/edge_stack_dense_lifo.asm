; Exercise the stack as a dense LIFO without hazard-hiding NOPs.
LLI SP, 0x20
LLI R2, 0x11
LLI R3, 0x22

PUSH R2
PUSH R3
POP R4
POP R5

; Also exercise SP-relative memory after SP has returned to its initial value.
LLI R6, 0xA5
STSP R6, -1
LDSP R7, -1
HALT
