# POTADOS CHILLED CPU

## ISA

An instruction occupies one 16-bit word unless shown with `IMM16` below.
Conditional jumps, `JMP`, and `JAL` occupy two words; the second word is the
absolute 16-bit word address of the target.

Fields below run from instruction bit 15 on the left to bit 0 on the right.
Each register field is three bits. `I5`, `I6`, and `I8` use the immediate
bit ordering documented below.

```text
NOP  0000 000 000 000   000
ADD  0000 DST 001 SRC_B SRC_A
SUB  0000 DST 010 SRC_B SRC_A
AND  0000 DST 011 SRC_B SRC_A
OR   0000 DST 100 SRC_B SRC_A
XOR  0000 DST 101 SRC_B SRC_A
NOT  0000 DST 110 000   SRC_A
MUL  0000 DST 111 SRC_B SRC_A

SGE  0001 DST 011 SRC_B SRC_A
SL   0001 DST 010 SRC_B SRC_A
SE   0001 DST 101 SRC_B SRC_A
SNE  0001 DST 100 SRC_B SRC_A
SAE  0001 DST 110 SRC_B SRC_A
SB   0001 DST 111 SRC_B SRC_A

SH   0010 I5 0 SRC_B SDP
ASH  0011 I5 0 SRC_B SDP

ADDI 0100 I8 0 SDP
LLI  0101 I8 0 DST
LUI  0101 I8 1 DST

LD   0110 I6 PTR_B DST
ST   0111 I6 PTR_B SRC_A
LDSP 1000 I8 0 DST
STSP 1001 I8 0 SRC_A

JGE  1010 000 011 SRC_B SRC_A IMM16
JL   1010 000 010 SRC_B SRC_A IMM16
JE   1010 000 101 SRC_B SRC_A IMM16
JNE  1010 000 100 SRC_B SRC_A IMM16
JAE  1010 000 110 SRC_B SRC_A IMM16
JB   1010 000 111 SRC_B SRC_A IMM16

JMP  1011 000 001 000 000   IMM16
JAL  1011 DST 010 000 000   IMM16

PUSH 1100 000 001 000 SRC_A
POP  1100 DST 010 000 000

JMPR 1101 000 001 000 SRC_A
JALR 1101 DST 010 000 SRC_A

FADD 1110 DST 001 SRC_B SRC_A
FSUB 1110 DST 010 SRC_B SRC_A
FMUL 1110 DST 011 SRC_B SRC_A
FDIV 1110 DST 100 SRC_B SRC_A
ITOF 1110 DST 101 000   SRC_A
FTOI 1110 DST 110 000   SRC_A
FTOU 1110 DST 111 000   SRC_A

HALT 1111 IIII IIII IIII
```

## Instruction reference

For binary arithmetic, comparisons, conditional jumps, and binary FPU
instructions, `SRC_A` is the left operand in bits `[2:0]` and `SRC_B` is the
right operand in bits `[5:3]`: `DST = SRC_A op SRC_B`. Unary instructions
read `SRC_A`. Assembly operand order is `OP DST, SRC_A, SRC_B`.

| Instruction | Operation |
| --- | --- |
| `NOP` | No operation. |
| `ADD`, `SUB`, `AND`, `OR`, `XOR`, `MUL` | Integer arithmetic and bitwise operations on A and B; `SUB` computes A minus B. Results wrap to 16 bits. |
| `NOT` | Bitwise complement of A. |
| `SGE`, `SL` | Set `DST` to 1 when signed A is greater than or equal to / less than B; otherwise set it to 0. |
| `SE`, `SNE` | Set `DST` to 1 when A equals / differs from B; otherwise set it to 0. |
| `SAE`, `SB` | Set `DST` to 1 when unsigned A is above or equal to / below B; otherwise set it to 0. |
| `SH`, `ASH` | Shift `SDP` in place by the signed amount `SRC_B + IMM5`. Negative amounts shift left; positive amounts shift right. `ASH` sign extends a right shift; `SH` zero fills. |
| `ADDI` | Add a sign-extended 8-bit immediate to `SDP`. |
| `LLI` | Load the immediate byte into the lower 8 bits of `DST` and clear its upper 8 bits. |
| `LUI` | Load the immediate byte into the upper 8 bits of `DST` and clear its lower 8 bits. |
| `LD` | `DST = RAM[PTR_B + IMM6]`. Syntax: `LD DST, [PTR_B + IMM]`. |
| `ST` | `RAM[PTR_B + IMM6] = SRC_A`. Syntax: `ST SRC_A, [PTR_B + IMM]`. |
| `LDSP` | `DST = RAM[SP + IMM8]`. |
| `STSP` | `RAM[SP + IMM8] = SRC_A`. |
| `JGE`, `JL`, `JE`, `JNE`, `JAE`, `JB` | Jump to `IMM16` when the corresponding comparison of A and B is true. Conditions match the corresponding set instructions. |
| `JMP` | Jump to `IMM16`. |
| `JAL` | Jump to `IMM16` and store the address after both instruction words in `DST`. |
| `PUSH` | Atomic stack operation: `RAM[SP] = SRC_A; SP += 1`. |
| `POP` | Atomic stack operation: `SP -= 1; DST = RAM[SP]`. |
| `JMPR` | Jump to the word address in `SRC_A`. |
| `JALR` | Jump to the word address in `SRC_A` and store the following instruction's address in `DST`. |
| `FADD`, `FSUB`, `FMUL`, `FDIV`, `ITOF`, `FTOI`, `FTOU` | Floating-point extension encodings. The current CPU exposes an FPU interface but has no built-in FPU implementation. |
| `HALT` | Halt execution; the lower 12 bits are available for extensions. |

The effective shift amount is the signed 16-bit sum of the register and the
sign-extended immediate, with addition wrapping to 16 bits. An amount of zero
leaves the value unchanged. Magnitudes of 16 or greater shift out all bits;
an arithmetic right shift of a negative value continues to fill with ones.
Use `SH R2, ZERO, -1` for an immediate left shift of R2 by one bit.

## Register fields

- `SRC_A`: bits `[2:0]`, the first/left source register.
- `SRC_B` / `PTR_B`: bits `[5:3]`, the second/right source or memory pointer.
- `DST`: bits `[11:9]` for ALU, set, FPU, `JAL`, `POP`, and `JALR`;
  bits `[2:0]` for shifts, immediate operations, and loads.
- `SDP`: bits `[2:0]`, a register read and written by the same instruction.

| Encoding | Register |
| --- | --- |
| `000` | ZERO (reads as zero; writes are discarded) |
| `001` | SP |
| `010`–`111` | R2–R7 |

## Immediate encodings

Short immediates place their **least significant bit at instruction bit 11**.
Following bits descend toward bit 4, aligning equal weights across formats.
All signed immediates use two's complement.

| Format | Instruction bits, left to right | Weights, left to right | Range / use |
| --- | --- | --- | --- |
| IMM5 | `[11:7]` | `1, 2, 4, 8, -16` | `-16..15`; shift displacement. Bit 6 is reserved and emitted as zero. |
| IMM6 | `[11:6]` | `1, 2, 4, 8, 16, -32` | `-32..31`; LD/ST displacement. |
| IMM8 | `[11:4]` | `1, 2, 4, 8, 16, 32, 64, -128` | `-128..127`; ADDI/LDSP/STSP. Bit 3 is reserved and emitted as zero. |
| IMM8 byte | `[11:4]` | `1, 2, 4, 8, 16, 32, 64, 128` | LLI/LUI load a raw byte; bit 3 selects LUI. |
| IMM9 | `[11:3]` | `1, 2, 4, 8, 16, 32, 64, 128, -256` | Reserved format; no current opcode uses it. |
| IMM16 | Second word `[15:0]` | Normal binary ordering, bit 0 has weight 1 | `0..65535`; absolute jump targets. |

For example, `ADDI R2, 1` encodes as `0x4802`, `ADDI R2, -128` as `0x4012`,
and `LLI R2, 7` as `0x5E02`.

## Memory

POTADOS has a 16-bit word address space, `0x0000..0xFFFF`, with 16-bit values.
