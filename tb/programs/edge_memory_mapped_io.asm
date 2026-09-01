; The testbench maps its peripheral at 0x8000 and 0x8001.
;
; 0x8000 is a readable/writable output register.
; 0x8001 is a read-only input register.
LUI R2, 0x80
LLI R3, 0x5A

ST R3, [R2 + 0]
LD R4, [R2 + 0]
LD R5, [R2 + 1]
HALT
