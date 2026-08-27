# POTADOS CHILLED CPU

## ISA

Unless noted otherwise, an instruction occupies one 16-bit word. `JGE` through
`JAL` are two-word instructions; their second word contains the `IMM16` target.

```text

NOP  0000 000 000 000 000
ADD  0000 DST 001 SRC_A SRC_B
SUB  0000 DST 010 SRC_A SRC_B
AND  0000 DST 011 SRC_A SRC_B
OR   0000 DST 100 SRC_A SRC_B
XOR  0000 DST 101 SRC_A SRC_B
NOT  0000 DST 110 000   SRC_B
MUL  0000 DST 111 SRC_A SRC_B

SGE  0001 DST 000 SRC_A SRC_B
SL   0001 DST 001 SRC_A SRC_B
SE   0001 DST 010 SRC_A SRC_B
SNE  0001 DST 011 SRC_A SRC_B
SAE  0001 DST 100 SRC_A SRC_B
SB   0001 DST 101 SRC_A SRC_B

SH   0010 0II III SRC DST
ASH  0011 0II III SRC DST

ADDI 0100 III III III SDP
LLI  0101 III III 0II SDP
LUI  0101 III III 1II SDP

LD   0110 III III PTR DST
ST   0111 III III PTR SRC
LDSP 1000 III III III SDP
STSP 1001 III III III SDP

JGE  1010 000 000 SRC_A SRC_B XXXX XXXX XXXX XXXX
JL   1010 000 001 SRC_A SRC_B XXXX XXXX XXXX XXXX
JE   1010 000 010 SRC_A SRC_B XXXX XXXX XXXX XXXX
JNE  1010 000 011 SRC_A SRC_B XXXX XXXX XXXX XXXX
JAE  1010 000 100 SRC_A SRC_B XXXX XXXX XXXX XXXX
JB   1010 000 101 SRC_A SRC_B XXXX XXXX XXXX XXXX

JMP  1011 000 001 000 000 XXXX XXXX XXXX XXXX
JAL  1011 000 010 000 DST XXXX XXXX XXXX XXXX

PUSH 1100 000 001 000 SRC
POP  1100 000 010 000 DST

JMPR 1101 000 001 000 SRC
JALR 1101 000 010 SRC_A DST

FADD 1110 DST 001 SRC_A SRC_B
FSUB 1110 DST 010 SRC_A SRC_B
FMUL 1110 DST 011 SRC_A SRC_B
FDIV 1110 DST 100 SRC_A SRC_B
ITOF 1110 DST 101 000   SRC_B
FTOI 1110 DST 110 000   SRC_B
FTOU 1110 DST 111 000   SRC_B

HALT 1111 III III III III
```

## Instruction reference

For binary arithmetic, compare, conditional-jump, and binary FPU instructions,
`SRC_A` is bits `[5:3]` (the left operand) and `SRC_B` is bits `[2:0]` (the
right operand): `DST = SRC_A op SRC_B`. Unary instructions use `SRC_B`.

| Instruction | Operation |
| --- | --- |
| `NOP` | No operation. |
| `ADD`, `SUB`, `AND`, `OR`, `XOR`, `NOT`, `MUL` | Integer arithmetic and bitwise operations. |
| `SGE` | Set `DST` to `1` if the signed comparison is greater than or equal; otherwise set it to `0`. |
| `SL` | Set `DST` to `1` if the signed comparison is less than; otherwise set it to `0`. |
| `SE` | Set `DST` to `1` if the operands are equal; otherwise set it to `0`. |
| `SNE` | Set `DST` to `1` if the operands are not equal; otherwise set it to `0`. |
| `SAE` | Set `DST` to `1` if the unsigned comparison is above or equal; otherwise set it to `0`. |
| `SB` | Set `DST` to `1` if the unsigned comparison is below; otherwise set it to `0`. |
| `SH` | Logical shift. The `IMM6` shift amount is encoded in the instruction; negative amounts shift left. |
| `ASH` | Arithmetic shift. The `IMM6` shift amount is encoded in the instruction; negative amounts shift left. |
| `ADDI` | Add a 9-bit SE immediate constant to the `SDP` register. |
| `LLI` | Load the 8 bit SE immediate into lower 8 bits of the `SDP` register and clear its upper 8 bits. |
| `LUI` | Load the 8 bit SE immediate into higher 8 bits of the `SDP` register and clear its lower 8 bits. |
| `LD` | Load `RAM[PTR + IMM]` into `DST`, using the 6bit SE immediate as a displacement from `PTR`. |
| `ST` | Store `SRC` to `RAM[PTR + IMM]`, using the 6bit SE immediate as a displacement from `PTR`. |
| `LDSP` | Load `RAM[SP+IMM]` into `DST`, using the 9bit SE immediate as a displacement from `SP` register. |
| `STSP` | Store `SRC` to `RAM[SP+IMM]`, using the 9bit SE immediate as a displacement from `SP` register. |
| `JGE`, `JL`, `JE`, `JNE` | Jump to `IMM16` when the signed comparison is respectively greater/equal, less, equal, or not equal. |
| `JAE`, `JB` | Jump to `IMM16` when the unsigned comparison is respectively above/equal or below. |
| `JMP` | Unconditional jump to `IMM16`. |
| `JAL` | Jump to `IMM16` and store the return address in `DST`. |
| `PUSH` | Atomic stack operation: `RAM[SP] = SRC; SP += 1`. |
| `POP` | Atomic stack operation: `SP -= 1; DST = RAM[SP]`. |
| `JMPR` | Jump to the address held in `SRC`. |
| `JALR` | Jump to the address held in `SRC` and store the return address in `DST`. |
| `FADD`, `FSUB`, `FMUL`, `FDIV`, `ITOF`, `FTOI`, `FTOU` | Floating-point extension instructions. |
| `HALT` | Halt execution; the opcode space may also be used for extensions. |

## Glossary

- `SRC_A` — 3-bit first/left source-register field, bits `[5:3]`.
- `SRC_B` — 3-bit second/right source-register field, bits `[2:0]`.
- `SRC` — an instruction-specific 3-bit source-register field.
- `DST` — 3-bit destination-register field.
- `SDP` — 3-bit source-and-destination register pair.
- `PTR` — 3-bit pointer-register field used by `LD` and `ST`.
- `IMM` — the immediate field encoded by a particular instruction.
- `IMM6`, `IMM8`, `IMM16` — immediate encodings decoded below, sign extended.

## Registers

```text
000 | ZERO
001 | SP
010 | R2
011 | R3
100 | R4
101 | R5
110 | R6
111 | R7
```

## Immediate encodings

### IMM6

Used only by the shift instructions.

```text
III III
 \\\ \\\  
  \\\ \\\  
   \\\ \\\  
    \\\ \\\__ 1
     \\\ \\__ 2
      \\\ \__ 4
       \\\___ 8
        \\___ 16
         \___ -32
```

### IMM8

Used for `LD` and `ST` displacements. Immediate bit mangling aligns bits of
equal weight to simplify immediate-handling logic.

```text
III III III
 \\\ \\\ \\\_ -256
  \\\ \\\ \\_ 64
   \\\ \\\ \_ 32
    \\\ \\\__ 16
     \\\ \\__ 1
      \\\ \__ 2
       \\\___ 4
        \\___ 8
         \___ 16
```

### IMM16

Used only by two-word opcodes. Immediate bit mangling aligns bits of equal
weight to simplify immediate-handling logic.

```text
XXXX XXXX XXXX XXXX
                 \\\_ 1
                  \\_ 2
                   \_ 4
                    ...
```


### Memory

Potados uses `0x0000-0xFFFF` 16 bit values as it's adress space. 
