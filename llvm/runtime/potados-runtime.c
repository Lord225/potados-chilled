/* Freestanding integer and memory support for the POTADOS Chilled ABI.
 * Memory helper counts use C bytes: one native 16-bit cell each. In particular
 * memset preserves all 16 bits of its unsigned-char conversion.
 * No arithmetic helper uses division, remainder, or wide multiplication.
 * Division by zero is undefined at the language level; these helpers return
 * an all-ones quotient and leave the dividend as the remainder.
 */
#include "potados.h"

#define NOINLINE __attribute__((noinline))
#define DEFINE_DIVISION(U, S, WIDTH, SUFFIX)                                     \
static NOINLINE U potados_udivmod##SUFFIX(U a, U b, U *remainder) {              \
    U quotient = 0, rest = 0;                                                   \
    if (!b) { *remainder = a; return (U)~(U)0; }                                 \
    for (unsigned short i = 0; i < WIDTH; ++i) {                                 \
        U carry = rest >> (WIDTH - 1);                                         \
        rest = (U)((rest << 1) | (a >> (WIDTH - 1)));                            \
        a = (U)(a << 1);                                                       \
        quotient = (U)(quotient << 1);                                         \
        if (carry || rest >= b) {                                              \
            rest = (U)(rest - b);                                              \
            quotient = (U)(quotient | 1);                                      \
        }                                                                     \
    }                                                                         \
    *remainder = rest;                                                        \
    return quotient;                                                          \
}                                                                             \
NOINLINE U __udiv##SUFFIX##3(U a, U b) {                                        \
    U remainder;                                                              \
    return potados_udivmod##SUFFIX(a, b, &remainder);                            \
}                                                                             \
NOINLINE U __umod##SUFFIX##3(U a, U b) {                                        \
    U remainder;                                                              \
    potados_udivmod##SUFFIX(a, b, &remainder);                                   \
    return remainder;                                                         \
}                                                                             \
NOINLINE S __div##SUFFIX##3(S a, S b) {                                         \
    U ua = (U)a, ub = (U)b;                                                    \
    U magnitude_a = a < 0 ? (U)(0 - ua) : ua;                                   \
    U magnitude_b = b < 0 ? (U)(0 - ub) : ub;                                   \
    U result = __udiv##SUFFIX##3(magnitude_a, magnitude_b);                       \
    return (S)((a < 0) != (b < 0) ? (U)(0 - result) : result);                  \
}                                                                             \
NOINLINE S __mod##SUFFIX##3(S a, S b) {                                         \
    U ua = (U)a, ub = (U)b;                                                    \
    U magnitude_a = a < 0 ? (U)(0 - ua) : ua;                                   \
    U magnitude_b = b < 0 ? (U)(0 - ub) : ub;                                   \
    U result = __umod##SUFFIX##3(magnitude_a, magnitude_b);                       \
    return (S)(a < 0 ? (U)(0 - result) : result);                               \
}

DEFINE_DIVISION(unsigned short, short, 16, hi)
DEFINE_DIVISION(unsigned long, long, 32, si)
DEFINE_DIVISION(unsigned long long, long long, 64, di)

NOINLINE void *memcpy(void *restrict destination, const void *restrict source,
                      __SIZE_TYPE__ count) {
    unsigned char *dst = destination;
    const unsigned char *src = source;
    for (__SIZE_TYPE__ i = 0; i < count; ++i) dst[i] = src[i];
    return destination;
}

NOINLINE void *memmove(void *destination, const void *source, __SIZE_TYPE__ count) {
    unsigned char *dst = destination;
    const unsigned char *src = source;
    if ((unsigned short)dst <= (unsigned short)src) {
        for (__SIZE_TYPE__ i = 0; i < count; ++i) dst[i] = src[i];
    } else {
        while (count) { --count; dst[count] = src[count]; }
    }
    return destination;
}

NOINLINE void *memset(void *destination, int value, __SIZE_TYPE__ count) {
    unsigned char *dst = destination;
    for (__SIZE_TYPE__ i = 0; i < count; ++i) dst[i] = (unsigned char)value;
    return destination;
}
