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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_instruction_decoder"

Dut = Any
Runner = Any


async def _expect(
    dut: Dut,
    instruction_low: int,
    *,
    op_primary: int,
    dst: int,
    op_secondary: int,
    src_a: int,
    src_b: int,
    immediate: int,
    partialy_decoded: int = 0,
    is_long: int = 0,
    instruction_high: int = 0,
    high_valid: int = 0,
) -> None:
    """Drive one instruction and compare every decoded output field."""
    dut.instruction_low.value = instruction_low
    dut.instruction_high.value = instruction_high
    dut.high_valid.value = high_valid
    await Timer(1, unit="ns")

    decoded = int(dut.decoded_instruction.value)
    assert (decoded >> 30) & 0b1111 == op_primary
    assert (decoded >> 27) & 0b111 == dst
    assert (decoded >> 24) & 0b111 == op_secondary
    assert (decoded >> 21) & 0b111 == src_a
    assert (decoded >> 18) & 0b111 == src_b
    assert (decoded >> 2) & 0xFFFF == immediate
    assert (decoded >> 1) & 0b1 == partialy_decoded
    assert decoded & 0b1 == is_long


@cocotb.test()
async def flat_fixed_instruction_decoding(dut: Dut) -> None:
    # Literal words from the ISA; asymmetric sources expose field swaps.
    for word, primary, dst, function, src_a, src_b in (
        (0x0000, 0, 0, 0, 0, 0),       # NOP
        (0x0A6C, 0, 5, 1, 4, 5),       # ADD R5, R4, R5
        (0x1CD7, 1, 6, 3, 7, 2),       # SGE R6, R7, R2
        (0xCC80, 12, 6, 2, 0, 0),      # POP R6
        (0xDE81, 13, 7, 2, 1, 0),      # JALR R7, SP
        (0xE64A, 14, 3, 1, 2, 1),      # FADD R3, R2, SP
    ):
        await _expect(dut, word, op_primary=primary, dst=dst,
                      op_secondary=function, src_a=src_a, src_b=src_b, immediate=0)
    await _expect(dut, 0xF5A3, op_primary=15, dst=0, op_secondary=6,
                  src_a=3, src_b=4, immediate=0xF5A3)


@cocotb.test()
async def flat_immediate_edge_case_decoding(dut: Dut) -> None:
    # Walk every instruction bit used by each immediate. Expected weights
    # come directly from the ISA's 1, 2, 4, ... sign-bit row.
    for primary, width in ((2, 5), (3, 5), (4, 8), (5, 8),
                           (6, 6), (7, 6), (8, 8), (9, 8)):
        cases = [(0, 0), (((1 << width) - 1) << (12 - width),
                          (1 << width) - 1)]
        cases += [(1 << (11 - bit), 1 << bit) for bit in range(width)]
        for encoded, value in cases:
            word = (primary << 12) | encoded | 2
            signed = value - (1 << width) if value & (1 << (width - 1)) else value
            immediate = value if primary == 5 else signed & 0xFFFF
            await _expect(dut, word, op_primary=primary, dst=2,
                          op_secondary=(word >> 6) & 7, src_a=2,
                          src_b=(word >> 3) & 7, immediate=immediate)
    # Reserved bits do not become immediate bits. Bit 3 selects LUI only.
    for word, primary, function, src_b, immediate in (
        (0x2842, 2, 1, 0, 1),
        (0x480A, 4, 0, 1, 1),
        (0x580A, 5, 0, 1, 1),
        (0x880A, 8, 0, 1, 1),
        (0x980A, 9, 0, 1, 1),
    ):
        await _expect(dut, word, op_primary=primary, dst=2,
                      op_secondary=function, src_a=2, src_b=src_b, immediate=immediate)


@cocotb.test()
async def flat_long_instruction_decoding(dut: Dut) -> None:
    for high_valid in (0, 1):
        await _expect(dut, 0xA0CC, op_primary=10, dst=0, op_secondary=3,
                      src_a=4, src_b=1, immediate=0xBEEF,
                      partialy_decoded=1-high_valid, is_long=1,
                      instruction_high=0xBEEF, high_valid=high_valid)
    await _expect(dut, 0xBA80, op_primary=11, dst=5, op_secondary=2,
                  src_a=0, src_b=0, immediate=0x1234, is_long=1,
                  instruction_high=0x1234, high_valid=1)


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_instruction_decoder",
        build_dir=SIM_BUILD,
        build_args=["-Wno-WIDTHTRUNC"],
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def instruction_decoder_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    """Run one named Cocotb coroutine as one Pytest test."""
    try:
        runner.test(
            hdl_toplevel="potados_instruction_decoder",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}",
            pytrace=False,
        )


def test_flat_fixed_instruction_decoding(instruction_decoder_runner: Runner) -> None:
    _run_cocotb_test(instruction_decoder_runner, "flat_fixed_instruction_decoding")


def test_flat_immediate_edge_case_decoding(
    instruction_decoder_runner: Runner,
) -> None:
    _run_cocotb_test(
        instruction_decoder_runner,
        "flat_immediate_edge_case_decoding",
    )


def test_flat_long_instruction_decoding(instruction_decoder_runner: Runner) -> None:
    _run_cocotb_test(instruction_decoder_runner, "flat_long_instruction_decoding")
