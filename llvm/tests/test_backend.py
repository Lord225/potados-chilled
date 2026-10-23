"""Compile freestanding C and execute machine words in the project RTL.

Every execution uses cocotb and Verilator. Expected answers are computed
independently of LLVM, the assembler, and the hardware implementation. The
shared driver also requests LLVM's machine instruction verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from potados_asm import assemble_file


@dataclass(frozen=True)
class Program:
    name: str
    source: str
    expected: int
    runtime: bool = False


PROGRAMS = (
    Program("native_cell_layout", """
        #include <limits.h>
        #include <stddef.h>
        #include <stdint.h>
        #include <stdbool.h>
        _Static_assert(CHAR_BIT == 16, "native byte is a word");
        _Static_assert(sizeof(char) == 1, "char size");
        _Static_assert(sizeof(short) == 1, "short size");
        _Static_assert(sizeof(int) == 1, "int size");
        _Static_assert(sizeof(void *) == 1, "pointer size");
        _Static_assert(sizeof(long) == 2, "long size");
        _Static_assert(sizeof(long long) == 4, "long long size");
        struct record { unsigned char tag; uint16_t value; unsigned char end; };
        struct __attribute__((packed)) packed_record { unsigned char tag; uint16_t value; unsigned char end; };
        _Static_assert(sizeof(struct record) == 3, "native structure layout");
        _Static_assert(sizeof(struct packed_record) == 3, "packed structure layout");
        _Static_assert(offsetof(struct record, value) == 1, "native member offset");
        _Static_assert(offsetof(struct record, end) == 2, "native trailing offset");
        volatile unsigned char cells[] = {0xABCD, 0xFFFF, 0x8000};
        volatile signed char low = -32768, high = 32767;
        int main(void) {
            unsigned char local[3];
            uintptr_t address = (uintptr_t)&local[0];
            ptrdiff_t distance = &local[2] - &local[0];
            bool okay = cells[0] == 0xABCD && cells[1] == UCHAR_MAX && cells[2] == 0x8000;
            okay = okay && low < 0 && high > 0;
            okay = okay && (unsigned char *)address == local && distance == 2;
            okay = okay && (uintptr_t)&local[1] == address + 1;
            return okay ? 42 : 1;
        }
    """, 42),
    Program("arithmetic16", """
        typedef unsigned short u16;
        volatile u16 a = 0xFEDC, b = 0xBEEF;
        int main(void) { return (u16)(((u16)(a * b) + (a >> 4) - (u16)(b << 3)) ^ 0x55AA); }
    """, (((0xFEDC * 0xBEEF) + (0xFEDC >> 4) - ((0xBEEF << 3) & 0xFFFF)) ^ 0x55AA) & 0xFFFF),
    Program("comparisons", """
        typedef unsigned short u16;
        volatile short sa = -1234, sb = 321;
        volatile u16 ua = 0xFEDC, ub = 0x8123;
        int main(void) {
            u16 r = 0;
            r |= (sa < sb) << 0; r |= (sa <= sb) << 1;
            r |= (sb > sa) << 2; r |= (sb >= sa) << 3;
            r |= (sa != sb) << 4; r |= (sa == sa) << 5;
            r |= (ua > ub) << 6; r |= (ua >= ub) << 7;
            r |= (ub < ua) << 8; r |= (ub <= ua) << 9;
            return r;
        }
    """, 1023),
    Program("variable_shifts", """
        typedef unsigned short u16;
        volatile short s = -12345;
        volatile u16 u = 0xA581, amount = 5;
        int main(void) { return (u16)(s >> amount) ^ (u16)(u << amount) ^ (u >> amount); }
    """, (((-12345 >> 5) & 0xFFFF) ^ ((0xA581 << 5) & 0xFFFF) ^ (0xA581 >> 5))),
    Program("recursion", """
        typedef unsigned short u16;
        __attribute__((noinline)) u16 fib(u16 n) {
            if (n < 2) return n;
            return fib(n - 1) + fib(n - 2);
        }
        volatile u16 input = 8;
        int main(void) { return fib(input); }
    """, 21),
    Program("stack_arguments", """
        typedef unsigned short u16;
        __attribute__((noinline)) u16 sum(u16 a, u16 b, u16 c, u16 d, u16 e, u16 f, u16 g) {
            return a + b * 2 + c * 3 + d * 4 + e * 5 + f * 6 + g * 7;
        }
        volatile u16 v[] = {1, 2, 3, 4, 5, 6, 7};
        int main(void) { return sum(v[0], v[1], v[2], v[3], v[4], v[5], v[6]); }
    """, 140),
    Program("indirect_calls", """
        typedef unsigned short u16;
        __attribute__((noinline)) u16 add(u16 a, u16 b) { return a + b; }
        __attribute__((noinline)) u16 subtract(u16 a, u16 b) { return a - b; }
        __attribute__((noinline)) u16 apply(u16 (*fn)(u16, u16), u16 a, u16 b) { return fn(a, b); }
        volatile u16 select = 1;
        int main(void) { return apply(select ? add : subtract, 1234, 321); }
    """, 1555),
    Program("global_function_pointer", """
        typedef unsigned short u16;
        __attribute__((noinline)) u16 add(u16 a, u16 b) { return a + b; }
        u16 (*volatile operation)(u16, u16) = add;
        volatile u16 a = 1234, b = 321;
        int main(void) { return operation(a, b); }
    """, 1555),
    Program("four_argument_indirect", """
        typedef unsigned short u16;
        __attribute__((noinline)) u16 combine(u16 a, u16 b, u16 c, u16 d) {
            return a + 2 * b + 3 * c + 4 * d;
        }
        __attribute__((noinline)) u16 apply(u16 (*fn)(u16,u16,u16,u16), u16 a, u16 b, u16 c, u16 d) {
            return fn(a,b,c,d);
        }
        volatile u16 input = 7;
        int main(void) { return apply(combine, input, 11, 13, 17); }
    """, 7 + 2 * 11 + 3 * 13 + 4 * 17),
    Program("dotted_function_symbol", """
        typedef unsigned short u16;
        u16 helper(u16, u16) __asm__("helper.part.1");
        __attribute__((noinline)) u16 helper(u16 a, u16 b) { return a ^ b; }
        volatile u16 input = 0xA581;
        int main(void) { return helper(input, 0x55AA); }
    """, 0xA581 ^ 0x55AA),
    Program("character_array", """
        typedef unsigned short u16;
        volatile unsigned char data[] = {0x81, 0x12, 0xFF, 0x7F, 0};
        int main(void) {
            data[1] ^= 0xF0;
            u16 total = 0;
            for (u16 i = 0; i < 5; ++i) total += data[i];
            return total;
        }
    """, 737),
    Program("struct_layout", """
        typedef unsigned short u16;
        struct record { unsigned char tag; u16 value; unsigned char end; };
        volatile struct record records[] = {{1, 0x1234, 2}, {3, 0x7FED, 4}};
        int main(void) {
            records[0].value ^= records[1].value;
            return records[0].value + records[0].tag + records[0].end + records[1].tag + records[1].end;
        }
    """, (0x1234 ^ 0x7FED) + 10),
    Program("signed_characters", """
        volatile signed char data[] = {-128, -1, 127, 0};
        int main(void) {
            data[3] = -5;
            return data[0] + data[1] + data[2] + data[3];
        }
    """, (-128 - 1 + 127 - 5) & 0xFFFF),
    Program("packed_struct", """
        typedef unsigned short u16;
        struct __attribute__((packed)) record { unsigned char tag; u16 value; unsigned char end; };
        volatile struct record records[] = {{1, 0x1234, 2}, {3, 0x7FED, 4}};
        int main(void) {
            records[1].value = records[0].value + 5;
            return records[1].value + records[0].tag + records[0].end + records[1].tag + records[1].end;
        }
    """, 0x1234 + 5 + 10),
    Program("large_stack_frame", """
        typedef unsigned short u16;
        int main(void) {
            volatile u16 local[260];
            for (u16 i = 0; i < 260; ++i) local[i] = i ^ 0x55;
            return local[0] + local[129] + local[259];
        }
    """, (0 ^ 0x55) + (129 ^ 0x55) + (259 ^ 0x55)),
    Program("wide_arithmetic", """
        typedef unsigned short u16;
        volatile unsigned long a = 0x1234FFFFUL, b = 0x00FF0101UL;
        int main(void) { return (u16)((a + b) >> 16) ^ (u16)((a * b) >> 16) ^ (u16)(a >> 19); }
    """, (((0x1234FFFF + 0x00FF0101) >> 16) ^ ((0x1234FFFF * 0x00FF0101) >> 16) ^ (0x1234FFFF >> 19)) & 0xFFFF),
    Program("wide64", """
        typedef unsigned short u16;
        volatile unsigned long long a = 0xFFFF12340000ABCDULL, b = 0x00001234FFFF0001ULL;
        int main(void) { return (u16)((a + b) >> 32) ^ (u16)((a ^ b) >> 47); }
    """, (((0xFFFF12340000ABCD + 0x00001234FFFF0001) >> 32) ^ ((0xFFFF12340000ABCD ^ 0x00001234FFFF0001) >> 47)) & 0xFFFF),
    Program("division16", """
        typedef unsigned short u16;
        volatile u16 a = 0xFEDC, b = 0x8123;
        volatile short c = -12345, d = 67;
        int main(void) { return (u16)(a / b) ^ (u16)(a % b) ^ (u16)(c / d) ^ (u16)(c % d); }
    """, ((0xFEDC // 0x8123) ^ (0xFEDC % 0x8123) ^ ((-184) & 0xFFFF) ^ ((-17) & 0xFFFF)), runtime=True),
)


@pytest.mark.parametrize("opt", ["O0", "O1", "O2", "O3", "Os"])
@pytest.mark.parametrize("program", PROGRAMS, ids=lambda program: program.name)
def test_compiled_program_behavior(
    compile_program: Callable[..., Path], tmp_path: Path, program: Program, opt: str,
) -> None:
    from potados_emulator import CPU

    output = compile_program(program.source, tmp_path, opt=opt, runtime=program.runtime, name=program.name)
    assembly = assemble_file(output)
    with CPU(assembly) as cpu:
        cpu.run(max_cycles=4_000_000)
        assert cpu.halted
        assert cpu.registers[2] == program.expected & 0xFFFF, (
            f"{program.name} -{opt}: R2=0x{cpu.registers[2]:04X}, expected 0x{program.expected & 0xFFFF:04X}; assembly: {output}"
        )
        assert cpu.registers[1] == 0x7F00, f"Stack pointer was not restored: {output}"
