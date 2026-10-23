"""Full-width checks for compiled arithmetic runtime and packed memory helpers."""
from __future__ import annotations

from pathlib import Path
import random
from typing import Callable

import pytest

from potados_asm import AssemblyResult, assemble_file
from potados_emulator import CPU

MASK64 = (1 << 64) - 1


def read_u64(cpu: CPU, program: AssemblyResult, name: str, index: int = 0) -> int:
    """Reconstruct all 64 result bits from physical little-endian RAM words."""
    address = program.symbols[name] // 2 + index * 4
    ram = cpu.ram
    return sum(ram[address + word] << (16 * word) for word in range(4))


def read_bytes(cpu: CPU, program: AssemblyResult, name: str, count: int) -> list[int]:
    base = program.symbols[name]
    ram = cpu.ram
    return [(ram[(base + index) // 2] >> (8 * ((base + index) & 1))) & 255 for index in range(count)]


def signed64(value: int) -> int:
    return value - (1 << 64) if value & (1 << 63) else value


def c_i64(value: int) -> str:
    if value == -(1 << 63):
        return "(-9223372036854775807LL - 1)"
    return f"({value}LL)"


@pytest.mark.parametrize("opt", ["O0", "O2"])
def test_compiled_64bit_division_preserves_every_result_word(
    compile_program: Callable[..., Path], tmp_path: Path, opt: str,
) -> None:
    rng = random.Random(0x506F7461)
    unsigned_cases = [
        (0, 1), (1, 1), (MASK64, 1), (MASK64, MASK64), (1, MASK64),
        (MASK64, 2), (1 << 63, 3),
        (0xFEDCBA9876543210, 0x8123456789ABCDEF),
        *((rng.getrandbits(64), rng.getrandbits(64) or 1) for _ in range(5)),
    ]
    signed_cases = [
        (-(1 << 63), 1), (-(1 << 63), 3), ((1 << 63) - 1, -3),
        (-0x123456789ABCDEF, 0x13579BDF),
        (0x123456789ABCDEF, -0x13579BDF),
        (-0x123456789ABCDEF, -0x13579BDF), (0, -1), (1, -(1 << 63)),
        *((signed64(rng.getrandbits(64)), signed64(rng.getrandbits(64)) or 1) for _ in range(5)),
    ]
    assert len(unsigned_cases) == len(signed_cases)
    count = len(unsigned_cases)
    unsigned_a = ",".join(f"{a}ULL" for a, _ in unsigned_cases)
    unsigned_b = ",".join(f"{b}ULL" for _, b in unsigned_cases)
    signed_a = ",".join(c_i64(a) for a, _ in signed_cases)
    signed_b = ",".join(c_i64(b) for _, b in signed_cases)
    source = f"""
        typedef unsigned long long u64;
        typedef long long i64;
        volatile u64 unsigned_a[] = {{{unsigned_a}}};
        volatile u64 unsigned_b[] = {{{unsigned_b}}};
        volatile i64 signed_a[] = {{{signed_a}}};
        volatile i64 signed_b[] = {{{signed_b}}};
        volatile u64 unsigned_q[{count}], unsigned_r[{count}];
        volatile i64 signed_q[{count}], signed_r[{count}];
        int main(void) {{
            for (unsigned short i = 0; i < {count}; ++i) {{
                unsigned_q[i] = unsigned_a[i] / unsigned_b[i];
                unsigned_r[i] = unsigned_a[i] % unsigned_b[i];
                signed_q[i] = signed_a[i] / signed_b[i];
                signed_r[i] = signed_a[i] % signed_b[i];
            }}
            return 42;
        }}
    """
    output = compile_program(source, tmp_path, opt=opt, runtime=True, name="runtime_div64")
    program = assemble_file(output)
    with CPU(program) as cpu:
        cpu.run(max_cycles=12_000_000)
        for index, (a, b) in enumerate(unsigned_cases):
            assert read_u64(cpu, program, "unsigned_q", index) == a // b, (opt, index, "unsigned quotient")
            assert read_u64(cpu, program, "unsigned_r", index) == a % b, (opt, index, "unsigned remainder")
        for index, (a, b) in enumerate(signed_cases):
            quotient = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                quotient = -quotient
            remainder = a - quotient * b
            assert read_u64(cpu, program, "signed_q", index) == quotient & MASK64, (opt, index, "signed quotient")
            assert read_u64(cpu, program, "signed_r", index) == remainder & MASK64, (opt, index, "signed remainder")
        assert cpu.registers[2] == 42
        assert cpu.registers[1] == 0x7F00


@pytest.mark.parametrize("opt", ["O0", "O2"])
def test_compiled_variable_wide_shifts_and_wide_return_abi(
    compile_program: Callable[..., Path], tmp_path: Path, opt: str,
) -> None:
    amounts = [0, 1, 15, 16, 17, 31, 32, 33, 47, 48, 49, 63]
    value = 0xFEDCBA9876543210
    other = 0x8123456789ABCDEF
    source = f"""
        typedef unsigned long long u64;
        typedef long long i64;
        volatile u64 input = {value}ULL;
        volatile u64 other = {other}ULL;
        volatile unsigned short amounts[] = {{{','.join(map(str, amounts))}}};
        volatile u64 left[{len(amounts)}], right[{len(amounts)}];
        volatile i64 arithmetic[{len(amounts)}];
        volatile u64 returned;
        __attribute__((noinline)) u64 transform(u64 a, u64 b) {{
            return (a ^ (b << 31)) + (a >> 17);
        }}
        int main(void) {{
            for (unsigned short i = 0; i < {len(amounts)}; ++i) {{
                left[i] = input << amounts[i];
                right[i] = input >> amounts[i];
                arithmetic[i] = ((i64)input) >> amounts[i];
            }}
            returned = transform(input, other);
            return 42;
        }}
    """
    output = compile_program(source, tmp_path, opt=opt, name="wide_shifts_and_return")
    program = assemble_file(output)
    with CPU(program) as cpu:
        cpu.run(max_cycles=4_000_000)
        for index, amount in enumerate(amounts):
            assert read_u64(cpu, program, "left", index) == (value << amount) & MASK64, (opt, amount, "left")
            assert read_u64(cpu, program, "right", index) == value >> amount, (opt, amount, "right")
            assert read_u64(cpu, program, "arithmetic", index) == (signed64(value) >> amount) & MASK64, (opt, amount, "arithmetic")
        expected_return = ((value ^ ((other << 31) & MASK64)) + (value >> 17)) & MASK64
        assert read_u64(cpu, program, "returned") == expected_return
        assert cpu.registers[2] == 42
        assert cpu.registers[1] == 0x7F00


@pytest.mark.parametrize("opt", ["O0", "O2"])
def test_compiled_memory_helpers_preserve_packed_neighbors_and_overlap(
    compile_program: Callable[..., Path], tmp_path: Path, opt: str,
) -> None:
    source = """
        void *memcpy(void *, const void *, unsigned short);
        void *memmove(void *, const void *, unsigned short);
        void *memset(void *, int, unsigned short);
        unsigned char source[] = {0x81,0x02,0xFE,0x7F,0x55,0xAA,1,2,3,4,5,6};
        unsigned char result[24];
        volatile unsigned short count = 12;
        volatile unsigned short pointer_results;
        int main(void) {
            unsigned short same = 0;
            same |= (memset(result, 0x1234, 24) == result) << 0;
            same |= (memcpy(result+1, source, count) == result+1) << 1;
            same |= (memmove(result+3, result+1, count) == result+3) << 2;
            same |= (memmove(result+1, result+3, count) == result+1) << 3;
            same |= (memset(result+5, -1, 3) == result+5) << 4;
            same |= (memcpy(result, source, 0) == result) << 5;
            same |= (memmove(result+1, result+1, count) == result+1) << 6;
            pointer_results = same;
            return 42;
        }
    """
    expected = [0x34] * 24
    initial = [0x81, 0x02, 0xFE, 0x7F, 0x55, 0xAA, 1, 2, 3, 4, 5, 6]
    expected[1:13] = initial
    expected[3:15] = expected[1:13]
    expected[1:13] = expected[3:15]
    expected[5:8] = [0xFF] * 3
    output = compile_program(source, tmp_path, opt=opt, runtime=True, name="memory_helpers")
    program = assemble_file(output)
    with CPU(program) as cpu:
        cpu.run(max_cycles=4_000_000)
        assert read_bytes(cpu, program, "result", 24) == expected
        pointer_address = program.symbols["pointer_results"] // 2
        assert cpu.ram[pointer_address] == 0x7F
        assert cpu.registers[2] == 42
        assert cpu.registers[1] == 0x7F00
