#include "potados.h"

volatile potados_u16 left = 0x1234;
volatile potados_u16 right = 0x0103;

potados_u16 main(void) {
    potados_u16 a = left, b = right;
    /* Full 16-bit C multiplication, despite the native 8 x 8 multiplier. */
    return (potados_u16)(a * b + (a << 3) - (b >> 1));
}
