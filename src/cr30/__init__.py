"""CR30 reference implementation.

Layer A per CLAUDE.md: knows about the device, knows nothing about ChromIQ.
"""
from .frame import Frame, FrameError, ChecksumError, ShortFrameError, checksum
from .identity import Identity, parse_identity

__all__ = ["Frame", "FrameError", "ChecksumError", "ShortFrameError",
           "checksum", "Identity", "parse_identity"]
