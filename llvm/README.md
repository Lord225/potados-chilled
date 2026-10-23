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
    -> native POTADOS C frontend (CHAR_BIT=16, word pointers)
    -> LLVM IR linker + optimizer
    -> llc -load=Potados.so -march=potados_chilled
    -> POTADOS flat assembly
    -> the project's assembler
    -> cocotb + Verilator executing rtl/potados.sv
```

The native frontend defines the C word-addressed data model. LLVM handles
optimization, instruction selection, register allocation, calls, frames,
and assembly output through the POTADOS target.

## Build and run

Prerequisites: CMake 3.20+, Ninja, a C++17 compiler, Python 3.10+, and Clang for preprocessing. Native C parsing and IR generation require
`pycparser` and `llvmlite`. RTL tests also
need the parent project's Python environment and Verilator. The simulator also
requires cocotb and Verilator; there is no software execution fallback. `just` is optional;
every recipe delegates to a Python script.

From the repository root:

```sh
uv sync --project llvm
git submodule update --init llvm/llvm-project
uv run --project llvm python llvm/scripts/build.py all
uv run --project llvm python llvm/scripts/compile.py llvm/examples/src/sample.c -o llvm/examples/build/sample.asm -O2
uv run --project llvm python llvm/scripts/run.py run llvm/examples/build/sample.asm
```

The sample halts with `R2=0x002A` (42) and the default No Message HALT code.
Explicit assembly messages such as `HALT PASS` are exposed by the real RTL
output and displayed by the runner and debugger. The toolchain saves frontend/input IR and optimized IR next to the output for
inspection, retaining binary bitcode inputs verbatim.

The equivalent recipes run from `llvm/` after activating the toolchain environment:

```sh
. .venv/bin/activate
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
LLVM_BUILD=/path/to/llvm-build uv run --project llvm python llvm/scripts/build.py backend
LLVM_BUILD=/path/to/llvm-build uv run --project llvm python llvm/scripts/compile.py program.c -o program.asm -O2
```

The dynamically loaded module and `llc` executable must use the same LLVM
revision and build configuration. `CLANG`, `OPT`, `LLC`, and `LLVM_LINK`
explicitly select the preprocessor and LLVM tools; `POTADOS_MODULE` selects
the target module.

## Source and outputs

```sh
uv run --project llvm python llvm/scripts/compile.py program.c -o program.asm -O0
uv run --project llvm python llvm/scripts/compile.py program.ll -o program.asm -O2
uv run --project llvm python llvm/scripts/compile.py program.c -o program.hex -O2
uv run --project llvm python llvm/scripts/compile.py program.c -o program.hex --format annotated-hex
uv run --project llvm python llvm/scripts/compile.py program.c -o program.bin --format binary
uv run --project llvm python llvm/scripts/run.py debug program.asm
```

Inputs must define `main` (or select a different entry with
`--llc-flag=-potados-entry=NAME`). Generated startup initializes SP, initializes data
RAM, calls `main`, and halts with its result in R2. The runtime is linked by
default. `--no-runtime` is useful for small self-contained programs and backend
tests. `--llc-flag=-regalloc=basic` passes an additional code-generator option;
`POTADOS_EXTRA_FLAGS` supplies a shell-style list of options.

POTADOS C has **16-bit bytes** (`CHAR_BIT == 16`). `char`, `short`, `int`,
and pointers each occupy one native cell; `long` occupies two and `long long`
four. Native headers provide exact 16/32/64-bit types, with no exact 8-bit type.
`sizeof`, structure layout, array strides, and pointer differences all use
these cell units. The native frontend emits the required word-addressed IR
marker; ordinary host or MSP430 IR is incompatible and rejected.

C data pointers contain native hardware addresses directly. An `int *`
advances by one cell, including MMIO:

```c
int main(void) {
    volatile int *io = (volatile int *)0x8000;
    io[0] = 42;  /* hardware address 0x8000 */
    io[1] = 99;  /* hardware address 0x8001 */
    return io[0];
}
```

The hardware multiplier computes unsigned **8 x 8 -> 16** products, ignoring
the high eight bits of its inputs. LLVM's 16-bit integer multiplication is expanded
to preserve C semantics. See the [ISA specification](../potados_spec.md).

## Layout and documentation

```text
llvm-project/       pinned upstream LLVM source submodule
potados-frontend/  native C parser, word-addressed IR generation, and headers
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
- [ABI and memory model](docs/abi.md): registers, calls, stack, and native cell sizes.
- [Examples and testing](docs/examples-and-testing.md): expected results and verification.
- [Backend development](docs/backend-guide.md): compiler stages and debugging.
- [Emulator guide](potados-emulator/README.md): execution, tracing, and debugger commands.

## Integration limits

The target emits flat textual assembly. It does not emit relocatable objects,
ELF executables, DWARF, or linker relocations, and it has no integrated LLVM
assembler or dedicated upstream Clang triple. The workflow is freestanding, without a
hosted C library, operating system, exceptions, interrupts ABI, TLS, floating
point, atomics, variadic functions, by-value aggregate calls, or dynamic
`alloca`, or over-aligned stack objects. Fixed stack frames, spills, and ordinary integer calls are handled
by the backend. Every emulator run executes the actual CPU pipeline and
synchronous memories in Verilator. Debugger stepping and execution budgets
count clock cycles; breakpoints stop fetch acceptance with older instructions
still present in the pipeline. See the emulator guide for those boundaries.

The native C frontend supports the freestanding integer subset exercised by
the examples and tests. It rejects variable-length arrays, bit-fields, static
local objects, initialized union globals, and multi-character literals. Native
headers are supplied under `potados-frontend/include`; host C library headers
describe a different byte model and must not be substituted.

The runtime defines deterministic results for division by zero for debugging;
this does not make division by zero defined in C. Limits and supported behavior
are documented alongside the tests rather than inferred from LLVM accepting
an input file.
