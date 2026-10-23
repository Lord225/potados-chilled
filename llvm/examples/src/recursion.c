#include "potados.h"

__attribute__((noinline)) static potados_u16 fibonacci(potados_u16 n) {
    if (n < 2) return n;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

__attribute__((noinline)) static potados_u16 factorial(potados_u16 n) {
    if (n < 2) return 1;
    return n * factorial(n - 1);
}

volatile potados_u16 input = 6;

potados_u16 main(void) {
    return fibonacci(input) + factorial(input);
}
