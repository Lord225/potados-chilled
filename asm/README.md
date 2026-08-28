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

Canonical memory and in-place immediate forms are:

```asm
ADDI R2, -1
ADDI R2, R2, -1       ; accepted for clarity; both registers must match
LD   R4, R2, 3
LD   R4, [R2 + 3]
ST   R4, [R2 - 1]
LDSP R4, 8
STSP R4, -8
```

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
print(result.words)                  # {0: 0x51C2, 1: 0xF000}
print(result.to_hex())
binary = result.to_binary()
symbols = result.symbols
```
