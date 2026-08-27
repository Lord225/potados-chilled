from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_decode_stage"

Dut = Any
Runner = Any


async def _clock_cycle(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def _reset(dut: Dut) -> None:
    dut.reset.value = 1
    dut.instruction_valid.value = 0
    dut.instruction_pc.value = 0
    dut.instruction_next_pc.value = 0
    dut.instruction_low.value = 0
    dut.instruction_high.value = 0
    dut.high_valid.value = 0
    dut.register_write_enable.value = 0
    dut.register_write_address.value = 0
    dut.register_write_data.value = 0
    dut.stack_pointer_write_data.value = 0
    dut.stack_pointer_operation.value = 0
    await _clock_cycle(dut)
    dut.reset.value = 0


async def _write_register(dut: Dut, address: int, value: int) -> None:
    dut.register_write_enable.value = 1
    dut.register_write_address.value = address
    dut.register_write_data.value = value
    await _clock_cycle(dut)
    dut.register_write_enable.value = 0


def _field(value: int, lsb: int, width: int) -> int:
    return (value >> lsb) & ((1 << width) - 1)


async def _expect_execute_stage(
    dut: Dut,
    instruction_low: int,
    *,
    valid: int = 1,
    pc: int = 0x0100,
    next_pc: int = 0x0101,
    operand_a: int = 0,
    operand_b: int = 0,
    memory_write_data: int = 0,
    jump_target: int = 0,
    dst: int = 0,
    alu_op: int = 0,
    cmp_op: int = 0,
    fpu_op: int = 0,
    memory_op: int = 0,
    stack_pointer_op: int = 0,
    jump_op: int = 0,
    writeback_source: int = 0,
    halt: int = 0,
    instruction_high: int = 0,
    high_valid: int = 0,
) -> None:
    """Drive one instruction and compare every execute_stage_t field."""
    dut.instruction_valid.value = 1
    dut.instruction_pc.value = pc
    dut.instruction_next_pc.value = next_pc
    dut.instruction_low.value = instruction_low
    dut.instruction_high.value = instruction_high
    dut.high_valid.value = high_valid
    await Timer(1, unit="ns")

    stage = int(dut.execute_stage.value)

    checks = (
        ("valid", _field(stage, 122, 1), valid),
        ("pc", _field(stage, 106, 16), pc),
        ("next_pc", _field(stage, 90, 16), next_pc),
        ("operand_a_value", _field(stage, 74, 16), operand_a),
        ("operand_b_value", _field(stage, 58, 16), operand_b),
        ("memory_write_data", _field(stage, 42, 16), memory_write_data),
        ("jump_target", _field(stage, 26, 16), jump_target),
        ("dst", _field(stage, 23, 3), dst),
        ("alu_op", _field(stage, 18, 5), alu_op),
        ("cmp_op", _field(stage, 14, 4), cmp_op),
        ("fpu_op", _field(stage, 10, 4), fpu_op),
        ("memory_op", _field(stage, 8, 2), memory_op),
        ("stack_pointer_op", _field(stage, 6, 2), stack_pointer_op),
        ("jump_op", _field(stage, 4, 2), jump_op),
        ("writeback_source", _field(stage, 1, 3), writeback_source),
        ("halt", _field(stage, 0, 1), halt),
    )
    for name, actual, expected in checks:
        assert actual == expected, (
            f"execute_stage.{name} == 0x{expected:X}; got 0x{actual:X}"
        )


@cocotb.test()
async def decode_stage_prepares_alu_compare_and_shift(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _write_register(dut, 0b010, 0x1234)
    await _write_register(dut, 0b011, 0x00F0)

    # NOP is the exact all-zero encoding. It writes the ALU result to ZERO.
    await _expect_execute_stage(
        dut, 0b0000_000_000_000_000,
        writeback_source=0b001,
    )

    # ADD R4, R2, R3
    await _expect_execute_stage(
        dut, 0b0000_100_001_010_011,
        operand_a=0x1234, operand_b=0x00F0, dst=0b100,
        alu_op=0b00001, writeback_source=0b001,
    )

    # NOT R4, R3
    await _expect_execute_stage(
        dut, 0b0000_100_110_000_011,
        operand_b=0x00F0, dst=0b100,
        alu_op=0b00110, writeback_source=0b001,
    )

    # SNE R4, R2, R3
    await _expect_execute_stage(
        dut, 0b0001_100_011_010_011,
        operand_a=0x1234, operand_b=0x00F0, dst=0b100,
        alu_op=0b01010, cmp_op=0b0100, writeback_source=0b001,
    )

    # SH R2, -1; the shift amount is the decoded signed IMM6.
    await _expect_execute_stage(
        dut, 0b0010_111111_010_010,
        operand_a=0x1234, operand_b=0xFFFF, dst=0b010,
        alu_op=0b01000, writeback_source=0b001,
    )

    # ASH R2, 1
    await _expect_execute_stage(
        dut, 0b0011_000001_010_010,
        operand_a=0x1234, operand_b=0x0001, dst=0b010,
        alu_op=0b01001, writeback_source=0b001,
    )


@cocotb.test()
async def decode_stage_prepares_immediate_and_memory_operations(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _write_register(dut, 0b010, 0x1000)
    await _write_register(dut, 0b011, 0xBEEF)
    await _write_register(dut, 0b110, 0x2000)
    await _write_register(dut, 0b001, 0x0400)

    # ADDI R3, 1
    await _expect_execute_stage(
        dut, 0b0100_000001_000_011,
        operand_a=0xBEEF, operand_b=0x0001, dst=0b011,
        alu_op=0b00001, writeback_source=0b001,
    )

    # LLI R2, 0xA5
    await _expect_execute_stage(
        dut, 0b0101_100101_010_010,
        operand_a=0x0000, operand_b=0x00A5, dst=0b010,
        alu_op=0b00100, writeback_source=0b001,
    )

    # LUI R2, 0xA5
    await _expect_execute_stage(
        dut, 0b0101_100101_110_010,
        operand_a=0x0000, operand_b=0xA500, dst=0b010,
        alu_op=0b00100, writeback_source=0b001,
    )

    # LD R1, [R6 + 1]
    await _expect_execute_stage(
        dut, 0b0110_000001_110_001,
        operand_a=0x2000, operand_b=0x0001, dst=0b001,
        alu_op=0b00001, memory_op=0b01, writeback_source=0b010,
    )

    # ST R3, [R2 - 1]
    await _expect_execute_stage(
        dut, 0b0111_111111_010_011,
        operand_a=0x1000, operand_b=0xFFFF, memory_write_data=0xBEEF, dst=0b011,
        alu_op=0b00001, memory_op=0b10,
    )

    # LDSP R3, [SP + 1]
    await _expect_execute_stage(
        dut, 0b1000_000001_000_011,
        operand_a=0x0400, operand_b=0x0001, dst=0b011,
        alu_op=0b00001, memory_op=0b01, writeback_source=0b010,
    )

    # STSP R3, [SP - 1]
    await _expect_execute_stage(
        dut, 0b1001_111111_111_011,
        operand_a=0x0400, operand_b=0xFFFF, memory_write_data=0xBEEF, dst=0b011,
        alu_op=0b00001, memory_op=0b10,
    )


@cocotb.test()
async def decode_stage_prepares_jumps_and_rejects_partial_long_words(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _write_register(dut, 0b010, 0x1111)
    await _write_register(dut, 0b011, 0x2222)

    # JNE R2, R3, 0xBEEF
    await _expect_execute_stage(
        dut, 0b1010_000_011_010_011,
        pc=0x0200, next_pc=0x0202,
        operand_a=0x1111, operand_b=0x2222, jump_target=0xBEEF,
        alu_op=0b01011, cmp_op=0b0100, jump_op=0b01,
        instruction_high=0xBEEF, high_valid=1,
    )

    # JMP 0xCAFE
    await _expect_execute_stage(
        dut, 0b1011_000_001_000_000,
        pc=0x0300, next_pc=0x0302, jump_target=0xCAFE, jump_op=0b10,
        instruction_high=0xCAFE, high_valid=1,
    )

    # JAL 0xCAFE, R3
    await _expect_execute_stage(
        dut, 0b1011_000_010_000_011,
        pc=0x0300, next_pc=0x0302, operand_b=0x2222, dst=0b011,
        jump_target=0xCAFE, jump_op=0b10, writeback_source=0b100,
        instruction_high=0xCAFE, high_valid=1,
    )

    # JMPR R3
    await _expect_execute_stage(
        dut, 0b1101_000_001_000_011,
        operand_b=0x2222, jump_target=0x2222, dst=0b011, jump_op=0b10,
    )

    # JALR R2, R3
    await _expect_execute_stage(
        dut, 0b1101_000_010_010_011,
        operand_a=0x1111, operand_b=0x2222, jump_target=0x1111,
        dst=0b011, jump_op=0b10,
        writeback_source=0b100,
    )

    # A long instruction without its high word must not enter execute.
    await _expect_execute_stage(
        dut, 0b1010_000_000_010_011,
        valid=0, pc=0, next_pc=0,
        instruction_high=0xBEEF, high_valid=0,
    )


@cocotb.test()
async def decode_stage_prepares_stack_fpu_and_halt(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _write_register(dut, 0b001, 0x0400)
    await _write_register(dut, 0b010, 0x1111)
    await _write_register(dut, 0b011, 0x2222)

    # PUSH R3
    await _expect_execute_stage(
        dut, 0b1100_000_001_000_011,
        operand_a=0x0400, memory_write_data=0x2222, dst=0b011,
        alu_op=0b00001, memory_op=0b10, stack_pointer_op=0b10,
    )

    # POP R2
    await _expect_execute_stage(
        dut, 0b1100_000_010_000_010,
        operand_a=0x03FF, dst=0b010, alu_op=0b00001,
        memory_op=0b01, stack_pointer_op=0b11, writeback_source=0b010,
    )

    # FADD R4, R2, R3
    await _expect_execute_stage(
        dut, 0b1110_100_001_010_011,
        operand_a=0x1111, operand_b=0x2222, dst=0b100,
        fpu_op=0b0001, writeback_source=0b011,
    )

    # FTOI R4, R3
    await _expect_execute_stage(
        dut, 0b1110_100_110_000_011,
        operand_a=0x2222, dst=0b100, fpu_op=0b0101,
        writeback_source=0b011,
    )

    # HALT
    await _expect_execute_stage(dut, 0b1111_000_000_000_000, halt=1)


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[
            RTL_DIR / "potados_instruction_decoder.sv",
            RTL_DIR / "potados_registers.sv",
        ],
        includes=[RTL_DIR],
        hdl_toplevel="instruction_decoder_stage_testbech_helper",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def decode_stage_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="instruction_decoder_stage_testbech_helper",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False)


def test_decode_stage_prepares_alu_compare_and_shift(decode_stage_runner: Runner) -> None:
    _run_cocotb_test(decode_stage_runner, "decode_stage_prepares_alu_compare_and_shift")


def test_decode_stage_prepares_immediate_and_memory_operations(
    decode_stage_runner: Runner,
) -> None:
    _run_cocotb_test(decode_stage_runner, "decode_stage_prepares_immediate_and_memory_operations")


def test_decode_stage_prepares_jumps_and_rejects_partial_long_words(
    decode_stage_runner: Runner,
) -> None:
    _run_cocotb_test(decode_stage_runner, "decode_stage_prepares_jumps_and_rejects_partial_long_words")


def test_decode_stage_prepares_stack_fpu_and_halt(decode_stage_runner: Runner) -> None:
    _run_cocotb_test(decode_stage_runner, "decode_stage_prepares_stack_fpu_and_halt")
