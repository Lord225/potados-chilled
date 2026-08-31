; Alternate writes and reads at one address without NOPs between RAM operations.
LLI R2, 64
LLI R3, 0x12
LLI R4, 0x34
LLI R5, 0x56

ST R3, [R2 + 0]
LD R6, [R2 + 0]
ST R4, [R2 + 0]
LD R7, [R2 + 0]
ST R5, [R2 + 0]
LD R6, [R2 + 0]
HALT
