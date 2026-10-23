; Signed byte additions and base/SP displacements at both boundaries.
LI SP, 0x0100
LI R2, 0x1280
ADDI R2, 127        ; 12FF
STSP R2, -128
ADDI R2, -128       ; 127F
STSP R2, 127
LDSP R3, -128
LDSP R4, 127
LI R5, 0xFFFF
ST R5, [R3 - 32]    ; address 12DF
LD R6, [R3 - 32]
LI R5, 0xFF80
ST R5, [R4 + 31]    ; address 129E
LD R7, [R4 + 31]
HALT
