JMP target

; This fallthrough path must be discarded by a taken jump.
LLI R2, 0x11
.space 2
HALT

target:
LLI R2, 0x2A
.space 3
HALT
