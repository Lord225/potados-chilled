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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_registers"

Dut = Any
Runner = Any


async def _clock_cycle(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def _reset(dut: Dut) -> None:
    dut.reset.value = 1
    dut.read_request.value = 0
    dut.write_request.value = 0
    dut.stack_pointer_request.value = 0
    await _clock_cycle(dut)
    dut.reset.value = 0
    assert _stack_pointer(dut) == 0x0000


async def _set_stack_pointer(dut: Dut, value: int) -> None:
    # stack_pointer_request_t = {write_data[15:0], operation[1:0]}.
    dut.stack_pointer_request.value = ((value & 0xFFFF) << 2) | 0b01
    await _clock_cycle(dut)
    dut.stack_pointer_request.value = 0
    assert _stack_pointer(dut) == value


def _stack_pointer(dut: Dut) -> int:
    # register_read_response_t = {data_a, data_b, stack_pointer, decremented}.
    return (int(dut.read_response.value) >> 16) & 0xFFFF


def _decremented_stack_pointer(dut: Dut) -> int:
    return int(dut.read_response.value) & 0xFFFF


@cocotb.test()
async def push_reads_current_sp_then_increments_on_clock(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _set_stack_pointer(dut, 0x0123)

    # RAM uses this current value as the PUSH store address before the edge.
    dut.stack_pointer_request.value = 0b10
    await Timer(1, unit="ns")
    assert _stack_pointer(dut) == 0x0123

    await _clock_cycle(dut)
    dut.stack_pointer_request.value = 0
    assert _stack_pointer(dut) == 0x0124


@cocotb.test()
async def pop_returns_decremented_sp_before_clock_and_commits_on_clock(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)
    await _set_stack_pointer(dut, 0x0123)

    # RAM uses the combinational decremented value as the POP load address.
    dut.stack_pointer_request.value = 0b11
    await Timer(1, unit="ns")
    assert _stack_pointer(dut) == 0x0123
    assert _decremented_stack_pointer(dut) == 0x0122

    await _clock_cycle(dut)
    dut.stack_pointer_request.value = 0
    assert _stack_pointer(dut) == 0x0122

    # Stack-pointer arithmetic wraps as 16-bit unsigned arithmetic.
    await _set_stack_pointer(dut, 0x0000)
    assert _decremented_stack_pointer(dut) == 0xFFFF
    dut.stack_pointer_request.value = 0b11
    await _clock_cycle(dut)
    dut.stack_pointer_request.value = 0
    assert _stack_pointer(dut) == 0xFFFF

    dut.stack_pointer_request.value = 0b10
    await _clock_cycle(dut)
    dut.stack_pointer_request.value = 0
    assert _stack_pointer(dut) == 0x0000


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados_registers.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_registers",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def registers_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_registers",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False)


def test_push_reads_current_sp_then_increments_on_clock(registers_runner: Runner) -> None:
    _run_cocotb_test(registers_runner, "push_reads_current_sp_then_increments_on_clock")


def test_pop_returns_decremented_sp_before_clock_and_commits_on_clock(
    registers_runner: Runner,
) -> None:
    _run_cocotb_test(
        registers_runner,
        "pop_returns_decremented_sp_before_clock_and_commits_on_clock",
    )
