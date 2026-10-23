"""Native C semantics that must be established before LLVM optimization."""
from pathlib import Path
import sys

import pytest
from llvmlite import binding

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'potados-frontend/src'))
from potados_frontend import FrontendError, compile_c, compile_text


def verified(source: str) -> str:
    output = compile_text(source)
    binding.parse_assembly(output).verify()
    return output


def test_native_sizes_and_member_offsets_are_constant_expressions():
    verified('''
        struct record { char tag; long value; int *pointer; };
        _Static_assert(sizeof(char) == 1, "char");
        _Static_assert(sizeof(int) == 1, "int");
        _Static_assert(sizeof(long) == 2, "long");
        _Static_assert(sizeof(long long) == 4, "long long");
        _Static_assert(sizeof(void *) == 1, "pointer");
        _Static_assert(sizeof(struct record) == 4, "record");
        _Static_assert(__builtin_offsetof(struct record, value) == 1, "field");
        _Static_assert(__builtin_offsetof(struct record, pointer) == 3, "pointer offset");
        int main(void) { return 42; }
    ''')


def test_unsigned_char_has_sixteen_value_bits_and_unsigned_promotion():
    output = verified('''
        _Static_assert((unsigned char)65535U == 65535U, "char value");
        _Static_assert((unsigned char)65535U + 1 == 0, "unsigned promotion");
        _Static_assert(-1 > 1U, "usual arithmetic conversion");
        _Static_assert(0xFFFFU + 1 == 0, "native unsigned wrap");
        _Static_assert(!(0 && (1 / 0)), "unused expression");
        int main(void) { return 42; }
    ''')
    assert 'i8' not in output


def test_native_constant_folding_and_local_array_sizes():
    output = verified('''
        _Bool truth = 123;
        unsigned int wrapped = 65535U + 43U;
        signed int converted = (signed int)65535U;
        _Static_assert(sizeof(0xFFFF) == 1, "unsigned int literal");
        _Static_assert(sizeof(65535) == 2, "decimal long literal");
        _Static_assert(sizeof(0177777) == 1, "octal unsigned int literal");
        _Static_assert(sizeof(4294967295U) == 2, "unsigned long literal");
        _Static_assert(sizeof(18446744073709551615U) == 4, "unsigned long long literal");
        int main(void) {
            char words[7];
            long wide[3];
            _Static_assert(sizeof(words) == 7, "local char array");
            _Static_assert(sizeof(wide) == 6, "local long array");
            return sizeof(words) + sizeof(wide);
        }
    ''')
    module = binding.parse_assembly(output)
    assert 'global i16 1,' in str(module.get_global_variable('truth'))
    assert 'global i16 42,' in str(module.get_global_variable('wrapped'))
    assert 'global i16 -1,' in str(module.get_global_variable('converted'))


def test_native_hex_character_escapes_and_recursive_records():
    output = verified(r'''
        struct node { int value; struct node *next; };
        char message[] = "\xABCD" "\xFFFF";
        _Static_assert(sizeof(message) == 3, "native string cells");
        _Static_assert((unsigned char)'\x8000' == 0x8000, "native character escape");
        int read(struct node *p) { return p->next->value; }
        int main(void) { return 42; }
    ''')
    module = binding.parse_assembly(output)
    assert '[3 x i16]' in str(module.get_global_variable('message'))


def test_native_memory_and_addresses_stay_opaque_to_llvm():
    output = verified('''
        long values[2] = {0x12345678L, 0x76543210L};
        long *next = values + 1;
        int main(void) {
            char local[2] = {1, 2};
            char *p = local;
            *(volatile int *)0x8000 = p[1];
            return (int)values[1] + (p + 1 - p);
        }
    ''')
    assert 'getelementptr' not in output
    assert ' load ' not in output and ' store ' not in output
    assert '__potados_store_volatile_word' in output
    assert 'add (i16 ptrtoint' in output and ', i16 2)' in output
    assert '!"potados.word-addressed", i32 1' in output


def test_function_prototype_does_not_override_definition_parameter_names():
    output = verified('''
        int helper(int, int) __asm__("helper.part.1");
        int helper(int a, int b) { return a + b; }
        int main(void) { return helper(20, 22); }
    ''')
    assert 'helper.part.1' in output


def test_native_preprocessing_macros_and_original_source_coordinates(tmp_path):
    source = tmp_path / 'native.c'
    source.write_text('''
#if __CHAR_BIT__ != 16 || __SCHAR_MAX__ != 32767 || __SIZEOF_POINTER__ != 1
#error invalid native macros
#endif
int main(void) {
    return missing;
}
''')
    with pytest.raises(FrontendError, match=r'native\.c:6:\d+: unknown identifier'):
        compile_c(source, tmp_path / 'native.ll')


def test_preprocessing_diagnostics_reach_the_caller(tmp_path):
    source = tmp_path / 'invalid.c'
    source.write_text('#error native frontend diagnostic example\n')
    with pytest.raises(FrontendError, match='native frontend diagnostic example'):
        compile_c(source, tmp_path / 'invalid.ll')


@pytest.mark.parametrize('source,message', [
    ('int main(void){return 1.5;}', 'floating point'),
    ('int main(int n){int x[n];return 0;}', 'variable-length arrays'),
    ('int f(int x,...);', 'variadic'),
    ('int main(void){__asm__("nop"); return 0;}', 'inline assembly'),
    ('struct x { int bit:1; };', 'bit-fields'),
])
def test_unsupported_constructs_have_source_diagnostics(source, message):
    with pytest.raises(FrontendError, match=message):
        compile_text(source, filename='unsupported.c')
