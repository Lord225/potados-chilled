#include "potados.h"

potados_u16 main(void) {
    potados_mmio_write(0x8000, 42);
    potados_mmio_write(0x8001, 255);
    return potados_mmio_read(0x8000);
}
