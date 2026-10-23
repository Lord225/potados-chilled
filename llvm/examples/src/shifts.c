#include "potados.h"

volatile potados_u16 input = 0x8001;
volatile potados_u16 amount = 3;

potados_u16 main(void) {
    potados_u16 a = input, n = amount;
    return (potados_u16)((a << n) ^ (a >> n) ^ ((potados_i16)a >> n));
}
