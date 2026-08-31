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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_writeback_stage"

Dut = Any
Runner = Any

WB_NONE = 0
WB_ALU = 1
WB_MEMORY = 2
WB_RETURN_ADDRESS = 4

STACK_POINTER_NONE = 0
STACK_POINTER_INCREMENT = 2
STACK_POINTER_DECREMENT = 3


def _writeback_stage(
    *,
    valid: int = 1,
    alu_result: int = 0,
    fpu_result: int = 0,
    next_pc: int = 0,
    destination: int = 0,
    stack_pointer_operation: int = STACK_POINTER_NONE,
    writeback_source: int = WB_NONE,
) -> int:
    """Pack writeback_stage_t in its SystemVerilog declaration order."""
    return (
        ((valid & 1) << 56)
        | ((alu_result & 0xFFFF) << 40)
        | ((fpu_result & 0xFFFF) << 24)
        | ((next_pc & 0xFFFF) << 8)
        | ((destination & 0b111) << 5)
        | ((stack_pointer_operation & 0b11) << 3)
        | (writeback_source & 0b111)
    )


def _register_write(dut: Dut) -> tuple[int, int, int]:
    request = int(dut.register_write_request.value)
    return (request >> 19) & 1, (request >> 16) & 0b111, request & 0xFFFF


def _stack_operation(dut: Dut) -> int:
    return int(dut.stack_pointer_request.value) & 0b11


async def _drive(dut: Dut, packet: int, *, ram_load_data: int = 0) -> None:
    dut.writeback_stage.value = packet
    dut.ram_load_data.value = ram_load_data
    await Timer(1, unit="ns")
    assert int(dut.writeback_declare_stall.value) == 0


@cocotb.test()
async def invalid_packet_has_no_architectural_side_effects(dut: Dut) -> None:
    """Garbage metadata in a bubble must not write a register or update SP."""
    await _drive(
        dut,
        _writeback_stage(
            valid=0,
            alu_result=0xCAFE,
            destination=5,
            stack_pointer_operation=STACK_POINTER_INCREMENT,
            writeback_source=WB_ALU,
        ),
    )

    write_enable, write_address, write_data = _register_write(dut)
    assert write_enable == 0
    assert write_address == 5
    assert write_data == 0xCAFE
    assert _stack_operation(dut) == STACK_POINTER_NONE


@cocotb.test()
async def writeback_selects_each_implemented_result_source(dut: Dut) -> None:
    await _drive(
        dut,
        _writeback_stage(
            alu_result=0x1234, destination=2, writeback_source=WB_ALU
        ),
        ram_load_data=0xBEEF,
    )
    assert _register_write(dut) == (1, 2, 0x1234)

    await _drive(
        dut,
        _writeback_stage(destination=3, writeback_source=WB_MEMORY),
        ram_load_data=0xBEEF,
    )
    assert _register_write(dut) == (1, 3, 0xBEEF)

    await _drive(
        dut,
        _writeback_stage(
            next_pc=0x4567,
            destination=7,
            writeback_source=WB_RETURN_ADDRESS,
        ),
    )
    assert _register_write(dut) == (1, 7, 0x4567)

    await _drive(dut, _writeback_stage(writeback_source=WB_NONE))
    assert _register_write(dut)[0] == 0


@cocotb.test()
async def valid_stack_operations_reach_the_register_file(dut: Dut) -> None:
    await _drive(
        dut,
        _writeback_stage(stack_pointer_operation=STACK_POINTER_INCREMENT),
    )
    assert _stack_operation(dut) == STACK_POINTER_INCREMENT

    await _drive(
        dut,
        _writeback_stage(stack_pointer_operation=STACK_POINTER_DECREMENT),
    )
    assert _stack_operation(dut) == STACK_POINTER_DECREMENT


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_writeback_stage",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def writeback_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_writeback_stage",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False
        )


def test_invalid_packet_has_no_architectural_side_effects(
    writeback_runner: Runner,
) -> None:
    _run_cocotb_test(writeback_runner, "invalid_packet_has_no_architectural_side_effects")


def test_writeback_selects_each_implemented_result_source(
    writeback_runner: Runner,
) -> None:
    _run_cocotb_test(writeback_runner, "writeback_selects_each_implemented_result_source")


def test_valid_stack_operations_reach_the_register_file(
    writeback_runner: Runner,
) -> None:
    _run_cocotb_test(writeback_runner, "valid_stack_operations_reach_the_register_file")
