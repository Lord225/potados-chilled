"""Compiler output executes in the cocotb/Verilator wrapper of potados.sv.

Expected values are independent Python calculations. The trace assertions inspect
real fetch, execute, writeback, and memory signals rather than another CPU model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from potados_asm import assemble_file
from potados_emulator import CPU


RTL_PROGRAMS = (
    ("multiply_and_shift", """
        typedef unsigned short u16;
        volatile u16 a=0xFEDC, b=0xBEEF, shift=5;
        int main(void) { return (u16)(a*b) ^ (u16)(a << shift) ^ (b >> shift); }
    """, ((0xFEDC * 0xBEEF) ^ (0xFEDC << 5) ^ (0xBEEF >> 5)) & 0xFFFF),
    ("characters_and_calls", """
        typedef unsigned short u16;
        volatile unsigned char values[]={0x81,0x12,0xFF,0x7F};
        __attribute__((noinline)) u16 sum(u16 n) {
            if (!n) return 0;
            return values[n-1] + sum(n-1);
        }
        int main(void) { values[1] ^= 0xF0; return sum(4); }
    """, 0x81 + (0x12 ^ 0xF0) + 0xFF + 0x7F),
    ("stack_arguments", """
        typedef unsigned short u16;
        volatile u16 n=3;
        __attribute__((noinline)) u16 many(u16 a,u16 b,u16 c,u16 d,u16 e,u16 f) {
            volatile u16 local[150]; local[0]=a+b; local[149]=e+f;
            return local[0]+local[149]+c+d;
        }
        int main(void) { return many(n,5,7,11,13,17); }
    """, 56),
)


@pytest.mark.parametrize(("name", "source", "expected"), RTL_PROGRAMS,
                         ids=[item[0] for item in RTL_PROGRAMS])
def test_compiled_program_on_rtl(
    compile_program: Callable[..., Path], tmp_path: Path,
    name: str, source: str, expected: int,
) -> None:
    output = compile_program(source, tmp_path, opt="O2", name=name)
    program = assemble_file(output)
    records = []
    with CPU(program) as cpu:
        cpu.run(max_cycles=200_000, trace=records.append)
        assert cpu.halted
        assert cpu.registers[2] == expected
        assert cpu.registers[1] == 0x7F00
        assert cpu.cycles > 0 and records
        assert any(event.fetch_accepted for event in records)
        assert any(event.execute_valid for event in records)
        assert any(event.register_writes for event in records)
        writes = [write for event in records for write in event.memory_writes if not write.io]
        assert writes, "Startup and stack stores must be visible on the real RAM interface"
        if name == "multiply_and_shift":
            assert any(event.fetch_accepted and (event.fetch_low & 0xF1C0) == 0x01C0
                       for event in records), "Expanded multiplication should execute native MUL"
        elif name == "characters_and_calls":
            word_address = program.symbols["values"]
            assert list(cpu.ram[word_address:word_address + 4]) == [0x81, 0xE2, 0xFF, 0x7F]
            assert any(write.address == word_address + 1 and write.value == 0xE2 for write in writes)
            assert any(write.address >= 0x7E00 for write in writes), "Recursive calls must save real stack state"
        else:
            stack_addresses = {write.address for write in writes if write.address >= 0x7000}
            assert len(stack_addresses) >= 4, "Outgoing arguments, locals, and links must reach physical RAM"


@pytest.mark.parametrize("opt", ["O0", "O1", "O2", "O3", "Os"])
def test_native_c_pointer_mmio_addresses_reach_the_real_bus(
    compile_program: Callable[..., Path], tmp_path: Path, opt: str,
) -> None:
    source = """
        _Static_assert(sizeof(char) == 1, "native C byte");
        _Static_assert(sizeof(int) == 1, "16-bit int");
        _Static_assert(sizeof(void *) == 1, "16-bit pointer");
        _Static_assert(__CHAR_BIT__ == 16, "16-bit char");
        int main(void) {
            volatile int *io = (volatile int *)0x8000;
            io[0] = 42;
            io[1] = 99;
            return io[0] == 42 && io[1] == 99 && (unsigned short)&io[1] == 0x8001;
        }
    """
    output = compile_program(source, tmp_path, opt=opt, name="direct_pointer_mmio")
    records = []
    with CPU(assemble_file(output)) as cpu:
        cpu.run(max_cycles=200_000, trace=records.append)
        assert cpu.halted and cpu.registers[2] == 1
        assert cpu.registers[1] == 0x7F00
        assert cpu.io_writes == [(0x8000, 42), (0x8001, 99)]
        reads = {(read.address, read.value) for event in records
                 for read in event.memory_reads if read.io}
        assert {(0x8000, 42), (0x8001, 99)} <= reads


@pytest.mark.parametrize("opt", ["O0", "O2", "Oz"])
def test_native_pointer_parity_is_not_inferred_from_llvm_storage_alignment(
    compile_program: Callable[..., Path], tmp_path: Path, opt: str,
) -> None:
    source = """
        volatile unsigned int head = 42;
        volatile unsigned int tail = 99;
        int main(void) { return (unsigned int)&tail & 1; }
    """
    output = compile_program(source, tmp_path, opt=opt, name="native_pointer_parity")
    program = assemble_file(output)
    assert program.symbols["tail"] == program.symbols["head"] + 1
    assert program.symbols["tail"] & 1, "The regression requires an odd native address"
    with CPU(program) as cpu:
        cpu.run(max_cycles=1000)
        assert cpu.registers[2] == program.symbols["tail"] & 1
        assert cpu.ram[program.symbols["head"]] == 42
        assert cpu.ram[program.symbols["tail"]] == 99
