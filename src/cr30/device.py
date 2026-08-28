"""One API over both transports.

    with CR30.open() as dev:          # BLE if available, else USB serial
        print(dev.identify().model)
        m = dev.read_measurement()

The caller never sees framing, checksums, chunking or poll bytes — and never
sees a reading that failed its guards, because `read_measurement` raises rather
than returning a doubtful one (ERRORS.md).
"""
from __future__ import annotations

import datetime
import struct

from . import ble
from .measurement import Measurement, MeasurementError


class CR30:
    def __init__(self, transport, kind: str):
        self._t, self.kind = transport, kind
        self._previous: Measurement | None = None
        self.model = ""

    # -- construction ----------------------------------------------------
    @classmethod
    def open_ble(cls, name: str = "CM454M0223", **kw) -> "CR30":
        t = ble.BleTransport(name, **kw); t.open()
        return cls(t, "ble")

    @classmethod
    def open_usb(cls, port: str | None = None) -> "CR30":
        from .transport import SerialTransport
        from .discovery import candidates
        if port is None:
            found = candidates()
            if not found:
                raise ConnectionError("no CH34x serial device found")
            port = found[0].device
        t = SerialTransport(port); t.open()
        return cls(t, "usb")

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> "CR30":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- operations ------------------------------------------------------
    def identify(self):
        """Ask the device what it is.

        The ONLY sound identification: USB descriptors describe the shared CH34x
        bridge and expose no serial number, so they cannot distinguish a CR30
        from any other CH34x device (PLATFORM_SUPPORT.md).
        """
        if self.kind == "ble":
            raw = self._t.ask(ble.STATUS, polls=4)
            i = raw.find(bytes([0xBB, 0x01, 0x00]))
            if i < 0 or len(raw) - i < 8:
                raise MeasurementError(f"no status reply ({len(raw)} bytes)")
            axis = ble.BleAxis.parse(raw[i:i + 8])
            self.model = "CR30"
            return {"model": "CR30", "axis": axis, "transport": "ble"}
        from .session import Session
        ident = Session(self._t).identify()
        self.model = ident.model
        return ident

    def trigger(self) -> None:
        """Ask the device to measure NOW (USB only).

        ⚠ Not to be used near a magnet -- see `usb_measure.trigger`. The spot
        workflow does not need it: the operator presses the instrument's own
        button and `read_measurement` collects the result.
        """
        if self.kind != "usb":
            raise NotImplementedError(
                "no host trigger is known on BLE; the operator presses the "
                "instrument's own button (TRANSPORT_BLE.md)")
        from . import usb_measure
        usb_measure.trigger(self._t)

    def read_measurement(self, *, enforce: bool = True,
                         button_header=None) -> Measurement:
        """Read the device's stored measurement.

        The CR30 stores the last reading; the spot workflow is *press the
        instrument's own button, then read*. With `enforce` (the default) the
        result is gated by `Measurement.check_usable`, so a tile constant, a
        set magnet-gate flag, or a bit-identical repeat raises instead of being
        returned.

        On USB, pass the unsolicited button header from
        `usb_measure.wait_for_button_header()` as `button_header`. It carries
        the magnet-gate flag AND the device's declared axis, and it is the only
        magnet check that is unit-independent and effective on the first reading
        of a run. Over BLE no equivalent frame is known, so the BLE path has
        **no protocol-level magnet detection at all** -- see TRANSPORT_BLE.md.
        """
        if self.kind == "usb":
            from . import usb_measure
            m = usb_measure.read_stored(self._t, button_header=button_header)
            m.device_model = self.model or "CR30"
            if enforce:
                m.check_usable(self._previous)
            self._previous = m
            return m
        raw = self._t.ask(ble.READ_MEASUREMENT)
        i = raw.find(ble.MEASUREMENT_HDR)
        if i < 0:
            raise MeasurementError(
                f"measurement header not found in {len(raw)} bytes")
        if len(raw) - i < ble.MIN_REPLY:
            raise MeasurementError(
                f"short reply: {len(raw) - i} bytes after header, "
                f"need {ble.MIN_REPLY}")
        axis = ble.BleAxis.parse(raw[i:i + 8])
        vals = list(struct.unpack_from(f"<{axis.bands}f", raw, i + ble.SPECTRUM_AT))
        lab = list(struct.unpack_from("<3f", raw, i + ble.LAB_AT))
        m = Measurement(
            wavelengths=axis.wavelengths(), values=[round(v, 6) for v in vals],
            lab=[round(v, 4) for v in lab], transport=self.kind,
            device_model=self.model or "CR30",
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            raw=raw[i:i + ble.MIN_REPLY],
            metadata={"axis": {"start_nm": axis.start_nm, "step_nm": axis.step_nm,
                               "bands": axis.bands},
                      "condition": "D65/10 (device display setting; spectra are "
                                   "illuminant-independent)",
                      "gate_flag": None,
                      "gate_flag_note": "BLE has no known magnet-gate flag; "
                                        "detection here is behavioural only"})
        if enforce:
            m.check_usable(self._previous)
        self._previous = m
        return m
