"""Build and control a persistent cocotb/Verilator instance of the project RTL.

The transport carries debug commands and observed HDL state. It never executes
or predicts an instruction in Python.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


class RTLError(RuntimeError):
    """A Verilator build, simulator process, or debug command failed."""


def _rtl_source() -> Path:
    explicit = os.environ.get("POTADOS_RTL_ROOT")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if (candidate / "potados.sv").is_file():
            return candidate
        raise RTLError("POTADOS_RTL_ROOT must name the RTL directory containing potados.sv")
    for location in (Path(__file__).resolve(), Path.cwd()):
        for parent in (location, *location.parents):
            if (parent / "rtl/potados.sv").is_file():
                return parent / "rtl"
    raise RTLError("cannot locate potados.sv; set POTADOS_RTL_ROOT=/path/to/project/rtl")


def _wrapper_source() -> Path:
    source_tree = Path(__file__).resolve().parents[2] / "rtl/potados_sim_top.sv"
    if source_tree.is_file():
        return source_tree
    packaged = Path(__file__).with_name("potados_sim_top.sv")
    if packaged.is_file():
        return packaged
    raise RTLError("the potados_sim_top.sv simulation wrapper is missing")


def _build(ram_low: int, ram_high: int, waves: bool) -> Path:
    try:
        import cocotb
        from cocotb_tools.runner import get_runner
    except ImportError as exc:
        raise RTLError("cocotb is required; install the potados-emulator project dependencies") from exc
    executable = shutil.which("verilator")
    if not executable:
        raise RTLError("Verilator is required for execution; install it and add verilator to PATH")
    rtl = _rtl_source()
    wrapper = _wrapper_source()
    try:
        version = subprocess.run([executable, "--version"], text=True, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RTLError(f"cannot execute Verilator: {exc}") from exc
    identity = hashlib.sha256()
    identity.update(json.dumps([str(rtl), version, cocotb.__version__, sys.version,
                                sys.executable, ram_low, ram_high, waves]).encode())
    for source in [*sorted(rtl.glob("*.sv")), wrapper]:
        identity.update(source.name.encode())
        identity.update(source.read_bytes())
    build_root = Path(os.environ.get("POTADOS_SIM_BUILD", rtl.parent / "build/sim/potados_emulator")).expanduser().resolve()
    directory = build_root / identity.hexdigest()[:20]
    directory.mkdir(parents=True, exist_ok=True)
    # Concurrent compiler tests share a simulator build, never a live instance.
    import fcntl
    with (directory / "build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (directory / "potados_sim_top").is_file():
            runner = get_runner("verilator")
            try:
                runner.build(sources=[wrapper], includes=[rtl], hdl_toplevel="potados_sim_top",
                             parameters={"RAM_LOW_ADDRESS": ram_low, "RAM_HIGH_ADDRESS": ram_high},
                             build_dir=directory, build_args=["-Wno-WIDTHTRUNC"],
                             waves=waves, log_file=directory / "build.log")
            except (Exception, SystemExit) as exc:
                log = (directory / "build.log").read_text(errors="replace") if (directory / "build.log").exists() else str(exc)
                raise RTLError(f"Verilator build failed; log: {directory / 'build.log'}\n{log[-6000:]}") from exc
    return directory


class RTLSession:
    """A clock-paused RTL process controlled by JSON commands over a local socket."""
    def __init__(self, program: Mapping[int, int], *, pc: int = 0, initial_sp: int = 0,
                 ram_low: int = 0, ram_high: int = 0x7FFF,
                 io: Mapping[int, int] | None = None, waves: bool | str | Path = False) -> None:
        if not 0 <= ram_low <= ram_high <= 0xFFFF:
            raise RTLError("invalid RAM window")
        if any(not 0 <= int(a) <= 0x7FFF or not 0 <= int(w) <= 0xFFFF for a, w in program.items()):
            raise RTLError("the RTL's configured ROM holds word addresses 0x0000..0x7fff")
        self.build_dir = _build(ram_low, ram_high, bool(waves))
        self._temporary = tempfile.TemporaryDirectory(prefix="potados-rtl-")
        self.directory = Path(self._temporary.name)
        self._wave_source = self.directory / "dump.vcd" if waves else None
        self._wave_destination = (Path(waves).expanduser().resolve() if not isinstance(waves, bool)
                                  else self.build_dir.parent / "waves" / (self.directory.name + ".vcd")) if waves else None
        self.waveform = self._wave_destination
        self._closed = False
        self._stream = None
        self._connection = None
        self._process = None
        self._log_stream = None
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_path = self.directory / "control.sock"
        listener.bind(str(socket_path))
        listener.listen(1)
        listener.settimeout(0.25)
        env = os.environ.copy()
        for inherited_filter in ("PYTEST_CURRENT_TEST", "COCOTB_TEST_FILTER", "COCOTB_TESTCASE"):
            env.pop(inherited_filter, None)
        env.update({"POTADOS_RTL_SOCKET": str(socket_path), "POTADOS_RTL_BUILD": str(self.build_dir),
                    "POTADOS_RTL_SESSION": str(self.directory), "POTADOS_RTL_WAVES": str(int(bool(waves))),
                    "POTADOS_RTL_SOURCE": str(_rtl_source() / "potados.sv"),
                    "COCOTB_LOG_LEVEL": "WARNING", "COCOTB_REDUCED_LOG_FMT": "1"})
        package_root = Path(__file__).resolve().parents[1]
        paths = [str(package_root), str(_rtl_source().parent / "asm/src")]
        paths += [str(Path(p).resolve()) for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
        env["PYTHONPATH"] = os.pathsep.join(paths)
        self._log_stream = (self.directory / "simulation.log").open("w")
        try:
            self._process = subprocess.Popen([sys.executable, "-c", "from potados_emulator.rtl import _worker; _worker()"],
                                             env=env, cwd=self.directory,
                                             stdout=self._log_stream, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 30
            while True:
                try:
                    self._connection, _ = listener.accept()
                    break
                except socket.timeout:
                    if self._process.poll() is not None or time.monotonic() >= deadline:
                        self._log_stream.flush()
                        detail = (self.directory / "simulation.log").read_text(errors="replace")[-6000:]
                        raise RTLError("cocotb/Verilator failed to start:\n" + detail)
            self._stream = self._connection.makefile("rwb")
            self.command({"op": "reset", "program": dict(program), "pc": pc, "initial_sp": initial_sp,
                          "ram_low": ram_low, "ram_high": ram_high, "io": dict(io or {})})
        except BaseException:
            self.close()
            raise
        finally:
            listener.close()

    def _log_tail(self) -> str:
        try:
            if self._log_stream is not None:
                self._log_stream.flush()
            return (self.directory / "simulation.log").read_text(errors="replace")[-6000:]
        except (OSError, ValueError):
            return "(simulator log is unavailable)"

    def command(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._closed or self._stream is None:
            raise RTLError("RTL session is closed")
        if self._process is not None and self._process.poll() is not None:
            raise RTLError("cocotb/Verilator worker exited unexpectedly:\n" + self._log_tail())
        try:
            self._stream.write(json.dumps(request).encode() + b"\n")
            self._stream.flush()
            line = self._stream.readline()
            if not line:
                raise RTLError("cocotb/Verilator terminated unexpectedly:\n" + self._log_tail())
            response = json.loads(line)
        except (OSError, json.JSONDecodeError) as exc:
            raise RTLError(f"RTL control connection failed: {exc}\n{self._log_tail()}") from exc
        if not response.get("ok"):
            raise RTLError(response.get("error", "RTL command failed"))
        return response

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        if self._stream is not None:
            try:
                self._stream.write(b'{"op":"close"}\n')
                self._stream.flush()
            except (OSError, ValueError):
                pass
            try:
                self._stream.close()
            except (OSError, ValueError):
                pass
        if self._connection is not None:
            try:
                self._connection.close()
            except OSError:
                pass
        if self._process is not None:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._signal_process_group(signal.SIGTERM)
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._signal_process_group(signal.SIGKILL)
                    self._process.wait()
            finally:
                # The worker normally waits for its simulator child. If it
                # crashed first, also stop that orphaned child in our private
                # process group rather than leaving Verilator behind.
                self._signal_process_group(signal.SIGTERM)
        if self._log_stream is not None:
            try:
                self._log_stream.close()
            except OSError:
                pass
        if self._wave_destination is not None and self._wave_source is not None and self._wave_source.exists():
            try:
                self._wave_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self._wave_source, self._wave_destination)
            except OSError as exc:
                raise RTLError(f"cannot save RTL waveform to {self._wave_destination}: {exc}") from exc

    def _signal_process_group(self, signum: int) -> None:
        try:
            os.killpg(self._process.pid, signum)
        except ProcessLookupError:
            pass

    def __enter__(self) -> RTLSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _worker() -> None:
    """Child-process launcher; cocotb itself runs the persistent RPC coroutine."""
    from cocotb_tools.runner import get_runner
    runner = get_runner("verilator")
    runner.test(test_module="potados_emulator.simulator", hdl_toplevel="potados_sim_top",
                hdl_toplevel_lang="verilog", build_dir=Path(os.environ["POTADOS_RTL_BUILD"]),
                test_dir=Path(os.environ["POTADOS_RTL_SESSION"]),
                waves=os.environ.get("POTADOS_RTL_WAVES") == "1",
                results_xml=str(Path(os.environ["POTADOS_RTL_SESSION"]) / "results.xml"))
