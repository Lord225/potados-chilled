# Native word-addressed C ABI

POTADOS C uses **16-bit bytes** (`CHAR_BIT == 16`). A byte is one native
addressable cell. The native frontend computes C types, `sizeof`, pointer
arithmetic, and structure layout before emitting LLVM IR; it does not borrow
an eight-bit-byte frontend's layout.

| C type | Bits | `sizeof` in native cells |
| --- | --- | --- |
| `char`, `signed char`, `unsigned char` | 16 | 1 |
| `short`, `int` | 16 | 1 |
| `long` | 32 | 2 |
| `long long` | 64 | 4 |
| Object or function pointer | 16 | 1 |

Plain `char` is signed. Exact-width `int16_t`, `int32_t`, and `int64_t` and their
unsigned counterparts are supplied in `<stdint.h>`. There is no exact-width
`int8_t` or `uint8_t`. `size_t` is unsigned int and `ptrdiff_t` is int.

## Registers and calls

| Register | ABI role |
| --- | --- |
| ZERO | Constant zero; never allocated. |
| SP | Native word-addressed stack pointer; never allocated. |
| R2–R5 | Allocatable 16-bit registers, arguments/results, caller saved. |
| R6 | Reserved expansion scratch register. |
| R7 | Reserved link register. |

Legalized 16-bit argument parts are assigned in order to R2, R3, R4, and R5.
Additional parts occupy one-cell stack slots. A 32-bit argument consumes two
parts and a 64-bit argument consumes four. Result parts are returned in R2–R5
in low-to-high order. Narrow LLVM integer parts use LLVM's extension rules.

`JAL R7, target` and `JALR R7, register` call functions; `JMPR R7` returns.
Functions that overwrite R7 preserve their incoming link in the stack frame.
There are no delay slots. The ABI has no variadic or by-value aggregate calls.

## Stack and data memory

The compiler grows the stack downward from native word address `0x7F00`.
The ISA's upward `PUSH`/`POP` convenience instructions increment/decrement SP
by one cell. LD/ST/LDSP/STSP displacements count native cells, so `+1` selects
the next 16-bit word. RAM and program ROM are separate Harvard memories.

All object pointers hold native data addresses directly. A pointer to a
one-cell type advances by one; `long *` advances by two and `long long *` by
four. Pointer subtraction reports element counts. A structure with three
one-cell members occupies three cells, including with the packed attribute.
Character arrays store one full 16-bit character per cell. Memory helper
counts likewise count native C bytes/cells: `memset(p, 0x1234, n)` stores
`0x1234` into each of the `n` cells.

The assembly printer assigns global symbols native data addresses and emits
startup stores for their initialized contents. Function pointers contain
program word addresses. Converting between function and object pointers does
not join the separate code/data memories. Dynamic `alloca`, dynamic stack
realignment, and over-aligned stack objects are unsupported.

## MMIO

The default RAM region is `0x0000..0x7fff`; peripheral addresses start at
`0x8000`. Ordinary volatile pointers reach the native bus directly:

```c
volatile int *io = (volatile int *)0x8000;
io[0] = 42;  /* native address 0x8000 */
io[1] = 99;  /* native address 0x8001 */
```

The optional `potados_mmio_read(word_address)` and
`potados_mmio_write(word_address, value)` helpers use those same addresses.
R2 holds the address, R3 the store value, and R2 the read result.

## Termination

Startup calls `main` and executes bare `HALT`, whose message is zero
(No Message). The C return value remains in R2. Assembly may select an explicit
message such as `HALT PASS`; see the [ISA HALT table](../../potados_spec.md).
The simulator reads this latched RTL output. All message codes halt; none
becomes a host process exit code.
