"""Freestanding C frontend for POTADOS native 16-bit addressable words."""
from .frontend import FrontendError, compile_c, compile_text
__all__ = ["FrontendError", "compile_c", "compile_text"]
