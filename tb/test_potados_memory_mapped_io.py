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
VERILATOR_X_ASSIGN_MODE = os.getenv("VERILATOR_X_ASSIGN_MODE", "unique")
VERILATOR_X_INITIAL_MODE = os.getenv("VERILATOR_X_INITIAL_MODE", "unique")

Dut = Any
Runner = Any


def _register(register_file: int, address: int) -> int:
    return (register_file >> ((7 - address) * 16)) & 0xFFFF


def _load_program(dut: Dut) -> None:
    result = assemble_file(PROGRAM_DIR / "edge_memory_mapped_io.asm")
    memory = dut.cpu.program_memory_inst.rom_inst.memory
    for address, word in result.words.items():
        memory[address].value = word


def _load_program_file(dut: Dut, filename: str) -> None:
    result = assemble_file(PROGRAM_DIR / filename)
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


@cocotb.test()
async def ram_values_are_loaded_then_written_to_led_mmio(dut: Dut) -> None:
    """A load-use dependency must preserve every RAM value on the IO bus."""
    _load_program_file(dut, "ram_to_led_mmio.asm")
    dut.clk.value = 0
    dut.reset.value = 1
    dut.peripheral_input.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset.value = 0

    writes: list[tuple[int, int]] = []
    for _ in range(4096):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if int(dut.io_write_enable.value):
            writes.append((int(dut.io_address.value), int(dut.io_write_data.value)))
        if int(dut.potados_done.value):
            break
    else:
        raise AssertionError("RAM-to-MMIO program did not reach HALT")

    ram = dut.cpu.potados_memory.ram_inst.memory
    expected = [0, 100, 148, 200, 255, 32]
    assert [int(ram[index].value) for index in range(6)] == expected
    assert writes == [(0x8000 + index, value) for index, value in enumerate(expected)]


@cocotb.test()
async def ram_to_mmio_copy_preserves_zero_one_bit_patterns_and_random_words(dut: Dut) -> None:
    """Every 16-bit RAM pattern must appear unchanged on its MMIO write."""
    _load_program_file(dut, "ram_to_led_mmio_copy.asm")
    dut.clk.value = 0
    dut.peripheral_input.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    patterns = {
        "all zero": [0x0000] * 6,
        "all one": [0xFFFF] * 6,
        "bit edges": [0x0001, 0x8000, 0x7FFF, 0x00FF, 0xFF00, 0xFFFF],
        "alternating": [0xAAAA, 0x5555, 0xAAAA, 0x5555, 0xAAAA, 0x5555],
        "deterministic random": [0x4A3D, 0xC017, 0x0081, 0x7E42, 0xBEEF, 0x1234],
    }
    ram = dut.cpu.potados_memory.ram_inst.memory

    for name, expected in patterns.items():
        dut.reset.value = 1
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        for address, value in enumerate(expected):
            ram[address].value = value

        dut.reset.value = 0
        writes: list[tuple[int, int]] = []
        for _ in range(4096):
            await RisingEdge(dut.clk)
            await Timer(1, unit="ns")
            if int(dut.io_write_enable.value):
                writes.append((int(dut.io_address.value), int(dut.io_write_data.value)))
            if int(dut.potados_done.value):
                break
        else:
            raise AssertionError(f"{name}: copy program did not reach HALT")

        assert writes == [(0x8000 + index, value) for index, value in enumerate(expected)], name


def _runner() -> Runner:
    if VERILATOR_X_ASSIGN_MODE not in {"0", "1", "fast", "unique"}:
        raise ValueError("VERILATOR_X_ASSIGN_MODE must be 0, 1, fast, or unique")
    if VERILATOR_X_INITIAL_MODE not in {"0", "fast", "unique"}:
        raise ValueError("VERILATOR_X_INITIAL_MODE must be 0, fast, or unique")

    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv", PROJECT_ROOT / "tb" / "potados_io_testbench.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_io_testbench",
        build_dir=SIM_BUILD,
        build_args=[
            "-Wno-WIDTHTRUNC",
            "--x-assign",
            VERILATOR_X_ASSIGN_MODE,
            "--x-initial",
            VERILATOR_X_INITIAL_MODE,
        ],
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


def test_ram_values_are_loaded_then_written_to_led_mmio(io_runner: Runner) -> None:
    try:
        io_runner.test(
            hdl_toplevel="potados_io_testbench",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter="ram_values_are_loaded_then_written_to_led_mmio",
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test failed with exit code {exc.code}", pytrace=False)


def test_ram_to_mmio_copy_preserves_zero_one_bit_patterns_and_random_words(
    io_runner: Runner,
) -> None:
    try:
        io_runner.test(
            hdl_toplevel="potados_io_testbench",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter="ram_to_mmio_copy_preserves_zero_one_bit_patterns_and_random_words",
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test failed with exit code {exc.code}", pytrace=False)
