; (3 * 4) + (5 * 6) = 42.
LLI R2, 3
.space 3
LLI R3, 4
.space 3
MUL R4, R2, R3
.space 3
LLI R5, 5
.space 3
LLI R6, 6
.space 3
MUL R7, R5, R6
.space 3
ADD R2, R4, R7
.space 3
HALT
