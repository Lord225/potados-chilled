from __future__ import annotations

import io
from contextlib import contextmanager
import json
from pathlib import Path

import pytest

# Every CPU execution below launches the cached Verilated project RTL.

from potados_asm import assemble
from potados_emulator import (
    CPU, EmulatorError, ExecutionLimitError, decode, disassemble, load_program,
)
from potados_emulator.cli import debug, run


@contextmanager
def execute(source: str, **kwargs: object):
    """Execute actual potados.sv clock cycles, releasing the simulator afterward."""
    with CPU(assemble(source), **kwargs) as cpu:
        cpu.run(max_cycles=1000)
        yield cpu


@pytest.mark.parametrize(("operation", "left", "right", "expected"), [
    ("ADD", 0xFFFF, 2, 1),
    ("SUB", 3, 5, 0xFFFE),
    ("AND", 0xA5A5, 0x3C3C, 0x2424),
    ("OR", 0xA5A5, 0x3C3C, 0xBDBD),
    ("XOR", 0xA5A5, 0x3C3C, 0x9999),
    ("MUL", 0xFFFF, 0x12FE, 0xFD02),
])
def test_integer_operations_and_byte_multiplier(operation: str, left: int, right: int, expected: int) -> None:
    with execute(f"LI R2, {left}\nLI R3, {right}\n{operation} R4, R2, R3\nHALT") as cpu:
        assert cpu.registers[4] == expected


def test_unary_source_and_zero_register() -> None:
    with execute("LI R2, 0xA5\nNOT R3, R2\nLI ZERO, 0x1234\nADD R4, ZERO, R2\nHALT") as cpu:
        assert cpu.registers[0] == 0
        assert cpu.registers[3:5] == [0xFF5A, 0x00A5]


@pytest.mark.parametrize(("operation", "a", "b", "expected"), [
    ("SGE", 0xFFFF, 1, 0), ("SGE", 1, 0xFFFF, 1),
    ("SL", 0xFFFF, 1, 1), ("SL", 1, 0xFFFF, 0),
    ("SE", 7, 7, 1), ("SE", 7, 8, 0),
    ("SNE", 7, 8, 1), ("SNE", 7, 7, 0),
    ("SAE", 0xFFFF, 1, 1), ("SAE", 1, 0xFFFF, 0),
    ("SB", 1, 0xFFFF, 1), ("SB", 0xFFFF, 1, 0),
])
def test_all_comparison_functions(operation: str, a: int, b: int, expected: int) -> None:
    with execute(f"LI R2, {a}\nLI R3, {b}\n{operation} R4, R2, R3\nHALT") as cpu:
        assert cpu.registers[4] == expected
    jump = "J" + operation[1:]
    with execute(f"LI R2, {a}\nLI R3, {b}\n{jump} R2, R3, taken\nHALT\ntaken: LLI R4, 1\nHALT") as cpu:
        assert cpu.registers[4] == expected


@pytest.mark.parametrize(("operation", "value", "register_amount", "immediate", "expected"), [
    ("SH", 0x8001, 2, -1, 0x4000),
    ("ASH", 0x8001, 2, -1, 0xC000),
    ("SH", 3, 0xFFFE, 1, 6),
    ("ASH", 0x8001, 0xFFFE, 1, 2),
    ("SH", 0xFFFF, 0, -16, 0),
    ("ASH", 0x8000, 32, 0, 0xFFFF),
    ("SH", 0x1234, 0xFFFF, 1, 0x1234),
    ("SH", 0xFFFF, 0x7FFF, 1, 0),
])
def test_register_plus_immediate_shift_direction_and_boundaries(operation: str, value: int, register_amount: int, immediate: int, expected: int) -> None:
    with execute(f"LI R2, {value}\nLI R3, {register_amount}\n{operation} R2, R3, {immediate}\nHALT") as cpu:
        assert cpu.registers[2] == expected


@pytest.mark.parametrize(("primary", "width"), [(2, 5), (3, 5), (4, 8), (5, 8), (6, 6), (7, 6), (8, 8), (9, 8)])
def test_raw_immediate_bit_weights(primary: int, width: int) -> None:
    for bit in range(width):
        word = primary << 12 | 1 << (11 - bit) | 2
        instruction = decode({0: word})
        expected = 1 << bit
        if bit == width - 1 and primary != 5:
            expected = -expected
        assert instruction.immediate == expected


def test_immediate_loads_clear_other_half_and_signed_addition() -> None:
    with execute("LI R2, 0xABCD\nLLI R2, 0x80\nADDI R2, -128\nLUI R3, 0xA5\nADDI R3, 127\nHALT") as cpu:
        assert cpu.registers[2] == 0
        assert cpu.registers[3] == 0xA57F


def test_memory_displacements_and_separate_program_ram() -> None:
    with execute("LI SP, 0x100\nLI R2, 0x40\nLI R3, 0xBEEF\nST R3, [R2 - 32]\nLD R4, [R2 - 32]\nST R4, [R2 + 31]\nLD R5, [R2 + 31]\nSTSP R3, -128\nLDSP R6, -128\nSTSP R3, 127\nLDSP R7, 127\nHALT") as cpu:
        assert cpu.registers[4:8] == [0xBEEF] * 4
        assert [cpu.ram[address] for address in (0x20, 0x5F, 0x80, 0x17F)] == [0xBEEF] * 4
        assert cpu.rom[0] != cpu.ram[0]


def test_push_pop_and_explicit_sp_destination_priority() -> None:
    with execute("LI SP, 0x20\nLI R2, 0xBEEF\nPUSH R2\nPUSH SP\nPOP R3\nPOP R4\nHALT") as cpu:
        assert cpu.registers[1] == 0x20
        assert cpu.registers[3:5] == [0x21, 0xBEEF]
    with execute("LI SP, 0x20\nLI R2, 0x1234\nPUSH R2\nPOP SP\nHALT") as cpu:
        assert cpu.registers[1] == 0x1234


def test_jump_link_destinations_and_indirect_target_aliasing() -> None:
    with execute("JAL R5, target\nHALT\ntarget: ADDI R2, 1\nJMPR R5") as cpu:
        assert cpu.registers[2] == 1
        assert cpu.registers[5] == 2
    with execute("LI R5, target\nJALR R5, R5\nHALT\ntarget: ADDI R2, 1\nJMPR R5") as cpu:
        assert cpu.registers[2] == 1
        assert cpu.registers[5] == 3


def test_breakpoints_and_real_cycle_trace_capture() -> None:
    program = assemble("LLI R2, 7\n" + "NOP\n" * 8 + "stop: ADDI R2, 1\nST R2, [ZERO + 16]\nHALT")
    with CPU(program) as cpu:
        records = []
        cpu.run(max_cycles=1000, breakpoints={program.symbols["stop"]}, trace=records.append)
        assert not cpu.halted and cpu.pc == program.symbols["stop"]
        # Breakpoints pause fetch acceptance; the pipeline is not artificially drained.
        assert cpu.registers[2] == 7
        assert cpu.cycles > 1
        cpu.step()
        cpu.run(max_cycles=1000, trace=records.append)
        writes = [write for event in records for write in event.memory_writes]
        assert any(write.address == 16 and write.value == 8 and not write.io for write in writes)
        assert any(event.register_writes for event in records)
        assert any(event.fetch_accepted for event in records)
        assert any(event.execute_valid for event in records)
        assert "cycle" in json.loads(json.dumps(records[0].to_dict()))
        assert cpu.ram[16] == 8


def test_mmio_uses_real_rtl_read_and_write_requests() -> None:
    source = "LI R2, 0x8000\nLLI R3, 42\nST R3, [R2]\nLD R4, [R2]\nHALT"
    with execute(source) as cpu:
        assert cpu.registers[4] == 42
        assert cpu.io[0x8000] == 42
        assert cpu.io_writes == [(0x8000, 42)]
    with execute("LI R2, 0x8006\nLD R3, [R2]\nHALT", io={0x8006: 6}) as cpu:
        assert cpu.registers[3] == 6


def test_execution_follows_rtl_defaults_and_cycle_limits() -> None:
    # The harness preloads unused ROM with HALT. It does not run a second
    # software ISA implementation or invent software traps for RTL defaults.
    with CPU({0: 0x1000, 1: 0xF000}) as cpu:
        cpu.run(max_cycles=1000)
        assert cpu.halted
    with CPU({0: 0}) as cpu:
        cpu.run(max_cycles=1000)
        assert cpu.halted
    with CPU.from_source("loop: JMP loop") as cpu:
        with pytest.raises(ExecutionLimitError):
            cpu.run(max_cycles=7)
        assert cpu.cycles == 7 and not cpu.halted


def test_waveform_is_generated_by_verilator(tmp_path: Path) -> None:
    waveform = tmp_path / "program.vcd"
    with CPU.from_source("LLI R2, 42\nHALT", waves=waveform) as cpu:
        cpu.run(max_cycles=1000)
        assert cpu.registers[2] == 42
    assert waveform.is_file()
    assert waveform.stat().st_size > 0
    assert b"$timescale" in waveform.read_bytes()[:4096]


def test_sparse_hex_and_binary_loaders(tmp_path: Path) -> None:
    source = assemble("LLI R2, 7\nHALT")
    for suffix, data in ((".hex", source.to_hex().encode()), (".bin", source.to_binary())):
        path = tmp_path / f"image{suffix}"
        path.write_bytes(data)
        with CPU(load_program(path)) as cpu:
            cpu.run(max_cycles=1000)
            assert cpu.registers[2] == 7
    path = tmp_path / "sparse.hex"
    path.write_text("@0020\n5E02 // LLI R2,7\nF000\n")
    with CPU(load_program(path), pc=0x20) as cpu:
        cpu.run(max_cycles=1000)
        assert cpu.registers[2] == 7
    path.write_text("@0020\nF000\n@0020\nF000\n")
    with pytest.raises(EmulatorError, match="duplicate"):
        load_program(path)
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\xF0")
    with pytest.raises(EmulatorError, match="partial"):
        load_program(path)


def test_disassembler_uses_new_operand_order_and_high_destination() -> None:
    assert disassemble({0: 0x089A}) == "SUB R4, R2, R3"
    assert disassemble({0: 0xBA80, 1: 0x1234}) == "JAL R5, 0x1234"
    assert disassemble({0: 0xCC80}) == "POP R6"
    assert disassemble({0: 0x4012}) == "ADDI R2, -128"


def test_cli_writes_trace_and_failure_dumps(tmp_path: Path) -> None:
    program = tmp_path / "program.s"
    trace, state, ram = (tmp_path / name for name in ("trace.jsonl", "state.json", "ram.json"))
    program.write_text("LLI R2, 42\nST R2, [ZERO + 16]\nHALT")
    assert run(["run", str(program), "--trace", str(trace), "--dump-state", str(state), "--dump-ram", str(ram)]) == 0
    assert json.loads(state.read_text())["registers"]["R2"] == 42
    assert json.loads(ram.read_text())["0x0010"] == 42
    records = [json.loads(line) for line in trace.read_text().splitlines()]
    assert len(records) > 3
    assert all("cycle" in event and "fetch_accepted" in event for event in records)
    program.write_text("loop: JMP loop")
    assert run(["run", str(program), "--max-cycles", "3", "--dump-state", str(state)]) == 1
    assert json.loads(state.read_text())["cycles"] == 3


def test_scripted_debugger_break_clock_step_and_real_state_mutation() -> None:
    source = "LLI R2, 7\n" + "NOP\n" * 8 + "main: ADDI R2, 1\n" + "NOP\n" * 8 + "HALT"
    with CPU.from_source(source) as cpu:
        commands = io.StringIO("break main\ncontinue\nregisters\nset R2 0x1234\nset ZERO 99\ncycle\nwrite 0x20 42\nmemory 0x20 1\ncontinue\nquit\n")
        output = io.StringIO()
        debug(cpu, stdin=commands, stdout=output)
        assert cpu.halted and cpu.registers[2] == 0x1235
        assert cpu.registers[0] == 0
        assert "ZERO is read-only" in output.getvalue()
        assert cpu.ram[0x20] == 42
        assert "Breakpoint:" in output.getvalue()
        assert "0020: 002A" in output.getvalue()


def test_disassembly_round_trip_preserves_words_and_instruction_addresses() -> None:
    # Reassemble the disassembler's complete textual output at a nonzero base.
    # Long targets must remain separate words, and every following address must
    # advance by the actual encoded instruction width rather than a fixed step.
    source = """
        .org 0x120
        NOP
        ADD R4, R2, R3
        SUB R5, R3, R2
        AND R2, R4, R5
        OR R3, R5, R4
        XOR R4, R3, R2
        NOT R5, R4
        MUL R6, R2, R3
        SGE R4, R2, R3
        SL R4, R2, R3
        SE R4, R2, R3
        SNE R4, R2, R3
        SAE R4, R2, R3
        SB R4, R2, R3
        SH R2, R3, -16
        ASH R4, ZERO, 15
        ADDI R2, -128
        LLI R3, 0x81
        LUI R4, 0xFE
        LD R5, [R2 - 32]
        ST R4, [R3 + 31]
        LDSP R5, -128
        STSP R6, 127
        JGE R2, R3, 0x1234
        JL R2, R3, 0x1234
        JE R2, R3, 0x1234
        JNE R2, R3, 0x1234
        JAE R2, R3, 0x1234
        JB R2, R3, 0x1234
        JMP 0xABCD
        JAL R5, 0xFEED
        PUSH R4
        POP R6
        JMPR R5
        JALR R7, R5
        FADD R4, R2, R3
        FSUB R4, R2, R3
        FMUL R4, R2, R3
        FDIV R4, R2, R3
        ITOF R4, R2
        FTOI R4, R2
        FTOU R4, R2
        HALT
    """
    original = assemble(source)
    address = 0x120
    lines = [".org 0x120"]
    while address <= max(original.words):
        instruction = decode(original.words, address)
        assert instruction.address == address
        assert instruction.size == (2 if instruction.mnemonic.startswith("J") and instruction.mnemonic not in {"JMPR", "JALR"} else 1)
        lines.append(str(instruction))
        address += instruction.size
    assert address == max(original.words) + 1
    assert assemble("\n".join(lines)).words == original.words


def test_rtl_process_is_reaped_when_cpu_context_exits() -> None:
    with CPU.from_source("LLI R2, 42\nHALT") as cpu:
        process = cpu._session._process
        assert process is not None and process.poll() is None
        cpu.run(max_cycles=1000)
        assert cpu.registers[2] == 42
    assert process.poll() is not None
    assert cpu._session is None


def test_rtl_process_failure_reports_error_and_still_cleans_up() -> None:
    with CPU.from_source("loop: JMP loop") as cpu:
        process = cpu._session._process
        assert process is not None and process.poll() is None
        process.terminate()
        process.wait(timeout=5)
        with pytest.raises(EmulatorError, match=r"(?i)(RTL|simulat|closed|exit)"):
            cpu.step()
    assert process.poll() is not None
    assert cpu._session is None
