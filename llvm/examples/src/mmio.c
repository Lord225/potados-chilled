#include "potados.h"

int main(void) {
    volatile int *io = (volatile int *)0x8000;
    io[0] = 42;
    io[1] = 99;
    return io[0];
}
