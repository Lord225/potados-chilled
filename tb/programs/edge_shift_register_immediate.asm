; Both inputs of SH/ASH must use current register values, including load forwarding.
LI R2, 0x8001
LLI R3, 2
ASH R2, R3, -1       ; arithmetic right by 1 => C000
ST R2, [ZERO + 16]
LI R3, -2
LLI R4, 3
SH R4, R3, 1        ; left by 1 => 0006
ST R4, [ZERO + 17]
SH R4, R3, 2        ; amount 0 => 0006
ST R4, [ZERO + 18]
LD R5, [ZERO + 17]
SH R5, ZERO, -1     ; load-to-value dependency => 000C
ST R5, [ZERO + 19]
LLI R6, 2
ST R6, [ZERO + 20]
LD R6, [ZERO + 20]
SH R5, R6, -1       ; load-to-amount dependency, right by 1 => 0006
ST R5, [ZERO + 21]
SH R5, ZERO, -16    ; every bit shifted out => 0000
ST R5, [ZERO + 22]
LI R5, 0x8000
LLI R6, 31
ASH R5, R6, 1       ; full register amount 32, arithmetic right => FFFF
ST R5, [ZERO + 23]
NOT R6, R4          ; unary source A => FFF9
ST R6, [ZERO + 24]
HALT
