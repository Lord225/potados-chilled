; Native word-addressed I/O entry points, using the C register argument ABI.
potados_mmio_read:
    LD R2, [R2]
    RET
potados_mmio_write:
    ST R3, [R2]
    RET
