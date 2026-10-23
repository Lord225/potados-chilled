# POTADOS native-word C frontend

This frontend gives freestanding C the CPU's native address model. A C byte is
one 16-bit word: `CHAR_BIT == 16`, and `sizeof(char) == sizeof(short) ==
sizeof(int) == sizeof(void *) == 1`. Plain `char` is signed. `long` is 32 bits
(two words), `long long` is 64 bits (four words), and `_Bool` occupies one word.
There is no exact 8-bit C integer type. All object alignments are one word.

```c
int *io = (int *)0x8000;
io[0] = 42;                  /* hardware word address 0x8000 */
io[1] = 7;                   /* hardware word address 0x8001 */
```

The maintained `llvm/scripts/compile.py` driver invokes this frontend for C.
The Python API is:

```python
from potados_frontend import compile_c
compile_c("program.c", "program.ll", clang="clang", include_dirs=["include"])
```

Clang performs preprocessing only. Native predefines and the freestanding
headers in `include/` describe the target rather than the preprocessing host.
`pycparser` parses the preprocessed C; the frontend computes native types,
constant expressions, member offsets, `sizeof`, integer promotions, and pointer
arithmetic. LLVM optimizes the resulting IR and the POTADOS backend selects
instructions. Source line markers preserve source coordinates in diagnostics.

## LLVM representation

C data and function pointers are `i16` values containing native word addresses.
Arrays and structures use native word offsets; pointer differences and memory
helper counts also use words. Scalars wider than 16 bits are stored with the
least significant word first.

LLVM's private backing objects occupy two LLVM octets per native word. This
private layout does not determine C sizes. Address materialization uses
`__potados_address(ptr)`, and every C access uses `__potados_load_word(i16)` or
`__potados_store_word(i16, i16)`, with separate volatile variants. Wider accesses
are explicitly split into consecutive word operations. The backend lowers
these operations directly to native addressing and memory instructions.
Opaque operations prevent LLVM's octet alias rules and backing-object alignment
from changing native address arithmetic or inferring that every address is even.

All emitted modules carry the `potados.word-addressed=1` ABI flag. Static pointer
initializers use a symbol address plus a native word offset. Do not combine
ordinary Clang-generated IR with this representation.

## Current language scope

The frontend supports the project's freestanding integer programs, including
16/32/64-bit arithmetic, enums, typedefs, fixed arrays, structs/unions, volatile
accesses, function pointers, recursion, control flow, switches, casts,
`sizeof`, `_Alignof`, `offsetof` and `_Static_assert`. GNU packed attributes are
accepted; native members already have one-word alignment. Function asm labels
are supported. Functions retain `noinline` to preserve explicit call boundaries.

Unsupported constructs produce diagnostics: floating point, variadic functions,
variable-length arrays, bit-fields, static local objects, aggregate arguments or
returns by value, initialized global unions, and multi-character literals.
GNU inline assembly and compiler-specific expression extensions are outside the
supported dialect. There is no hosted C library; `include/` supplies native
integer/limits/basic memory declarations and the project supplies its runtime.

Run focused frontend checks with:

```sh
.venv/bin/python -m pytest -q llvm/tests/test_frontend.py
```

These check type/layout semantics and verify emitted LLVM IR. Executable
compiler regressions live in `llvm/tests` and run the actual SystemVerilog CPU
through cocotb and Verilator.
