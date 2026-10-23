#ifndef POTADOS_NATIVE_PREDEFINES_H
#define POTADOS_NATIVE_PREDEFINES_H
/* The host Clang executable is used only as a preprocessor. These definitions
 * describe POTADOS C; the native frontend computes types, sizes, and layout.
 */
#undef __CHAR_BIT__
#define __CHAR_BIT__ 16
#undef __SIZEOF_SHORT__
#define __SIZEOF_SHORT__ 1
#undef __SIZEOF_INT__
#define __SIZEOF_INT__ 1
#undef __SIZEOF_LONG__
#define __SIZEOF_LONG__ 2
#undef __SIZEOF_LONG_LONG__
#define __SIZEOF_LONG_LONG__ 4
#undef __SIZEOF_POINTER__
#define __SIZEOF_POINTER__ 1
#undef __SIZEOF_SIZE_T__
#define __SIZEOF_SIZE_T__ 1
#undef __SIZEOF_PTRDIFF_T__
#define __SIZEOF_PTRDIFF_T__ 1
#undef __SIZEOF_BOOL__
#define __SIZEOF_BOOL__ 1
#undef __SIZE_TYPE__
#define __SIZE_TYPE__ unsigned int
#undef __PTRDIFF_TYPE__
#define __PTRDIFF_TYPE__ int
#undef __INTPTR_TYPE__
#define __INTPTR_TYPE__ int
#undef __UINTPTR_TYPE__
#define __UINTPTR_TYPE__ unsigned int
#undef __INTMAX_TYPE__
#define __INTMAX_TYPE__ long long
#undef __UINTMAX_TYPE__
#define __UINTMAX_TYPE__ unsigned long long
/* Exact eight-bit integer types cannot exist with CHAR_BIT=16. */
#undef __INT8_TYPE__
#undef __UINT8_TYPE__
#undef __INT8_MAX__
#undef __UINT8_MAX__
#undef __INT8_C_SUFFIX__
#undef __UINT8_C_SUFFIX__
#undef __INT_LEAST8_TYPE__
#define __INT_LEAST8_TYPE__ int
#undef __UINT_LEAST8_TYPE__
#define __UINT_LEAST8_TYPE__ unsigned int
#undef __INT_LEAST8_MAX__
#define __INT_LEAST8_MAX__ 32767
#undef __UINT_LEAST8_MAX__
#define __UINT_LEAST8_MAX__ 65535U
#undef __INT_FAST8_TYPE__
#define __INT_FAST8_TYPE__ int
#undef __UINT_FAST8_TYPE__
#define __UINT_FAST8_TYPE__ unsigned int
#undef __INT_FAST8_MAX__
#define __INT_FAST8_MAX__ 32767
#undef __UINT_FAST8_MAX__
#define __UINT_FAST8_MAX__ 65535U
#undef __SCHAR_MAX__
#define __SCHAR_MAX__ 32767
#undef __SHRT_MAX__
#define __SHRT_MAX__ 32767
#undef __INT_MAX__
#define __INT_MAX__ 32767
#undef __LONG_MAX__
#define __LONG_MAX__ 2147483647L
#undef __LONG_LONG_MAX__
#define __LONG_LONG_MAX__ 9223372036854775807LL
#define __POTADOS__ 1
#define __POTADOS_WORD_ADDRESSED__ 1
#endif
