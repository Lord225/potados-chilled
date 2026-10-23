#include "potados.h"

unsigned char values[] = {9, 2, 7, 4, 1, 8};
struct Record { unsigned char tag; potados_u16 value; unsigned char flags; };
struct Record records[] = {{7, 0x1234, 3}, {2, 0x00FF, 1}};

potados_u16 main(void) {
    for (potados_u16 end = 6; end > 1; --end) {
        for (potados_u16 i = 1; i < end; ++i) {
            if (values[i - 1] > values[i]) {
                unsigned char swap = values[i - 1];
                values[i - 1] = values[i];
                values[i] = swap;
            }
        }
    }
    potados_u16 sum = 0;
    for (potados_u16 i = 0; i < 6; ++i) sum += values[i];
    return sum + records[0].tag + records[0].value + records[0].flags;
}
