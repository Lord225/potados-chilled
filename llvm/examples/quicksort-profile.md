# Sixteen-element quicksort resource usage

Measured on the actual `rtl/potados.sv` CPU using cocotb/Verilator.
All sizes below are native 16-bit words. The in-place array occupies 16
global RAM words, separate from the reported stack.

| Optimization | ROM words | Stack: shuffled | Stack: sorted | Stack: reverse |
| --- | ---: | ---: | ---: | ---: |
| -O0 | 294 | 61 | 151 | 151 |
| -O1 | 303 | 62 | 152 | 152 |
| -O2 | 303 | 62 | 152 | 152 |
| -O3 | 303 | 62 | 152 | 152 |
| -Os | 301 | 62 | 152 | 152 |
| -Oz | 287 | 61 | 151 | 151 |

The ROM count includes startup, initialization of all 16 array cells, both
sort functions, and `main` with its result check. Compilation uses
`--no-runtime`: this program needs no arithmetic or memory-library helpers.

Stack peaks come from the committed architectural SP on every RTL clock,
starting after startup initializes SP to `0x7F00`. This includes `main`,
recursive quicksort frames, partition temporaries, register spills, and saved
return addresses. Every run returned with SP restored to `0x7F00` and R2 zero.
The physical RAM array was independently checked against `0, 1, ..., 15`.

The shuffled initializer is in [quicksort.c](src/quicksort.c). Sorted and
reverse-sorted fixtures exercise the deepest recursion for the last-element
pivot. These measurements apply to this implementation, compiler revision,
and sixteen-element inputs.

Reproduce from the repository root with a built backend:

```sh
uv run --project llvm python llvm/scripts/profile_quicksort.py
```

Assembly and frontend/optimized IR are retained for each optimization mode
under `llvm/examples/build/quicksort-profile/`. The generated `results.json`
also records minimum SP and RTL cycle counts.
