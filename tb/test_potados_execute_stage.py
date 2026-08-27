from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import cocotb
import pytest
from cocotb.triggers import Timer
from cocotb_tools.runner import get_runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_execute_stage"

Dut = Any
Runner = Any


def _pack_execute_stage(
    *,
    valid: int = 1,
    pc: int = 0,
    next_pc: int = 0,
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
) -> int:
    """Pack execute_stage_t in declaration order for the DUT input port."""
    return (
        ((valid & 0b1) << 122)
        | ((pc & 0xFFFF) << 106)
        | ((next_pc & 0xFFFF) << 90)
        | ((operand_a & 0xFFFF) << 74)
        | ((operand_b & 0xFFFF) << 58)
        | ((memory_write_data & 0xFFFF) << 42)
        | ((jump_target & 0xFFFF) << 26)
        | ((dst & 0b111) << 23)
        | ((alu_op & 0b1_1111) << 18)
        | ((cmp_op & 0b1111) << 14)
        | ((fpu_op & 0b1111) << 10)
        | ((memory_op & 0b11) << 8)
        | ((stack_pointer_op & 0b11) << 6)
        | ((jump_op & 0b11) << 4)
        | ((writeback_source & 0b111) << 1)
        | (halt & 0b1)
    )


def _field(value: int, lsb: int, width: int) -> int:
    return (value >> lsb) & ((1 << width) - 1)


async def _expect(
    dut: Dut,
    *,
    fpu_output: int = 0,
    expected_valid: int = 1,
    expected_alu_result: int = 0,
    expected_memory_write_data: int = 0,
    expected_fpu_result: int = 0,
    expected_next_pc: int = 0,
    expected_memory_op: int = 0,
    expected_stack_pointer_op: int = 0,
    expected_dst: int = 0,
    expected_writeback_source: int = 0,
    expected_jump_enable: int = 0,
    expected_jump_address: int = 0,
    expected_halt: int = 0,
) -> None:
    """Compare every memory_stage_t field plus execute control-flow outputs."""
    dut.fpu_output.value = fpu_output
    await Timer(1, unit="ns")

    memory_stage = int(dut.memory_stage.value)
    checks = (
        ("memory_stage.valid", _field(memory_stage, 74, 1), expected_valid),
        ("memory_stage.alu_result", _field(memory_stage, 58, 16), expected_alu_result),
        (
            "memory_stage.memory_write_data",
            _field(memory_stage, 42, 16),
            expected_memory_write_data,
        ),
        ("memory_stage.fpu_result", _field(memory_stage, 26, 16), expected_fpu_result),
        ("memory_stage.next_pc", _field(memory_stage, 10, 16), expected_next_pc),
        ("memory_stage.memory_op", _field(memory_stage, 8, 2), expected_memory_op),
        (
            "memory_stage.stack_pointer_op",
            _field(memory_stage, 6, 2),
            expected_stack_pointer_op,
        ),
        ("memory_stage.dst", _field(memory_stage, 3, 3), expected_dst),
        (
            "memory_stage.writeback_source",
            _field(memory_stage, 0, 3),
            expected_writeback_source,
        ),
        ("jump_enable", int(dut.jump_enable.value), expected_jump_enable),
        ("jump_address", int(dut.jump_address.value), expected_jump_address),
        ("halt", int(dut.halt.value), expected_halt),
    )
    for name, actual, expected in checks:
        assert actual == expected, f"{name} == 0x{expected:X}; got 0x{actual:X}"


@cocotb.test()
async def execute_stage_runs_alu_and_preserves_writeback_metadata(dut: Dut) -> None:
    dut.clk.value = 0
    dut.reset.value = 0
    dut.execute_stage.value = _pack_execute_stage(
        pc=0x0100,
        next_pc=0x0101,
        operand_a=0x1234,
        operand_b=0x0102,
        dst=0b101,
        alu_op=0b00001,  # ALU_ADD
        writeback_source=0b001,  # WB_ALU
    )
    await _expect(
        dut,
        expected_alu_result=0x1336,
        expected_next_pc=0x0101,
        expected_dst=0b101,
        expected_writeback_source=0b001,
    )


@cocotb.test()
async def execute_stage_prepares_memory_and_stack_operations(dut: Dut) -> None:
    dut.clk.value = 0
    dut.reset.value = 0
    dut.execute_stage.value = _pack_execute_stage(
        next_pc=0x0201,
        operand_a=0x1000,
        operand_b=0xFFFF,
        memory_write_data=0xBEEF,
        dst=0b011,
        alu_op=0b00001,  # ALU_ADD: effective address = 0x0FFF
        memory_op=0b10,  # MEMORY_STORE
        stack_pointer_op=0b10,  # STACK_POINTER_INCREMENT
    )
    await _expect(
        expected_alu_result=0x0FFF,
        expected_memory_write_data=0xBEEF,
        expected_next_pc=0x0201,
        expected_memory_op=0b10,
        expected_stack_pointer_op=0b10,
        expected_dst=0b011,
    )


@cocotb.test()
async def execute_stage_resolves_conditional_and_unconditional_jumps(dut: Dut) -> None:
    dut.clk.value = 0
    dut.reset.value = 0

    # JL: signed 3 < 5, so the conditional jump is taken.
    dut.execute_stage.value = _pack_execute_stage(
        operand_a=3,
        operand_b=5,
        jump_target=0xBEEF,
        alu_op=0b01011,  # ALU_CMP
        cmp_op=0b0010,  # CMP_L
        jump_op=0b01,  # JUMP_CONDITIONAL
    )
    await _expect(
        expected_alu_result=0xFFFE,
        expected_jump_enable=1,
        expected_jump_address=0xBEEF,
    )

    # JGE: signed 3 >= 5 is false, so no jump is requested.
    dut.execute_stage.value = _pack_execute_stage(
        operand_a=3,
        operand_b=5,
        jump_target=0xBEEF,
        alu_op=0b01011,  # ALU_CMP
        cmp_op=0b0001,  # CMP_GE
        jump_op=0b01,
    )
    await _expect(dut, expected_alu_result=0xFFFE, expected_jump_address=0xBEEF)

    # An unconditional jump does not depend on the comparator output.
    dut.execute_stage.value = _pack_execute_stage(
        jump_target=0xCAFE,
        jump_op=0b10,  # JUMP_ALWAYS
    )
    await _expect(dut, expected_jump_enable=1, expected_jump_address=0xCAFE)


@cocotb.test()
async def execute_stage_forwards_fpu_result_and_halt(dut: Dut) -> None:
    dut.clk.value = 0
    dut.reset.value = 0
    dut.execute_stage.value = _pack_execute_stage(
        next_pc=0x0401,
        dst=0b100,
        fpu_op=0b0001,  # FPU_ADD
        writeback_source=0b011,  # WB_FPU
        halt=1,
    )
    await _expect(
        dut,
        fpu_output=0xF00D,
        expected_fpu_result=0xF00D,
        expected_next_pc=0x0401,
        expected_dst=0b100,
        expected_writeback_source=0b011,
        expected_halt=1,
    )


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_execute_stage",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def execute_stage_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_execute_stage",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False)


def test_execute_stage_runs_alu_and_preserves_writeback_metadata(
    execute_stage_runner: Runner,
) -> None:
    _run_cocotb_test(execute_stage_runner, "execute_stage_runs_alu_and_preserves_writeback_metadata")


def test_execute_stage_prepares_memory_and_stack_operations(
    execute_stage_runner: Runner,
) -> None:
    _run_cocotb_test(execute_stage_runner, "execute_stage_prepares_memory_and_stack_operations")


def test_execute_stage_resolves_conditional_and_unconditional_jumps(
    execute_stage_runner: Runner,
) -> None:
    _run_cocotb_test(execute_stage_runner, "execute_stage_resolves_conditional_and_unconditional_jumps")


def test_execute_stage_forwards_fpu_result_and_halt(
    execute_stage_runner: Runner,
) -> None:
    _run_cocotb_test(execute_stage_runner, "execute_stage_forwards_fpu_result_and_halt")
