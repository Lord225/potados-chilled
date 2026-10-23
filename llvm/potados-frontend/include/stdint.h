#ifndef POTADOS_STDINT_H
#define POTADOS_STDINT_H
/* A C byte is one 16-bit addressable cell. There is no exact 8-bit C type. */
typedef signed int int16_t;
typedef unsigned int uint16_t;
typedef signed long int32_t;
typedef unsigned long uint32_t;
typedef signed long long int64_t;
typedef unsigned long long uint64_t;
/* Least/fast 8-bit families need at least eight bits, not exactly eight. */
typedef int16_t int_least8_t;
typedef uint16_t uint_least8_t;
typedef int16_t int_fast8_t;
typedef uint16_t uint_fast8_t;
typedef int16_t int_least16_t;
typedef uint16_t uint_least16_t;
typedef int32_t int_least32_t;
typedef uint32_t uint_least32_t;
typedef int64_t int_least64_t;
typedef uint64_t uint_least64_t;
typedef int16_t int_fast16_t;
typedef uint16_t uint_fast16_t;
typedef int32_t int_fast32_t;
typedef uint32_t uint_fast32_t;
typedef int64_t int_fast64_t;
typedef uint64_t uint_fast64_t;
typedef int16_t intptr_t;
typedef uint16_t uintptr_t;
typedef int64_t intmax_t;
typedef uint64_t uintmax_t;
#define INT16_MIN (-32767 - 1)
#define INT16_MAX 32767
#define UINT16_MAX 65535U
#define INT32_MIN (-2147483647L - 1)
#define INT32_MAX 2147483647L
#define UINT32_MAX 4294967295UL
#define INT64_MIN (-9223372036854775807LL - 1)
#define INT64_MAX 9223372036854775807LL
#define UINT64_MAX 18446744073709551615ULL
#define INT_LEAST8_MIN INT16_MIN
#define INT_LEAST8_MAX INT16_MAX
#define UINT_LEAST8_MAX UINT16_MAX
#define INT_LEAST16_MIN INT16_MIN
#define INT_LEAST16_MAX INT16_MAX
#define UINT_LEAST16_MAX UINT16_MAX
#define INT_LEAST32_MIN INT32_MIN
#define INT_LEAST32_MAX INT32_MAX
#define UINT_LEAST32_MAX UINT32_MAX
#define INT_LEAST64_MIN INT64_MIN
#define INT_LEAST64_MAX INT64_MAX
#define UINT_LEAST64_MAX UINT64_MAX
#define INT_FAST8_MIN INT16_MIN
#define INT_FAST8_MAX INT16_MAX
#define UINT_FAST8_MAX UINT16_MAX
#define INT_FAST16_MIN INT16_MIN
#define INT_FAST16_MAX INT16_MAX
#define UINT_FAST16_MAX UINT16_MAX
#define INT_FAST32_MIN INT32_MIN
#define INT_FAST32_MAX INT32_MAX
#define UINT_FAST32_MAX UINT32_MAX
#define INT_FAST64_MIN INT64_MIN
#define INT_FAST64_MAX INT64_MAX
#define UINT_FAST64_MAX UINT64_MAX
#define INTPTR_MIN INT16_MIN
#define INTPTR_MAX INT16_MAX
#define UINTPTR_MAX UINT16_MAX
#define INTMAX_MIN INT64_MIN
#define INTMAX_MAX INT64_MAX
#define UINTMAX_MAX UINT64_MAX
#define SIZE_MAX UINT16_MAX
#define PTRDIFF_MIN INT16_MIN
#define PTRDIFF_MAX INT16_MAX
#define INT16_C(value) value
#define UINT16_C(value) value##U
#define INT32_C(value) value##L
#define UINT32_C(value) value##UL
#define INT64_C(value) value##LL
#define UINT64_C(value) value##ULL
#define INTMAX_C(value) INT64_C(value)
#define UINTMAX_C(value) UINT64_C(value)
#endif
