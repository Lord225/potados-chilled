# Building and using the toolchain

The entry points are Python scripts under `llvm/scripts/`. Install their
dependencies in the toolchain environment before compiling or running programs.

## Dependencies and source

Use CMake 3.20+, Ninja, a C++17 compiler, and Python 3.10 or later. Clang performs preprocessing only. The native C frontend requires
`pycparser` and `llvmlite`; it computes the 16-bit-byte C layout itself.
Execution and debugging require cocotb and Verilator. The Python tests also
require pytest; these dependencies are available through the parent project
environment or the emulator package.

Install Python dependencies and initialize the pinned upstream source from the
repository root:

```sh
uv sync --project llvm
git submodule update --init llvm/llvm-project
```

The upstream revision is pinned because LLVM's C++ target APIs are not a stable
plugin ABI. Updating the submodule requires rebuilding LLVM and the module,
then rerunning the compiler and RTL checks.

## Building

```sh
uv run --project llvm python llvm/scripts/build.py llvm
uv run --project llvm python llvm/scripts/build.py backend
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
| `POTADOS_RTL_ROOT` | Directory containing the actual `potados.sv` sources; discovered in source checkouts. |
| `POTADOS_SIM_BUILD` | Cache directory for compiled cocotb/Verilator wrappers. |

Changing `POTADOS_BUILD` also requires setting `POTADOS_MODULE` when compiling.
A supported external LLVM installation/build can be reused by setting
`LLVM_BUILD`, provided its revision and configuration match the module.

## Compilation

```sh
uv run --project llvm python llvm/scripts/compile.py source.c -o program.asm -O2 --verbose
uv run --project llvm python llvm/scripts/compile.py source.ll -o program.asm -Os
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
Binary images serialize each ROM word as two big-endian eight-bit octets.
This file format is independent of C's 16-bit-byte address units and the
low-word-first order of multiword C objects in RAM.

## Execution and debugging

```sh
uv run --project llvm python llvm/scripts/run.py run program.asm --max-cycles 1000000
uv run --project llvm python llvm/scripts/run.py debug program.asm
uv run --project llvm python llvm/scripts/run.py run program.asm --trace trace.jsonl --dump-state state.json
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
uv run --project llvm python llvm/scripts/compile.py source.c -o rom.hex -O2
```

Only replace the board's ROM deliberately: the build recipe at the project
root assembles `demo.asm` into `rom.hex`, so it will regenerate that image if
used unchanged.

## Imported LLVM IR

Textual IR (`.ll`) and bitcode (`.bc`) must implement the native POTADOS
word-addressed ABI and carry the `potados.word-addressed=1` module marker.
Ordinary host or MSP430 Clang output is rejected: even a 16-bit-pointer layout
still assumes eight-bit C bytes and cannot represent this ABI by changing the
LLVM data layout alone. Use the native compilation driver to produce C IR.

The frontend represents C object addresses in native cell units and emits
explicit native memory operations. LLVM's own storage units remain an internal
compiler detail. Inspect the preserved `*.frontend.ll` when working on lowering.
LLVM-generated private scratch/frame offsets still count octets; the backend
converts those separately from native C word addresses. The driver rejects
dynamic LLVM `ptrtoint` and LLVM `memcpy`/`memmove`/`memset` intrinsics, whose
alignment and count rules describe octets. Use the native address operations
and C memory helpers instead. Static native pointer initializers are supported.
The target module and LLVM tools must be built from the same pinned revision;
major-version compatibility alone does not establish plugin ABI compatibility.
