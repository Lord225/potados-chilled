# POTADOS assembler

`potados-asm` is a dependency-free, importable Python assembler for the
POTADOS Chilled CPU. Addresses are **16-bit word addresses**, matching the CPU
program counter and the ROM's `$readmemh` layout.

## Installation and CLI

```sh
python -m pip install -e ./asm
potados-asm program.asm -o rom.hex
potados-asm program.asm -o listing.hex --format annotated-hex
potados-asm program.asm -o program.bin --format binary
python -m potados_asm program.asm --format bytecode
```

`-` can be used as the source path to read assembly from standard input. If
`-o` is omitted, output is written to standard output.

The CPU Cocotb programs in [`../tb/programs/`](../tb/programs/) are assembly
sources. Their test runners assemble them in Python and preload the resulting
words directly into the simulator's ROM memory before reset; no temporary
`rom.hex` is needed. The CLI output remains useful for FPGA builds and manual
simulations that use the ROM file-loading path.

Output formats:

- `hex`: 16-bit `$readmemh` words, with `@ADDR` records for sparse sections;
- `annotated-hex` or `hex-comments`: the same format with address/source
  comments suitable for debugging;
- `bytecode`: textual big-endian byte pairs such as `0xB0 0x40`;
- `binary`: raw big-endian bytes, including zero-filled gaps between sections.

The current machine encodings are documented in [`../potados_spec.md`](../potados_spec.md).
Programs assembled for the earlier ISA must be reassembled.

## Source syntax

Mnemonics and registers are case-insensitive. Labels and constants are
case-sensitive. Comments begin with `;` or `#` and are ignored inside quoted
strings.

```asm
.section vectors, 0x0000
    JMP start

.section data, 0x0040
message:
    .string "Hello; POTADOS!"
    .word 0xBEEF, message

.section code, 0x0100
start:
    LLI R2, %lo(message)
    LUI R3, %hi(message)
    ADDI R2, 1
    JNE R2, ZERO, start
    HALT
```

Supported directives:

- `.org ADDRESS` changes the word location counter;
- `.section NAME, ADDRESS` changes the location and defines `NAME`;
- `.equ NAME, EXPRESSION` defines a constant;
- `.word`/`.dw`, `.byte`/`.db`, and `.string` emit word-addressed data;
- `.space COUNT[, VALUE]` emits reserved/fill words.

Expressions support decimal, binary, octal, and hexadecimal integers,
character literals, symbols, parentheses, unary `+`/`-`, addition/subtraction,
and `%hi()`, `%lo()`, `%rel()`.

ADDI, LDSP, and STSP accept signed 8-bit constants (`-128..127`). LD/ST
displacements are signed 6-bit values (`-32..31`); shifts accept signed 5-bit
displacements (`-16..15`). SH/ASH update their first register in place and use
the second register plus the immediate as the signed shift amount. Negative
amounts shift left; positive amounts shift right.

Canonical memory and in-place immediate forms are:

```asm
ADDI R2, -1
ADDI R2, R2, -1       ; accepted for clarity; both registers must match
LD   R4, [R2 + 3]
ST   R4, [R2 - 1]
LDSP R4, 8
STSP R4, -8
SH   R2, ZERO, -1     ; R2 <<= 1
ASH  R2, R3, 2        ; R2 >>= signed(R3 + 2), preserving the sign
```

Convenience pseudo-instructions keep common code compact. They expand into
ordinary POTADOS ISA instructions, so no RTL support is required:

```asm
LI  R2, 42        ; one word: LLI R2, 42
LI  R3, 0x1234    ; two words: LUI R3, 0x12; ADDI R3, 0x34
LI  R4, 0x12FF    ; two words: LUI R4, 0x13; ADDI R4, -1
LEA R3, table      ; address-oriented spelling of LI
MOV R4, R2        ; ADD R4, R2, ZERO
ADD R4, R2        ; destructive form: ADD R4, R4, R2
LD  R3, R2        ; zero-offset form: LD R3, [R2 + 0]
ST  R3, R2        ; zero-offset form: ST R3, [R2 + 0]
CLR R2            ; LLI R2, 0
INC R2            ; ADDI R2, 1
DEC R2            ; ADDI R2, -1
NEG R4, R2        ; SUB R4, ZERO, R2; ``NEG R2`` is destructive
J loop            ; JMP loop
CALL function     ; JAL R7, function
RET               ; JMPR R7
```

`LI` uses one word for compile-time constants from `0` through `255`; all
other 16-bit values use the two-word expansion. Symbolic `LI` expressions use
the two-word form to keep forward-label addresses stable. The expansion adjusts
the upper byte when the low byte requires a negative signed ADDI.

`LD` and `ST` use a bracketed memory operand: `[PTR + IMM]` or
`[PTR - IMM]`. Whitespace inside the brackets is optional.

Direct and conditional jumps emit two words. Labels therefore automatically
resolve to the correct word address:

```asm
loop:
    ADDI R2, 1
    JNE R2, R3, loop

    JAL R7, function
    HALT

function:
    JMPR R7
```

## Python API

```python
from potados_asm import assemble

result = assemble("LLI R2, 7\nHALT\n", filename="example.asm")
print(result.words)                  # {0: 0x5E02, 1: 0xF000}
print(result.to_hex())
binary = result.to_binary()
symbols = result.symbols
```
