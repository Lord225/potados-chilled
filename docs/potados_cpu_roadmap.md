# POTADOS CPU roadmap

This document describes the work needed to turn the current straight-through
pipeline into a CPU with defined architectural behaviour.  It also records the
current ISA/RTL differences so the specification can be made authoritative
before an assembler is written.

## Current baseline

The pipeline has these logical steps:

```text
program memory -> decoder/register read -> execute -> data memory -> writeback
```

The first end-to-end tests in `tb/test_potados.py` deliberately cover only
instructions separated by NOPs:

- `LLI R2, 7`, then `HALT`;
- `LLI R2, 7`, `LLI R3, 9`, `ADD R4, R2, R3`, then `HALT`.
- `(3 * 4) + (5 * 6)`, using `MUL` and `ADD` with hazard-avoiding NOPs.

They check that an integer ALU result reaches the architectural register file.
They do not test, or promise correct behaviour for, data hazards, control
hazards, RAM loads, stacks, FPU operations, or jumps.

## Work required for a usable core

### 1. Make the pipeline transaction rules explicit

Define one `valid`/bubble rule for every stage.  A stage with `valid == 0`
must have no architectural side effects.  The core already carries `valid` in
the stage packets; finish applying it to every write, RAM request, stack update,
jump, and halt action.

Decide when each unit produces a result:

- integer ALU and comparator: combinational in execute;
- RAM read: registered, therefore data appears after a clock edge;
- RAM write: committed at a clock edge;
- FPU: choose either a fixed latency or a ready/valid interface.

This timing contract determines how many pipeline registers are needed.  In
particular, a registered RAM read needs a response stage (or a memory stage
that waits) before `WB_MEMORY` can write a register.

### 2. Complete memory and stack execution

Add a memory-read result field to `writeback_stage_t` (or an equivalent
response stage).  `WB_MEMORY` must select that read result, not the store-data
field.  Keep a load request associated with its destination and writeback
metadata until the RAM response is available.

Then test:

- `ST` followed later by `LD`, including positive and negative displacement;
- `LDSP` and `STSP`;
- `PUSH`: store at the old SP and increment exactly once;
- `POP`: read from `SP - 1`, decrement exactly once, and write the loaded
  value to `DST`.

### 3. Add data-hazard handling

Decode currently reads the committed register file, while the previous three
instructions may still be in execute, memory, or writeback.  Pick one policy:

- **Stall only:** detect a source register that has an outstanding write and
  hold fetch/decode until its value commits.  This is the simplest initial
  implementation.
- **Forwarding plus stalls:** forward ALU, return-address, and later FPU values
  where available; stall for RAM/FPU values that are not ready.

The chosen mechanism must include SP dependencies.  A load-use test such as
`LLI R2, 1; ADDI R2, 1` should work without manually inserted NOPs once this
step is complete.

### 4. Define and implement control-hazard behaviour

`potados_execute_stage` produces `jump_enable` and `jump_address`, and the
top-level now sends them to program memory.  It does not yet flush or kill
younger pipeline entries, so wrong-path instructions can still execute.

For a taken jump, choose and document one of:

- flush all fetched/decoded younger instructions and restart fetch at the
  target; or
- stall fetch until the branch resolves.

The first choice gives better throughput and is conventional for this pipeline.
Both need an explicit kill/bubble signal for younger decode/execute entries.
Test taken and not-taken conditional jumps, `JMP`, `JAL`, `JMPR`, and `JALR`,
including the exact return-address value.

### 5. Implement or deliberately exclude the FPU

At present the top-level ties `fpu_output` to zero.  Either add an FPU stage
with a specified latency and ready/valid handshake, or mark all FPU opcodes as
reserved until a coprocessor exists.  Do not let FPU instructions silently
write zero as if they had completed.

### 6. Architectural completion and FPGA integration

Define reset and HALT behaviour precisely: whether HALT freezes fetch only or
all state, and whether it is sticky.  Add a top-level board wrapper that
instantiates `potados`, exposes an observable status interface, and provides a
repeatable ROM-image build flow.

## Testbench plan

All tests should remain normal Pytest tests that each launch one clearly named
Cocotb coroutine.  Tests should primarily inspect architectural outputs
(`registers_out`, memory, `halt_out`, and PC); internal signals are appropriate
for focused stage-wiring assertions only.

| Batch | Scope | Status |
| --- | --- | --- |
| 1 | Fetch, integer writeback, HALT; programs are hazard-free through NOP drain slots. | Implemented in `tb/test_potados.py`. |
| 2 | Integer ISA: arithmetic, SET, shifts, LLI/LUI, ADDI, ZERO-register protection. | Add after resolving shift direction and immediate definitions. |
| 3 | RAM and stack operations, including synchronous read latency. | Blocked on memory-response design. |
| 4 | RAW hazards, SP hazards, and back-to-back write/read sequences. | Initial stress regressions added; dense RAW chains are strict expected failures pending stall/forwarding design. |
| 5 | Direct/register jumps, conditional taken/not taken, flush behaviour, JAL/JALR return address. | Blocked on control-hazard design. |
| 6 | FPU latency/result/writeback behaviour. | Blocked on FPU contract and implementation. |
| 7 | Random instruction streams checked against a small Python reference model. | Requires batches 2-6. |

Each program test uses a small checked-in `.asm` source image. The test runner
assembles it in Python and preloads the resulting words directly into the
simulator's ROM memory before reset, so tests do not create a temporary
`rom.hex`. The assembler can still emit a ROM image for FPGA builds and manual
file-based simulations.

## ISA and implementation differences to resolve

| Area | ISA/specification | Current RTL | Required decision |
| --- | --- | --- | --- |
| Shift direction | Negative shift amounts shift left. | `ALU_SH`/`ALU_ASH` shift left for non-negative values and right for negative values. | Reverse the ALU behaviour or change the ISA wording and tests. |
| LD/ST immediate width | The reference table says 6-bit; the `IMM8` heading says it is used by LD/ST, while its diagram shows nine bit positions. | Decoder extracts `IMM6` from bits `[11:6]`. | Choose one width and one bit mapping; update spec, decoder, assembler, and tests together. |
| LLI/LUI immediate wording | The reference says an 8-bit signed immediate. | Decoder constructs a 9-bit immediate, then uses its lower eight bits; bit `[5]` selects LLI/LUI. | Specify the actual 8-bit bit ordering and state that the value is zero-filled into the selected byte. |
| FPU conversion opcode | ISA calls opcode `111` `FTOU`. | RTL enum and decoder call it `FPU_UTOF`. | Decide whether opcode `111` is float-to-unsigned or unsigned-to-float and rename consistently. |
| FPU execution | ISA lists seven FPU operations. | No FPU implementation exists; top-level supplies zero. | Implement the unit or reserve the opcode range. |
| Jumps | ISA defines conditional jumps and direct/register jump-and-link. | Execute target/taken signals reach fetch, but younger wrong-path instructions are not flushed. | Implement control-hazard/flush policy. |
| Memory loads | `LD`, `LDSP`, and `POP` write a RAM value to `DST`. | RAM reads are registered, but writeback currently has no captured RAM-read result; `WB_MEMORY` selects a store-data field. | Add a RAM response path before claiming load support. |
| HALT | ISA says execution halts. | `halt_out` is an execute-stage signal; fetch requests stop, but the signal is not latched/sticky. | Define whether HALT is sticky and freeze all architectural state accordingly. |

## Assembler project scope

Create a small standalone Python package only after the immediate and FPU
rows above are resolved.  Proposed layout:

```text
assembler/
  pyproject.toml
  src/potados_asm/
    __main__.py       # python -m potados_asm
    parser.py          # lines, labels, operands, diagnostics
    isa.py             # one authoritative opcode/field table
    encoder.py         # parsed instruction -> one or two 16-bit words
    listing.py          # optional address/word/source listing
  tests/
```

Initial command-line interface:

```text
python -m potados_asm program.pota -o rom.hex
python -m potados_asm program.pota -o rom.hex --listing program.lst
```

First-version language:

- labels (`loop:`) and symbolic jump targets;
- integer literals in decimal and `0x` hexadecimal;
- register names `ZERO`, `SP`, and `R2` through `R7`;
- comments and blank lines;
- the complete non-FPU ISA once its encodings are frozen;
- one 16-bit hexadecimal word per `rom.hex` line, with a second line for every
  long instruction.

The assembler should use two passes: first assign word addresses to labels;
then encode and range-check every operand.  It should reject undefined labels,
duplicate labels, invalid registers, unsupported opcodes, and immediates that
do not fit the selected signed field.  Macros, includes, linker relocations,
and binary object formats are explicitly out of scope for the first version.

Assembler tests should include golden encodings for every instruction form and
an integration test that assembles a short program, preloads its words into the
simulated ROM, and checks the same architectural result in Cocotb.
