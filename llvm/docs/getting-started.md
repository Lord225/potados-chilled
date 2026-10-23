# Building and using the toolchain

The entry points are Python scripts under `llvm/scripts/`; no Python package
installation is needed to compile or execute programs from a source checkout.

## Dependencies and source

Use CMake 3.20+, Ninja, a C++17 compiler, and Python 3.10 or later. A separate
Clang must support `-target msp430-unknown-none`; Clang 21 is the tested frontend.
Execution and debugging require cocotb and Verilator. The Python tests also
require pytest; these dependencies are available through the parent project
environment or the emulator package.

Initialize the pinned upstream source from the repository root:

```sh
git submodule update --init llvm/llvm-project
```

The upstream revision is pinned because LLVM's C++ target APIs are not a stable
plugin ABI. Updating the submodule requires rebuilding LLVM and the module,
then rerunning the compiler and RTL checks.

## Building

```sh
python3 llvm/scripts/build.py llvm
python3 llvm/scripts/build.py backend
```

The first command builds `llvm-config`, `llvm-tblgen`, `llvm-link`, `opt`, and
`llc` in `llvm/build/llvm`. The second configures and builds the module in
`llvm/build/potados-backend`. `build.py all` performs both steps. The default
configuration uses Release mode with assertions and two build jobs. Only the
MSP430 built-in target is built by default; the custom POTADOS target is loaded
separately.

Environment settings:

| Setting | Purpose |
| --- | --- |
| `JOBS` | Parallel compiler jobs; default 2. |
| `BUILD_TYPE` | CMake build type; default Release. |
| `LLVM_TARGETS` | Built-in LLVM targets; default MSP430. |
| `LLVM_BUILD` | LLVM build directory. |
| `POTADOS_BUILD` | Backend build directory, used by the build script. |
| `POTADOS_MODULE` | Module path, used by the compile script. |
| `CLANG`, `OPT`, `LLC`, `LLVM_LINK` | Explicit compiler/tool executables. |
| `POTADOS_EXTRA_FLAGS` | Extra `llc` options. |

Changing `POTADOS_BUILD` also requires setting `POTADOS_MODULE` when compiling.
A supported external LLVM installation/build can be reused by setting
`LLVM_BUILD`, provided its revision and configuration match the module.

## Compilation

```sh
python3 llvm/scripts/compile.py source.c -o program.asm -O2 --verbose
python3 llvm/scripts/compile.py source.ll -o program.asm -Os
```

The driver preserves `program.frontend.ll` for C/textual IR inputs, `program.frontend.bc` for bitcode
inputs, and `program.optimized.ll` for all inputs. It links the arithmetic runtime,
optimizes the resulting module, runs the target with machine verification,
appends native MMIO wrappers, and validates the complete text with the project's
assembler before writing the assembly output.

`-O0`, `-O1`, `-O2`, `-O3`, `-Os`, and `-Oz` select optimization levels.
LLVM 23 implements Os/Oz through its O2 pipeline with `optsize`/`minsize`
function attributes; the driver applies these to both C and IR inputs.
`--no-runtime` omits runtime code; using an operation that needs an omitted
helper is an assembly error instead of an unresolved program image.

Outputs are selected from the suffix (`.hex`, `.bin`, or assembly) or
`--format asm|hex|annotated-hex|binary`. Hex images contain 16-bit ROM words.
Binary images use the existing assembler's big-endian byte serialization;
this file serialization is independent of the little-endian C RAM layout.

## Execution and debugging

```sh
python3 llvm/scripts/run.py run program.asm --max-cycles 1000000
python3 llvm/scripts/run.py debug program.asm
python3 llvm/scripts/run.py run program.asm --trace trace.jsonl --dump-state state.json
```

The runner compiles a wrapper of `rtl/potados.sv` with Verilator and drives it
through cocotb. The compiled simulator is cached until the RTL changes. There
is no Python instruction-execution model. Assembly inputs retain labels for
debugging; hex/binary inputs contain no source labels. Execution budgets and
`step` count RTL clock cycles. Timeouts and tool failures return a nonzero
status. See the emulator guide for pipeline-aware breakpoints, waveform
recording, debugger commands, and real RAM/register dumps.

A board ROM is produced with:

```sh
python3 llvm/scripts/compile.py source.c -o rom.hex -O2
```

Only replace the board's ROM deliberately: the build recipe at the project
root assembles `demo.asm` into `rom.hex`, so it will regenerate that image if
used unchanged.

## Imported LLVM IR

Textual IR (`.ll`) and bitcode (`.bc`) must use the target's frontend data
layout:

```text
e-m:e-p:16:16-i32:16-i64:16-f32:16-f64:16-a:8-n8:16-S16
```

Explicit incompatible layouts, including host IR with 64-bit pointers, are
rejected before optimization. Handwritten IR may omit the layout; the driver
supplies the layout through LLVM's `-data-layout` option before running passes.
This does not convert arbitrary host-generated IR to the POTADOS ABI. Generate
C IR with `clang -target msp430-unknown-none` or use the compilation driver.

The driver checks that `llc` and `opt` are LLVM 23 before loading the target,
and rejects a Clang frontend newer than the backend. This major-version check
is an early diagnostic, not a substitute for building the module and LLVM
tools from the same pinned revision.
