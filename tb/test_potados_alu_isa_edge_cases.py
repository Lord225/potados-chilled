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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_alu_isa_edge_cases"

Dut = Any
Runner = Any

ALU_SH = 8
ALU_ASH = 9


def _alu_request(*, operand_a: int, shift_amount: int, alu_op: int) -> int:
    """Pack alu_request_t; SH/ASH consume the lower signed five bits."""
    return (
        ((operand_a & 0xFFFF) << 25)
        | ((shift_amount & 0xFFFF) << 9)
        | ((alu_op & 0b1_1111) << 4)
    )


@cocotb.test()
async def negative_shift_amount_shifts_right(dut: Dut) -> None:
    """ISA rule: SH 0x8001, -1 == 0x4000."""
    dut.clk.value = 0
    dut.reset.value = 0
    dut.alu_request.value = _alu_request(
        operand_a=0x8001, shift_amount=-1, alu_op=ALU_SH
    )
    await Timer(1, unit="ns")
    assert int(dut.alu_output.value) == 0x4000


@cocotb.test()
async def positive_arithmetic_shift_shifts_left(dut: Dut) -> None:
    """ISA rule: ASH 0x4001, 1 == 0x8002."""
    dut.clk.value = 0
    dut.reset.value = 0
    dut.alu_request.value = _alu_request(
        operand_a=0x4001, shift_amount=1, alu_op=ALU_ASH
    )
    await Timer(1, unit="ns")
    assert int(dut.alu_output.value) == 0x8002


@cocotb.test()
async def imm6_sign_bit_is_ignored_by_shift_execution(dut: Dut) -> None:
    """SH 0x1234, -32 uses low IMM5 == 0 and is therefore a no-op."""
    dut.clk.value = 0
    dut.reset.value = 0
    dut.alu_request.value = _alu_request(
        operand_a=0x1234, shift_amount=-32, alu_op=ALU_SH
    )
    await Timer(1, unit="ns")
    assert int(dut.alu_output.value) == 0x1234


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
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
def alu_runner() -> Runner:
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


def test_negative_shift_amount_shifts_right(alu_runner: Runner) -> None:
    _run_cocotb_test(alu_runner, "negative_shift_amount_shifts_right")


def test_positive_arithmetic_shift_shifts_left(alu_runner: Runner) -> None:
    _run_cocotb_test(alu_runner, "positive_arithmetic_shift_shifts_left")


def test_imm6_sign_bit_is_ignored_by_shift_execution(alu_runner: Runner) -> None:
    _run_cocotb_test(alu_runner, "imm6_sign_bit_is_ignored_by_shift_execution")
