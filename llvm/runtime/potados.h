#ifndef POTADOS_CHILLED_RUNTIME_H
#define POTADOS_CHILLED_RUNTIME_H

/* Native POTADOS C has CHAR_BIT=16. A char, short, int, and pointer each
 * occupy one 16-bit addressable cell; long uses two and long long four.
 * No potados_u8/potados_i8 aliases exist: an exact 8-bit C type is unavailable.
 */
typedef unsigned int potados_u16;
typedef int potados_i16;
typedef unsigned long potados_u32;
typedef long potados_i32;
typedef unsigned long long potados_u64;
typedef long long potados_i64;

/* Optional compatibility helpers. Ordinary volatile pointers reach the same
 * native word bus directly: ((volatile int *)0x8000)[1] addresses 0x8001.
 */
potados_u16 potados_mmio_read(potados_u16 word_address);
void potados_mmio_write(potados_u16 word_address, potados_u16 value);
#endif
