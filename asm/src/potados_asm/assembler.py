from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence, TypeAlias


OutputFormat: TypeAlias = Literal["hex", "annotated-hex", "bytecode", "binary"]


class AssemblerError(Exception):
    def __init__(
        self, filename: str, line: int, column: int | None, message: str
    ) -> None:
        super().__init__(message)
        self.filename = filename
        self.line = line
        self.column = column
        self.message = message

    def __str__(self) -> str:
        location = f"{self.filename}:{self.line}"
        if self.column is not None:
            location += f":{self.column}"
        return f"{location}: {self.message}"


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    file: str
    line: int
    column: int
    value: int | str | None = None


ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "0": "\0",
    "'": "'",
    '"': '"',
    "\\": "\\",
}


def strip_comment(line: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in line:
        if quote is not None:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            result.append(char)
        elif char in {";", "#"}:
            break
        else:
            result.append(char)
    return "".join(result)


class Tokenizer:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def tokenize(self, lines: Sequence[str]) -> list[tuple[int, str, list[Token]]]:
        return [
            (
                line_no,
                raw.rstrip("\n"),
                self._tokenize_line(strip_comment(raw.rstrip("\n")), line_no),
            )
            for line_no, raw in enumerate(lines, 1)
        ]

    def _tokenize_line(self, text: str, line_no: int) -> list[Token]:
        tokens: list[Token] = []
        i = 0
        punctuation = {
            ":": "COLON",
            ",": "COMMA",
            "(": "LPAREN",
            ")": "RPAREN",
            "[": "LBRACKET",
            "]": "RBRACKET",
            "%": "PERCENT",
            "+": "PLUS",
            "-": "MINUS",
            ".": "DOT",
        }
        while i < len(text):
            char = text[i]
            if char.isspace():
                i += 1
                continue
            if char.isalpha() or char == "_":
                start = i
                i += 1
                while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                    i += 1
                tokens.append(
                    Token("IDENT", text[start:i], self.filename, line_no, start + 1)
                )
                continue
            if char.isdigit():
                token, i = self._lex_number(text, line_no, i)
                tokens.append(token)
                continue
            if char in {"'", '"'}:
                token, i = self._lex_quoted(text, line_no, i, char)
                tokens.append(token)
                continue
            if char in punctuation:
                tokens.append(
                    Token(punctuation[char], char, self.filename, line_no, i + 1)
                )
                i += 1
                continue
            raise AssemblerError(
                self.filename, line_no, i + 1, f"unexpected character '{char}'"
            )
        return tokens

    def _lex_number(self, text: str, line_no: int, start: int) -> tuple[Token, int]:
        i = start
        base = 10
        if text[i : i + 2].lower() in {"0b", "0o", "0d", "0x"}:
            prefix = text[i + 1].lower()
            base = {"b": 2, "o": 8, "d": 10, "x": 16}[prefix]
            i += 2
        digit_start = i
        valid = "0123456789abcdef"[:base]
        while i < len(text) and (text[i].lower() in valid or text[i] == "_"):
            i += 1
        digits = text[digit_start:i].replace("_", "")
        if not digits:
            raise AssemblerError(
                self.filename, line_no, start + 1, "numeric literal missing digits"
            )
        return Token(
            "NUMBER",
            text[start:i],
            self.filename,
            line_no,
            start + 1,
            int(digits, base),
        ), i

    def _lex_quoted(
        self, text: str, line_no: int, start: int, quote: str
    ) -> tuple[Token, int]:
        chars: list[str] = []
        i = start + 1
        while i < len(text):
            char = text[i]
            if char == quote:
                i += 1
                value = "".join(chars)
                if quote == "'":
                    if len(value) != 1:
                        raise AssemblerError(
                            self.filename,
                            line_no,
                            start + 1,
                            "character literal must contain one character",
                        )
                    return Token(
                        "CHAR",
                        text[start:i],
                        self.filename,
                        line_no,
                        start + 1,
                        ord(value),
                    ), i
                return Token(
                    "STRING", text[start:i], self.filename, line_no, start + 1, value
                ), i
            if char == "\\":
                i += 1
                if i >= len(text):
                    break
                escaped = text[i]
                if escaped not in ESCAPES:
                    raise AssemblerError(
                        self.filename, line_no, i + 1, f"unknown escape '\\{escaped}'"
                    )
                chars.append(ESCAPES[escaped])
            else:
                chars.append(char)
            i += 1
        raise AssemblerError(self.filename, line_no, start + 1, "unterminated literal")


@dataclass
class Expr:
    token: Token


@dataclass
class NumberExpr(Expr):
    value: int


@dataclass
class SymbolExpr(Expr):
    name: str


@dataclass
class UnaryExpr(Expr):
    op: str
    operand: Expr


@dataclass
class BinaryExpr(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class FunctionExpr(Expr):
    name: str
    argument: Expr


class ExpressionParser:
    def __init__(self, tokens: Sequence[Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse(self) -> Expr:
        expression = self._parse_additive()
        if self._peek() is not None:
            token = self._peek_required()
            raise AssemblerError(
                token.file, token.line, token.column, "unexpected token in expression"
            )
        return expression

    def _parse_additive(self) -> Expr:
        result = self._parse_unary()
        while (token := self._peek()) is not None and token.kind in {"PLUS", "MINUS"}:
            self.position += 1
            result = BinaryExpr(token, token.text, result, self._parse_unary())
        return result

    def _parse_unary(self) -> Expr:
        token = self._peek()
        if token is not None and token.kind in {"PLUS", "MINUS"}:
            self.position += 1
            return UnaryExpr(token, token.text, self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        token = self._peek_required()
        if token.kind in {"NUMBER", "CHAR"}:
            self.position += 1
            assert isinstance(token.value, int)
            return NumberExpr(token, token.value)
        if token.kind == "IDENT":
            self.position += 1
            return SymbolExpr(token, token.text)
        if token.kind == "LPAREN":
            self.position += 1
            result = self._parse_additive()
            self._expect("RPAREN")
            return result
        if token.kind == "PERCENT":
            percent = self._expect("PERCENT")
            name = self._expect("IDENT")
            lowered = name.text.lower()
            if lowered not in {"hi", "lo", "rel"}:
                raise AssemblerError(
                    name.file,
                    name.line,
                    name.column,
                    f"unknown expression function '%{name.text}'",
                )
            self._expect("LPAREN")
            argument = self._parse_additive()
            self._expect("RPAREN")
            return FunctionExpr(percent, lowered, argument)
        raise AssemblerError(
            token.file, token.line, token.column, "expected expression"
        )

    def _peek(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _peek_required(self) -> Token:
        token = self._peek()
        if token is None:
            if self.tokens:
                last = self.tokens[-1]
                raise AssemblerError(
                    last.file,
                    last.line,
                    last.column + len(last.text),
                    "incomplete expression",
                )
            raise AssemblerError("<unknown>", 0, None, "missing expression")

        return token

    def _expect(self, kind: str) -> Token:
        token = self._peek_required()
        if token.kind != kind:
            raise AssemblerError(
                token.file, token.line, token.column, f"expected {kind.lower()}"
            )
        self.position += 1
        return token


@dataclass
class Operand:
    tokens: list[Token]
    _expression: Expr | None = field(default=None, init=False, repr=False)

    def first(self) -> Token:
        if not self.tokens:
            raise AssemblerError("<unknown>", 0, None, "missing operand")
        return self.tokens[0]

    def expression(self) -> Expr:
        if self._expression is None:
            self._expression = ExpressionParser(self.tokens).parse()
        return self._expression


@dataclass(frozen=True)
class Instruction:
    mnemonic: str
    token: Token
    operands: list[Operand]


@dataclass(frozen=True)
class Directive:
    name: str
    token: Token
    operands: list[Operand]


@dataclass
class Statement:
    labels: list[Token]
    body: Instruction | Directive | None
    line: int
    source: str
    address: int | None = None


DIRECTIVES = {"org", "section", "equ", "word", "dw", "byte", "db", "string", "space"}
INSTRUCTIONS = {
    "NOP",
    "ADD",
    "SUB",
    "AND",
    "OR",
    "XOR",
    "NOT",
    "MUL",
    "SGE",
    "SL",
    "SE",
    "SNE",
    "SAE",
    "SB",
    "SH",
    "ASH",
    "ADDI",
    "LLI",
    "LUI",
    "LD",
    "ST",
    "LDSP",
    "STSP",
    "JGE",
    "JL",
    "JE",
    "JNE",
    "JAE",
    "JB",
    "JMP",
    "JAL",
    "PUSH",
    "POP",
    "JMPR",
    "JALR",
    "FADD",
    "FSUB",
    "FMUL",
    "FDIV",
    "ITOF",
    "FTOI",
    "FTOU",
    "HALT",
    # Assembler pseudo-instructions. They expand to ordinary ISA words.
    "LI",
    "LEA",
    "MOV",
    "CLR",
    "INC",
    "DEC",
    "NEG",
    "J",
    "CALL",
    "RET",
}


def _split_operands(tokens: Sequence[Token]) -> list[Operand]:
    if not tokens:
        return []
    result: list[Operand] = []
    current: list[Token] = []
    depth = 0
    for token in tokens:
        if token.kind in {"LPAREN", "LBRACKET"}:
            depth += 1
        elif token.kind in {"RPAREN", "RBRACKET"}:
            depth -= 1
            if depth < 0:
                raise AssemblerError(
                    token.file, token.line, token.column, "unmatched closing delimiter"
                )
        if token.kind == "COMMA" and depth == 0:
            if not current:
                raise AssemblerError(
                    token.file, token.line, token.column, "missing operand before comma"
                )
            result.append(Operand(current))
            current = []
        else:
            current.append(token)
    if depth != 0:
        token = tokens[-1]
        raise AssemblerError(token.file, token.line, token.column, "unclosed delimiter")
    if not current:
        token = tokens[-1]
        raise AssemblerError(token.file, token.line, token.column, "dangling comma")
    result.append(Operand(current))
    return result


def parse_source(source: str, filename: str) -> list[Statement]:
    tokenized = Tokenizer(filename).tokenize(source.splitlines())
    statements: list[Statement] = []
    for line_no, raw, tokens in tokenized:
        position = 0
        labels: list[Token] = []
        while (
            position + 1 < len(tokens)
            and tokens[position].kind == "IDENT"
            and tokens[position + 1].kind == "COLON"
        ):
            labels.append(tokens[position])
            position += 2
        if position == len(tokens):
            if labels:
                statements.append(Statement(labels, None, line_no, raw))
            continue
        dotted = False
        if tokens[position].kind == "DOT":
            dotted = True
            position += 1
        if position >= len(tokens):
            token = tokens[-1]
            raise AssemblerError(
                token.file,
                token.line,
                token.column,
                "expected directive name after '.'",
            )
        if tokens[position].kind != "IDENT":
            token = tokens[position]
            raise AssemblerError(
                token.file,
                token.line,
                token.column,
                "expected instruction or directive",
            )
        name_token = tokens[position]
        position += 1
        lowered = name_token.text.lower()
        uppered = name_token.text.upper()
        operands = _split_operands(tokens[position:])
        if lowered in DIRECTIVES:
            body: Instruction | Directive = Directive(lowered, name_token, operands)
        elif uppered in INSTRUCTIONS and not dotted:
            body = Instruction(uppered, name_token, operands)
        else:
            raise AssemblerError(
                name_token.file,
                name_token.line,
                name_token.column,
                f"unknown instruction or directive '{name_token.text}'",
            )

        statements.append(Statement(labels, body, line_no, raw))
    return statements


def evaluate(expression: Expr, symbols: Mapping[str, int], current_address: int) -> int:
    if isinstance(expression, NumberExpr):
        return expression.value
    if isinstance(expression, SymbolExpr):
        if expression.name not in symbols:
            raise AssemblerError(
                expression.token.file,
                expression.token.line,
                expression.token.column,
                f"undefined symbol '{expression.name}'",
            )
        return symbols[expression.name]
    if isinstance(expression, UnaryExpr):
        value = evaluate(expression.operand, symbols, current_address)
        return value if expression.op == "+" else -value
    if isinstance(expression, BinaryExpr):
        left = evaluate(expression.left, symbols, current_address)
        right = evaluate(expression.right, symbols, current_address)
        return left + right if expression.op == "+" else left - right
    if isinstance(expression, FunctionExpr):
        value = evaluate(expression.argument, symbols, current_address)
        if expression.name == "hi":
            return (value >> 8) & 0xFF
        if expression.name == "lo":
            return value & 0xFF
        if expression.name == "rel":
            return value - current_address
    raise AssemblerError(
        expression.token.file,
        expression.token.line,
        expression.token.column,
        "invalid expression",
    )


REGISTER_ALIASES = {"zero": 0, "sp": 1, **{f"r{index}": index for index in range(8)}}


def _register(operand: Operand, description: str) -> int:
    if len(operand.tokens) != 1 or operand.tokens[0].kind != "IDENT":
        token = operand.first()
        raise AssemblerError(
            token.file, token.line, token.column, f"{description} must be a register"
        )
    token = operand.tokens[0]
    name = token.text.lower()
    if name not in REGISTER_ALIASES:
        raise AssemblerError(
            token.file, token.line, token.column, f"invalid register '{token.text}'"
        )
    return REGISTER_ALIASES[name]


def _require_operands(instruction: Instruction, counts: int | Iterable[int]) -> None:
    valid = {counts} if isinstance(counts, int) else set(counts)
    if len(instruction.operands) not in valid:
        expected = " or ".join(str(value) for value in sorted(valid))
        raise AssemblerError(
            instruction.token.file,
            instruction.token.line,
            instruction.token.column,
            f"{instruction.mnemonic} expects {expected} operand(s), got {len(instruction.operands)}",
        )


def _signed(value: int, bits: int, token: Token, description: str) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << (bits - 1)) - 1
    if not minimum <= value <= maximum:
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            f"{description} out of range [{minimum}..{maximum}]",
        )
    return value & ((1 << bits) - 1)


def _bit_pattern(value: int, bits: int, token: Token, description: str) -> int:
    minimum = -(1 << (bits - 1))
    maximum = (1 << bits) - 1
    if not minimum <= value <= maximum:
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            f"{description} out of range [{minimum}..{maximum}]",
        )
    return value & maximum


def _unsigned(value: int, bits: int, token: Token, description: str) -> int:
    maximum = (1 << bits) - 1
    if not 0 <= value <= maximum:
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            f"{description} out of range [0..{maximum}]",
        )
    return value


def _value(operand: Operand, symbols: Mapping[str, int], address: int) -> int:
    return evaluate(operand.expression(), symbols, address)


def _encode_register_fields(
    *, opcode: int, destination: int, function: int, source_a: int, source_b: int
) -> int:
    """Encode the regular ``opcode/dst/function/src_a/src_b`` instruction form."""
    return (
        (opcode & 0b1111) << 12       # [15:12] primary opcode
        | (destination & 0b111) << 9  # [11:9]  destination register
        | (function & 0b111) << 6     # [8:6]   secondary opcode
        | (source_a & 0b111) << 3     # [5:3]   left source register
        | (source_b & 0b111)          # [2:0]   right source register
    )


def _encode_split_immediate_9(*, opcode: int, immediate: int, register: int) -> int:
    """Encode the split IMM9 used by ADDI, LDSP, and STSP.

    The ISA places the low six immediate bits above the high three bits::

        15          12 11             6 5          3 2          0
        +-------------+----------------+------------+------------+
        |   opcode    | immediate[5:0] | imm[8:6]   | register   |
        +-------------+----------------+------------+------------+
    """
    immediate_low = immediate & 0b11_1111
    immediate_high = (immediate >> 6) & 0b111
    return (
        (opcode & 0b1111) << 12
        | immediate_low << 6
        | immediate_high << 3
        | (register & 0b111)
    )


def _memory_operand(operand: Operand) -> tuple[int, Operand]:
    tokens = operand.tokens
    if len(tokens) < 3 or tokens[0].kind != "LBRACKET" or tokens[-1].kind != "RBRACKET":
        token = operand.first()
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            "memory operand must have form [register + displacement]",
        )
    register_operand = Operand([tokens[1]])
    pointer = _register(register_operand, "pointer")
    remainder = tokens[2:-1]
    if not remainder:
        zero = Token("NUMBER", "0", tokens[0].file, tokens[0].line, tokens[0].column, 0)
        return pointer, Operand([zero])
    if remainder[0].kind not in {"PLUS", "MINUS"}:
        token = remainder[0]
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            "expected '+' or '-' after memory pointer",
        )
    if remainder[0].kind == "MINUS":
        remainder = [remainder[0], *remainder[1:]]
    else:
        remainder = remainder[1:]
    if not remainder:
        token = tokens[-1]
        raise AssemblerError(
            token.file, token.line, token.column, "missing memory displacement"
        )
    return pointer, Operand(list(remainder))


ALU_SECONDARY = {"ADD": 1, "SUB": 2, "AND": 3, "OR": 4, "XOR": 5, "MUL": 7}
SET_SECONDARY = {"SGE": 0, "SL": 1, "SE": 2, "SNE": 3, "SAE": 4, "SB": 5}
JUMP_SECONDARY = {"JGE": 0, "JL": 1, "JE": 2, "JNE": 3, "JAE": 4, "JB": 5}
FPU_SECONDARY = {"FADD": 1, "FSUB": 2, "FMUL": 3, "FDIV": 4}
FPU_UNARY_SECONDARY = {"ITOF": 5, "FTOI": 6, "FTOU": 7}


def _encode_binary_register_instruction(
    instruction: Instruction, *, opcode: int, function: int
) -> list[int]:
    """Encode three-operand or destructive two-operand register operations."""
    _require_operands(instruction, {2, 3})
    destination = instruction.operands[0]
    if len(instruction.operands) == 2:
        # ``ADD R2, R3`` means ``ADD R2, R2, R3``.
        source_a, source_b = destination, instruction.operands[1]
    else:
        _, source_a, source_b = instruction.operands
    return [
        _encode_register_fields(
            opcode=opcode,
            destination=_register(destination, "destination"),
            function=function,
            source_a=_register(source_a, "left source"),
            source_b=_register(source_b, "right source"),
        )
    ]


def _encode_not_instruction(instruction: Instruction) -> list[int]:
    """Encode ``NOT destination, source``; the unused source-A field is zero."""
    _require_operands(instruction, 2)
    destination, source = instruction.operands
    return [
        _encode_register_fields(
            opcode=0b0000,
            destination=_register(destination, "destination"),
            function=0b110,
            source_a=0,
            source_b=_register(source, "source"),
        )
    ]


def _encode_shift_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode the shift-specific ``opcode/0/IMM5/source/destination`` form."""
    _require_operands(instruction, 3)
    destination_operand, source_operand, immediate_operand = instruction.operands
    immediate = _signed(
        _value(immediate_operand, symbols, address),
        5,
        immediate_operand.first(),
        "shift amount",
    )
    opcode = 0b0010 if instruction.mnemonic == "SH" else 0b0011
    word = (
        opcode << 12
        | 0 << 11                              # [11]    reserved, always zero
        | (immediate & 0b1_1111) << 6          # [10:6]  signed shift amount
        | _register(source_operand, "source") << 3  # [5:3] source register
        | _register(destination_operand, "destination")  # [2:0] destination
    )
    return [word]


def _encode_addi_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode ``ADDI register, [same_register,] immediate``."""
    _require_operands(instruction, {2, 3})
    destination = _register(instruction.operands[0], "source/destination")
    immediate_operand = instruction.operands[-1]

    if len(instruction.operands) == 3:
        source_operand = instruction.operands[1]
        if _register(source_operand, "source") != destination:
            token = source_operand.first()
            raise AssemblerError(
                token.file,
                token.line,
                token.column,
                "ADDI source and destination must be the same register",
            )

    immediate = _signed(
        _value(immediate_operand, symbols, address),
        9,
        immediate_operand.first(),
        "immediate",
    )
    return [
        _encode_split_immediate_9(
            opcode=0b0100, immediate=immediate, register=destination
        )
    ]


def _encode_load_immediate_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode LLI/LUI's split byte and its selector bit."""
    _require_operands(instruction, 2)
    destination_operand, immediate_operand = instruction.operands
    destination = _register(destination_operand, "destination")
    immediate = _bit_pattern(
        _value(immediate_operand, symbols, address),
        8,
        immediate_operand.first(),
        "immediate",
    )
    upper_byte = int(instruction.mnemonic == "LUI")
    return [
        0b0101 << 12
        | (immediate & 0b11_1111) << 6  # [11:6] immediate[5:0]
        | upper_byte << 5               # [5]    0 = LLI, 1 = LUI
        | ((immediate >> 6) & 0b11) << 3  # [4:3] immediate[7:6]
        | destination                   # [2:0] destination register
    ]


def _encode_load_immediate_word(destination: int, immediate: int, *, upper: bool) -> int:
    """Return one LLI/LUI word for an already validated byte value."""
    return (
        0b0101 << 12
        | (immediate & 0b11_1111) << 6
        | int(upper) << 5
        | ((immediate >> 6) & 0b11) << 3
        | destination
    )


def _li_short_value(instruction: Instruction, address: int) -> int | None:
    """Return a byte-sized constant when LI can safely occupy one word.

    Symbolic expressions deliberately use the long form during layout.  That
    keeps label addresses stable even when a forward reference later resolves
    to a small value.
    """
    operand = instruction.operands[1]
    try:
        value = _value(operand, {}, address)
    except AssemblerError as error:
        if error.message.startswith("undefined symbol"):
            return None
        raise
    return value if 0 <= value <= 0xFF else None


def _encode_li_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Expand ``LI register, value`` to LLI or LUI followed by ADDI.

    LI is an assembler convenience only: the processor still has exactly the
    two explicit immediate instructions defined by the ISA.
    """
    _require_operands(instruction, 2)
    destination_operand, value_operand = instruction.operands
    destination = _register(destination_operand, "destination")
    value = _bit_pattern(
        _value(value_operand, symbols, address),
        16,
        value_operand.first(),
        "LI immediate",
    )

    short_value = _li_short_value(instruction, address)
    if short_value is not None:
        return [_encode_load_immediate_word(destination, short_value, upper=False)]

    high_byte = (value >> 8) & 0xFF
    low_byte = value & 0xFF
    return [
        _encode_load_immediate_word(destination, high_byte, upper=True),
        _encode_split_immediate_9(
            opcode=0b0100, immediate=low_byte, register=destination
        ),
    ]


def _encode_addi_word(register: int, immediate: int) -> int:
    """Return one ADDI word for a validated signed nine-bit immediate."""
    return _encode_split_immediate_9(
        opcode=0b0100, immediate=immediate, register=register
    )


def _encode_base_memory_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode ``LD/ST data_register, [pointer + displacement]``."""
    _require_operands(instruction, {2, 3})
    data_operand = instruction.operands[0]
    data_description = "destination" if instruction.mnemonic == "LD" else "source"
    data_register = _register(data_operand, data_description)

    if len(instruction.operands) == 2:
        address_operand = instruction.operands[1]
        if len(address_operand.tokens) == 1 and address_operand.tokens[0].kind == "IDENT":
            # ``LD R3, R2`` / ``ST R3, R2`` are concise zero-offset forms.
            pointer = _register(address_operand, "pointer")
            token = address_operand.first()
            displacement_operand = Operand(
                [Token("NUMBER", "0", token.file, token.line, token.column, 0)]
            )
        else:
            pointer, displacement_operand = _memory_operand(address_operand)
    else:
        pointer = _register(instruction.operands[1], "pointer")
        displacement_operand = instruction.operands[2]

    displacement = _signed(
        _value(displacement_operand, symbols, address),
        6,
        displacement_operand.first(),
        "displacement",
    )
    opcode = 0b0110 if instruction.mnemonic == "LD" else 0b0111
    return [
        opcode << 12
        | displacement << 6  # [11:6] signed displacement
        | pointer << 3       # [5:3] pointer register
        | data_register      # [2:0] load destination / store source
    ]


def _encode_stack_memory_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode LDSP/STSP using the same split IMM9 layout as ADDI."""
    _require_operands(instruction, 2)
    register_operand, immediate_operand = instruction.operands
    register_description = (
        "destination" if instruction.mnemonic == "LDSP" else "source"
    )
    register = _register(register_operand, register_description)
    immediate = _signed(
        _value(immediate_operand, symbols, address),
        9,
        immediate_operand.first(),
        "SP displacement",
    )
    opcode = 0b1000 if instruction.mnemonic == "LDSP" else 0b1001
    return [
        _encode_split_immediate_9(
            opcode=opcode, immediate=immediate, register=register
        )
    ]


def _jump_target(
    operand: Operand, symbols: Mapping[str, int], address: int
) -> int:
    return _unsigned(
        _value(operand, symbols, address),
        16,
        operand.first(),
        "jump target",
    )


def _encode_conditional_jump_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode a compare-and-jump word followed by its absolute target word."""
    _require_operands(instruction, 3)
    source_a, source_b, target_operand = instruction.operands
    instruction_word = _encode_register_fields(
        opcode=0b1010,
        destination=0,
        function=JUMP_SECONDARY[instruction.mnemonic],
        source_a=_register(source_a, "left source"),
        source_b=_register(source_b, "right source"),
    )
    return [instruction_word, _jump_target(target_operand, symbols, address)]


def _encode_direct_jump_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Encode JMP or JAL followed by its absolute target word."""
    if instruction.mnemonic == "JMP":
        _require_operands(instruction, 1)
        destination = 0
        function = 0b001
        target_operand = instruction.operands[0]
    else:
        _require_operands(instruction, 2)
        destination = _register(
            instruction.operands[0], "return-address destination"
        )
        function = 0b010
        target_operand = instruction.operands[1]

    instruction_word = _encode_register_fields(
        opcode=0b1011,
        destination=0,
        function=function,
        source_a=0,
        source_b=destination,
    )
    return [instruction_word, _jump_target(target_operand, symbols, address)]


def _encode_single_register_instruction(instruction: Instruction) -> list[int]:
    """Encode PUSH, POP, or JMPR; each stores its register in bits [2:0]."""
    _require_operands(instruction, 1)
    opcode, function = {
        "PUSH": (0b1100, 0b001),
        "POP": (0b1100, 0b010),
        "JMPR": (0b1101, 0b001),
    }[instruction.mnemonic]
    register = _register(instruction.operands[0], "register")
    return [
        _encode_register_fields(
            opcode=opcode,
            destination=0,
            function=function,
            source_a=0,
            source_b=register,
        )
    ]


def _encode_jalr_instruction(instruction: Instruction) -> list[int]:
    """Encode ``JALR link_destination, target_source``."""
    _require_operands(instruction, 2)
    destination_operand, source_operand = instruction.operands
    return [
        _encode_register_fields(
            opcode=0b1101,
            destination=0,
            function=0b010,
            source_a=_register(source_operand, "jump target source"),
            source_b=_register(destination_operand, "return-address destination"),
        )
    ]


def _encode_fpu_instruction(instruction: Instruction) -> list[int]:
    if instruction.mnemonic in FPU_SECONDARY:
        return _encode_binary_register_instruction(
            instruction,
            opcode=0b1110,
            function=FPU_SECONDARY[instruction.mnemonic],
        )

    _require_operands(instruction, 2)
    destination_operand, source_operand = instruction.operands
    return [
        _encode_register_fields(
            opcode=0b1110,
            destination=_register(destination_operand, "destination"),
            function=FPU_UNARY_SECONDARY[instruction.mnemonic],
            source_a=0,
            source_b=_register(source_operand, "source"),
        )
    ]


def encode_instruction(
    instruction: Instruction, symbols: Mapping[str, int], address: int
) -> list[int]:
    """Dispatch an instruction to the encoder for its visible ISA bit layout."""
    mnemonic = instruction.mnemonic

    if mnemonic == "NOP":
        _require_operands(instruction, 0)
        return [0x0000]
    if mnemonic in {"J", "CALL"}:
        _require_operands(instruction, 1)
        function = 0b001 if mnemonic == "J" else 0b010
        return [
            _encode_register_fields(
                opcode=0b1011,
                destination=0,
                function=function,
                source_a=0,
                source_b=0 if mnemonic == "J" else 0b111,
            ),
            _jump_target(instruction.operands[0], symbols, address),
        ]
    if mnemonic == "RET":
        _require_operands(instruction, 0)
        return [
            _encode_register_fields(
                opcode=0b1101,
                destination=0,
                function=0b001,
                source_a=0,
                source_b=0b111,
            )
        ]
    if mnemonic == "MOV":
        _require_operands(instruction, 2)
        destination, source = instruction.operands
        return [
            _encode_register_fields(
                opcode=0b0000,
                destination=_register(destination, "destination"),
                function=ALU_SECONDARY["ADD"],
                source_a=_register(source, "source"),
                source_b=0,
            )
        ]
    if mnemonic in {"LI", "LEA"}:
        return _encode_li_instruction(instruction, symbols, address)
    if mnemonic == "CLR":
        _require_operands(instruction, 1)
        return [
            _encode_load_immediate_word(
                _register(instruction.operands[0], "destination"), 0, upper=False
            )
        ]
    if mnemonic in {"INC", "DEC"}:
        _require_operands(instruction, 1)
        immediate = 1 if mnemonic == "INC" else -1
        return [
            _encode_addi_word(
                _register(instruction.operands[0], "source/destination"), immediate
            )
        ]
    if mnemonic == "NEG":
        _require_operands(instruction, {1, 2})
        destination = instruction.operands[0]
        source = instruction.operands[-1]
        return [
            _encode_register_fields(
                opcode=0b0000,
                destination=_register(destination, "destination"),
                function=ALU_SECONDARY["SUB"],
                source_a=0,
                source_b=_register(source, "source"),
            )
        ]
    if mnemonic in ALU_SECONDARY:
        return _encode_binary_register_instruction(
            instruction, opcode=0b0000, function=ALU_SECONDARY[mnemonic]
        )
    if mnemonic in SET_SECONDARY:
        return _encode_binary_register_instruction(
            instruction, opcode=0b0001, function=SET_SECONDARY[mnemonic]
        )
    if mnemonic == "NOT":
        return _encode_not_instruction(instruction)
    if mnemonic in {"SH", "ASH"}:
        return _encode_shift_instruction(instruction, symbols, address)
    if mnemonic == "ADDI":
        return _encode_addi_instruction(instruction, symbols, address)
    if mnemonic in {"LLI", "LUI"}:
        return _encode_load_immediate_instruction(instruction, symbols, address)
    if mnemonic in {"LD", "ST"}:
        return _encode_base_memory_instruction(instruction, symbols, address)
    if mnemonic in {"LDSP", "STSP"}:
        return _encode_stack_memory_instruction(instruction, symbols, address)
    if mnemonic in JUMP_SECONDARY:
        return _encode_conditional_jump_instruction(instruction, symbols, address)
    if mnemonic in {"JMP", "JAL"}:
        return _encode_direct_jump_instruction(instruction, symbols, address)
    if mnemonic in {"PUSH", "POP", "JMPR"}:
        return _encode_single_register_instruction(instruction)
    if mnemonic == "JALR":
        return _encode_jalr_instruction(instruction)
    if mnemonic in FPU_SECONDARY or mnemonic in FPU_UNARY_SECONDARY:
        return _encode_fpu_instruction(instruction)
    if mnemonic == "HALT":
        _require_operands(instruction, 0)
        return [0xF000]
    raise AssemblerError(
        instruction.token.file,
        instruction.token.line,
        instruction.token.column,
        f"unsupported instruction '{mnemonic}'",
    )


def _instruction_size(instruction: Instruction) -> int:
    if instruction.mnemonic in {"LI", "LEA"}:
        return 1 if _li_short_value(instruction, 0) is not None else 2
    return 2 if instruction.mnemonic in {*JUMP_SECONDARY, "JMP", "JAL", "J", "CALL"} else 1


def _directive_address(
    directive: Directive, symbols: dict[str, int], location: int
) -> int:
    operands = directive.operands
    if directive.name == "org":
        if len(operands) != 1:
            raise AssemblerError(
                directive.token.file,
                directive.token.line,
                directive.token.column,
                "org expects one address",
            )
        value = _value(operands[0], symbols, location)
    else:
        if len(operands) not in {1, 2}:
            raise AssemblerError(
                directive.token.file,
                directive.token.line,
                directive.token.column,
                "section expects ADDRESS or NAME, ADDRESS",
            )
        value = _value(operands[-1], symbols, location)
        if len(operands) == 2:
            name_operand = operands[0]
            if len(name_operand.tokens) != 1 or name_operand.tokens[0].kind != "IDENT":
                token = name_operand.first()
                raise AssemblerError(
                    token.file,
                    token.line,
                    token.column,
                    "section name must be an identifier",
                )
            name = name_operand.tokens[0].text
            if name in symbols:
                token = name_operand.first()
                raise AssemblerError(
                    token.file,
                    token.line,
                    token.column,
                    f"symbol '{name}' is already defined",
                )
            symbols[name] = value
    return _unsigned(value, 16, operands[-1].first(), "section address")


def layout(statements: list[Statement]) -> dict[str, int]:
    symbols: dict[str, int] = {}
    symbol_tokens: dict[str, Token] = {}
    location = 0
    for statement in statements:
        statement.address = location
        for label in statement.labels:
            if label.text in symbols:
                previous = symbol_tokens.get(label.text)
                suffix = f" at line {previous.line}" if previous is not None else ""
                raise AssemblerError(
                    label.file,
                    label.line,
                    label.column,
                    f"symbol '{label.text}' already defined{suffix}",
                )
            symbols[label.text] = location
            symbol_tokens[label.text] = label
        body = statement.body
        if body is None:
            continue
        if isinstance(body, Instruction):
            location += _instruction_size(body)
        elif body.name in {"org", "section"}:
            location = _directive_address(body, symbols, location)
        elif body.name == "equ":
            if len(body.operands) != 2:
                raise AssemblerError(
                    body.token.file,
                    body.token.line,
                    body.token.column,
                    "equ expects NAME, EXPRESSION",
                )
            name_operand = body.operands[0]
            if len(name_operand.tokens) != 1 or name_operand.tokens[0].kind != "IDENT":
                token = name_operand.first()
                raise AssemblerError(
                    token.file,
                    token.line,
                    token.column,
                    "constant name must be an identifier",
                )
            name = name_operand.tokens[0].text
            if name in symbols:
                token = name_operand.first()
                raise AssemblerError(
                    token.file,
                    token.line,
                    token.column,
                    f"symbol '{name}' is already defined",
                )
            symbols[name] = _value(body.operands[1], symbols, location)
            symbol_tokens[name] = name_operand.first()
        elif body.name in {"word", "dw", "byte", "db"}:
            if not body.operands:
                raise AssemblerError(
                    body.token.file,
                    body.token.line,
                    body.token.column,
                    f"{body.name} expects at least one value",
                )
            location += len(body.operands)
        elif body.name == "string":
            if not body.operands:
                raise AssemblerError(
                    body.token.file,
                    body.token.line,
                    body.token.column,
                    "string expects at least one string literal",
                )
            for operand in body.operands:
                if len(operand.tokens) != 1 or operand.tokens[0].kind != "STRING":
                    token = operand.first()
                    raise AssemblerError(
                        token.file,
                        token.line,
                        token.column,
                        "string expects string literals",
                    )
                assert isinstance(operand.tokens[0].value, str)
                location += len(operand.tokens[0].value)
        elif body.name == "space":
            if len(body.operands) not in {1, 2}:
                raise AssemblerError(
                    body.token.file,
                    body.token.line,
                    body.token.column,
                    "space expects COUNT or COUNT, VALUE",
                )
            count = _value(body.operands[0], symbols, location)
            if count < 0:
                token = body.operands[0].first()
                raise AssemblerError(
                    token.file,
                    token.line,
                    token.column,
                    "space count must not be negative",
                )
            location += count
        if location > 0x10000:
            raise AssemblerError(
                body.token.file,
                body.token.line,
                body.token.column,
                "output exceeds the 16-bit word address space",
            )
    return symbols


@dataclass(frozen=True)
class ListingEntry:
    address: int
    word: int
    source: str
    continuation: bool = False


@dataclass(frozen=True)
class AssemblyResult:
    words: dict[int, int]
    symbols: dict[str, int]
    listing: tuple[ListingEntry, ...]

    def dense_words(self) -> list[int]:
        if not self.words:
            return []
        return [self.words.get(address, 0) for address in range(max(self.words) + 1)]

    def to_binary(self) -> bytes:
        result = bytearray()
        for word in self.dense_words():
            result.extend(((word >> 8) & 0xFF, word & 0xFF))
        return bytes(result)

    def to_hex(self, *, annotated: bool = False) -> str:
        lines: list[str] = []
        previous: int | None = None
        entries = {entry.address: entry for entry in self.listing}
        for address in sorted(self.words):
            if previous is None:
                if address != 0:
                    lines.append(f"@{address:04X}")
            elif address != previous + 1:
                lines.append(f"@{address:04X}")
            word_text = f"{self.words[address]:04X}"
            if annotated:
                entry = entries[address]
                suffix = " [second word]" if entry.continuation else ""
                source = entry.source.strip() or "<generated>"
                word_text += f"  // {address:04X}: {source}{suffix}"
            lines.append(word_text)
            previous = address
        return "\n".join(lines) + ("\n" if lines else "")

    def to_bytecode(self) -> str:
        return "\n".join(
            f"0x{word >> 8:02X} 0x{word & 0xFF:02X}" for word in self.dense_words()
        ) + ("\n" if self.words else "")

    def render(self, output_format: OutputFormat) -> str | bytes:
        if output_format == "hex":
            return self.to_hex()
        if output_format == "annotated-hex":
            return self.to_hex(annotated=True)
        if output_format == "bytecode":
            return self.to_bytecode()
        if output_format == "binary":
            return self.to_binary()
        raise ValueError(f"unknown output format: {output_format}")


def _write_word(
    words: dict[int, int],
    listing: list[ListingEntry],
    address: int,
    word: int,
    statement: Statement,
    *,
    continuation: bool = False,
) -> None:
    if not 0 <= address <= 0xFFFF:
        token = (
            statement.body.token if statement.body is not None else statement.labels[0]
        )
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            f"address 0x{address:X} is outside the 16-bit word address space",
        )
    if address in words:
        token = (
            statement.body.token if statement.body is not None else statement.labels[0]
        )
        raise AssemblerError(
            token.file,
            token.line,
            token.column,
            f"word address 0x{address:04X} is written more than once",
        )
    words[address] = word & 0xFFFF
    listing.append(ListingEntry(address, word & 0xFFFF, statement.source, continuation))


def _emit_directive(
    statement: Statement,
    directive: Directive,
    symbols: Mapping[str, int],
    words: dict[int, int],
    listing: list[ListingEntry],
) -> None:
    address = statement.address or 0
    if directive.name in {"org", "section", "equ"}:
        return
    if directive.name in {"word", "dw", "byte", "db"}:
        bits = 8 if directive.name in {"byte", "db"} else 16
        for offset, operand in enumerate(directive.operands):
            value = _bit_pattern(
                _value(operand, symbols, address + offset),
                bits,
                operand.first(),
                directive.name,
            )
            _write_word(words, listing, address + offset, value, statement)
        return
    if directive.name == "string":
        offset = 0
        for operand in directive.operands:
            token = operand.tokens[0]
            assert isinstance(token.value, str)
            for char in token.value:
                code = ord(char)
                if code > 0xFF:
                    raise AssemblerError(
                        token.file,
                        token.line,
                        token.column,
                        "string contains a character outside the 8-bit range",
                    )
                _write_word(words, listing, address + offset, code, statement)
                offset += 1
        return
    if directive.name == "space":
        count = _value(directive.operands[0], symbols, address)
        fill = (
            _value(directive.operands[1], symbols, address)
            if len(directive.operands) == 2
            else 0
        )
        fill = _bit_pattern(fill, 16, directive.operands[-1].first(), "space fill")
        for offset in range(count):
            _write_word(words, listing, address + offset, fill, statement)
        return
    raise AssemblerError(
        directive.token.file,
        directive.token.line,
        directive.token.column,
        f"unsupported directive '{directive.name}'",
    )


def assemble(source: str, *, filename: str = "<string>") -> AssemblyResult:
    statements = parse_source(source, filename)
    symbols = layout(statements)
    words: dict[int, int] = {}
    listing: list[ListingEntry] = []
    for statement in statements:
        body = statement.body
        if body is None:
            continue
        address = statement.address or 0
        if isinstance(body, Directive):
            _emit_directive(statement, body, symbols, words, listing)
            continue
        for offset, word in enumerate(encode_instruction(body, symbols, address)):
            _write_word(
                words,
                listing,
                address + offset,
                word,
                statement,
                continuation=offset > 0,
            )
    return AssemblyResult(words, symbols, tuple(listing))


def assemble_file(path: str | Path) -> AssemblyResult:
    source_path = Path(path)
    return assemble(source_path.read_text(encoding="utf-8"), filename=str(source_path))


def write_output(
    result: AssemblyResult, path: str | Path, output_format: OutputFormat
) -> None:
    output_path = Path(path)
    rendered = result.render(output_format)
    if isinstance(rendered, bytes):
        output_path.write_bytes(rendered)
    else:
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
