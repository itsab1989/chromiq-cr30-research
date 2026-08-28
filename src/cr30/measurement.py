"""The measurement model, and the guards that keep a bad one out.

Everything here exists because of a VERIFIED hazard (MEASUREMENT.md,
CALIBRATION.md): with a magnet near the aperture the CR30 performs a white
CALIBRATION instead of a measurement and returns a stored constant. The
transaction is indistinguishable from a real one — correct framing, valid
checksum, a plausible near-neutral spectrum, no error, no status byte, and
offset 24 unchanged on the host path.

So a caller CANNOT rely on the protocol to tell it something went wrong.
Detection is behavioural, and it lives here.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


class MeasurementError(Exception):
    """A reading that must not be used. Never downgraded to a warning."""


# The gated/stored tile spectrum, captured on this unit over BOTH transports
# (EXP-MEAS-002/003, EXP-BLE-010) — bit-identical every time, and identical
# with white OR green under the aperture.
TILE_SIGNATURE = [
    70.3943, 74.8234, 77.4351, 78.3985, 77.9172, 77.6712, 78.0504, 78.5432,
    79.2815, 80.1434, 80.6955, 80.7391, 80.5451, 80.1352, 79.9302, 79.7828,
    79.6362, 79.6665, 79.7891, 79.9468, 79.9118, 79.8988, 79.9740, 80.0577,
    80.1447, 80.6163, 80.4520, 80.1841, 79.5773, 78.8277, 77.9322,
]

# Physical bounds. A reflectance FACTOR can legitimately exceed 100 % — a
# strongly brightened paper fluoresces under the device's illumination while the
# calibration tile does not — but not by much. Above ~120 % the explanation is a
# wrong white reference, not a bright sample.
#
# Calibrated with real data: a healthy reading of plain paper peaked at 96.4 %
# (EXP-MEAS-001); the same paper read 156.8 % mean and 193.8 % peak with the
# white reference corrupted (EXP-CAL-002). The hard bound must therefore sit
# below 156, and comfortably above 100.
SUSPICIOUS_REFLECTANCE = 110.0   # plausible only for a fluorescing sample
MAX_REFLECTANCE = 130.0          # above this the white reference is wrong
MIN_REFLECTANCE = -1.0


@dataclass
class Measurement:
    """One CR30 reading. `values` are PERCENT reflectance."""

    wavelengths: list[int]
    values: list[float]
    lab: list[float] | None = None          # device-reported L*a*b*, if available
    transport: str = ""
    device_model: str = ""
    timestamp: str = ""
    raw: bytes = b""
    metadata: dict = field(default_factory=dict)

    # -- validation ------------------------------------------------------
    def validate(self) -> None:
        """Raise unless this is structurally and physically plausible."""
        if len(self.values) != len(self.wavelengths):
            raise MeasurementError(
                f"{len(self.values)} values for {len(self.wavelengths)} bands")
        if not self.values:
            raise MeasurementError("empty spectrum")
        bad = [(w, v) for w, v in zip(self.wavelengths, self.values)
               if not math.isfinite(v)]
        if bad:
            raise MeasurementError(f"non-finite value at {bad[0][0]} nm")
        lo, hi = min(self.values), max(self.values)
        if lo < MIN_REFLECTANCE or hi > MAX_REFLECTANCE:
            raise MeasurementError(
                f"reflectance outside physical range: {lo:.4g}..{hi:.4g} %. "
                "A reading far above 100 % means the stored white reference is "
                "wrong, not that the sample is bright — recalibrate against the "
                "white tile (seat the cap correctly, press the device button).")
        if hi > SUSPICIOUS_REFLECTANCE:
            self.metadata["warning"] = (
                f"peak {hi:.1f} %R exceeds {SUSPICIOUS_REFLECTANCE:.0f} %. "
                "Plausible for a strongly brightened paper, but also the early "
                "sign of a drifting white reference.")
        if self.lab is not None:
            if not all(math.isfinite(x) for x in self.lab):
                raise MeasurementError("non-finite Lab")
            if not 0.0 <= self.lab[0] <= 100.0:
                raise MeasurementError(f"L* out of range: {self.lab[0]:.4g}")

    # -- the magnet hazard ----------------------------------------------
    def looks_like_calibration_tile(self, tol: float = 0.05) -> bool:
        """Is this the stored tile constant rather than a measurement?

        VERIFIED: with a magnet present the device returns exactly this, whether
        the white tile or a GREEN surface is under the aperture.
        """
        if len(self.values) != len(TILE_SIGNATURE):
            return False
        return all(abs(a - b) <= tol
                   for a, b in zip(self.values, TILE_SIGNATURE))

    def identical_to(self, other: "Measurement | None") -> bool:
        """Bit-identical to the previous reading.

        Genuine consecutive readings differ in the low bits even without lifting
        the instrument (0.056 % worst-band SD, EXP-MEAS-001). Exact equality
        means either the device is gated or no new reading was taken.
        """
        if other is None:
            return False
        return self.values == other.values

    def check_usable(self, previous: "Measurement | None" = None) -> None:
        """Full gate. Raise unless this reading may be used for profiling."""
        self.validate()
        if self.looks_like_calibration_tile():
            raise MeasurementError(
                "reading matches the stored calibration-tile spectrum. A magnet "
                "near the aperture makes the CR30 return this constant instead "
                "of measuring. Remove the cap or any magnet and read again.")
        if self.identical_to(previous):
            raise MeasurementError(
                "reading is bit-identical to the previous one. Either no new "
                "measurement was taken, or a magnet is gating the device. "
                "Genuine repeats differ in the low bits.")

    # -- convenience -----------------------------------------------------
    @property
    def mean(self) -> float:
        return statistics.fmean(self.values)

    def as_dict(self) -> dict:
        return {"wavelengths": self.wavelengths, "values": self.values,
                "lab": self.lab, "transport": self.transport,
                "device": self.device_model, "timestamp": self.timestamp,
                "metadata": self.metadata}
