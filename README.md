# potados-chilled

Simple FPGA starter project for the Tang Nano 20K, using OSS CAD Suite and cocotb.

`btn1` increments the six-bit counter; `btn2` resets it. The counter value is shown on `led[5:0]`.

```sh
just test   # Run cocotb tests with Verilator
just        # Synthesize, place-and-route, and package top.fs
just flash  # Build and flash a connected Tang Nano 20K
```
