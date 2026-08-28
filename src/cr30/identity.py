"""Device identity (command 0xAA 0x0A ss 0x00).

Field offsets are VERIFIED against EXP-MAC-USB-001, but from a single unit.
Offsets that held on one device are marked PROBABLE where a second unit could
disagree; see PROTOCOL.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .frame import Frame, START_IDENTITY

CMD_IDENTITY = 0x0A
SUB_MODEL = 0x00
SUB_SERIAL = 0x01
SUB_BUILD = 0x02
SUB_STATUS = 0x03


def _ascii(payload: bytes, start: int, length: int) -> str:
    """Absolute-frame offsets are used in PROTOCOL.md; payload starts at 4."""
    raw = payload[start - 4: start - 4 + length]
    return raw.decode("ascii", errors="replace").rstrip("\x00").strip()


@dataclass
class Identity:
    model: str = ""
    device_id: str = ""
    second_id: str = ""
    version_a: str = ""
    version_b: str = ""
    build: str = ""
    status_byte: int | None = None
    raw: dict = field(default_factory=dict)

    def is_cr30(self) -> bool:
        """The ONLY trustworthy CR30 identification.

        USB descriptors identify the CH34x bridge, not the instrument, and the
        device exposes no USB serial number -- so descriptor matching cannot
        distinguish a CR30 from any other CH34x device. Asking the device is
        the only sound test. See PLATFORM_SUPPORT.md.
        """
        return self.model.upper() == "CR30"


def parse_identity(frames: dict[int, Frame]) -> Identity:
    """Build an Identity from {subcmd: Frame} for subcmds 0x00..0x03."""
    ident = Identity()
    for sub, f in frames.items():
        if f.start != START_IDENTITY or f.cmd != CMD_IDENTITY:
            raise ValueError(
                f"not an identity frame: start=0x{f.start:02X} cmd=0x{f.cmd:02X}")
        ident.raw[sub] = f.to_bytes().hex()
        if sub == SUB_MODEL:
            ident.device_id = _ascii(f.payload, 9, 10)
            ident.model = _ascii(f.payload, 39, 4)
        elif sub == SUB_SERIAL:
            ident.second_id = _ascii(f.payload, 19, 10)
            ident.version_a = _ascii(f.payload, 49, 8)
        elif sub == SUB_BUILD:
            ident.build = _ascii(f.payload, 5, 12)
            ident.version_b = _ascii(f.payload, 29, 9)
        elif sub == SUB_STATUS:
            ident.status_byte = f.payload[19 - 4]
    return ident
