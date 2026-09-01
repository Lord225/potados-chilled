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
from potados_asm import assemble_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
PROGRAM_DIR = PROJECT_ROOT / "tb" / "programs"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_memory_mapped_io"

Dut = Any
Runner = Any


def _register(register_file: int, address: int) -> int:
    return (register_file >> ((7 - address) * 16)) & 0xFFFF


def _load_program(dut: Dut) -> None:
    result = assemble_file(PROGRAM_DIR / "edge_memory_mapped_io.asm")
    memory = dut.cpu.program_memory_inst.rom_inst.memory
    for address, word in result.words.items():
        memory[address].value = word


@cocotb.test()
async def cpu_reads_and_writes_a_one_cycle_mmio_peripheral(dut: Dut) -> None:
    """ST/LD must use the external bus outside the configured RAM range."""
    _load_program(dut)
    dut.clk.value = 0
    dut.reset.value = 1
    dut.peripheral_input.value = 0xBEEF
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset.value = 0

    writes: list[tuple[int, int]] = []
    reads: list[int] = []

    for _ in range(128):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if int(dut.io_write_enable.value):
            writes.append((int(dut.io_address.value), int(dut.io_write_data.value)))
        if int(dut.io_read_enable.value):
            reads.append(int(dut.io_address.value))
        if int(dut.potados_done.value):
            break
    else:
        raise AssertionError("CPU did not reach HALT within 128 cycles")

    registers = int(dut.registers_out.value)
    assert writes == [(0x8000, 0x005A)]
    assert reads == [0x8000, 0x8001]
    assert int(dut.peripheral_output.value) == 0x005A
    assert _register(registers, 0b100) == 0x005A
    assert _register(registers, 0b101) == 0xBEEF


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv", PROJECT_ROOT / "tb" / "potados_io_testbench.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_io_testbench",
        build_dir=SIM_BUILD,
        build_args=["-Wno-WIDTHTRUNC"],
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def io_runner() -> Runner:
    return _runner()


def test_cpu_reads_and_writes_a_one_cycle_mmio_peripheral(io_runner: Runner) -> None:
    try:
        io_runner.test(
            hdl_toplevel="potados_io_testbench",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter="cpu_reads_and_writes_a_one_cycle_mmio_peripheral",
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test failed with exit code {exc.code}", pytrace=False)
