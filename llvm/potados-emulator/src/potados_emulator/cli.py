"""Batch execution and a terminal debugger for the cocotb/Verilator wrapper."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shlex
import sys
from typing import TextIO

from potados_asm import AssemblerError
from .core import CPU, EmulatorError, REGISTER_NAMES, decode, load_program


def _number(text: str) -> int:
    return int(text, 0)


def _address(cpu: CPU, text: str) -> int:
    value = cpu.symbols[text] if text in cpu.symbols else _number(text)
    if not 0 <= value <= 0xFFFF:
        raise ValueError("address must be in 0..65535")
    return value


def _registers(cpu: CPU) -> str:
    return " ".join(f"{name}={value:04X}" for name, value in zip(REGISTER_NAMES, cpu.registers))


def _halt(cpu: CPU) -> str:
    return f"HALT [{cpu.halt_message_name}]"


def _location(cpu: CPU) -> str:
    labels = [name for name, address in cpu.symbols.items() if address == cpu.pc]
    suffix = f" ({', '.join(labels)})" if labels else ""
    try:
        instruction = str(decode(cpu.rom, cpu.pc))
    except EmulatorError as exc:
        instruction = str(exc)
    return f"fetch PC={cpu.pc:04X}{suffix}: {instruction}"


def _dump(path: str | Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def debug(
    cpu: CPU,
    *,
    max_cycles: int = 1_000_000,
    max_steps: int | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Pause and clock the real RTL; step counts are clock cycles."""
    if max_steps is not None:
        max_cycles = max_steps
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    breakpoints: set[int] = set()
    print("POTADOS RTL debugger (cocotb/Verilator). 'help' lists commands.", file=stdout)
    print("Step advances clock cycles; fetch breakpoints do not drain the pipeline.", file=stdout)
    print(_location(cpu), file=stdout)
    while True:
        print("potados> ", end="", file=stdout, flush=True)
        raw = stdin.readline()
        if not raw:
            return
        try:
            args = shlex.split(raw)
            if not args:
                continue
            command, operands = args[0].lower(), args[1:]
            if command in {"q", "quit", "exit"}:
                return
            if command in {"h", "help", "?"}:
                print(
                    "step [N] | cycle [N]    clock N RTL cycles\n"
                    "continue | break ADDRESS/SYMBOL | delete [ADDRESS/SYMBOL]\n"
                    "registers | set REGISTER VALUE | memory EVEN_BYTE_ADDRESS [WORDS]\n"
                    "write ADDRESS VALUE | disassemble [ADDRESS [COUNT]] | io\n"
                    "dump PATH | quit\n"
                    "Numbers use decimal or 0xHEX. Addresses are physical words.\n"
                    "Breakpoints pause before fetch acceptance; older pipeline entries remain.",
                    file=stdout,
                )
            elif command in {"s", "step", "si", "cycle", "tick"}:
                if len(operands) > 1:
                    raise ValueError("step expects at most one clock-cycle count")
                count = _number(operands[0]) if operands else 1
                if not 1 <= count <= max_cycles:
                    raise ValueError(f"cycle count must be in 1..{max_cycles}")
                if not cpu.halted:
                    if count == 1:
                        event = cpu.step()
                        print(
                            f"cycle {event.cycle}: fetch={event.pc:04X} "
                            f"accepted={int(event.accepted)} execute_valid={int(event.execute_valid)} "
                            f"execute_pc={event.execute_pc:04X}",
                            file=stdout,
                        )
                    else:
                        before = cpu.cycles
                        cpu.tick(count)
                        print(f"Advanced {cpu.cycles - before} clock cycles.", file=stdout)
                print(_halt(cpu) if cpu.halted else _location(cpu), file=stdout)
            elif command in {"c", "continue", "run"}:
                if operands:
                    raise ValueError("continue takes no operands")
                cpu.run(
                    max_cycles=max_cycles, breakpoints=breakpoints,
                    ignore_current_breakpoint=True,
                )
                print(_halt(cpu) if cpu.halted else f"Breakpoint: {_location(cpu)}", file=stdout)
            elif command in {"b", "break"}:
                if operands:
                    if len(operands) != 1:
                        raise ValueError("break expects one address or symbol")
                    breakpoints.add(_address(cpu, operands[0]))
                print("Breakpoints: " + ", ".join(f"0x{a:04X}" for a in sorted(breakpoints)), file=stdout)
            elif command in {"d", "delete"}:
                if len(operands) > 1:
                    raise ValueError("delete expects at most one address or symbol")
                if operands:
                    breakpoints.discard(_address(cpu, operands[0]))
                else:
                    breakpoints.clear()
            elif command in {"r", "regs", "registers"}:
                print(_registers(cpu), file=stdout)
                print(f"fetch PC={cpu.pc:04X} cycles={cpu.cycles} halted={cpu.halted} "
                      f"halt_message={cpu.halt_message_name}", file=stdout)
            elif command == "set":
                if len(operands) != 2:
                    raise ValueError("set expects REGISTER VALUE")
                cpu.set_register(operands[0], _number(operands[1]))
            elif command in {"m", "mem", "memory"}:
                if len(operands) not in {1, 2}:
                    raise ValueError("memory expects ADDRESS [COUNT]")
                address = _address(cpu, operands[0])
                count = _number(operands[1]) if len(operands) == 2 else 16
                if not 1 <= count <= 32768:
                    raise ValueError("count must be in 1..32768 native words")
                for index in range(count):
                    current = (address + index) & 0xFFFF
                    print(f"{current:04X}: {cpu.read(current):04X}", file=stdout)
            elif command == "write":
                if len(operands) != 2:
                    raise ValueError("write expects ADDRESS VALUE")
                cpu.write(_address(cpu, operands[0]), _number(operands[1]))
            elif command in {"u", "dis", "disassemble"}:
                if len(operands) > 2:
                    raise ValueError("disassemble expects [ADDRESS [COUNT]]")
                address = _address(cpu, operands[0]) if operands else cpu.pc
                count = _number(operands[1]) if len(operands) > 1 else 8
                if not 1 <= count <= 65536:
                    raise ValueError("count must be in 1..65536")
                for _ in range(count):
                    instruction = decode(cpu.rom, address)
                    words = " ".join(f"{word:04X}" for word in instruction.words)
                    print(f"{address:04X}: {words:9} {instruction}", file=stdout)
                    address = (address + instruction.size) & 0xFFFF
            elif command == "io":
                print(json.dumps(cpu.state()["io"], indent=2), file=stdout)
            elif command == "dump":
                if len(operands) != 1:
                    raise ValueError("dump expects PATH")
                _dump(operands[0], cpu.state(include_ram=True))
            else:
                raise ValueError(f"unknown command {command!r}; use help")
        except (EmulatorError, ValueError, OSError) as exc:
            print(f"error: {exc}", file=stdout)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or debug POTADOS programs using cocotb and Verilator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "debug"):
        sub = subparsers.add_parser(command)
        sub.add_argument("program", type=Path, help=".asm/.s, readmemh .hex, or big-endian .bin")
        sub.add_argument("--entry", help="initial fetch symbol or physical word address (default: 0)")
        sub.add_argument("--initial-sp", type=_number, default=0, help="initial physical word SP; startup code may overwrite it")
        sub.add_argument("--ram-low", type=_number, default=0)
        sub.add_argument("--ram-high", type=_number, default=0x7FFF)
        sub.add_argument("--max-cycles", "--max-steps", dest="max_cycles", type=int, default=1_000_000,
                         help="maximum RTL clock cycles; --max-steps is a compatibility alias")
        sub.add_argument("--input", action="append", default=[], metavar="ADDRESS=VALUE", help="initialize an MMIO input value")
        sub.add_argument("--waves", nargs="?", const=True, default=False, type=Path, metavar="PATH",
                         help="record RTL waveforms; optionally copy the waveform to PATH")
        sub.add_argument("--dump-state", type=Path, help="dump real RTL registers, fetch PC, cycle count, and MMIO as JSON")
        sub.add_argument("--dump-ram", type=Path, help="dump nonzero RTL RAM words keyed by native word address")
        if command == "run":
            sub.add_argument("--trace", metavar="PATH", help="real clock-cycle trace as JSONL; '-' writes to stdout")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    cpu: CPU | None = None
    exit_code = 0
    try:
        if args.max_cycles < 1:
            raise ValueError("max-cycles must be positive")
        program = load_program(args.program)
        symbols = program.symbols if hasattr(program, "symbols") else {}
        pc = symbols[args.entry] if args.entry in symbols else _number(args.entry) if args.entry else 0
        if not 0 <= pc <= 0xFFFF:
            raise ValueError("entry address must be in 0..65535")
        inputs: dict[int, int] = {}
        for assignment in args.input:
            address_text, separator, value_text = assignment.partition("=")
            if not separator:
                raise ValueError("input must have form ADDRESS=VALUE")
            address = symbols[address_text] if address_text in symbols else _number(address_text)
            if not 0 <= address <= 0xFFFF:
                raise ValueError("MMIO input address must be in 0..65535")
            if args.ram_low <= address <= args.ram_high:
                raise ValueError("input address must be outside the RAM window")
            inputs[address] = _number(value_text) & 0xFFFF
        cpu = CPU(program, pc=pc, initial_sp=args.initial_sp, ram_low=args.ram_low,
                  ram_high=args.ram_high, io=inputs, waves=args.waves)
        if args.command == "debug":
            debug(cpu, max_cycles=args.max_cycles)
        else:
            with ExitStack() as stack:
                stream = None
                if args.trace:
                    stream = sys.stdout if args.trace == "-" else stack.enter_context(open(args.trace, "w", encoding="utf-8"))
                trace = (lambda event: print(json.dumps(event.to_dict()), file=stream)) if stream else None
                cpu.run(max_cycles=args.max_cycles, trace=trace)
            print(f"{_halt(cpu)} after {cpu.cycles} clock cycles; {_registers(cpu)}",
                  file=sys.stderr if args.trace == "-" else sys.stdout)
    except (AssemblerError, EmulatorError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if cpu is not None:
            try:
                if args.dump_state:
                    _dump(args.dump_state, cpu.state())
                if args.dump_ram:
                    _dump(args.dump_ram, cpu.state(include_ram=True)["ram"])
            except OSError as exc:
                print(f"error: {exc}", file=sys.stderr)
                exit_code = 1
            finally:
                cpu.close()
                if cpu.waveform is not None:
                    print(f"RTL waveforms: {cpu.waveform}", file=sys.stderr)
    return exit_code


def main() -> None:
    raise SystemExit(run())
