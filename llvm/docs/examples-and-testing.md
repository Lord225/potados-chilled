# Examples and verification

The maintained examples live in `llvm/examples/src`; expected low-word return
values are recorded in `llvm/examples/expected.json`.

| Program | Exercises | Expected R2 |
| --- | --- | --- |
| `sample` | Initialized volatile global and multiplication | 42 |
| `arithmetic` | Full-width product and shifts | 64443 (`0xFBBB`) |
| `recursion` | Recursive Fibonacci, factorial, calls and stack frames | 728 |
| `memory` | Byte array sorting and padded structure globals | 4701 |
| `shifts` | Variable logical/arithmetic shifts and sign extension | 57352 (`0xE008`) |
| `wide_integers` | 32/64-bit values and division/remainder | 8307 |
| `division` | Unsigned and signed 16-bit division/remainder | 65434 |
| `mmio` | Native word-addressed peripheral reads/writes | 42 |

Run a single case or the complete optimizer matrix:

```sh
python3 llvm/scripts/verify.py --program sample --opt O2
python3 llvm/scripts/verify.py
```

The default matrix compiles each example at O0, O1, O2, O3, and Os. Every output
is assembled, executed to HALT, and checked against its expected result. The
MMIO example also checks the captured peripheral register values. A timeout,
assembly failure, compiler failure, or result mismatch makes verification fail.
A failing optimized case leaves its IR and assembly available under
`llvm/examples/build/<optimization>/`.

The Python test suite exercises raw assembly and compiled programs on the same
cocotb/Verilator wrapper used by the CLI. Expected results are calculated
independently of the compiler and hardware; no custom CPU interpreter is used:

```sh
.venv/bin/python -m pytest -q llvm/tests
```

Compiler integration tests require built LLVM tools and `Potados.so`; their
skip messages identify unavailable prerequisites. The RTL harness additionally
requires Verilator and cocotb. Use the explicit LLVM environment when reusing
an external build:

```sh
LLVM_BUILD=/path/to/llvm-build .venv/bin/python -m pytest -q llvm/tests
```

Every executable emulator test runs the actual fetch/decode/execute/memory/
writeback pipeline, including forwarding, hazards, and synchronous memory
responses. Focused tests inspect real cycle traces, MMIO requests, stack state,
and physical RAM alongside independent expected results. Execution limits are
clock-cycle budgets. Parent-project assembler and hardware regressions remain
available through the normal root test suite.
