# ABI and memory model

The frontend data layout is compatible with MSP430's little-endian 16-bit C
model. The CPU's native instruction and memory encodings are POTADOS-specific.

## Registers and function calls

| Register | ABI role |
| --- | --- |
| ZERO | Constant zero; never allocated. |
| SP | Native word-addressed stack pointer; never allocated. |
| R2–R5 | Allocatable 16-bit registers, arguments/results, caller saved. |
| R6 | Reserved expansion scratch register. |
| R7 | Reserved link register. |

Legalized 16-bit argument parts are assigned in order to R2, R3, R4, and R5.
Additional parts occupy two-byte stack slots. A 32-bit argument consumes two
parts and a 64-bit argument consumes four. Result parts are returned in R2–R5
in low-to-high order. Narrow integer arguments/results use promoted register
values under LLVM's extension rules.

`JAL R7, target` and `JALR R7, register` perform calls. `JMPR R7` returns.
Functions that overwrite R7 preserve their incoming return address in the
stack frame. There are no delay slots. C and LLVM fast calls share this
register convention; variadic and by-value aggregate calls are rejected.

## Stack

The compiler ABI grows the stack downward, even though the ISA also has upward
`PUSH`/`POP` convenience instructions. LLVM frame offsets and sizes are bytes;
the backend converts aligned stack accesses and adjustments to native word
units. Fixed frame allocation, outgoing argument areas, and spills use the
normal SP-relative instruction forms where possible.

The generated startup initializes SP to word address `0x7F00`. Globals occupy
a separate low RAM region. Dynamic `alloca` and stack objects requiring alignment greater than two bytes
are rejected; the target does not perform dynamic stack realignment. C data pointers
constructed from stack addresses are byte addresses (`SP * 2` plus the byte
offset), so pointer arithmetic remains consistent with local objects.

## Byte-addressed C data

Ordinary C pointers range over 65,536 bytes. Byte addresses `2*n` and `2*n+1`
refer to the low and high bytes of native RAM word `n` respectively. This gives
C a 32,768-word RAM view without changing the frontend's rules for GEP,
`sizeof`, arrays, padding, or structure layout.

A 16-bit aligned access shifts the byte pointer right by one and performs one
native load/store. Byte loads select a lane and apply the required zero/sign
extension. Byte stores preserve the other lane. These software sequences may
use temporary stack space and are not atomic read-modify-write operations.
Code requiring atomic or volatile device byte transactions must use an
appropriate native device interface instead.

The assembly printer assigns global symbols byte addresses, emits their
initialized contents in startup code, and keeps program ROM separate from
data RAM. Function pointers are code word addresses because calls target the
native program counter. Consequently the Harvard code/data address spaces
must not be conflated using pointer casts.

## Native MMIO

The CPU maps word addresses starting at `0x8000` to peripherals by default.
That region cannot be expressed through a 16-bit packed-byte C pointer. Use:

```c
potados_u16 potados_mmio_read(potados_u16 word_address);
void potados_mmio_write(potados_u16 word_address, potados_u16 value);
```

The supplied assembly implementations access the native address directly.
Arguments follow the normal ABI: R2 is the word address, R3 the store value,
and R2 the load result. These wrappers preserve the ordinary distinction
between C RAM pointers and peripheral word addresses.

## Arithmetic

The native `MUL` ignores both high operand bytes and computes unsigned
8 x 8 -> 16. A 16-bit C product is expanded from byte products, shifts, and
addition. Generic wide integer lowering operates on 16-bit parts.

Division/remainder helpers use unsigned restoring division with explicit
carry handling. The signed wrappers compute unsigned magnitudes first,
avoiding signed overflow when taking the magnitude of the minimum value.
For debugging, a zero divisor gives an all-ones unsigned quotient and the
original dividend as remainder; C still treats a zero divisor as undefined.

The target supplies no floating-point calling convention or operations.
