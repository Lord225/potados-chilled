# potados-chilled

Simple FPGA starter project for the Tang Nano 20K, using OSS CAD Suite and cocotb.

The importable POTADOS assembler and its CLI live in [`asm/`](asm/README.md).
The [LLVM backend, C runtime, examples, and debugger](llvm/README.md) live in
[`llvm/`](llvm/). They share this project's assembler and CPU RTL.

```sh
uv run --project asm potados-asm program.asm -o rom.hex
uv run --project asm potados-asm program.asm --format annotated-hex
```

`btn1` increments the six-bit counter; `btn2` resets it. The counter value is shown on `led[5:0]`.

```sh
just test   # Run cocotb tests with Verilator
just        # Synthesize, place-and-route, and package top.fs
just flash  # Build and flash a connected Tang Nano 20K
```

Compile and run freestanding C:

```sh
git submodule update --init llvm/llvm-project
python3 llvm/scripts/build.py all
uv run --project llvm python llvm/scripts/compile.py llvm/examples/src/sample.c -o build/sample.asm -O2
uv run --project llvm python llvm/scripts/run.py run build/sample.asm
uv run --project llvm python llvm/scripts/run.py debug build/sample.asm
```

The sample returns 42 in R2. The native C frontend uses 16-bit addressable words,
16-bit integers and pointers, and `sizeof(int) == 1`. Pointer increments advance
one word: `io[1]` from address `0x8000` accesses `0x8001`. The backend expands
full 16-bit multiplication using the native unsigned 8×8→16 multiplier. See the [ISA](potados_spec.md) and
[compiler ABI](llvm/docs/abi.md) for the memory and calling conventions.
Execution and debugging use cocotb and Verilator running the CPU in `rtl/potados.sv`.
The simulator wrapper exposes the real pipeline and memory state; stepping
advances clock cycles.
