#ifndef POTADOS_CHILLED_RUNTIME_H
#define POTADOS_CHILLED_RUNTIME_H

/* The MSP430 frontend supplies the same integer sizes and pointer width.
 * POTADOS instruction selection and calling conventions are implemented by
 * this project's target, independently of MSP430 code generation.
 */
typedef unsigned char potados_u8;
typedef signed char potados_i8;
typedef unsigned short potados_u16;
typedef short potados_i16;
typedef unsigned long potados_u32;
typedef long potados_i32;
typedef unsigned long long potados_u64;
typedef long long potados_i64;

/* These functions take native CPU WORD addresses. Ordinary C pointers use
 * byte addresses and cannot be used to address the CPU's upper-half MMIO.
 * The board's LED registers occupy word addresses 0x8000..0x8005.
 */
#ifdef __cplusplus
extern "C" {
#endif
potados_u16 potados_mmio_read(potados_u16 word_address);
void potados_mmio_write(potados_u16 word_address, potados_u16 value);
#ifdef __cplusplus
}
#endif
#endif
