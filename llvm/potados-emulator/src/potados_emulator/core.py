"""Program images, disassembly, and a client for the actual POTADOS RTL.

Execution is exclusively delegated to cocotb and Verilator. The decoder below
formats instructions for the debugger; it never changes architectural state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import tempfile
from collections.abc import Callable, Mapping
from typing import Any

from potados_asm import AssemblyResult, assemble, assemble_file

MASK = 0xFFFF
REGISTER_NAMES = ("ZERO", "SP", "R2", "R3", "R4", "R5", "R6", "R7")


class EmulatorError(RuntimeError):
    """A malformed image or failed architectural execution."""


class FetchError(EmulatorError):
    """An instruction word was requested outside the loaded program."""


class IllegalInstructionError(EmulatorError):
    """The instruction has no defined operation in the current ISA."""


class UnsupportedInstructionError(EmulatorError):
    """The instruction requires an extension absent from this CPU."""


class ExecutionLimitError(EmulatorError):
    """The RTL instance exhausted its clock-cycle budget before HALT."""


def signed(value: int, width: int = 16) -> int:
    value &= (1 << width) - 1
    return value - (1 << width) if value & (1 << (width - 1)) else value


def _immediate(word: int, width: int, *, sign: bool = True) -> int:
    # Immediate weights ascend as instruction positions descend from bit 11.
    value = sum(((word >> (11 - bit)) & 1) << bit for bit in range(width))
    return signed(value, width) if sign else value


@dataclass(frozen=True)
class Instruction:
    address: int
    words: tuple[int, ...]
    mnemonic: str
    dst: int = 0
    src_a: int = 0
    src_b: int = 0
    immediate: int = 0
    function: int = 0

    @property
    def size(self) -> int:
        return len(self.words)

    def __str__(self) -> str:
        r = REGISTER_NAMES
        m = self.mnemonic
        if m in {"NOP", "HALT"}:
            return m
        if m in {"ADD", "SUB", "AND", "OR", "XOR", "MUL", "SGE", "SL", "SE", "SNE", "SAE", "SB", "FADD", "FSUB", "FMUL", "FDIV"}:
            return f"{m} {r[self.dst]}, {r[self.src_a]}, {r[self.src_b]}"
        if m in {"NOT", "ITOF", "FTOI", "FTOU", "JALR"}:
            return f"{m} {r[self.dst]}, {r[self.src_a]}"
        if m in {"SH", "ASH"}:
            return f"{m} {r[self.dst]}, {r[self.src_b]}, {self.immediate}"
        if m in {"ADDI", "LLI", "LUI", "LDSP", "STSP"}:
            return f"{m} {r[self.dst]}, {self.immediate}"
        if m in {"LD", "ST"}:
            return f"{m} {r[self.dst]}, [{r[self.src_b]} {self.immediate:+}]"
        if m in {"JGE", "JL", "JE", "JNE", "JAE", "JB"}:
            return f"{m} {r[self.src_a]}, {r[self.src_b]}, 0x{self.immediate:04X}"
        if m == "JMP":
            return f"JMP 0x{self.immediate:04X}"
        if m == "JAL":
            return f"JAL {r[self.dst]}, 0x{self.immediate:04X}"
        if m == "POP":
            return f"POP {r[self.dst]}"
        return f"{m} {r[self.src_a]}"


def decode(program: Mapping[int, int], address: int = 0) -> Instruction:
    address &= MASK
    if address not in program:
        raise FetchError(f"no program word at PC=0x{address:04X}")
    word = program[address]
    primary, dst, function = word >> 12, (word >> 9) & 7, (word >> 6) & 7
    a, b = word & 7, (word >> 3) & 7
    words = (word,)
    immediate = 0
    if primary in {10, 11}:
        high_address = (address + 1) & MASK
        if high_address not in program:
            raise FetchError(f"missing second instruction word at PC=0x{address:04X}")
        immediate = program[high_address]
        words += (immediate,)
    mnemonic: str | None = None
    if primary == 0:
        mnemonic = {1: "ADD", 2: "SUB", 3: "AND", 4: "OR", 5: "XOR", 6: "NOT", 7: "MUL"}.get(function)
        if word == 0:
            mnemonic = "NOP"
    elif primary == 1:
        mnemonic = {3: "SGE", 2: "SL", 5: "SE", 4: "SNE", 6: "SAE", 7: "SB"}.get(function)
    elif primary in {2, 3}:
        mnemonic = "SH" if primary == 2 else "ASH"
        dst, immediate = a, _immediate(word, 5)
    elif primary == 4:
        mnemonic, dst, immediate = "ADDI", a, _immediate(word, 8)
    elif primary == 5:
        mnemonic = "LUI" if word & 8 else "LLI"
        dst, immediate = a, _immediate(word, 8, sign=False)
    elif primary in {6, 7}:
        mnemonic = "LD" if primary == 6 else "ST"
        dst, immediate = a, _immediate(word, 6)
    elif primary in {8, 9}:
        mnemonic = "LDSP" if primary == 8 else "STSP"
        dst, immediate = a, _immediate(word, 8)
    elif primary == 10:
        mnemonic = {3: "JGE", 2: "JL", 5: "JE", 4: "JNE", 6: "JAE", 7: "JB"}.get(function)
    elif primary == 11:
        mnemonic = {1: "JMP", 2: "JAL"}.get(function)
    elif primary == 12:
        mnemonic = {1: "PUSH", 2: "POP"}.get(function)
    elif primary == 13:
        mnemonic = {1: "JMPR", 2: "JALR"}.get(function)
    elif primary == 14:
        mnemonic = {1: "FADD", 2: "FSUB", 3: "FMUL", 4: "FDIV", 5: "ITOF", 6: "FTOI", 7: "FTOU"}.get(function)
    elif primary == 15:
        mnemonic = "HALT"
    if mnemonic is None:
        raise IllegalInstructionError(f"undefined instruction 0x{word:04X} at PC=0x{address:04X}")
    return Instruction(address, words, mnemonic, dst, a, b, immediate, function)


def disassemble(program: Mapping[int, int] | AssemblyResult, address: int = 0) -> str:
    words = program.words if isinstance(program, AssemblyResult) else program
    return str(decode(words, address))


@dataclass(frozen=True)
class MemoryAccess:
    address: int
    value: int
    io: bool = False


@dataclass(frozen=True)
class TraceCycle:
    """Signals and architectural side effects observed during one RTL clock."""

    cycle: int
    pc: int
    registers: tuple[int, ...]
    register_writes: tuple[tuple[int, int], ...] = ()
    memory_reads: tuple[MemoryAccess, ...] = ()
    memory_writes: tuple[MemoryAccess, ...] = ()
    halted: bool = False
    fetch_valid: bool = False
    fetch_accepted: bool = False
    fetch_low: int = 0
    fetch_high: int = 0
    fetch_high_valid: bool = False
    next_pc: int = 0
    execute_valid: bool = False
    execute_pc: int = 0
    jump_enable: bool = False
    jump_address: int = 0
    pipeline: dict[str, int] = field(default_factory=dict)

    @property
    def index(self) -> int:
        return self.cycle

    @property
    def accepted(self) -> bool:
        """Compatibility spelling for the RTL fetch-accept signal."""
        return self.fetch_accepted

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, event: Mapping[str, Any]) -> TraceCycle:
        return cls(
            cycle=int(event.get("cycle", event.get("index", 0))),
            pc=int(event.get("pc", 0)),
            registers=tuple(event.get("registers", (0,) * 8)),
            register_writes=tuple(tuple(item) for item in event.get("register_writes", ())),
            memory_reads=tuple(MemoryAccess(**item) for item in event.get("memory_reads", ())),
            memory_writes=tuple(MemoryAccess(**item) for item in event.get("memory_writes", ())),
            halted=bool(event.get("halted", False)),
            fetch_valid=bool(event.get("fetch_valid", False)),
            fetch_accepted=bool(event.get(
                "fetch_accepted", event.get("accepted", event.get("instruction_accepted", False))
            )),
            fetch_low=int(event.get("fetch_low", 0)),
            fetch_high=int(event.get("fetch_high", 0)),
            fetch_high_valid=bool(event.get("fetch_high_valid", False)),
            next_pc=int(event.get("next_pc", 0)),
            execute_valid=bool(event.get("execute_valid", False)),
            execute_pc=int(event.get("execute_pc", 0)),
            jump_enable=bool(event.get("jump_enable", False)),
            jump_address=int(event.get("jump_address", 0)),
            pipeline={name: int(value) for name, value in event.get("pipeline", {}).items()},
        )


# Compatibility name. A trace entry now describes one real clock cycle.
TraceStep = TraceCycle


def _integer_key(value: int | str) -> int:
    return value if isinstance(value, int) else int(value, 0)


class CPU:
    """A synchronous client of a cocotb-controlled Verilator CPU instance.

    ``program`` is loaded into the wrapper's real ROM. Registers, RAM, MMIO,
    forwarding, stalls, branches, and HALT are all implemented by ``potados.sv``.
    Use this class as a context manager to close the simulator promptly.
    """

    def __init__(
        self,
        program: AssemblyResult | Mapping[int, int] | list[int] | tuple[int, ...],
        *,
        pc: int = 0,
        initial_sp: int = 0,
        ram_low: int = 0,
        ram_high: int = 0x7FFF,
        io: Mapping[int, int] | None = None,
        waves: bool | str | Path = False,
        io_read: Callable[[int], int] | None = None,
        io_write: Callable[[int, int], None] | None = None,
    ) -> None:
        self._session: Any = None
        self._state: dict[str, Any] = {}
        self._ram: tuple[int, ...] | None = None
        self._waveform: Path | None = None
        if io_read is not None or io_write is not None:
            raise ValueError("RTL execution accepts MMIO input maps through io= or set_io(); Python MMIO callbacks are not supported")
        if not 0 <= ram_low <= ram_high <= MASK:
            raise ValueError("invalid RAM address window")
        self.symbols = dict(program.symbols) if isinstance(program, AssemblyResult) else {}
        words = program.words if isinstance(program, AssemblyResult) else program
        if not isinstance(words, Mapping):
            words = dict(enumerate(words))
        if any(not 0 <= address <= MASK or not 0 <= word <= MASK for address, word in words.items()):
            raise ValueError("program addresses and words must fit in 16 bits")
        self.rom = dict(words)
        self.ram_low, self.ram_high = ram_low, ram_high
        from .rtl import RTLSession
        try:
            self._session = RTLSession(
                self.rom, pc=pc & MASK, initial_sp=initial_sp & MASK,
                ram_low=ram_low, ram_high=ram_high, io=dict(io or {}), waves=waves,
            )
            self._waveform = self._session.waveform
            self._rpc({"op": "snapshot", "include_ram": True})
        except (RuntimeError, OSError) as exc:
            self.close()
            raise EmulatorError(str(exc)) from exc

    @classmethod
    def from_source(cls, source: str, **kwargs: Any) -> CPU:
        return cls(assemble(source), **kwargs)

    @classmethod
    def from_file(cls, path: str | Path, **kwargs: Any) -> CPU:
        return cls(load_program(path), **kwargs)

    def __enter__(self) -> CPU:
        if self._session is None:
            raise EmulatorError("RTL simulator is closed")
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            session.close()
            self._waveform = session.waveform

    @property
    def waveform(self) -> Path | None:
        """Requested waveform destination, flushed when the session closes."""
        return self._waveform

    def _rpc(self, command: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise EmulatorError("RTL simulator is closed")
        try:
            result = self._session.command(command)
        except (RuntimeError, OSError) as exc:
            raise EmulatorError(str(exc)) from exc
        if not result.get("ok", True):
            raise EmulatorError(result.get("error", "RTL simulator command failed"))
        if "state" in result:
            incoming = dict(result["state"])
            if "ram" in incoming:
                self._ram = None
            elif command.get("op") in {"run", "tick", "write", "reset"}:
                self._ram = None
            elif "ram" in self._state:
                incoming["ram"] = self._state["ram"]
            self._state = incoming
        return result

    @property
    def registers(self) -> list[int]:
        return list(self._state.get("registers", (0,) * 8))

    @property
    def pc(self) -> int:
        return int(self._state.get("pc", 0))

    @property
    def cycles(self) -> int:
        return int(self._state.get("cycles", 0))

    @property
    def steps(self) -> int:
        """Compatibility alias for clock cycles, never instruction count."""
        return self.cycles

    @property
    def accepted_fetches(self) -> int:
        """Fetches accepted by decode; this is not a retirement counter."""
        return int(self._state.get("accepted_fetches", self._state.get("instructions", 0)))

    @property
    def halted(self) -> bool:
        return bool(self._state.get("halted", False))

    @property
    def io(self) -> dict[int, int]:
        return {_integer_key(key): int(value) for key, value in self._state.get("io", {}).items()}

    @property
    def io_writes(self) -> list[tuple[int, int]]:
        return [(int(address), int(value)) for address, value in self._state.get("io_writes", ())]

    @property
    def ram(self) -> tuple[int, ...]:
        if self._ram is None:
            if "ram" not in self._state:
                self._rpc({"op": "snapshot", "include_ram": True})
            words = [0] * 0x10000
            for address, value in self._state.get("ram", {}).items():
                words[_integer_key(address)] = int(value)
            self._ram = tuple(words)
        return self._ram

    def read(self, address: int) -> int:
        return int(self._rpc({"op": "read", "address": address & MASK})["value"])

    def write(self, address: int, value: int) -> None:
        self._rpc({"op": "write", "address": address & MASK, "value": value & MASK})

    def set_io(self, address: int, value: int) -> None:
        address &= MASK
        if self.ram_low <= address <= self.ram_high:
            raise ValueError("MMIO input address must be outside the RAM window")
        self._rpc({"op": "set_io", "address": address, "value": value & MASK})

    def set_register(self, register: int | str, value: int) -> None:
        if isinstance(register, str):
            name = register.upper()
            names = {**{f"R{i}": i for i in range(8)}, "ZERO": 0, "SP": 1}
            if name not in names:
                raise ValueError("unknown register")
            register = names[name]
        if register == 0:
            raise ValueError("ZERO is read-only")
        if not 0 <= register <= 7:
            raise ValueError("register must be in 0..7")
        self._rpc({"op": "set_reg", "register": register, "value": value & MASK})

    def step(self) -> TraceCycle:
        """Advance exactly one clock cycle and return signals sampled by cocotb."""
        if self.halted:
            raise EmulatorError("CPU is halted")
        result = self._rpc({"op": "tick", "count": 1, "trace": True})
        events = result.get("events", ())
        if not events:
            raise EmulatorError("RTL simulator did not return its clock-cycle trace")
        return TraceCycle.from_dict(events[-1])

    def tick(self, count: int = 1) -> CPU:
        """Advance up to ``count`` real clock cycles, stopping at HALT."""
        if count < 1:
            raise ValueError("cycle count must be positive")
        self._rpc({"op": "tick", "count": count, "trace": False})
        return self

    def run(
        self,
        max_cycles: int | None = None,
        *,
        max_steps: int | None = None,
        trace: Callable[[TraceCycle], None] | None = None,
        breakpoints: set[int] | None = None,
        ignore_current_breakpoint: bool = False,
    ) -> CPU:
        """Clock the actual RTL until HALT, a fetch breakpoint, or a cycle limit.

        Fetch breakpoints pause before an accepted fetch enters decode. Older
        pipeline entries may still be present: this is not instruction stepping.
        ``max_steps`` is retained as an alias for ``max_cycles``.
        """
        if max_cycles is not None and max_steps is not None:
            raise ValueError("specify max_cycles or max_steps, not both")
        limit = max_cycles if max_cycles is not None else max_steps
        limit = 1_000_000 if limit is None else limit
        if limit < 1:
            raise ValueError("max_cycles must be positive")
        if self.halted:
            return self
        command: dict[str, Any] = {
            "op": "run", "max_cycles": limit,
            "breakpoints": sorted(breakpoints or ()),
            "ignore_current_breakpoint": ignore_current_breakpoint,
        }
        if trace:
            # Cocotb writes trace rows directly; even a long RTL run need not
            # accumulate millions of cycle records in a socket response.
            with tempfile.TemporaryDirectory(prefix="potados-trace-") as work:
                path = Path(work) / "cycles.jsonl"
                command["trace_path"] = str(path)
                result = self._rpc(command)
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        trace(TraceCycle.from_dict(json.loads(line)))
        else:
            result = self._rpc(command)
        if result.get("reason") == "limit" and not self.halted:
            raise ExecutionLimitError(f"clock-cycle limit ({limit}) reached at fetch PC=0x{self.pc:04X}")
        return self

    def state(self, *, include_ram: bool = False) -> dict[str, Any]:
        """Return a debugger snapshot of state obtained from the RTL instance."""
        result: dict[str, Any] = {
            "backend": "cocotb-verilator", "pc": self.pc, "halted": self.halted,
            "cycles": self.cycles, "steps": self.cycles,
            "accepted_fetches": self.accepted_fetches,
            "fetch_valid": bool(self._state.get("fetch_valid", False)),
            "fetch_accepted": bool(self._state.get("fetch_accepted", self._state.get("instruction_accepted", False))),
            "pipeline": dict(self._state.get("pipeline", {})),
            "registers": dict(zip(REGISTER_NAMES, self.registers)),
            "io": {f"0x{address:04X}": value for address, value in sorted(self.io.items())},
            "io_writes": list(self.io_writes),
        }
        if self.waveform is not None:
            result["waveform"] = str(self.waveform)
        if include_ram:
            result["ram"] = {f"0x{address:04X}": value for address, value in enumerate(self.ram) if value}
        return result


def load_program(path: str | Path) -> AssemblyResult | dict[int, int]:
    """Load .asm/.s source, a readmemh .hex image, or big-endian .bin words."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".asm", ".s", ".pasm"}:
        return assemble_file(path)
    if suffix in {".bin", ".binary"}:
        data = path.read_bytes()
        if len(data) % 2:
            raise EmulatorError("binary program has a partial 16-bit word")
        if len(data) > 0x20000:
            raise EmulatorError("binary program exceeds the 16-bit word address space")
        return {offset // 2: int.from_bytes(data[offset:offset + 2], "big") for offset in range(0, len(data), 2)}
    if suffix not in {".hex", ".mem", ".rom"}:
        raise EmulatorError(f"unsupported program suffix {suffix!r}; use .asm, .s, .hex, or .bin")
    words: dict[int, int] = {}
    address = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("//", 1)[0].split("#", 1)[0].split(";", 1)[0]
        for token in line.split():
            try:
                if token.startswith("@"):
                    address = int(token[1:], 16)
                    if not 0 <= address <= MASK:
                        raise ValueError("address outside the 16-bit word address space")
                else:
                    word = int(token, 16)
                    if not 0 <= word <= MASK or not 0 <= address <= MASK:
                        raise ValueError("word or address outside the 16-bit range")
                    if address in words:
                        raise ValueError("duplicate program address")
                    words[address] = word
                    address += 1
            except ValueError as exc:
                raise EmulatorError(f"{path}:{line_number}: invalid image token {token!r}: {exc}") from exc
    return words
