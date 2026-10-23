#include "potados.h"

volatile potados_u32 input = 0x12345678UL;
volatile potados_u16 divisor = 257;
volatile potados_u64 wide_input = 0x1020304050607080ULL;

potados_u16 main(void) {
    potados_u32 a = input;
    potados_u64 b = wide_input;
    return (potados_u16)((a / divisor) ^ (a % divisor) ^ (b >> 44));
}
