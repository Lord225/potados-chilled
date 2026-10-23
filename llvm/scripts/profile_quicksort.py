#!/usr/bin/env python3
"""Measure 16-element quicksort ROM and stack use on actual POTADOS RTL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "asm/src"))
sys.path.insert(0, str(ROOT / "potados-emulator/src"))
from potados_asm import assemble_file  # noqa: E402
from potados_emulator import CPU, TraceCycle  # noqa: E402
from compile import compile_source  # noqa: E402

INITIAL_SP = 0x7F00
LEVELS = ("O0", "O1", "O2", "O3", "Os", "Oz")


def measure(program, inputs: list[int] | None = None) -> dict:
    """Capture SP after every real clock; exclude reset before startup sets SP."""
    lowest_sp = INITIAL_SP
    initialized = False

    def trace(event: TraceCycle) -> None:
        nonlocal initialized, lowest_sp
        if not initialized:
            initialized = any(reg == 1 and value == INITIAL_SP
                              for reg, value in event.register_writes)
        if initialized:
            sp = event.registers[1]
            if not 0 < sp <= INITIAL_SP:
                raise RuntimeError(f"unexpected stack pointer 0x{sp:04X}")
            lowest_sp = min(lowest_sp, sp)

    with CPU(program) as cpu:
        address = program.symbols["values"]
        if inputs is not None:
            # Let generated startup initialize real RAM, then replace only the
            # input fixture before main is fetched. No C instrumentation changes
            # the recursive frames being measured.
            cpu.run(max_cycles=10_000, trace=trace,
                    breakpoints={program.symbols["main"]})
            if cpu.halted or cpu.pc != program.symbols["main"]:
                raise RuntimeError("did not reach main breakpoint")
            if sorted(cpu.ram[address:address + 16]) != list(range(16)):
                raise RuntimeError("startup did not initialize the input array")
            for index, value in enumerate(inputs):
                cpu.write(address + index, value)
        cpu.run(max_cycles=1_000_000, trace=trace,
                ignore_current_breakpoint=True)
        actual = list(cpu.ram[address:address + 16])
        if actual != list(range(16)) or cpu.registers[2] != 0:
            raise RuntimeError(f"sort failed: R2={cpu.registers[2]}, values={actual}")
        if not initialized or cpu.registers[1] != INITIAL_SP:
            raise RuntimeError("startup SP was not observed or final SP was not restored")
        return {"stack_words": INITIAL_SP - lowest_sp,
                "minimum_sp": lowest_sp, "final_sp": cpu.registers[1],
                "cycles": cpu.cycles, "sorted_values": actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "examples/build/quicksort-profile")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    print("| Optimization | ROM words | Stack: shuffled | Stack: sorted | Stack: reverse |", flush=True)
    print("| --- | ---: | ---: | ---: | ---: |", flush=True)
    for level in LEVELS:
        assembly = args.output_dir / level / "quicksort.asm"
        compile_source(ROOT / "examples/src/quicksort.c", assembly,
                       optimization=level, runtime=False)
        program = assemble_file(assembly)
        rom_words = max(program.words) + 1
        if len(program.words) != rom_words:
            raise RuntimeError("unexpected gap in flat ROM image")
        cases = {"shuffled": measure(program),
                 "sorted": measure(program, list(range(16))),
                 "reverse": measure(program, list(reversed(range(16))))}
        row = {"optimization": level, "rom_words": rom_words,
               "rom_bits": rom_words * 16, "initial_sp": INITIAL_SP,
               "global_array_words": 16, "cases": cases}
        rows.append(row)
        print(f"| -{level} | {rom_words} | {cases['shuffled']['stack_words']} | "
              f"{cases['sorted']['stack_words']} | {cases['reverse']['stack_words']} |", flush=True)
    report = args.output_dir / "results.json"
    report.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
