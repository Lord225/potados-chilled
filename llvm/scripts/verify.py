#!/usr/bin/env python3
"""Compile, assemble, execute, and check the maintained C examples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "asm/src"))
sys.path.insert(0, str(ROOT / "potados-emulator/src"))
from potados_asm import assemble_file  # noqa: E402
from potados_emulator import CPU  # noqa: E402
from compile import compile_source  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", action="append", help="example name; may be repeated")
    parser.add_argument("--opt", action="append", choices=["O0", "O1", "O2", "O3", "Os", "Oz"], help="optimization level; may be repeated")
    parser.add_argument("--max-cycles", "--max-steps", dest="max_cycles", type=int, default=4_000_000,
                        help="RTL clock-cycle budget per program")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    expected = json.loads((ROOT / "examples/expected.json").read_text())
    programs = args.program or list(expected)
    unknown = set(programs) - set(expected)
    if unknown:
        parser.error("unknown examples: " + ", ".join(sorted(unknown)))
    failures = 0
    for level in args.opt or ["O0", "O1", "O2", "O3", "Os", "Oz"]:
        for name in programs:
            try:
                output = ROOT / "examples/build" / level / f"{name}.asm"
                compile_source(ROOT / "examples/src" / f"{name}.c", output,
                               optimization=level, verbose=args.verbose)
                with CPU(assemble_file(output)) as cpu:
                    cpu.run(max_cycles=args.max_cycles)
                    actual = cpu.registers[2]
                    want = expected[name]["r2"]
                    if actual != want:
                        raise RuntimeError(f"R2 = {actual} (0x{actual:04X}); expected {want} (0x{want:04X})")
                    if name == "mmio" and (cpu.io.get(0x8000) != 42 or cpu.io.get(0x8001) != 99):
                        raise RuntimeError("MMIO register contents did not match")
                    print(f"PASS {level} {name}: R2={actual}; {cpu.cycles} RTL clock cycles", flush=True)
            except Exception as error:
                failures += 1
                print(f"FAIL {level} {name}: {error}", file=sys.stderr, flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
