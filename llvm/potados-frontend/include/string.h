#ifndef POTADOS_STRING_H
#define POTADOS_STRING_H
#include <stddef.h>
/* Counts are C bytes: one 16-bit native cell each. */
void *memcpy(void *restrict destination, const void *restrict source, size_t count);
void *memmove(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);
#endif
