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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_scoreboard"

Dut = Any
Runner = Any


async def _clock_cycle(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def _reset(dut: Dut) -> None:
    dut.reset.value = 1
    dut.reserve_write_mask.value = 0
    dut.release_write_mask.value = 0
    await _clock_cycle(dut)
    dut.reset.value = 0
    assert int(dut.register_status.value) == 0


@cocotb.test()
async def reserve_and_release_masks_track_in_flight_writes(dut: Dut) -> None:
    """Reservations win over releases for the same architectural register."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    dut.reserve_write_mask.value = 0b0000_0100  # R2
    await _clock_cycle(dut)
    assert int(dut.register_status.value) == 0b0000_0100

    # The retiring R2 write and a newer R2 issue overlap: keep R2 pending.
    dut.release_write_mask.value = 0b0000_0100
    await _clock_cycle(dut)
    assert int(dut.register_status.value) == 0b0000_0100

    # Release R2 while reserving R3 in the same cycle.
    dut.reserve_write_mask.value = 0b0000_1000
    await _clock_cycle(dut)
    assert int(dut.register_status.value) == 0b0000_1000

    dut.reserve_write_mask.value = 0
    dut.release_write_mask.value = 0b0000_1000
    await _clock_cycle(dut)
    assert int(dut.register_status.value) == 0

    # ZERO must never become pending, even if a bad upstream mask requests it.
    dut.reserve_write_mask.value = 0b0000_0001
    await _clock_cycle(dut)
    assert int(dut.register_status.value) == 0


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados_scoreboard.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_scoreboard",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def scoreboard_runner() -> Runner:
    return _runner()


def test_reserve_and_release_masks_track_in_flight_writes(
    scoreboard_runner: Runner,
) -> None:
    try:
        scoreboard_runner.test(
            hdl_toplevel="potados_scoreboard",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter="reserve_and_release_masks_track_in_flight_writes",
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb scoreboard test failed with exit code {exc.code}", pytrace=False)
