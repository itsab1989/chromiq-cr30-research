"""CR30 wire framing.

Transport-agnostic: this module never imports serial or bleak. It turns bytes
into frames and frames into bytes, and it is the only place the checksum rule
lives.

Every rule here is VERIFIED against real device traffic; see PROTOCOL.md.
"""
from __future__ import annotations

from dataclasses import dataclass

FRAME_SIZE = 60
MARKER = 58          # index of the marker byte
CHECKSUM = 59        # index of the checksum byte

START_IDENTITY = 0xAA
START_COMMAND = 0xBB


class FrameError(Exception):
    """Base class. A malformed frame is always an error, never a warning."""


class ShortFrameError(FrameError):
    """Fewer than FRAME_SIZE bytes were available."""


class ChecksumError(FrameError):
    """Received frame failed its checksum."""


def checksum(data: bytes) -> int:
    """Checksum over bytes 0..58 inclusive, mod 256.

    VERIFIED against every device-originated frame captured so far
    (EXP-MAC-USB-001). Note this INCLUDES the marker byte at index 58.

    This deliberately differs from itohio/color-science, which sums 0..57 and
    subtracts 1 for 0xBB starts. That rule is off by exactly +1 on real device
    frames, because it omits the marker (0xFF == -1 mod 256). See PROTOCOL.md §2.
    """
    return sum(data[:CHECKSUM]) % 256


@dataclass(frozen=True)
class Frame:
    """One 60-byte CR30 frame."""

    start: int
    cmd: int
    subcmd: int
    param: int
    payload: bytes          # bytes 4..57 inclusive -> 54 bytes
    marker: int = 0xFF

    PAYLOAD_SIZE = MARKER - 4       # 54

    def __post_init__(self) -> None:
        if len(self.payload) != self.PAYLOAD_SIZE:
            raise FrameError(
                f"payload must be {self.PAYLOAD_SIZE} bytes, got {len(self.payload)}")

    # -- encode ----------------------------------------------------------
    def to_bytes(self) -> bytes:
        d = bytearray(FRAME_SIZE)
        d[0], d[1], d[2], d[3] = self.start, self.cmd, self.subcmd, self.param
        d[4:MARKER] = self.payload
        d[MARKER] = self.marker
        d[CHECKSUM] = checksum(d)
        return bytes(d)

    # -- decode ----------------------------------------------------------
    @classmethod
    def parse(cls, data: bytes, *, verify: bool = True) -> "Frame":
        """Parse a received frame.

        Raises rather than repairing. A short or corrupt frame must never be
        rounded up into a usable one (CLAUDE.md §14).
        """
        if len(data) < FRAME_SIZE:
            raise ShortFrameError(
                f"need {FRAME_SIZE} bytes, got {len(data)}: {data.hex()}")
        if len(data) > FRAME_SIZE:
            raise FrameError(
                f"expected exactly {FRAME_SIZE} bytes, got {len(data)}; "
                "refusing to guess frame boundaries")
        if verify:
            want = checksum(data)
            if data[CHECKSUM] != want:
                raise ChecksumError(
                    f"checksum 0x{data[CHECKSUM]:02X}, expected 0x{want:02X} "
                    f"for frame {data.hex()}")
        return cls(start=data[0], cmd=data[1], subcmd=data[2], param=data[3],
                   payload=bytes(data[4:MARKER]), marker=data[MARKER])

    @classmethod
    def build(cls, start: int, cmd: int, subcmd: int = 0, param: int = 0,
              data: bytes = b"", marker: int = 0xFF) -> "Frame":
        if len(data) > cls.PAYLOAD_SIZE:
            raise FrameError(
                f"data too long: {len(data)} > {cls.PAYLOAD_SIZE}")
        return cls(start, cmd, subcmd, param,
                   data + bytes(cls.PAYLOAD_SIZE - len(data)), marker)

    def hex(self) -> str:
        return self.to_bytes().hex(" ")
