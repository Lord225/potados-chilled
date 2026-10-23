from __future__ import annotations

from pathlib import Path

import pytest

from potados_asm import AssemblerError, assemble, assemble_file
from potados_asm.cli import run


ASM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ASM_ROOT.parent
PROGRAM_DIR = PROJECT_ROOT / "tb" / "programs"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("NOP", [0x0000]),
        ("ADD R4, R2, R3", [0x085A]),
        ("SUB R4, R2, R3", [0x089A]),
        ("AND R4, R2, R3", [0x08DA]),
        ("OR R4, R2, R3", [0x091A]),
        ("XOR R4, R2, R3", [0x095A]),
        ("NOT R4, R3", [0x0983]),
        ("MUL R4, R2, R3", [0x09DA]),
        ("SGE R4, R2, R3", [0x18DA]),
        ("SL R4, R2, R3", [0x189A]),
        ("SE R4, R2, R3", [0x195A]),
        ("SNE R4, R2, R3", [0x191A]),
        ("SAE R4, R2, R3", [0x199A]),
        ("SB R4, R2, R3", [0x19DA]),
        ("SH R2, R2, -1", [0x2F92]),
        ("ASH R2, R2, 1", [0x3812]),
        ("ADDI R3, -1", [0x4FF3]),
        ("LLI R2, 0xA5", [0x5A52]),
        ("LUI R2, 0xA5", [0x5A5A]),
        ("LI R2, 0xA5", [0x5A52]),
        ("LI R2, 0x1234", [0x548A, 0x42C2]),
        ("LI R2, -1", [0x500A, 0x4FF2]),
        ("LEA R2, 0xA5", [0x5A52]),
        ("MOV R4, R2", [0x0842]),
        ("CLR R2", [0x5002]),
        ("INC R2", [0x4802]),
        ("DEC R2", [0x4FF2]),
        ("NEG R4, R2", [0x0890]),
        ("NEG R2", [0x0490]),
        ("ADD R4, R2", [0x0854]),
        ("LD R4, [ R2 + 1 ]", [0x6814]),
        ("LD R4, R2", [0x6014]),
        ("LD R4, [R2 - 1]", [0x6FD4]),
        ("ST R3, [ R2 + 1 ]", [0x7813]),
        ("ST R3, R2", [0x7013]),
        ("ST R3, [R2 - 1]", [0x7FD3]),
        ("LDSP R4, -1", [0x8FF4]),
        ("STSP R3, 1", [0x9803]),
        ("JGE R2, R3, 0x1234", [0xA0DA, 0x1234]),
        ("JL R2, R3, 0x1234", [0xA09A, 0x1234]),
        ("JE R2, R3, 0x1234", [0xA15A, 0x1234]),
        ("JNE R2, R3, 0x1234", [0xA11A, 0x1234]),
        ("JAE R2, R3, 0x1234", [0xA19A, 0x1234]),
        ("JB R2, R3, 0x1234", [0xA1DA, 0x1234]),
        ("JMP 0x1234", [0xB040, 0x1234]),
        ("J 0x1234", [0xB040, 0x1234]),
        ("JAL R5, 0x1234", [0xBA80, 0x1234]),
        ("CALL 0x1234", [0xBE80, 0x1234]),
        ("PUSH R2", [0xC042]),
        ("POP R3", [0xC680]),
        ("JMPR R2", [0xD042]),
        ("RET", [0xD047]),
        ("JALR R5, R2", [0xDA82]),
        ("FADD R4, R2, R3", [0xE85A]),
        ("FSUB R4, R2, R3", [0xE89A]),
        ("FMUL R4, R2, R3", [0xE8DA]),
        ("FDIV R4, R2, R3", [0xE91A]),
        ("ITOF R4, R3", [0xE943]),
        ("FTOI R4, R3", [0xE983]),
        ("FTOU R4, R3", [0xE9C3]),
        ("HALT", [0xF000]),
    ],
)
def test_instruction_golden_encodings(source: str, expected: list[int]) -> None:
    result = assemble(source, filename="golden.asm")
    assert result.dense_words() == expected


def test_regular_register_fields_are_visible_in_the_encoded_word() -> None:
    word = assemble("SUB R4, R2, R3", filename="fields.asm").dense_words()[0]

    assert (word >> 12) & 0b1111 == 0b0000  # primary opcode: integer ALU
    assert (word >> 9) & 0b111 == 0b100     # destination: R4
    assert (word >> 6) & 0b111 == 0b010     # function: SUB
    assert word & 0b111 == 0b010            # source A: R2
    assert (word >> 3) & 0b111 == 0b011      # source B: R3


def test_irregular_immediate_fields_are_encoded_explicitly() -> None:
    shift = assemble("SH R2, R3, -1", filename="fields.asm").dense_words()[0]
    assert (shift >> 12) & 0b1111 == 0b0010
    assert (shift >> 6) & 1 == 0            # reserved bit
    assert (shift >> 7) & 0b1_1111 == 0b1_1111  # signed IMM5: -1
    assert (shift >> 3) & 0b111 == 0b011     # shift amount register: R3
    assert shift & 0b111 == 0b010            # source/destination: R2

    addi = assemble("ADDI R3, -1", filename="fields.asm").dense_words()[0]
    assert (addi >> 4) & 0xFF == 0xFF        # IMM8: -1
    assert (addi >> 3) & 1 == 0              # reserved bit
    assert addi & 0b111 == 0b011             # source/destination: R3

    lui = assemble("LUI R2, 0xA5", filename="fields.asm").dense_words()[0]
    assert (lui >> 4) & 0xFF == 0xA5         # bit-reversed byte (A5 is symmetric)
    assert (lui >> 3) & 1 == 1               # upper-byte selector
    assert lui & 0b111 == 0b010              # destination: R2


def test_long_jump_encodes_the_target_as_a_separate_word() -> None:
    instruction, target = assemble(
        "JAL R5, 0x1234", filename="fields.asm"
    ).dense_words()

    assert (instruction >> 12) & 0b1111 == 0b1011
    assert (instruction >> 6) & 0b111 == 0b010  # JAL function
    assert (instruction >> 9) & 0b111 == 0b101  # link destination: R5
    assert instruction & 0x3F == 0
    assert target == 0x1234


def test_long_jumps_and_labels_use_word_addresses() -> None:
    result = assemble(
        """
        start: JNE R2, R3, target
               JMP start
        target: JAL R7, start
                HALT
        """,
        filename="jumps.asm",
    )
    assert result.symbols == {"start": 0, "target": 4}
    assert result.dense_words() == [
        0xA11A, 0x0004,
        0xB040, 0x0000,
        0xBE80, 0x0000,
        0xF000,
    ]


def test_symbolic_li_uses_the_long_form_to_keep_forward_labels_stable() -> None:
    result = assemble(
        """
        LI R2, target
        J target
        target: HALT
        """,
        filename="li-label.asm",
    )

    # The target has a byte-sized address, but symbolic LI deliberately remains
    # two words so a forward reference cannot change later label addresses.
    assert result.symbols == {"target": 4}
    assert result.dense_words() == [0x500A, 0x4202, 0xB040, 0x0004, 0xF000]


def test_comments_sections_data_and_expressions() -> None:
    result = assemble(
        r'''
        .equ OFFSET, 2
        .section vectors, 0x0002
        start: .word 0x1234

        .org 0x0010
        data: .string "A#;", "\n" ; comment after quoted comment markers
              .byte %lo(start + OFFSET)
              JMP start
        ''',
        filename="sections.asm",
    )
    assert result.symbols == {"OFFSET": 2, "vectors": 2, "start": 2, "data": 0x10}
    assert result.words == {
        0x0002: 0x1234,
        0x0010: ord("A"),
        0x0011: ord("#"),
        0x0012: ord(";"),
        0x0013: ord("\n"),
        0x0014: 0x0004,
        0x0015: 0xB040,
        0x0016: 0x0002,
    }


def test_all_output_formats() -> None:
    result = assemble(".org 1\nvalue: .word 0xABCD\n", filename="formats.asm")
    assert result.to_hex() == "@0001\nABCD\n"
    assert result.to_bytecode() == "0x00 0x00\n0xAB 0xCD\n"
    assert result.to_binary() == bytes.fromhex("0000 ABCD")
    annotated = result.to_hex(annotated=True)
    assert "ABCD  // 0001: value: .word 0xABCD" in annotated


def test_cli_writes_requested_format(tmp_path: Path) -> None:
    source = tmp_path / "program.asm"
    output = tmp_path / "program.hex"
    source.write_text("LLI R2, 7\nHALT\n", encoding="utf-8")
    assert run([str(source), "-o", str(output), "--format", "hex-comments"]) == 0
    text = output.read_text(encoding="utf-8")
    assert "5E02  // 0000: LLI R2, 7" in text
    assert "F000  // 0001: HALT" in text


def test_example_assembles_to_the_cpu_regression_rom() -> None:
    example = ASM_ROOT / "examples" / "multiply_accumulate.asm"
    regression_program = PROJECT_ROOT / "tb" / "programs" / "multiply_accumulate_then_halt.asm"
    result = assemble(example.read_text(encoding="utf-8"), filename=str(example))
    regression_result = assemble(regression_program.read_text(encoding="utf-8"), filename=str(regression_program))
    assert result.dense_words() == regression_result.dense_words()
    assert result.dense_words() == [
        0x5C02, 0x0000, 0x0000, 0x0000,
        0x5203, 0x0000, 0x0000, 0x0000,
        0x09DA, 0x0000, 0x0000, 0x0000,
        0x5A05, 0x0000, 0x0000, 0x0000,
        0x5606, 0x0000, 0x0000, 0x0000,
        0x0FF5, 0x0000, 0x0000, 0x0000,
        0x047C, 0x0000, 0x0000, 0x0000,
        0xF000,
    ]


def test_cli_writes_raw_binary(tmp_path: Path) -> None:
    source = tmp_path / "program.asm"
    output = tmp_path / "program.bin"
    source.write_text("JMP 0x1234\n", encoding="utf-8")
    assert run([str(source), "-o", str(output), "--format", "binary"]) == 0
    assert output.read_bytes() == bytes.fromhex("B040 1234")


@pytest.mark.parametrize("program", sorted(PROGRAM_DIR.glob("*.asm")), ids=lambda path: path.stem)
def test_cpu_program_sources_assemble(program: Path) -> None:
    result = assemble_file(program)
    assert result.words, f"{program.name} emitted no words"
    assert all(0 <= address <= 0xFFFF and 0 <= word <= 0xFFFF for address, word in result.words.items())


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("ADDI R2, 128", "immediate out of range"),
        ("SH R2, R2, -17", "shift amount out of range [-16..15]"),
        ("SH R2, R2, 16", "shift amount out of range [-16..15]"),
        ("LD R2, R3, -33", "displacement out of range"),
        ("JMP nowhere", "undefined symbol 'nowhere'"),
        ("same: NOP\nsame: HALT", "already defined"),
        (".org 2\n.word 1\n.org 2\n.word 2", "written more than once"),
        ("ADDI R2, R3, 1", "must be the same register"),
        (".word", "expects at least one value"),
        (".", "expected directive name"),
    ],
)
def test_source_errors_include_location(source: str, message: str) -> None:
    with pytest.raises(AssemblerError) as captured:
        assemble(source, filename="bad.asm")
    assert str(captured.value).startswith("bad.asm:")
    assert message in str(captured.value)


@pytest.mark.parametrize("mnemonic", ["SH", "ASH", "ADDI", "LLI", "LUI", "LD", "ST", "LDSP", "STSP"])
def test_immediate_bit_weights_match_the_isa(mnemonic: str) -> None:
    width = 5 if mnemonic in {"SH", "ASH"} else 6 if mnemonic in {"LD", "ST"} else 8
    def instruction(value: int) -> str:
        if mnemonic in {"SH", "ASH"}:
            return f"{mnemonic} R2, ZERO, {value}"
        if mnemonic in {"LD", "ST"}:
            return f"{mnemonic} R2, ZERO, {value}"
        return f"{mnemonic} R2, {value}"
    base = assemble(instruction(0)).dense_words()[0]
    for bit in range(width):
        value = 1 << bit
        if bit == width - 1 and mnemonic not in {"LLI", "LUI"}:
            value = -value
        word = assemble(instruction(value)).dense_words()[0]
        assert word ^ base == 1 << (11 - bit)


@pytest.mark.parametrize("mnemonic", ["ADDI", "LDSP", "STSP"])
@pytest.mark.parametrize("value", [-129, 128, 255])
def test_signed_byte_immediates_reject_values_outside_the_new_range(mnemonic: str, value: int) -> None:
    with pytest.raises(AssemblerError, match=r"out of range \[-128..127\]"):
        assemble(f"{mnemonic} R2, {value}")


@pytest.mark.parametrize("value", [0, 1, 127, 128, 255, 256, 0x127F, 0x1280,
                                   0x12FF, 0x7FFF, 0x8000, 0xFF7F, 0xFF80,
                                   0xFFFF, -128, -1])
def test_li_reconstructs_constants_with_signed_byte_addi(value: int) -> None:
    words = assemble(f"LI R2, {value}").dense_words()
    def byte(word: int) -> int:
        # Read the literal binary column in the opposite direction to the
        # normal instruction word: IMM bit 0 is instruction bit 11.
        return int(f"{word:016b}"[4:12][::-1], 2)
    result = byte(words[0])
    if len(words) == 2:
        assert words[0] & 8                 # LUI selector
        assert words[1] >> 12 == 4         # ADDI
        low = byte(words[1])
        result = (result << 8) + (low - 256 if low >= 128 else low)
    assert result & 0xFFFF == value & 0xFFFF
