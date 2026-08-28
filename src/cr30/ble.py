"""BLE transport for the CR30.

BLE is NOT "USB over Bluetooth". Verified differences (TRANSPORT_BLE.md):

  * frames are 10 bytes, not 60
  * the host must write a single 0x01 byte to POLL; the device answers a poll,
    not a command-and-wait. This is the single reason every earlier attempt
    failed.
  * the spectral axis is a big-endian uint16 nm start, where USB uses a byte x10
  * bulk replies arrive as ATT notifications, fragmented at the MTU
  * the checksum rule is the SAME: sum(all bytes but the last) mod 256

Requires `bleak`. Kept import-light so the protocol layer never depends on it.
"""
from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

FFE0_SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
FFE2 = "0000ffe2-0000-1000-8000-00805f9b34fb"

POLL = bytes([0x01])
FRAME_LEN = 10
MARKER_AT = 8

# Reply header for "read stored measurement". Used to RESYNC: stragglers from a
# previous exchange otherwise prefix the reply and shift every offset.
MEASUREMENT_HDR = bytes([0xBB, 0x02, 0x10, 0x00])

SPECTRUM_AT = 8          # 31 x float32 LE
LAB_AT = 184             # 3 x float32 LE
MIN_REPLY = 196


def checksum(data: bytes) -> int:
    """sum(every byte but the last) mod 256 — the same rule USB uses."""
    return sum(data[:-1]) % 256


def frame(cmd: int, sub: int = 0, param: int = 0, data: bytes = b"") -> bytes:
    """Build a 10-byte BLE command frame."""
    if len(data) > 4:
        raise ValueError(f"BLE payload is 4 bytes, got {len(data)}")
    d = bytearray(FRAME_LEN)
    d[0], d[1], d[2], d[3] = 0xBB, cmd, sub, param
    d[4:4 + len(data)] = data
    d[MARKER_AT] = 0xFF
    d[9] = checksum(d)
    return bytes(d)


READ_MEASUREMENT = frame(0x02, 0x10)
STATUS = frame(0x01, 0x00)

ADVERTISED_NAME_HINT = "CM"   # the device advertises its own device-id string


@dataclass
class BleAxis:
    start_nm: int
    step_nm: int
    bands: int

    @classmethod
    def parse(cls, hdr: bytes) -> "BleAxis":
        """Bytes 4..7 of a reply: uint16 BE start, uint8 step, uint8 count."""
        start = struct.unpack_from(">H", hdr, 4)[0]
        return cls(start, hdr[6], hdr[7])

    def wavelengths(self) -> list[int]:
        return [self.start_nm + i * self.step_nm for i in range(self.bands)]


class BleTransport:
    """Poll-driven BLE link. Synchronous facade over bleak's async API."""

    def __init__(self, name: str = "CM454M0223", *, address: str | None = None,
                 timeout: float = 20.0):
        self.name, self.address, self.timeout = name, address, timeout
        self._client = None
        self._buf = bytearray()
        self._loop = None

    # -- lifecycle -------------------------------------------------------
    def _run(self, coro):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coro)

    def open(self) -> None:
        from bleak import BleakClient, BleakScanner

        async def _open():
            target = self.address
            if target is None:
                dev = await BleakScanner.find_device_by_name(self.name,
                                                             timeout=self.timeout)
                if dev is None:
                    raise ConnectionError(
                        f"CR30 {self.name!r} is not advertising. It stops "
                        "advertising while another central holds it — "
                        "disconnect the phone app.")
                target = dev
            c = BleakClient(target, timeout=self.timeout)
            await c.connect()
            await c.start_notify(FFE1, self._on_notify)
            return c

        self._client = self._run(_open())

    def close(self) -> None:
        if self._client is None:
            return

        async def _close():
            try:
                await self._client.stop_notify(FFE1)
            except Exception:
                pass
            await self._client.disconnect()

        self._run(_close())
        self._client = None

    def __enter__(self) -> "BleTransport":
        self.open(); return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- link ------------------------------------------------------------
    def _on_notify(self, _sender, data: bytearray) -> None:
        self._buf.extend(bytes(data))

    async def _drain(self, wait: float = 0.4) -> None:
        """Flush stragglers BEFORE a command.

        Notifications keep arriving after polling stops. Left in place they
        prefix the next reply and shift every offset — which silently produced
        fifteen garbage readings before this was added.
        """
        for _ in range(3):
            self._buf.clear()
            await asyncio.sleep(wait)
            if not self._buf:
                break
        self._buf.clear()

    async def _ask(self, req: bytes, polls: int, wait: float) -> bytes:
        await self._drain()
        await self._client.write_gatt_char(FFE1, req, response=False)
        await asyncio.sleep(wait)
        quiet = 0
        for _ in range(polls):
            n = len(self._buf)
            await self._client.write_gatt_char(FFE1, POLL, response=False)
            await asyncio.sleep(wait)
            quiet = quiet + 1 if len(self._buf) == n else 0
            if quiet >= 3 and self._buf:
                break
        return bytes(self._buf)

    def ask(self, req: bytes, *, polls: int = 10, wait: float = 0.35) -> bytes:
        """Send one frame, poll until the device stops sending, return raw bytes."""
        if self._client is None:
            raise ConnectionError("BLE transport is not open")
        return self._run(self._ask(req, polls, wait))
