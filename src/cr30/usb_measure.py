"""USB measurement: trigger, chunk fetch, spectrum reassembly.

VERIFIED against real captures (EXP-MEAS-001, EXP-MEAS-002/003):

    trigger        BB 01 00 00  -> header BB 01 09 .., axis at offsets 4..6
    fetch chunk    BB 01 10 00  -> 12 x float32 LE at frame offset 6  (bands 0-11)
                   BB 01 11 00  ->                                    (bands 12-23)
                   BB 01 12 00  ->                                    (bands 24-35)
                   BB 01 13 00  -> NOT extra spectrum

Three chunks give 36 floats; only the first 31 are bands, the rest are 0.0.

**Chunk 0x13 is not spectrum.** Its offsets 34..53 repeat bands 0..4 (verified,
60/60 vendor measurement groups and our own captures). itohio/color-science
fetches it and discards it, then accumulates 144 bytes and uses 124 -- the
"20 unexplained bytes" in its write-up. There is nothing unexplained: the
chunking was simply misread.

The axis encoding differs from BLE. Here it is a BYTE x 10 (`28` = 400 nm);
over BLE it is a big-endian uint16 (`01 90` = 400). See TRANSPORT_BLE.md.

**Reading the stored measurement does NOT require a trigger.** The device caches
the last reading (VERIFIED, EXP-MEAS-001), so the spot workflow is: the operator
presses the instrument's own button, we fetch the chunks. That path sends no
trigger, which matters -- see the warning on `trigger()`.
"""
from __future__ import annotations

import datetime
import struct

from .frame import Frame
from .measurement import Measurement, MeasurementError

CMD_MEASURE = 0x01
SUB_TRIGGER = 0x00
SUB_HEADER = 0x09
CHUNK_SUBS = (0x10, 0x11, 0x12)      # 0x13 deliberately excluded: not spectrum
CHUNK_DATA_AT = 6
VALS_PER_CHUNK = 12


def trigger_frame() -> Frame:
    return Frame.build(0xBB, CMD_MEASURE, SUB_TRIGGER, 0)


def chunk_frame(sub: int) -> Frame:
    return Frame.build(0xBB, CMD_MEASURE, sub, 0)


def parse_axis(header: Frame | bytes) -> tuple[int, int, int]:
    """(start_nm, step_nm, bands) from a BB 01 09 header. Byte x 10 encoding."""
    b = header.to_bytes() if isinstance(header, Frame) else header
    return b[4] * 10, b[6], b[5]


def chunk_values(frame: Frame | bytes) -> list[float]:
    b = frame.to_bytes() if isinstance(frame, Frame) else frame
    return list(struct.unpack_from(f"<{VALS_PER_CHUNK}f", b, CHUNK_DATA_AT))


def assemble(chunks: dict[int, Frame | bytes], bands: int = 31) -> list[float]:
    """Reassemble the spectrum from chunks 0x10/0x11/0x12.

    Raises rather than padding: a missing chunk must fail loudly, never be
    rounded up into a short spectrum (ERRORS.md).
    """
    missing = [s for s in CHUNK_SUBS if s not in chunks]
    if missing:
        raise MeasurementError(
            "missing spectrum chunk(s) " + ", ".join(f"0x{s:02X}" for s in missing)
            + " -- refusing to assemble a partial spectrum")
    vals: list[float] = []
    for s in CHUNK_SUBS:
        vals += chunk_values(chunks[s])
    if len(vals) < bands:
        raise MeasurementError(f"{len(vals)} values for {bands} bands")
    return [round(v, 6) for v in vals[:bands]]


def read_stored(transport, *, timeout: float = 5.0) -> Measurement:
    """Fetch the cached measurement. Sends NO trigger.

    This is the spot-workflow path and the safe one: the operator presses the
    instrument's button, we collect. It cannot cause a calibration write.
    """
    chunks: dict[int, bytes] = {}
    for sub in CHUNK_SUBS:
        reply = transport.transact(chunk_frame(sub), timeout=timeout)
        chunks[sub] = reply.to_bytes() if isinstance(reply, Frame) else reply
    values = assemble(chunks)
    return Measurement(
        wavelengths=[400 + 10 * i for i in range(len(values))],
        values=values, transport="usb",
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        metadata={"path": "read_stored (no trigger sent)"})


def trigger(transport, *, timeout: float = 10.0) -> tuple[int, int, int]:
    """Ask the device to measure now, and return its declared axis.

    ⚠ **Do not call this with a magnet near the aperture.** VERIFIED
    (CALIBRATION.md): a magnet turns a measurement into a white CALIBRATION
    against whatever is under the aperture. `EXP-MEAS-003` could not establish
    whether the host trigger or the button press performed that write, so until
    `EXP-MEAS-004` settles it, a host trigger near a magnet may silently destroy
    the user's stored white reference. `read_stored()` carries no such risk.
    """
    header = transport.transact(trigger_frame(), timeout=timeout)
    return parse_axis(header)
