#include "potados.h"

volatile potados_u16 dividend = 65535;
volatile potados_u16 divisor = 257;
volatile potados_i16 signed_dividend = -12345;
volatile potados_i16 signed_divisor = 37;

potados_u16 main(void) {
    potados_u16 u = dividend, v = divisor;
    potados_i16 a = signed_dividend, b = signed_divisor;
    return (potados_u16)((u / v) + (u % v) + (a / b) + (a % b));
}
