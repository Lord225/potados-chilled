# Examples and verification

The maintained examples live in `llvm/examples/src`; expected low-word return
values are recorded in `llvm/examples/expected.json`.

| Program | Exercises | Expected R2 |
| --- | --- | --- |
| `sample` | Initialized volatile global and multiplication | 42 |
| `arithmetic` | Full-width product and shifts | 64443 (`0xFBBB`) |
| `recursion` | Recursive Fibonacci, factorial, calls and stack frames | 728 |
| `memory` | Native character array sorting and structure globals | 4701 |
| `shifts` | Variable logical/arithmetic shifts and sign extension | 57352 (`0xE008`) |
| `wide_integers` | 32/64-bit values and division/remainder | 8307 |
| `division` | Unsigned and signed 16-bit division/remainder | 65434 |
| `mmio` | Native word-addressed peripheral reads/writes | 42 |
| `quicksort` | Recursive in-place sort and validation of 16 integers | 0 |

Run a single case or the complete optimizer matrix:

```sh
uv run --project llvm python llvm/scripts/verify.py --program sample --opt O2
uv run --project llvm python llvm/scripts/verify.py
```

The default matrix compiles each example at O0, O1, O2, O3, Os, and Oz (54 runs). Every output
is assembled, executed to HALT, and checked against its expected result. The
MMIO example also checks the captured peripheral register values. A timeout,
assembly failure, compiler failure, or result mismatch makes verification fail.
A failing optimized case leaves its IR and assembly available under
`llvm/examples/build/<optimization>/`.

The Python test suite exercises raw assembly and compiled programs on the same
cocotb/Verilator wrapper used by the CLI. Expected results are calculated
independently of the compiler and hardware; no custom CPU interpreter is used:

```sh
uv run --project llvm python -m pytest -q llvm/tests
```

Compiler integration tests require built LLVM tools and `Potados.so`; their
skip messages identify unavailable prerequisites. The RTL harness additionally
requires Verilator and cocotb. Use the explicit LLVM environment when reusing
an external build:

```sh
LLVM_BUILD=/path/to/llvm-build uv run --project llvm python -m pytest -q llvm/tests
```

Every executable emulator test runs the actual fetch/decode/execute/memory/
writeback pipeline, including forwarding, hazards, and synchronous memory
responses. Focused tests inspect real cycle traces, MMIO requests, stack state,
and physical RAM alongside independent expected results. Execution limits are
clock-cycle budgets. Parent-project assembler and hardware regressions remain
available through the normal root test suite.

The direct-pointer MMIO integration case compiles `volatile int *io =
(volatile int *)0x8000; io[0] = 42; io[1] = 99;` at O0, O1, O2, O3, and Os
and checks actual bus writes/readback at `0x8000` and `0x8001`. Static
assertions preserve 16-bit C bytes, one-cell `int`, and one-cell pointers.
Native layout checks also cover full-range characters, structure sizes, pointer
round trips, and pointer differences. Runtime checks verify all 64 result bits
and full-cell memcpy/memmove/memset semantics.

## Quicksort stack and ROM profile

The recursive [quicksort example](../examples/src/quicksort.c) sorts sixteen
integers using a last-element pivot. Run its RTL resource measurement with:

```sh
uv run --project llvm python llvm/scripts/profile_quicksort.py
```

This compiles all six optimization modes without unused runtime helpers and
checks the exact sorted contents of physical RAM. It reports the full flat ROM
image, including startup, array initialization, and the C result check. Stack
usage is the difference between initial SP (`0x7F00`) and the lowest committed
SP observed in the cycle trace; final SP must be restored. Input data occupies
16 global RAM words in addition to the stack.

The same compiled image runs with shuffled, sorted, and reverse-sorted inputs.
For the latter two, the RTL debugger replaces the initialized RAM fixture before
`main` is fetched. There is no profiling instrumentation in the C functions.
Results, minimum SP, cycle counts, and verified sorted arrays are saved under
`llvm/examples/build/quicksort-profile/results.json`. All size units are native
16-bit words. See the [recorded measurements](../examples/quicksort-profile.md).
