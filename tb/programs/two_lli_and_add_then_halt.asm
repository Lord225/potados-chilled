; NOP drain slots intentionally avoid RAW hazards.
LLI R2, 7
.space 3
LLI R3, 9
.space 3
ADD R4, R2, R3
.space 3
HALT
