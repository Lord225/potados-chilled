# POTADOS Chilled LLVM backend

This directory contains the out-of-tree LLVM target, arithmetic runtime, C
examples, build scripts, and a cocotb/Verilator RTL simulator and debugger.
The simulator instantiates this project’s `rtl/potados.sv` through a small
SystemVerilog wrapper; Python drives clocks and inspects real hardware state.
Its organization follows [KAMP LLVM](https://github.com/Lord225/kamp-llvm).
The assembler and hardware remain in this project's existing `../asm` and
`../rtl` directories.

```text
freestanding C / LLVM IR
    -> MSP430 frontend (16-bit C data and pointer model)
    -> LLVM IR linker + optimizer
    -> llc -load=Potados.so -march=potados_chilled
    -> POTADOS flat assembly
    -> the project's assembler
    -> cocotb + Verilator executing rtl/potados.sv
```

MSP430 supplies only the frontend data model. POTADOS instruction selection,
register allocation, calling convention, stack layout, memory access, startup,
and assembly output belong to this backend.

## Build and run

Prerequisites: CMake 3.20+, Ninja, a C++17 compiler, Python 3.10+, and a Clang
with an MSP430 frontend. The validated frontend is Clang 21. RTL tests also
need the parent project's Python environment and Verilator. The simulator also
requires cocotb and Verilator; there is no software execution fallback. `just` is optional;
every recipe delegates to a Python script.

From the repository root:

```sh
git submodule update --init llvm/llvm-project
python3 llvm/scripts/build.py all
python3 llvm/scripts/compile.py llvm/examples/src/sample.c -o llvm/examples/build/sample.asm -O2
python3 llvm/scripts/run.py run llvm/examples/build/sample.asm
```

The sample halts with `R2=0x002A` (42). The toolchain saves frontend/input IR and optimized IR next to the output for
inspection, retaining binary bitcode inputs verbatim.

The equivalent recipes run from `llvm/`:

```sh
just build
just example sample -O2
just emulator examples/build/sample.asm
just emulator-cui examples/build/sample.asm
just verify-programs
```

`JOBS` defaults to 2. The pinned LLVM checkout is revision
`c47d1cf955f607fea1d089b9e05aedf8867231ff` (LLVM 23). LLVM builds can take
substantial disk space and time. To reuse tools built from the same revision:

```sh
LLVM_BUILD=/path/to/llvm-build python3 llvm/scripts/build.py backend
LLVM_BUILD=/path/to/llvm-build python3 llvm/scripts/compile.py program.c -o program.asm -O2
```

The dynamically loaded module and the `llc` executable must use the same LLVM
revision and build configuration. The frontend can be an older compatible
Clang. `CLANG`, `OPT`, `LLC`, and `LLVM_LINK` explicitly select individual
executables; `POTADOS_MODULE` selects the target module.

## Source and outputs

```sh
python3 llvm/scripts/compile.py program.c -o program.asm -O0
python3 llvm/scripts/compile.py program.ll -o program.asm -O2
python3 llvm/scripts/compile.py program.c -o program.hex -O2
python3 llvm/scripts/compile.py program.c -o program.hex --format annotated-hex
python3 llvm/scripts/compile.py program.c -o program.bin --format binary
python3 llvm/scripts/run.py debug program.asm
```

Inputs must define `main` (or select a different entry with
`--llc-flag=-potados-entry=NAME`). Generated startup initializes SP, initializes data
RAM, calls `main`, and halts with its result in R2. The runtime is linked by
default. `--no-runtime` is useful for small self-contained programs and backend
tests. `--llc-flag=-regalloc=basic` passes an additional code-generator option;
`POTADOS_EXTRA_FLAGS` supplies a shell-style list of options.

For C, `char` is 8 bits, `short` and `int` are 16 bits, `long` is 32 bits,
`long long` is 64 bits, and pointers are 16 bits. LLVM IR inputs must use the
same data layout; explicit incompatible layouts are rejected, and inputs with
no layout receive the target layout before optimization. Include `potados.h` for
explicitly sized types and native MMIO accessors. Ordinary C pointers address
**bytes**; the backend maps each pair of bytes to one native 16-bit RAM word.
Native hardware addresses passed to MMIO functions are **word addresses**:

```c
#include "potados.h"
potados_u16 main(void) {
    potados_mmio_write(0x8000, 42);
    return potados_mmio_read(0x8000);
}
```

The hardware multiplier computes unsigned **8 x 8 -> 16** products, ignoring
the high bytes of its inputs. LLVM's 16-bit integer multiplication is expanded
to preserve C semantics. See the [ISA specification](../potados_spec.md).

## Layout and documentation

```text
llvm-project/       pinned upstream LLVM source submodule
potados-backend/   target C++ and TableGen files
potados-emulator/  cocotb/Verilator wrapper, RTL runner, and debugger
runtime/           freestanding arithmetic, memory, and MMIO support
examples/          maintained C sources and expected results
scripts/           build, compilation, execution, and verification drivers
tests/             RTL execution, compiler integration, and driver checks
docs/              ABI and development notes
build/             generated tools and target module (ignored)
```

- [Getting started](docs/getting-started.md): build options and manual workflow.
- [ABI and memory model](docs/abi.md): registers, calls, stack, and byte access.
- [Examples and testing](docs/examples-and-testing.md): expected results and verification.
- [Backend development](docs/backend-guide.md): compiler stages and debugging.
- [Emulator guide](potados-emulator/README.md): execution, tracing, and debugger commands.

## Integration limits

The target emits flat textual assembly. It does not emit relocatable objects,
ELF executables, DWARF, or linker relocations, and it has no integrated LLVM
assembler or dedicated Clang triple. The workflow is freestanding, without a
hosted C library, operating system, exceptions, interrupts ABI, TLS, floating
point, atomics, variadic functions, by-value aggregate calls, or dynamic
`alloca`, or stack objects requiring alignment above two bytes. Fixed stack frames, spills, and ordinary integer calls are handled
by the backend. Every emulator run executes the actual CPU pipeline and
synchronous memories in Verilator. Debugger stepping and execution budgets
count clock cycles; breakpoints stop fetch acceptance with older instructions
still present in the pipeline. See the emulator guide for those boundaries.

The runtime defines deterministic results for division by zero for debugging;
this does not make division by zero defined in C. Limits and supported behavior
are documented alongside the tests rather than inferred from LLVM accepting
an input file.
