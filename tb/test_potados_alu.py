from __future__ import annotations

import os
import random
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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_alu"

Dut = Any
Runner = Any

# Keep these values in sync with the typedef enums in rtl/potados_alu.sv.
ALU_NONE = 0
ALU_ADD = 1
ALU_SUB = 2
ALU_AND = 3
ALU_OR = 4
ALU_XOR = 5
ALU_NOT = 6
ALU_MUL = 7
ALU_SH = 8
ALU_ASH = 9
ALU_SET = 10
ALU_CMP = 11

CMP_NONE = 0
CMP_GE = 1
CMP_L = 2
CMP_E = 3
CMP_NE = 4
CMP_AE = 5
CMP_B = 6

CMP_RESULT_NONE = 0
CMP_RESULT_TRUE = 1
CMP_RESULT_FALSE = 2

EDGE_VALUES = (0x0000, 0x0001, 0x0002, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF)


async def _clock_cycles(dut: Dut, cycles: int) -> None:
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


async def _reset(dut: Dut) -> None:
    dut.reset.value = 1
    dut.alu_request.value = _pack_alu_request(
        cin=0, operand_a=0, operand_b=0, alu_op=ALU_NONE, cmp_op=CMP_NONE
    )
    await _clock_cycles(dut, 2)
    assert int(dut.alu_output.value) == 0
    assert int(dut.cmp_output.value) == CMP_RESULT_NONE
    assert int(dut.out_ready.value) == 0
    dut.reset.value = 0


async def _execute(
    dut: Dut,
    *,
    alu_op: int,
    operand_a: int,
    operand_b: int = 0,
    cin: int = 0,
    cmp_op: int = CMP_NONE,
) -> None:
    dut.alu_request.value = _pack_alu_request(
        cin=cin,
        operand_a=operand_a,
        operand_b=operand_b,
        alu_op=alu_op,
        cmp_op=cmp_op,
    )
    await _clock_cycles(dut, 1)


def _pack_alu_request(
    *, cin: int, operand_a: int, operand_b: int, alu_op: int, cmp_op: int
) -> int:
    """Pack alu_request_t in its SystemVerilog declaration order."""
    return (
        ((cin & 0b1) << 41)
        | ((operand_a & 0xFFFF) << 25)
        | ((operand_b & 0xFFFF) << 9)
        | ((alu_op & 0b1_1111) << 4)
        | (cmp_op & 0b1111)
    )


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _compare(operand_a: int, operand_b: int, op: int) -> int:
    signed_a = _signed16(operand_a)
    signed_b = _signed16(operand_b)
    unsigned_a = operand_a & 0xFFFF
    unsigned_b = operand_b & 0xFFFF

    if op == CMP_NONE:
        return CMP_RESULT_NONE
    if op == CMP_GE:
        return CMP_RESULT_TRUE if signed_a >= signed_b else CMP_RESULT_FALSE
    if op == CMP_L:
        return CMP_RESULT_TRUE if signed_a < signed_b else CMP_RESULT_FALSE
    if op == CMP_E:
        return CMP_RESULT_TRUE if unsigned_a == unsigned_b else CMP_RESULT_FALSE
    if op == CMP_NE:
        return CMP_RESULT_TRUE if unsigned_a != unsigned_b else CMP_RESULT_FALSE
    if op == CMP_AE:
        return CMP_RESULT_TRUE if unsigned_a >= unsigned_b else CMP_RESULT_FALSE
    if op == CMP_B:
        return CMP_RESULT_TRUE if unsigned_a < unsigned_b else CMP_RESULT_FALSE
    raise AssertionError(f"Unknown comparison opcode: {op}")


def _expected_output(
    alu_op: int, operand_a: int, operand_b: int, cin: int, cmp_op: int
) -> tuple[int, int, int]:
    operand_a &= 0xFFFF
    operand_b &= 0xFFFF

    if alu_op == ALU_NONE:
        return 0, CMP_RESULT_NONE, 0
    if alu_op == ALU_ADD:
        return (operand_a + operand_b + cin) & 0xFFFF, CMP_RESULT_NONE, 1
    if alu_op == ALU_SUB:
        return (
            (operand_a - operand_b - cin) & 0xFFFF,
            _compare(operand_a, operand_b, cmp_op),
            1,
        )
    if alu_op == ALU_AND:
        return operand_a & operand_b, CMP_RESULT_NONE, 1
    if alu_op == ALU_OR:
        return operand_a | operand_b, CMP_RESULT_NONE, 1
    if alu_op == ALU_XOR:
        return operand_a ^ operand_b, CMP_RESULT_NONE, 1
    if alu_op == ALU_NOT:
        return (~operand_b) & 0xFFFF, CMP_RESULT_NONE, 1
    if alu_op == ALU_MUL:
        return (operand_a * operand_b) & 0xFFFF, CMP_RESULT_NONE, 1
    if alu_op == ALU_SH:
        shift = operand_b & 0x3F
        if shift & 0x20:
            result = operand_a >> ((-shift) & 0x3F)
        else:
            result = operand_a << shift
        return result & 0xFFFF, CMP_RESULT_NONE, 1
    if alu_op == ALU_ASH:
        shift = operand_b & 0x3F
        if shift & 0x20:
            result = _signed16(operand_a) >> ((-shift) & 0x3F)
        else:
            result = operand_a << shift
        return result & 0xFFFF, CMP_RESULT_NONE, 1
    if alu_op == ALU_SET:
        result = _compare(operand_a, operand_b, cmp_op)
        return int(result == CMP_RESULT_TRUE), result, 1
    if alu_op == ALU_CMP:
        return (
            (operand_a - operand_b - cin) & 0xFFFF,
            _compare(operand_a, operand_b, cmp_op),
            1,
        )
    raise AssertionError(f"Unknown ALU opcode: {alu_op}")


def _assert_result(dut: Dut, expected: tuple[int, int, int]) -> None:
    output, comparison, ready = expected
    assert int(dut.alu_output.value) == output
    assert int(dut.cmp_output.value) == comparison
    assert int(dut.out_ready.value) == ready


@cocotb.test()
async def arithmetic_and_logic_operations(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _execute(dut, alu_op=ALU_ADD, operand_a=0x1234, operand_b=0x0102)
    assert int(dut.alu_output.value) == 0x1336
    assert int(dut.out_ready.value) == 1
    assert int(dut.cmp_output.value) == CMP_RESULT_NONE

    await _execute(dut, alu_op=ALU_ADD, operand_a=0xFFFF, operand_b=0, cin=1)
    assert int(dut.alu_output.value) == 0

    await _execute(dut, alu_op=ALU_SUB, operand_a=3, operand_b=5)
    assert int(dut.alu_output.value) == 0xFFFE

    await _execute(dut, alu_op=ALU_AND, operand_a=0xA5A5, operand_b=0x3C3C)
    assert int(dut.alu_output.value) == 0x2424

    await _execute(dut, alu_op=ALU_OR, operand_a=0xA5A5, operand_b=0x3C3C)
    assert int(dut.alu_output.value) == 0xBDBD

    await _execute(dut, alu_op=ALU_XOR, operand_a=0xA5A5, operand_b=0x3C3C)
    assert int(dut.alu_output.value) == 0x9999

    await _execute(dut, alu_op=ALU_NOT, operand_a=0x0000, operand_b=0x00F0)
    assert int(dut.alu_output.value) == 0xFF0F


@cocotb.test()
async def multiply_and_shift_operations(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _execute(dut, alu_op=ALU_MUL, operand_a=0x1234, operand_b=3)
    assert int(dut.alu_output.value) == 0x369C
    assert int(dut.out_ready.value) == 1

    await _execute(dut, alu_op=ALU_SH, operand_a=1, operand_b=4)
    assert int(dut.alu_output.value) == 0x0010

    # Negative signed IMM6 values shift right; -1 shifts right by one bit.
    await _execute(dut, alu_op=ALU_SH, operand_a=0x8001, operand_b=-1)
    assert int(dut.alu_output.value) == 0x4000

    # Negative signed IMM6 values preserve the sign for arithmetic shifts.
    await _execute(dut, alu_op=ALU_ASH, operand_a=0x8001, operand_b=-1)
    assert int(dut.alu_output.value) == 0xC000


@cocotb.test()
async def comparison_and_set_operations(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _execute(dut, alu_op=ALU_CMP, operand_a=5, operand_b=3, cmp_op=CMP_GE)
    assert int(dut.cmp_output.value) == CMP_RESULT_TRUE

    await _execute(dut, alu_op=ALU_CMP, operand_a=3, operand_b=5, cmp_op=CMP_GE)
    assert int(dut.cmp_output.value) == CMP_RESULT_FALSE

    await _execute(dut, alu_op=ALU_CMP, operand_a=0xFFFE, operand_b=1, cmp_op=CMP_L)
    assert int(dut.cmp_output.value) == CMP_RESULT_TRUE

    await _execute(dut, alu_op=ALU_SET, operand_a=7, operand_b=7, cmp_op=CMP_E)
    assert int(dut.alu_output.value) == 1
    assert int(dut.cmp_output.value) == CMP_RESULT_TRUE

    await _execute(dut, alu_op=ALU_SET, operand_a=7, operand_b=7, cmp_op=CMP_NE)
    assert int(dut.alu_output.value) == 0
    assert int(dut.cmp_output.value) == CMP_RESULT_FALSE


@cocotb.test()
async def randomised_all_operation_inputs(dut: Dut) -> None:
    """Case 2: exercise every ALU opcode with reproducible random inputs."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    rng = random.Random(0x504F5441)
    comparison_ops = range(CMP_NONE, CMP_B + 1)
    for alu_op in range(ALU_NONE, ALU_CMP + 1):
        for _ in range(128):
            operand_a = rng.randrange(1 << 16)
            operand_b = rng.randrange(1 << 16)
            cin = rng.randrange(2)
            cmp_op = rng.choice(list(comparison_ops))
            expected = _expected_output(alu_op, operand_a, operand_b, cin, cmp_op)
            await _execute(
                dut,
                alu_op=alu_op,
                operand_a=operand_a,
                operand_b=operand_b,
                cin=cin,
                cmp_op=cmp_op,
            )
            _assert_result(dut, expected)


@cocotb.test()
async def edge_case_matrix_for_all_operations(dut: Dut) -> None:
    """Case 1: check every opcode against important 16-bit boundary values."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    for alu_op in range(ALU_NONE, ALU_CMP + 1):
        for operand_a in EDGE_VALUES:
            for operand_b in EDGE_VALUES:
                for cin in range(2):
                    for cmp_op in range(CMP_NONE, CMP_B + 1):
                        expected = _expected_output(
                            alu_op, operand_a, operand_b, cin, cmp_op
                        )
                        await _execute(
                            dut,
                            alu_op=alu_op,
                            operand_a=operand_a,
                            operand_b=operand_b,
                            cin=cin,
                            cmp_op=cmp_op,
                        )
                        _assert_result(dut, expected)


@cocotb.test()
async def comparison_boundary_benchmark(dut: Dut) -> None:
    """Case 3: comparison-focused boundary and randomized regression vectors."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    # Signed boundaries, unsigned boundaries, equality, and overflow-sensitive pairs.
    boundary_pairs = [
        (0x0000, 0x0000),
        (0x0000, 0x0001),
        (0xFFFF, 0x0000),
        (0x7FFF, 0xFFFF),
        (0x8000, 0x0001),
        (0x8000, 0x7FFF),
        (0xFFFF, 0xFFFE),
    ]
    rng = random.Random(0x434D5050)
    boundary_pairs.extend(
        (rng.randrange(1 << 16), rng.randrange(1 << 16)) for _ in range(256)
    )

    for cmp_op in range(CMP_NONE, CMP_B + 1):
        for operand_a, operand_b in boundary_pairs:
            expected_comparison = _compare(operand_a, operand_b, cmp_op)

            await _execute(
                dut,
                alu_op=ALU_CMP,
                operand_a=operand_a,
                operand_b=operand_b,
                cmp_op=cmp_op,
            )
            assert int(dut.cmp_output.value) == expected_comparison

            await _execute(
                dut,
                alu_op=ALU_SET,
                operand_a=operand_a,
                operand_b=operand_b,
                cmp_op=cmp_op,
            )
            assert int(dut.cmp_output.value) == expected_comparison
            assert int(dut.alu_output.value) == int(
                expected_comparison == CMP_RESULT_TRUE
            )


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados_alu.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_alu",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def potados_alu_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_alu",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False
        )


def test_arithmetic_and_logic_operations(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "arithmetic_and_logic_operations")


def test_multiply_and_shift_operations(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "multiply_and_shift_operations")


def test_comparison_and_set_operations(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "comparison_and_set_operations")


def test_randomised_all_operation_inputs(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "randomised_all_operation_inputs")


def test_edge_case_matrix_for_all_operations(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "edge_case_matrix_for_all_operations")


def test_comparison_boundary_benchmark(potados_alu_runner: Runner) -> None:
    _run_cocotb_test(potados_alu_runner, "comparison_boundary_benchmark")
