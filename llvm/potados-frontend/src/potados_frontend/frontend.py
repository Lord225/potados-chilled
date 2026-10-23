"""Translate a native-word C dialect into LLVM's integer/target-operation IR.

C addressable units are 16 bits. LLVM's ordinary octet-based object layout is
used only for private backing storage; no ordinary LLVM load, store, GEP, or
pointer-to-integer assumption implements a C memory operation. Explicit target
operations carry native addresses through optimization without byte aliasing.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import subprocess
from typing import Any

from llvmlite import ir
from pycparser import c_ast, c_parser

DATA_LAYOUT = "e-m:e-p:16:16-i32:16-i64:16-f32:16-f64:16-a:8-n8:16-S16"
I16 = ir.IntType(16)


class FrontendError(ValueError):
    """The source is invalid or uses an unsupported freestanding C construct."""


@dataclass(eq=False)
class CType:
    kind: str
    bits: int = 16
    signed: bool = True
    base: CType | None = None
    count: int = 0
    fields: list[tuple[str, CType]] = field(default_factory=list)
    params: list[CType] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    volatile: bool = False
    tag: str = ""
    rank: int = 3

    @property
    def size(self) -> int:
        if self.kind == "array":
            return self.count * self.base.size
        if self.kind == "struct":
            return sum(t.size for _, t in self.fields)
        if self.kind == "union":
            return max((t.size for _, t in self.fields), default=0)
        if self.kind in {"void", "function"}:
            raise FrontendError(f"sizeof({self.kind}) is not supported")
        return max(1, (self.bits + 15) // 16)

    @property
    def aggregate(self) -> bool:
        return self.kind in {"array", "struct", "union"}

    def llvm(self) -> ir.Type:
        if self.kind == "void":
            return ir.VoidType()
        if self.kind == "array":
            return ir.ArrayType(self.base.llvm(), self.count)
        if self.kind == "struct":
            return ir.LiteralStructType([t.llvm() for _, t in self.fields])
        if self.kind == "union":
            return ir.ArrayType(I16, self.size)
        if self.kind in {"pointer", "function"}:
            return I16
        return ir.IntType(self.bits)

    def function_llvm(self) -> ir.FunctionType:
        assert self.kind == "function"
        return ir.FunctionType(self.base.llvm(), [p.llvm() for p in self.params])


SINT = CType("int")
UINT = CType("int", signed=False)
VOID = CType("void", bits=0)


def pointer(base: CType, *, volatile: bool = False) -> CType:
    return CType("pointer", signed=False, base=base, volatile=volatile)


@dataclass
class Value:
    value: Any
    type: CType


@dataclass
class Object:
    address: Any
    type: CType
    function: ir.Function | None = None
    constant: int | None = None


class Compiler:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.module = ir.Module(name=Path(filename).name)
        self.module.triple = "unknown-unknown-none"
        self.module.data_layout = DATA_LAYOUT
        flag = self.module.add_metadata([ir.Constant(ir.IntType(32), 1),
                                         ir.MetaDataString(self.module, "potados.word-addressed"),
                                         ir.Constant(ir.IntType(32), 1)])
        self.module.add_named_metadata("llvm.module.flags").add(flag)
        self.typedefs: dict[str, CType] = {}
        self.records: dict[tuple[str, str], CType] = {}
        self.global_scope: dict[str, Object] = {}
        self.scopes: list[dict[str, Object]] = [self.global_scope]
        self.functions: dict[str, tuple[CType, ir.Function]] = {}
        self.aliases: dict[str, str] = {}
        self.builder: ir.IRBuilder | None = None
        self.function: ir.Function | None = None
        self.return_type = VOID
        self.breaks: list[Any] = []
        self.continues: list[Any] = []
        self.labels: dict[str, Any] = {}
        self.counter = 0
        self.address_op = ir.Function(self.module, ir.FunctionType(I16, [ir.PointerType()]), "__potados_address")
        self.memory_ops: dict[tuple[bool, bool], ir.Function] = {}
        for store in (False, True):
            for volatile in (False, True):
                name = "__potados_" + ("store_" if store else "load_") + ("volatile_" if volatile else "") + "word"
                typ = ir.FunctionType(ir.VoidType() if store else I16, [I16, I16] if store else [I16])
                self.memory_ops[store, volatile] = ir.Function(self.module, typ, name)

    def error(self, node: Any, message: str) -> Any:
        coord = getattr(node, "coord", None)
        raise FrontendError(f"{coord or self.filename}: {message}")

    def lookup(self, name: str, node: Any = None) -> Object:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.error(node, f"unknown identifier '{name}'")

    def ctype(self, node: Any, initializer: Any = None) -> CType:
        if isinstance(node, (c_ast.Decl, c_ast.Typedef, c_ast.Typename)):
            return self.ctype(node.type, initializer)
        if isinstance(node, c_ast.TypeDecl):
            t = self.ctype(node.type, initializer)
            return replace(t, volatile=t.volatile or "volatile" in (node.quals or []))
        if isinstance(node, c_ast.IdentifierType):
            names = node.names
            if len(names) == 1 and names[0] in self.typedefs:
                return self.typedefs[names[0]]
            if "void" in names:
                return VOID
            if any(n in names for n in ("float", "double", "_Complex")):
                self.error(node, "floating point is not supported by the POTADOS frontend")
            if "_Bool" in names:
                return CType("bool", signed=False, rank=0)
            if not all(n in {"signed", "unsigned", "char", "short", "int", "long"} for n in names):
                self.error(node, f"unsupported type {' '.join(names)}")
            longs = names.count("long")
            bits = 64 if longs > 1 else 32 if longs else 16
            rank = 5 if longs > 1 else 4 if longs else 1 if "char" in names else 2 if "short" in names else 3
            return CType("int", bits, "unsigned" not in names, rank=rank)
        if isinstance(node, c_ast.PtrDecl):
            return pointer(self.ctype(node.type), volatile="volatile" in (node.quals or []))
        if isinstance(node, c_ast.ArrayDecl):
            if node.dim is None:
                if isinstance(initializer, c_ast.InitList):
                    count = len(initializer.exprs or [])
                elif isinstance(initializer, c_ast.Constant) and initializer.type == "string":
                    count = len(self.string(initializer.value)) + 1
                else:
                    self.error(node, "array bound must be known at compile time")
            else:
                try:
                    count = self.const_int(node.dim)
                except FrontendError:
                    self.error(node, "variable-length arrays are not supported")
            if count < 0:
                self.error(node, "negative array size")
            return CType("array", base=self.ctype(node.type), count=count)
        if isinstance(node, c_ast.FuncDecl):
            params, names = [], []
            for p in node.args.params if node.args else []:
                if isinstance(p, c_ast.EllipsisParam):
                    self.error(p, "variadic functions are not supported")
                t = self.ctype(p)
                if t.kind == "void":
                    continue
                if t.kind == "array":
                    t = pointer(t.base)
                if t.kind == "function":
                    t = pointer(t)
                if t.aggregate:
                    self.error(p, "aggregate arguments by value are not supported")
                params.append(t)
                names.append(getattr(p, "name", None) or f"arg{len(names)}")
            ret = self.ctype(node.type)
            if ret.aggregate:
                self.error(node, "aggregate returns are not supported")
            return CType("function", base=ret, params=params, names=names)
        if isinstance(node, (c_ast.Struct, c_ast.Union)):
            kind = "struct" if isinstance(node, c_ast.Struct) else "union"
            key = kind, node.name or f"anonymous_{id(node)}"
            if key not in self.records:
                self.records[key] = CType(kind, tag=node.name or "")
            result = self.records[key]
            if node.decls is not None:
                if any(d.bitsize is not None for d in node.decls):
                    self.error(node, "bit-fields are not supported")
                # Qualifier copies and recursive pointers share this field list.
                result.fields[:] = [(d.name, self.ctype(d)) for d in node.decls]
            return result
        if isinstance(node, c_ast.Enum):
            next_value = 0
            for enumerator in node.values.enumerators if node.values else []:
                next_value = self.const_int(enumerator.value) if enumerator.value else next_value
                self.scopes[-1][enumerator.name] = Object(None, SINT, constant=next_value)
                next_value += 1
            return SINT
        self.error(node, f"unsupported type node {type(node).__name__}")

    @staticmethod
    def string(text: str) -> str:
        # C hexadecimal escapes consume all hex digits; Python's \x escape
        # consumes exactly two and cannot describe a native 16-bit character.
        fragments = re.findall(r'(?:u8|[LuU])?("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', text)
        output = []
        simple = dict(zip("abfnrtv\\\'\"?", "\a\b\f\n\r\t\v\\\'\"?"))
        for fragment in fragments:
            content, index = fragment[1:-1], 0
            while index < len(content):
                char = content[index]
                index += 1
                if char != "\\":
                    output.append(char)
                    continue
                escape = content[index]
                index += 1
                if escape in simple:
                    output.append(simple[escape])
                elif escape in "x01234567uU":
                    pattern = r"[0-9a-fA-F]+" if escape == "x" else r"[0-7]{0,2}" if escape.isdigit() else r"[0-9a-fA-F]{" + ("4" if escape == "u" else "8") + "}"
                    match = re.match(pattern, content[index:])
                    digits = (escape if escape.isdigit() else "") + (match[0] if match else "")
                    if not digits:
                        raise FrontendError("invalid C character escape")
                    value = int(digits, 8 if escape.isdigit() else 16)
                    if value > 65535:
                        raise FrontendError("character escape exceeds the native 16-bit character range")
                    output.append(chr(value))
                    index += len(match[0]) if match else 0
                else:
                    raise FrontendError(f"unsupported C character escape \\{escape}")
        return "".join(output)

    def constant_type(self, node: c_ast.Constant) -> CType:
        if node.type == "char":
            return SINT
        if node.type == "string":
            return CType("array", base=CType("int", rank=1), count=len(self.string(node.value)) + 1)
        if node.type in {"float", "double", "long double"}:
            self.error(node, "floating point is not supported by the POTADOS frontend")
        raw = node.value.lower()
        suffix = re.search(r"[ul]+$", raw)
        suff = suffix[0] if suffix else ""
        integer = self.literal_integer(raw)
        decimal = not (raw.startswith(("0x", "0b")) or (len(raw) > 1 and raw.startswith("0")))
        ranks = [(16, 3), (32, 4), (64, 5)]
        if "ll" in suff:
            ranks = ranks[2:]
        elif "l" in suff:
            ranks = ranks[1:]
        for bits, rank in ranks:
            signedness = [False] if "u" in suff else [True] if decimal else [True, False]
            for signed in signedness:
                if integer < (1 << (bits - int(signed))):
                    return CType("int", bits, signed, rank=rank)
        self.error(node, "integer literal exceeds the native 64-bit integer range")

    @staticmethod
    def normalize_integer(value: int, typ: CType) -> int:
        if typ.kind == "bool":
            return int(value != 0)
        value &= (1 << typ.bits) - 1
        return value - (1 << typ.bits) if typ.signed and value & (1 << (typ.bits - 1)) else value

    @staticmethod
    def literal_integer(raw: str) -> int:
        raw = re.sub(r"[uUlL]+$", "", raw)
        if raw.startswith(("0x", "0X", "0b", "0B")):
            return int(raw, 0)
        return int(raw, 8 if len(raw) > 1 and raw.startswith("0") else 10)

    def const_int(self, node: Any) -> int:
        if node is None:
            return 0
        if isinstance(node, c_ast.Constant):
            if node.type == "char":
                value = self.string(node.value)
                if len(value) != 1:
                    self.error(node, "multi-character character literals are unsupported")
                return ord(value)
            return self.normalize_integer(self.literal_integer(node.value), self.constant_type(node))
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) and node.name.name == "__potados_offsetof":
            args = node.args.exprs
            typ = self.ctype(args[0].to_type).base
            path = self.string(args[1].value)
            offset = 0
            for member in path.split("."):
                match = re.fullmatch(r"([A-Za-z_]\w*)(?:\[(\d+)\])?", member)
                if not match:
                    self.error(node, "unsupported offsetof member designator")
                for name, field_type in typ.fields:
                    if name == match[1]:
                        typ = field_type
                        break
                    if typ.kind != "union":
                        offset += field_type.size
                else:
                    self.error(node, "unknown offsetof member")
                if match[2] is not None:
                    offset += int(match[2]) * typ.base.size
                    typ = typ.base
            return offset
        if isinstance(node, c_ast.ID):
            obj = self.lookup(node.name, node)
            if obj.constant is not None:
                return obj.constant
        if isinstance(node, c_ast.Cast):
            t = self.ctype(node.to_type)
            return self.normalize_integer(self.const_int(node.expr), t)
        if isinstance(node, c_ast.UnaryOp):
            if node.op == "sizeof":
                return self.ctype(node.expr).size if isinstance(node.expr, c_ast.Typename) else self.typeof(node.expr).size
            if node.op in {"_Alignof", "alignof"}:
                return 1
            a = self.const_int(node.expr)
            result = {"+": lambda: a, "-": lambda: -a, "~": lambda: ~a, "!": lambda: int(not a)}[node.op]()
            return self.normalize_integer(result, self.typeof(node))
        if isinstance(node, c_ast.BinaryOp):
            a = self.const_int(node.left)
            if node.op == "&&" and not a:
                return 0
            if node.op == "||" and a:
                return 1
            b = self.const_int(node.right)
            typ = self.promote(self.typeof(node.left)) if node.op in {"<<", ">>"} else self.common(self.typeof(node.left), self.typeof(node.right))
            a, b = self.normalize_integer(a, typ), self.normalize_integer(b, typ)
            table = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
                     "/": lambda: abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1),
                     "%": lambda: a - (abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)) * b,
                     "<<": lambda: a << b, ">>": lambda: a >> b, "&": lambda: a & b,
                     "|": lambda: a | b, "^": lambda: a ^ b, "==": lambda: int(a == b),
                     "!=": lambda: int(a != b), "<": lambda: int(a < b), ">": lambda: int(a > b),
                     "<=": lambda: int(a <= b), ">=": lambda: int(a >= b),
                     "&&": lambda: int(bool(a) and bool(b)), "||": lambda: int(bool(a) or bool(b))}
            if node.op in table:
                return self.normalize_integer(table[node.op](), self.typeof(node))
        if isinstance(node, c_ast.TernaryOp):
            return self.const_int(node.iftrue if self.const_int(node.cond) else node.iffalse)
        self.error(node, "expected an integer constant expression")

    def promote(self, t: CType) -> CType:
        if t.kind == "bool":
            return SINT
        if t.kind == "int" and t.rank < 3:
            return UINT if not t.signed and t.bits == 16 else SINT
        return t

    def common(self, a: CType, b: CType) -> CType:
        a, b = self.promote(a), self.promote(b)
        if a.kind == "pointer":
            return a
        if b.kind == "pointer":
            return b
        if a.signed == b.signed:
            return a if a.rank >= b.rank else b
        unsigned, signed = (a, b) if not a.signed else (b, a)
        if unsigned.rank >= signed.rank:
            return unsigned
        if signed.bits > unsigned.bits:
            return signed
        return replace(signed, signed=False)

    def typeof(self, node: Any) -> CType:
        if isinstance(node, c_ast.ID):
            return self.lookup(node.name, node).type
        if isinstance(node, c_ast.Constant):
            return self.constant_type(node)
        if isinstance(node, c_ast.Cast):
            return self.ctype(node.to_type)
        if isinstance(node, c_ast.ArrayRef):
            t = self.typeof(node.name)
            return t.base
        if isinstance(node, c_ast.StructRef):
            t = self.typeof(node.name)
            t = t.base if node.type == "->" else t
            return next(t for name, t in t.fields if name == node.field.name)
        if isinstance(node, c_ast.UnaryOp):
            t = self.typeof(node.expr) if not isinstance(node.expr, c_ast.Typename) else self.ctype(node.expr)
            if node.op == "&":
                return pointer(t)
            if node.op == "*":
                return t.base
            if node.op in {"sizeof", "_Alignof", "alignof"}:
                return UINT
            return SINT if node.op == "!" else self.promote(t) if node.op in {"+", "-", "~"} else t
        if isinstance(node, c_ast.BinaryOp):
            if node.op in {"==", "!=", "<", ">", "<=", ">=", "&&", "||"}:
                return SINT
            a, b = self.typeof(node.left), self.typeof(node.right)
            if node.op == "-" and a.kind == b.kind == "pointer":
                return SINT
            if a.kind == "array":
                a = pointer(a.base)
            if b.kind == "array":
                b = pointer(b.base)
            return self.promote(a) if node.op in {"<<", ">>"} else self.common(a, b)
        if isinstance(node, c_ast.TernaryOp):
            return self.common(self.typeof(node.iftrue), self.typeof(node.iffalse))
        if isinstance(node, c_ast.Assignment):
            return self.typeof(node.lvalue)
        if isinstance(node, c_ast.FuncCall):
            if isinstance(node.name, c_ast.ID) and node.name.name == "__potados_offsetof":
                return UINT
            t = self.typeof(node.name)
            return (t.base if t.kind == "pointer" else t).base
        if isinstance(node, c_ast.ExprList):
            return self.typeof(node.exprs[-1])
        self.error(node, f"cannot determine type of {type(node).__name__}")

    def cast(self, value: Value, target: CType) -> Value:
        if target.kind == "void":
            return Value(None, target)
        source = value.type
        if source.kind == "array":
            source = pointer(source.base)
        if source.kind == "function":
            source = pointer(source)
        if target.kind == "bool":
            return Value(self.builder.zext(self.truth(value), I16), target)
        if source.aggregate or target.aggregate:
            if source is target:
                return value
            raise FrontendError("unsupported aggregate conversion")
        bits = target.bits
        raw = value.value
        if raw.type.width < bits:
            raw = (self.builder.sext if source.signed and source.kind == "int" else self.builder.zext)(raw, ir.IntType(bits))
        elif raw.type.width > bits:
            raw = self.builder.trunc(raw, ir.IntType(bits))
        return Value(raw, target)

    def truth(self, value: Value) -> Any:
        return self.builder.icmp_unsigned("!=", value.value, ir.Constant(value.value.type, 0))

    def object_address(self, obj: Object) -> Any:
        if isinstance(obj.address.type, ir.PointerType):
            return self.builder.call(self.address_op, [obj.address])
        return obj.address

    def addr_add(self, address: Any, offset: int | Any) -> Any:
        if isinstance(offset, int):
            if not offset:
                return address
            offset = ir.Constant(I16, offset & 0xFFFF)
        return self.builder.add(address, offset)

    def load(self, address: Any, typ: CType, *, volatile: bool = False) -> Value:
        if typ.aggregate or typ.kind == "function":
            return Value(address, typ)
        words = typ.size
        out = None
        for index in range(words):
            word = self.builder.call(self.memory_ops[False, volatile or typ.volatile], [self.addr_add(address, index)])
            part = word if typ.bits == 16 else self.builder.zext(word, typ.llvm())
            if index:
                part = self.builder.shl(part, ir.Constant(typ.llvm(), index * 16))
            out = part if out is None else self.builder.or_(out, part)
        if typ.kind == "bool":
            out = self.builder.zext(self.builder.icmp_unsigned("!=", out, ir.Constant(I16, 0)), I16)
        return Value(out, typ)

    def store(self, address: Any, typ: CType, value: Value, *, volatile: bool = False) -> None:
        if typ.aggregate:
            if not value.type.aggregate:
                raise FrontendError("aggregate assignment requires compatible object")
            for index in range(typ.size):
                v = self.load(self.addr_add(value.value, index), UINT)
                self.store(self.addr_add(address, index), UINT, v, volatile=volatile or typ.volatile)
            return
        value = self.cast(value, typ)
        for index in range(typ.size):
            part = value.value
            if index:
                part = self.builder.lshr(part, ir.Constant(part.type, index * 16))
            if part.type.width != 16:
                part = self.builder.trunc(part, I16)
            self.builder.call(self.memory_ops[True, volatile or typ.volatile], [self.addr_add(address, index), part])

    def lvalue(self, node: Any) -> tuple[Any, CType]:
        if isinstance(node, c_ast.ID):
            obj = self.lookup(node.name, node)
            if obj.function is not None:
                self.error(node, "function is not a writable object")
            return self.object_address(obj), obj.type
        if isinstance(node, c_ast.UnaryOp) and node.op == "*":
            p = self.expression(node.expr)
            if p.type.kind != "pointer":
                self.error(node, "indirection requires a pointer")
            return p.value, p.type.base
        if isinstance(node, c_ast.ArrayRef):
            p = self.expression(node.name)
            index = self.cast(self.expression(node.subscript), UINT)
            if p.type.kind == "array":
                p = Value(p.value, pointer(p.type.base))
            if p.type.kind != "pointer":
                self.error(node, "indexing requires an array or pointer")
            stride = p.type.base.size
            offset = index.value if stride == 1 else self.builder.mul(index.value, ir.Constant(I16, stride))
            return self.addr_add(p.value, offset), p.type.base
        if isinstance(node, c_ast.StructRef):
            if node.type == "->":
                p = self.expression(node.name)
                address, typ = p.value, p.type.base
            else:
                address, typ = self.lvalue(node.name)
            offset = 0
            for name, field_type in typ.fields:
                if name == node.field.name:
                    return self.addr_add(address, offset), replace(field_type, volatile=field_type.volatile or typ.volatile)
                if typ.kind != "union":
                    offset += field_type.size
            self.error(node, f"unknown field '{node.field.name}'")
        self.error(node, "expression is not an lvalue")

    def expression(self, node: Any) -> Value:
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID) and node.name.name == "__potados_offsetof":
            return Value(ir.Constant(I16, self.const_int(node)), UINT)
        if isinstance(node, c_ast.ID):
            obj = self.lookup(node.name, node)
            if obj.constant is not None:
                return Value(ir.Constant(I16, obj.constant & 0xFFFF), obj.type)
            if obj.function is not None:
                return Value(self.builder.call(self.address_op, [obj.function]), pointer(obj.type))
            if obj.type.kind == "array":
                return Value(self.object_address(obj), pointer(obj.type.base))
            return self.load(self.object_address(obj), obj.type)
        if isinstance(node, c_ast.Constant):
            typ = self.constant_type(node)
            if node.type == "string":
                text = self.string(node.value)
                vals = [ord(c) for c in text] + [0]
                if any(v > 65535 for v in vals):
                    self.error(node, "string character exceeds the native 16-bit character range")
                name = f"__potados_string_{self.counter}"
                self.counter += 1
                g = ir.GlobalVariable(self.module, ir.ArrayType(I16, len(vals)), name)
                g.initializer = ir.Constant(g.value_type, [ir.Constant(I16, v) for v in vals])
                g.linkage = "internal"
                return Value(self.builder.call(self.address_op, [g]), pointer(typ.base))
            return Value(ir.Constant(typ.llvm(), self.const_int(node) & ((1 << typ.bits) - 1)), typ)
        if isinstance(node, (c_ast.ArrayRef, c_ast.StructRef)):
            return self.load(*self.lvalue(node))
        if isinstance(node, c_ast.Cast):
            return self.cast(self.expression(node.expr), self.ctype(node.to_type))
        if isinstance(node, c_ast.Assignment):
            address, typ = self.lvalue(node.lvalue)
            rhs = self.expression(node.rvalue)
            if node.op != "=":
                rhs = self.binary(node.op[:-1], self.load(address, typ), rhs)
            rhs = self.cast(rhs, typ) if not typ.aggregate else rhs
            self.store(address, typ, rhs)
            return rhs
        if isinstance(node, c_ast.UnaryOp):
            op = node.op
            if op in {"sizeof", "_Alignof", "alignof"}:
                return Value(ir.Constant(I16, self.const_int(node)), UINT)
            if op == "&":
                if isinstance(node.expr, c_ast.ID) and self.lookup(node.expr.name).function is not None:
                    return self.expression(node.expr)
                a, t = self.lvalue(node.expr)
                return Value(a, pointer(t))
            if op == "*":
                p = self.expression(node.expr)
                if p.type.base.kind == "function":
                    return p
                return self.load(p.value, p.type.base)
            if op in {"++", "--", "p++", "p--"}:
                address, typ = self.lvalue(node.expr)
                old = self.load(address, typ)
                new = self.binary("+" if "+" in op else "-", old, Value(ir.Constant(I16, 1), SINT))
                new = self.cast(new, typ)
                self.store(address, typ, new)
                return old if op.startswith("p") else new
            value = self.expression(node.expr)
            if op == "!":
                return Value(self.builder.zext(self.builder.not_(self.truth(value)), I16), SINT)
            value = self.cast(value, self.promote(value.type))
            if op == "+":
                return value
            if op == "-":
                return Value(self.builder.neg(value.value), value.type)
            if op == "~":
                return Value(self.builder.not_(value.value), value.type)
            self.error(node, f"unsupported unary operator {op}")
        if isinstance(node, c_ast.BinaryOp):
            if node.op in {"&&", "||"}:
                left = self.truth(self.expression(node.left))
                prior = self.builder.block
                right_block = self.function.append_basic_block("logic.rhs")
                end = self.function.append_basic_block("logic.end")
                if node.op == "&&":
                    self.builder.cbranch(left, right_block, end)
                else:
                    self.builder.cbranch(left, end, right_block)
                self.builder.position_at_end(right_block)
                right = self.truth(self.expression(node.right))
                right_prior = self.builder.block
                self.builder.branch(end)
                self.builder.position_at_end(end)
                phi = self.builder.phi(ir.IntType(1))
                phi.add_incoming(ir.Constant(ir.IntType(1), node.op == "||"), prior)
                phi.add_incoming(right, right_prior)
                return Value(self.builder.zext(phi, I16), SINT)
            return self.binary(node.op, self.expression(node.left), self.expression(node.right))
        if isinstance(node, c_ast.TernaryOp):
            condition = self.truth(self.expression(node.cond))
            true_block = self.function.append_basic_block("select.true")
            false_block = self.function.append_basic_block("select.false")
            end = self.function.append_basic_block("select.end")
            self.builder.cbranch(condition, true_block, false_block)
            self.builder.position_at_end(true_block)
            a = self.expression(node.iftrue)
            common = self.common(self.typeof(node.iftrue), self.typeof(node.iffalse))
            a = self.cast(a, common)
            a_block = self.builder.block
            self.builder.branch(end)
            self.builder.position_at_end(false_block)
            b = self.cast(self.expression(node.iffalse), common)
            b_block = self.builder.block
            self.builder.branch(end)
            self.builder.position_at_end(end)
            if common.kind == "void":
                return Value(None, VOID)
            phi = self.builder.phi(common.llvm())
            phi.add_incoming(a.value, a_block)
            phi.add_incoming(b.value, b_block)
            return Value(phi, common)
        if isinstance(node, c_ast.FuncCall):
            if isinstance(node.name, c_ast.ID) and node.name.name in {"__asm__", "__asm", "asm"}:
                self.error(node, "inline assembly is not supported; supply target assembly or LLVM IR")
            if isinstance(node.name, c_ast.ID) and node.name.name in {"__builtin_offsetof", "offsetof"}:
                self.error(node, "offsetof must be expanded by the native header")
            if isinstance(node.name, c_ast.ID) and node.name.name in self.functions:
                typ, function = self.functions[node.name.name]
            else:
                callee = self.expression(node.name)
                typ = callee.type.base
                if typ.kind != "function":
                    self.error(node, "called expression is not a function pointer")
                function = self.builder.inttoptr(callee.value, typ.function_llvm().as_pointer())
            arguments = list(node.args.exprs) if node.args else []
            if len(arguments) != len(typ.params):
                self.error(node, "function argument count does not match prototype")
            args = [self.cast(self.expression(arg), t).value for arg, t in zip(arguments, typ.params)]
            return Value(self.builder.call(function, args), typ.base)
        if isinstance(node, c_ast.ExprList):
            value = Value(None, VOID)
            for expr in node.exprs:
                value = self.expression(expr)
            return value
        self.error(node, f"unsupported expression {type(node).__name__}")

    def binary(self, op: str, a: Value, b: Value) -> Value:
        if a.type.kind == "pointer" or b.type.kind == "pointer":
            if op == "+" and b.type.kind == "pointer":
                a, b = b, a
            if op in {"+", "-"} and a.type.kind == "pointer":
                if b.type.kind == "pointer":
                    if op != "-":
                        raise FrontendError("two pointers cannot be added")
                    diff = self.builder.sub(a.value, b.value)
                    if a.type.base.size > 1:
                        diff = self.builder.sdiv(diff, ir.Constant(I16, a.type.base.size))
                    return Value(diff, SINT)
                index = self.cast(b, UINT).value
                if a.type.base.size > 1:
                    index = self.builder.mul(index, ir.Constant(I16, a.type.base.size))
                return Value((self.builder.add if op == "+" else self.builder.sub)(a.value, index), a.type)
            if op not in {"==", "!=", "<", ">", "<=", ">="}:
                raise FrontendError(f"invalid pointer operator {op}")
            a, b = self.cast(a, UINT), self.cast(b, UINT)
        typ = self.promote(a.type) if op in {"<<", ">>"} else self.common(a.type, b.type)
        a, b = self.cast(a, typ), self.cast(b, typ)
        x, y = a.value, b.value
        if op in {"==", "!=", "<", ">", "<=", ">="}:
            result = (self.builder.icmp_signed if typ.signed else self.builder.icmp_unsigned)(op, x, y)
            return Value(self.builder.zext(result, I16), SINT)
        operators = {"+": self.builder.add, "-": self.builder.sub, "*": self.builder.mul,
                     "/": self.builder.sdiv if typ.signed else self.builder.udiv,
                     "%": self.builder.srem if typ.signed else self.builder.urem,
                     "&": self.builder.and_, "|": self.builder.or_, "^": self.builder.xor,
                     "<<": self.builder.shl, ">>": self.builder.ashr if typ.signed else self.builder.lshr}
        if op not in operators:
            raise FrontendError(f"unsupported binary operator {op}")
        return Value(operators[op](x, y), typ)

    def static_initializer(self, typ: CType, init: Any) -> Any:
        if init is None:
            return ir.Constant(typ.llvm(), None)
        if typ.kind == "array":
            if isinstance(init, c_ast.Constant) and init.type == "string":
                values = [ord(c) for c in self.string(init.value)] + [0]
                return ir.Constant(typ.llvm(), [ir.Constant(typ.base.llvm(), values[i] if i < len(values) else 0) for i in range(typ.count)])
            values = init.exprs if isinstance(init, c_ast.InitList) else [init]
            if len(values) > typ.count:
                self.error(init, "too many array initializer elements")
            return ir.Constant(typ.llvm(), [self.static_initializer(typ.base, values[i] if i < len(values) else None) for i in range(typ.count)])
        if typ.kind == "struct":
            values = init.exprs if isinstance(init, c_ast.InitList) else [init]
            return ir.Constant(typ.llvm(), [self.static_initializer(t, values[i] if i < len(values) else None) for i, (_, t) in enumerate(typ.fields)])
        if typ.kind == "union":
            self.error(init, "initialized union globals are not supported")
        if isinstance(init, c_ast.InitList):
            init = init.exprs[0]
        if typ.kind == "pointer":
            return self.constant_address(init)
        return ir.Constant(typ.llvm(), self.normalize_integer(self.const_int(init), typ))

    def constant_address(self, node: Any) -> Any:
        if isinstance(node, c_ast.Cast):
            return self.constant_address(node.expr)
        if isinstance(node, c_ast.Constant):
            if node.type == "string":
                values = [ord(c) for c in self.string(node.value)] + [0]
                name = f"__potados_string_{self.counter}"
                self.counter += 1
                storage = ir.GlobalVariable(self.module, ir.ArrayType(I16, len(values)), name)
                storage.linkage = "internal"
                storage.align = 2
                storage.initializer = ir.Constant(storage.value_type, [ir.Constant(I16, value) for value in values])
                return storage.ptrtoint(I16)
            return ir.Constant(I16, self.const_int(node) & 0xFFFF)
        if isinstance(node, c_ast.ID):
            obj = self.global_scope.get(node.name)
            if obj is None:
                self.error(node, "static address references an unknown global")
            target = obj.function if obj.function is not None else obj.address
            return target.ptrtoint(I16)
        if isinstance(node, c_ast.UnaryOp) and node.op == "&":
            return self.constant_lvalue(node.expr)[0]
        if isinstance(node, c_ast.BinaryOp) and node.op in {"+", "-"}:
            base = self.constant_address(node.left)
            scale = self.typeof(node.left).base.size
            offset = ir.Constant(I16, self.const_int(node.right) * scale)
            return base.add(offset) if node.op == "+" else base.sub(offset)
        self.error(node, "unsupported static pointer initializer")

    def constant_lvalue(self, node: Any) -> tuple[Any, CType]:
        if isinstance(node, c_ast.ID):
            return self.constant_address(node), self.typeof(node)
        if isinstance(node, c_ast.ArrayRef):
            typ = self.typeof(node.name).base
            base = self.constant_address(node.name)
            return base.add(ir.Constant(I16, self.const_int(node.subscript) * typ.size)), typ
        if isinstance(node, c_ast.StructRef):
            if node.type == "->":
                base, typ = self.constant_address(node.name), self.typeof(node.name).base
            else:
                base, typ = self.constant_lvalue(node.name)
            offset = 0
            for name, field_type in typ.fields:
                if name == node.field.name:
                    return base if offset == 0 else base.add(ir.Constant(I16, offset)), field_type
                if typ.kind != "union":
                    offset += field_type.size
            self.error(node, "unknown static address member")
        if isinstance(node, c_ast.UnaryOp) and node.op == "*":
            return self.constant_address(node.expr), self.typeof(node.expr).base
        self.error(node, "unsupported static object address")

    def local_initializer(self, address: Any, typ: CType, init: Any) -> None:
        if typ.aggregate:
            if not isinstance(init, c_ast.InitList) and not (isinstance(init, c_ast.Constant) and init.type == "string"):
                self.store(address, typ, self.expression(init))
                return
            for index in range(typ.size):
                self.store(self.addr_add(address, index), UINT, Value(ir.Constant(I16, 0), UINT))
            if typ.kind == "array":
                if isinstance(init, c_ast.Constant):
                    values = [ord(c) for c in self.string(init.value)] + [0]
                    for index, value in enumerate(values[:typ.count]):
                        self.store(self.addr_add(address, index), typ.base, Value(ir.Constant(I16, value), SINT))
                else:
                    for index, value in enumerate(init.exprs or []):
                        self.local_initializer(self.addr_add(address, index * typ.base.size), typ.base, value)
            elif typ.kind == "struct":
                offset = 0
                for (_, t), value in zip(typ.fields, init.exprs or []):
                    self.local_initializer(self.addr_add(address, offset), t, value)
                    offset += t.size
            else:
                self.local_initializer(address, typ.fields[0][1], init.exprs[0])
            return
        if isinstance(init, c_ast.InitList):
            init = init.exprs[0]
        self.store(address, typ, self.expression(init))

    def declaration(self, decl: c_ast.Decl) -> None:
        if isinstance(decl.type, c_ast.FuncDecl):
            self.declare_function(decl)
            return
        typ = self.ctype(decl, decl.init)
        if decl.name is None:
            return
        if "extern" in (decl.storage or []):
            if decl.name not in self.global_scope:
                g = ir.GlobalVariable(self.module, typ.llvm(), decl.name)
                self.global_scope[decl.name] = Object(g, typ)
            return
        if "static" in (decl.storage or []):
            self.error(decl, "static local objects are not supported")
        # Put every backing object in a dedicated entry block, before its branch.
        # Its native address is materialized at the declaration's execution point.
        alloc_builder = ir.IRBuilder(self.function.entry_basic_block)
        alloc_builder.position_before(self.function.entry_basic_block.terminator)
        storage = alloc_builder.alloca(typ.llvm(), name=decl.name)
        storage.align = 2
        address = self.builder.call(self.address_op, [storage], name=decl.name + ".wordaddr")
        self.scopes[-1][decl.name] = Object(address, typ)
        if decl.init is not None:
            self.local_initializer(address, typ, decl.init)

    def declare_function(self, decl: c_ast.Decl) -> None:
        typ = self.ctype(decl)
        name = decl.name
        symbol = self.aliases.get(name, name)
        if name in self.functions:
            return
        if name.startswith("__potados_") and name in self.module.globals:
            self.error(decl, "reserved POTADOS target operation name")
        f = ir.Function(self.module, typ.function_llvm(), symbol)
        if "static" in (decl.storage or []):
            f.linkage = "internal"
        self.functions[name] = typ, f
        self.global_scope[name] = Object(None, typ, function=f)

    def statement(self, node: Any) -> None:
        if node is None:
            return
        if isinstance(node, c_ast.Label):
            block = self.labels.setdefault(node.name, self.function.append_basic_block("label." + node.name))
            if not self.builder.block.is_terminated:
                self.builder.branch(block)
            self.builder.position_at_end(block)
            self.statement(node.stmt)
            return
        if self.builder.block.is_terminated:
            return
        if isinstance(node, c_ast.Compound):
            self.scopes.append({})
            for item in node.block_items or []:
                self.statement(item)
            self.scopes.pop()
        elif isinstance(node, c_ast.Decl):
            self.declaration(node)
        elif isinstance(node, c_ast.Typedef):
            self.typedefs[node.name] = self.ctype(node)
        elif isinstance(node, c_ast.DeclList):
            for item in node.decls:
                self.declaration(item)
        elif isinstance(node, c_ast.Return):
            if node.expr is None or self.return_type.kind == "void":
                if node.expr is not None:
                    self.expression(node.expr)
                self.builder.ret_void()
            else:
                self.builder.ret(self.cast(self.expression(node.expr), self.return_type).value)
        elif isinstance(node, c_ast.If):
            a = self.function.append_basic_block("if.then")
            b = self.function.append_basic_block("if.else")
            end = self.function.append_basic_block("if.end")
            self.builder.cbranch(self.truth(self.expression(node.cond)), a, b)
            self.builder.position_at_end(a)
            self.statement(node.iftrue)
            if not self.builder.block.is_terminated:
                self.builder.branch(end)
            self.builder.position_at_end(b)
            self.statement(node.iffalse)
            if not self.builder.block.is_terminated:
                self.builder.branch(end)
            self.builder.position_at_end(end)
        elif isinstance(node, (c_ast.While, c_ast.DoWhile, c_ast.For)):
            self.scopes.append({})
            if isinstance(node, c_ast.For):
                self.statement(node.init)
            condition = self.function.append_basic_block("loop.cond")
            body = self.function.append_basic_block("loop.body")
            advance = self.function.append_basic_block("loop.next")
            end = self.function.append_basic_block("loop.end")
            self.builder.branch(body if isinstance(node, c_ast.DoWhile) else condition)
            self.builder.position_at_end(condition)
            expr = node.cond
            if expr is None:
                self.builder.branch(body)
            else:
                self.builder.cbranch(self.truth(self.expression(expr)), body, end)
            self.breaks.append(end)
            self.continues.append(advance if isinstance(node, c_ast.For) else condition)
            self.builder.position_at_end(body)
            self.statement(node.stmt)
            if not self.builder.block.is_terminated:
                self.builder.branch(advance)
            self.builder.position_at_end(advance)
            if isinstance(node, c_ast.For) and node.next is not None:
                self.expression(node.next)
            self.builder.branch(condition)
            self.breaks.pop()
            self.continues.pop()
            self.builder.position_at_end(end)
            self.scopes.pop()
        elif isinstance(node, c_ast.Break):
            if not self.breaks:
                self.error(node, "break outside loop or switch")
            self.builder.branch(self.breaks[-1])
        elif isinstance(node, c_ast.Continue):
            if not self.continues:
                self.error(node, "continue outside loop")
            self.builder.branch(self.continues[-1])
        elif isinstance(node, c_ast.Goto):
            block = self.labels.setdefault(node.name, self.function.append_basic_block("label." + node.name))
            self.builder.branch(block)
        elif isinstance(node, c_ast.Switch):
            self.switch(node)
        elif isinstance(node, c_ast.StaticAssert):
            if not self.const_int(node.cond):
                self.error(node, "static assertion failed")
        elif isinstance(node, (c_ast.EmptyStatement, c_ast.Pragma)):
            pass
        else:
            self.expression(node)

    def switch(self, node: c_ast.Switch) -> None:
        value = self.expression(node.cond)
        end = self.function.append_basic_block("switch.end")
        items = node.stmt.block_items if isinstance(node.stmt, c_ast.Compound) else [node.stmt]
        default = end
        cases: list[tuple[Any, Any]] = []
        for item in items or []:
            if isinstance(item, c_ast.Case):
                cases.append((item, self.function.append_basic_block("switch.case")))
            elif isinstance(item, c_ast.Default):
                default = self.function.append_basic_block("switch.default")
                cases.append((item, default))
            else:
                self.error(item, "declarations before switch cases are unsupported")
        instruction = self.builder.switch(value.value, default)
        for item, block in cases:
            if isinstance(item, c_ast.Case):
                instruction.add_case(ir.Constant(value.value.type, self.const_int(item.expr)), block)
        self.breaks.append(end)
        for index, (item, block) in enumerate(cases):
            self.builder.position_at_end(block)
            for stmt in item.stmts or []:
                self.statement(stmt)
            if not self.builder.block.is_terminated:
                self.builder.branch(cases[index + 1][1] if index + 1 < len(cases) else end)
        self.breaks.pop()
        self.builder.position_at_end(end)

    def define_function(self, node: c_ast.FuncDef) -> None:
        _, function = self.functions[node.decl.name]
        typ = self.ctype(node.decl)
        if "static" in (node.decl.storage or []):
            function.linkage = "internal"
        self.function = function
        self.return_type = typ.base
        self.labels = {}
        self.scopes = [self.global_scope, {}]
        function.attributes.add("noinline")
        function.attributes.add("nounwind")
        entry = function.append_basic_block("entry")
        body = function.append_basic_block("body")
        ir.IRBuilder(entry).branch(body)
        self.builder = ir.IRBuilder(body)
        for argument, name, t in zip(function.args, typ.names, typ.params):
            argument.name = name
            d = ir.IRBuilder(entry)
            d.position_before(entry.terminator)
            storage = d.alloca(t.llvm(), name=name + ".slot")
            storage.align = 2
            address = self.builder.call(self.address_op, [storage], name=name + ".wordaddr")
            self.scopes[-1][name] = Object(address, t)
            self.store(address, t, Value(argument, t))
        self.statement(node.body)
        if not self.builder.block.is_terminated:
            if self.return_type.kind == "void":
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(self.return_type.llvm(), 0))
        for block in function.blocks:
            if not block.is_terminated:
                ir.IRBuilder(block).unreachable()
        self.scopes = [self.global_scope]

    def compile(self, source: str) -> str:
        # Asm labels are the only GNU asm form accepted. They name a function;
        # inline asm instructions require an LLVM IR input instead.
        label_pattern = re.compile(r'\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*__asm__\s*\(\s*"([^"\\]*)"\s*\)')
        for match in label_pattern.finditer(source):
            self.aliases[match[1]] = match[2]
        source = label_pattern.sub(lambda m: re.sub(r'__asm__\s*\(\s*"[^"\\]*"\s*\)', '', m[0]), source)
        source = re.sub(r"__builtin_offsetof\s*\(\s*([^,()]+),\s*([^()]+)\)",
                        lambda m: '__potados_offsetof((' + m[1] + ' *)0, "' + m[2].strip() + '")', source)
        try:
            tree = c_parser.CParser().parse(source, filename=self.filename)
        except Exception as exc:
            raise FrontendError(str(exc)) from exc
        # First collect types, function declarations, and all backing globals.
        definitions = []
        initializers: list[tuple[Any, CType, Any]] = []
        for node in tree.ext:
            if isinstance(node, c_ast.Typedef):
                self.typedefs[node.name] = self.ctype(node)
            elif isinstance(node, c_ast.FuncDef):
                self.declare_function(node.decl)
                definitions.append(node)
            elif isinstance(node, c_ast.Decl):
                if isinstance(node.type, c_ast.FuncDecl):
                    self.declare_function(node)
                    continue
                typ = self.ctype(node, node.init)
                if node.name is None:
                    continue
                if node.name in self.global_scope:
                    # Repeated tentative definitions share one backing object.
                    if node.init is not None:
                        initializers.append((self.global_scope[node.name].address, typ, node.init))
                    continue
                g = ir.GlobalVariable(self.module, typ.llvm(), node.name)
                g.align = 2
                if "static" in (node.storage or []):
                    g.linkage = "internal"
                self.global_scope[node.name] = Object(g, typ)
                if "extern" not in (node.storage or []):
                    initializers.append((g, typ, node.init))
            elif isinstance(node, c_ast.StaticAssert):
                if not self.const_int(node.cond):
                    self.error(node, "static assertion failed")
            elif isinstance(node, c_ast.Pragma):
                pass
            else:
                self.error(node, f"unsupported declaration {type(node).__name__}")
        for g, typ, initializer in initializers:
            g.initializer = self.static_initializer(typ, initializer)
        # Native global addresses are obtained through the opaque address op,
        # never through LLVM's alignment-aware ptrtoint optimization.
        for definition in definitions:
            self.define_function(definition)
        return str(self.module)


def compile_text(source: str, *, filename: str = "<string>") -> str:
    """Compile already-preprocessed freestanding C with native word semantics."""
    return Compiler(filename).compile(source)


def compile_c(source_path: str | Path, output_path: str | Path, *, clang: str = "clang",
              include_dirs: list[str | Path] | None = None, optimization: str = "O2") -> Path:
    """Preprocess C with Clang, then emit native-word LLVM target-operation IR."""
    source_path, output_path = Path(source_path).resolve(), Path(output_path).resolve()
    root = Path(__file__).resolve().parents[3]
    dirs = [root / "potados-frontend/include", root / "runtime", source_path.parent]
    dirs += [Path(p).resolve() for p in include_dirs or []]
    command = [clang, "-E", "-nostdinc", "-target", "msp430-unknown-none",
               "-Wno-builtin-macro-redefined", "-D__attribute__(x)=", "-D__extension__=",
               "-D__inline__=inline", "-D__restrict__=restrict", "-D__CHAR_BIT__=16",
               "-D__SIZE_TYPE__=unsigned int", "-D__PTRDIFF_TYPE__=int",
               "-D__SIZEOF_POINTER__=1", "-D__SIZEOF_INT__=1", "-D__SIZEOF_SHORT__=1",
               "-D__SIZEOF_LONG__=2", "-D__SIZEOF_LONG_LONG__=4"]
    for directory in dirs:
        command += ["-I", str(directory)]
    command += ["-include", str(root / "potados-frontend/include/native_predefines.h")]
    command.append(str(source_path))
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise FrontendError(result.stderr.strip() or f"{source_path}: C preprocessing failed")
    output = compile_text(result.stdout, filename=str(source_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return output_path
