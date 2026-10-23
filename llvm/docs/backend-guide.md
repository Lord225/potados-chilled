# Backend implementation and debugging

The directory structure follows the KAMP reference project, while the target
implementation uses POTADOS registers, instructions, byte memory lowering,
and calling convention. The module is registered under `potados_chilled`.
LLVM's closed architecture enum has no out-of-tree POTADOS member, so command
lines select it explicitly with `-march=potados_chilled`.

## Stages

1. `compile.py` invokes a freestanding MSP430 Clang frontend to establish the
   supported 16-bit pointer/data layout. LLVM optimizations are disabled at
   this stage so that the subsequent optimizer pipeline is explicit.
2. The LLVM IR linker combines the input with the freestanding runtime.
3. `opt` runs the selected default optimization pipeline.
4. `llc` loads `Potados.so`, performs SelectionDAG lowering and target
   instruction selection, allocates registers, constructs frames, and emits
   flat POTADOS text.
5. The existing Python assembler validates and encodes the text. The emulator
   loads those words into the actual RTL ROM and runs `potados.sv` using
   cocotb/Verilator.

## Target sources

- `PotadosRegisterInfo.td`: architectural registers and allocatable classes.
- `PotadosInstrInfo.td`: machine instruction patterns and expansion pseudos.
- `PotadosISelLowering.cpp`: argument/result ABI, calls, comparisons, globals,
  and legalization of wide operations.
- `PotadosISelDAGToDAG.cpp`: memory selection, stack addresses, and shifts.
- `PotadosFrameLowering.cpp` / `PotadosRegisterInfo.cpp`: frame creation and
  elimination of abstract frame indices.
- `PotadosInstrInfo.cpp`: physical copies and spill/reload insertion.
- `PotadosAsmPrinter.cpp`: flat assembly expansion, labels, globals, startup,
  and instruction-specific sequences.
- `PotadosMC.cpp`: minimum MC descriptions needed by LLVM's assembly pipeline.

The machine-instruction forms are compiler implementation details. The Python
assembler remains the authoritative binary encoder and the ISA specification
records the hardware-visible layout.

## Investigating failures

Keep the compiler input, `*.frontend.ll`, `*.optimized.ll`, and `*.asm` together.
Use `--verbose` to inspect the exact tool commands. Reproduce instruction
selection directly with:

```sh
LLVM_BUILD=/path/to/llvm-build
"$LLVM_BUILD/bin/llc" -load=llvm/build/potados-backend/Potados.so \
  -march=potados_chilled -mcpu=generic -filetype=asm -verify-machineinstrs \
  program.optimized.ll -o program.asm
```

Machine-verifier failures indicate broken operand constraints, register uses,
or frame handling even when the generated text looks plausible. Preserve
`-verify-machineinstrs` while modifying the target. For register-pressure
issues, compare `--llc-flag=-regalloc=basic` with the default allocator and
inspect the spill instructions.

Once assembly succeeds, use the RTL debugger, clock-cycle JSONL trace, and
Verilator waveforms to locate the first divergence. Trace records expose real
fetch/accept, execute, writeback, and memory signals. Check byte-lane selection,
signed comparison direction, shift amount sign, caller-saved registers, and
pipeline dependencies. A debugger breakpoint pauses fetch acceptance; earlier
instructions can still be in flight, so inspect the cycle trace before treating
a register snapshot as a completed-instruction state.

Changes to the ISA must update the RTL, assembler, display-only disassembler,
native runtime assembly, compiler expansion, and their golden encodings
together. Execution remains defined by the RTL rather than a second Python
implementation of the ISA. In particular, native MUL is an unsigned byte multiply;
replacing compiler 16-bit multiplication with a single MUL silently truncates
its operands.
