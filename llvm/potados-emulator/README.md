# POTADOS Chilled RTL simulator and debugger

The `potados-emulator` command executes this project's **actual
`rtl/potados.sv`** using cocotb and Verilator. A small SystemVerilog wrapper
exposes loading, clock control, register/RAM inspection, and MMIO. Python
controls simulation; it does not implement instruction execution.

Verilator and a C++ compiler must be installed. The Python package supplies
cocotb and the local assembler. The first run builds the Verilated wrapper;
later runs reuse the cached build until the RTL sources or configuration change.
Missing tools or a failed build produce an error; there is no software fallback.

`POTADOS_RTL_ROOT=/path/to/project/rtl` selects the source directory containing
`potados.sv` and its components. Source checkouts discover this automatically.
Installed wheels carry the simulation wrapper but intentionally use the actual
project RTL rather than a frozen duplicate; set this variable when the checkout
cannot be discovered. `POTADOS_SIM_BUILD=/path/to/cache` selects the compiled
simulator cache. The cache separates different RTL/configuration fingerprints.

From this directory:

```sh
uv run potados-emulator run ../examples/build/sample.asm
uv run potados-emulator debug ../examples/build/sample.asm
uv run potados-emulator run ../../demo.asm --max-cycles 100000
```

Without `uv`, install the two local packages and invoke the module:

```sh
python -m pip install -e ../../asm -e .
python -m potados_emulator run program.asm
```

The repository launcher adds the source paths automatically:

```sh
.venv/bin/python llvm/scripts/run.py run program.asm
.venv/bin/python llvm/scripts/run.py debug program.asm
```

## Execution and memory

Assembly (`.asm`, `.s`, `.pasm`), readmemh hexadecimal images, and big-endian
word-pair binary images are loaded into the RTL program ROM. Assembly inputs
retain labels for breakpoints and disassembly. The display disassembler decodes
words for inspection only; the RTL decoder and ALU determine execution.

The default RTL ROM holds 32,768 words. Program addresses must fit that hardware
configuration. The harness preloads otherwise unused ROM with HALT and clears
real RAM before reset so repeated simulations start deterministically. The CPU's
own reset then initializes its architectural registers and pipeline. Generated
standalone programs initialize SP and global RAM before calling `main`.

RAM and MMIO use **native 16-bit word addresses**. Neighboring cells are
`0, 1, 2, ...`; LD/ST/LDSP/STSP immediate displacements count cells, and
PUSH/POP adjust SP by one. The default RAM window is `0x0000..0x7fff`;
addresses from `0x8000` go to the real RTL MMIO interface. Native C pointers
use these addresses directly: `volatile int *io = (volatile int *)0x8000`
accesses `io[0]` at `0x8000` and `io[1]` at `0x8001`. C `CHAR_BIT` is 16.

`--ram-low` and `--ram-high` select a matching wrapper configuration. The
simulated peripheral register map responds to the CPU's synchronous MMIO
requests; writes are recorded in order. `--input 0x8006=1` initializes a
peripheral input value. The map is a test fixture, not a model of the board's
PWM circuit or buttons.

`--entry SYMBOL` or a numeric word address selects the initial RTL fetch PC.
`--initial-sp` sets the initial physical SP; startup instructions can overwrite
it. These options modify simulator state before clocking and do not emulate
instructions. Undefined opcodes and optional extensions follow the current RTL;
there are no additional software ISA traps.

## HALT messages

`HALT` can carry a three-bit message, for example `HALT PASS` or `HALT ERROR`.
The [ISA HALT table](../../potados_spec.md) defines the codes. `HALT` without
an operand and `HALT NO_MESSAGE` both use zero. The simulator reads the message
latched by the real CPU output; it does not infer a result from the source text.

`cpu.halt_message` exposes the numeric code, `cpu.halt_message_name` its display
name, and state dumps include both fields. CLI and debugger summaries display
reasons such as `HALT [PASS]`. All message codes still halt the CPU. They do not
change the host exit status: even `HALT ERROR` returns a successful simulator
status when the hardware halted normally. Execution/build failures and cycle
budget timeouts remain host errors.

## Clock budgets, traces, and waveforms

```sh
potados-emulator run program.asm --max-cycles 1000000 \
  --trace trace.jsonl --dump-state state.json --dump-ram ram.json
potados-emulator run program.asm --waves run.vcd
```

Execution budgets count **RTL clock cycles**. `--max-steps` is retained as an
alias for the cycle budget. Reaching HALT returns zero; exhausting the budget
or failing to build/run the simulator returns nonzero. A compiled C return
value remains in R2 and is not the host process exit code.

JSONL trace records contain real cycle counts, PC and register state, fetch
valid/accept signals and words, execute activity, committed register writes,
and RAM/MMIO requests observed from the DUT. `--trace -` writes JSONL to stdout
and the final summary to stderr. The simulator performs long runs internally,
without a host request for every clock cycle. Waveforms are generated by
Verilator from the SystemVerilog hierarchy and copied to the selected path when
the simulator closes.

State/RAM dumps are also written on a cycle-budget timeout. RAM dumps contain
sparse native word addresses, including values produced by the actual memory
module. The simulated memories are separate Harvard ROM and RAM instances.

## Debugger

```text
break main                  pause before fetch acceptance at main
continue                    run until a breakpoint, HALT, or the cycle limit
cycle 5                     advance five RTL clock cycles
step 5                      alias of cycle 5
registers                   inspect actual architectural registers and fetch PC
set R2 0x1234               change a real register while the clock is paused
set SP 0x100                set the native word stack pointer
memory 0x100 8              read eight RAM/MMIO words at 0x100, 0x101, ...
write 0x100 42              change a RAM/MMIO word while paused
disassemble main 12         display instruction words without executing them
io                          inspect the peripheral register map
delete main                 remove a breakpoint
dump paused-state.json      dump real registers, RAM, and MMIO
quit                        terminate the simulator process
```

A breakpoint stops the edge that would accept the selected fetched instruction.
**Older instructions may still be in the pipeline.** Registers can therefore
reflect an earlier committed instruction rather than the source line displayed
at the fetch PC. The debugger neither drains nor replaces the pipeline to
create a software instruction boundary. Inspect the cycle trace or waveform
when debugging forwarding, stalls, branches, and delayed writes.

Register and memory writes modify actual paused simulator state. In-flight
instructions can subsequently overwrite a debug mutation, just as hardware
writes can. ZERO remains read-only. Continue can execute through a breakpoint
at the current fetch boundary, avoiding a repeated stop at the same edge.

## Python API

```python
from potados_asm import assemble
from potados_emulator import CPU

program = assemble("LLI R2, 42\nHALT")
with CPU(program) as cpu:
    cpu.run(max_cycles=1000)
    assert cpu.registers[2] == 42
    print(cpu.cycles)
    print(cpu.state(include_ram=True))
```

A CPU owns one persistent cocotb/Verilator process. Use a context manager or
`close()` to release it. `step()` advances one clock and returns a `TraceCycle`;
`run(trace=callback)` supplies real cycle events. `cycles` is the clock count;
`steps` remains a compatibility alias for that same count. Use `set_register`,
`write`, and `set_io` to change simulator state rather than mutating a returned
snapshot. `registers`, `ram`, and `io` expose snapshots of the actual DUT state.

The `ram` snapshot is indexed by native word address: `cpu.ram[0x20]`
reads the 16-bit cell at address `0x20`, and the next cell is `cpu.ram[0x21]`.
State/RAM dumps use those same addresses. Program ROM and the fetch PC use
instruction word addresses in the separate code space.
