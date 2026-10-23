#include "potados.h"

volatile potados_u16 input = 7;

potados_u16 main(void) {
    return input * 6;
}
