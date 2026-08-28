"""What the shipped guards do NOT catch — every case from a real capture.

Filed by `[CR30-SKEPTIC]`, 2026-08-28, attacking `src/cr30/measurement.py`.

These are not hypotheticals. Each one is driven by bytes that are already in
`captures/public/`, and each one is a case where a reading that is *known to be
wrong* is accepted, or a defence is *known to be inert*. They are pinned here so
that a future change to the guards has to confront them explicitly instead of
rediscovering them on a user's chart.

Nothing here asserts that the current behaviour is CORRECT. They assert what it
IS, and the docstrings say what it should become.
"""
import json
import pathlib
import struct
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30.measurement import (Measurement, MeasurementError,  # noqa: E402
                              MAX_REFLECTANCE, SUSPICIOUS_REFLECTANCE,
                              TILE_SIGNATURE)
from cr30 import usb_measure  # noqa: E402

PUB = ROOT / "captures" / "public"
WL = list(range(400, 701, 10))


def phases(name):
    return {p["phase"]: p for p in json.loads((PUB / name).read_text())["phases"]}


M3 = phases("EXP-MEAS-003-magnet-trigger.json")
M2 = phases("EXP-MEAS-002-magnet-gating.json")
HEALTHY = M3["measure: distinctive patch, cap OFF"]["spectrum"]
CORRUPTED = M3["measure: distinctive patch again, cap OFF"]["spectrum"]
GATED = M3["measure: HOST-TRIGGERED with magnet engaged"]["spectrum"]


# --------------------------------------------------------------- gap 1
def test_a_real_corrupted_calibration_reading_is_ACCEPTED():
    """The bounds are fitted to the most extreme number and a milder one passes.

    `EXP-MEAS-003`'s `patch_after` was taken seconds after the unit's white
    reference was overwritten with a green surface, in the very experiment that
    overwrote it. Band-by-band it is 1.96x the same patch measured minutes
    earlier (sd 0.38 -- spectrally shaped, the signature of a coloured
    reference). It peaks at 105.47 %R.

    MAX_REFLECTANCE is 130 and SUSPICIOUS_REFLECTANCE is 110, so it clears both
    and `check_usable` returns without even setting the metadata warning.

    The lost capture (paper at 156.8 % mean, 193.8 % peak) is the ONLY corrupted
    reading these bounds were ever tested against, and it is the outlier.
    """
    peak = max(CORRUPTED)
    assert 100.0 < peak < SUSPICIOUS_REFLECTANCE < MAX_REFLECTANCE
    m = Measurement(WL, CORRUPTED)
    m.check_usable(Measurement(WL, HEALTHY))       # must not raise -> the gap
    assert "warning" not in m.metadata, "not even a warning is raised"


def test_the_undetectable_side_of_a_corrupted_reference():
    """Gating on a chart's own white patch DEFLATES readings, and nothing sees it.

    A white calibration sets gain = nominal_tile / measured_surface. Plain paper
    reads ~85.8 %R mean where the tile's nominal is ~78.9 %R, so calibrating
    against paper scales every later reading by ~0.92. `validate()` has an upper
    bound and no meaningful lower one, so an 8 % systematic darkening of an
    entire chart passes without a murmur.
    """
    tile_mean = sum(TILE_SIGNATURE) / len(TILE_SIGNATURE)
    paper_mean = 85.842                                   # EXP-MEAS-001
    factor = tile_mean / paper_mean
    assert factor < 1.0                                    # readings come back DARK
    deflated = [v * factor for v in HEALTHY]
    Measurement(WL, deflated).check_usable()               # must not raise -> the gap
    assert max(deflated) < MAX_REFLECTANCE


# --------------------------------------------------------------- gap 2
def test_intermittent_gating_defeats_the_bit_identical_check():
    """The hall sensor is POSITIONAL, so gated readings need not be adjacent.

    Operator, 2026-08-28: *"it does not always show the values for the white
    tile. It seems the magnet must be in the correct position."* Interleave a
    gated reading with real ones and `identical_to` never fires, because no
    gated reading is ever compared with another gated reading.

    Only `looks_like_calibration_tile()` stands between that pattern and a
    profile -- and that check is unit-specific (see below). Here the tile check
    is bypassed to isolate the mechanism, which is the point of the test.
    """
    seq = [HEALTHY, GATED, CORRUPTED, GATED]
    prev = None
    for spectrum in seq:
        m = Measurement(WL, spectrum)
        assert not m.identical_to(prev), "no two ADJACENT readings are equal"
        prev = m
    assert seq[1] == seq[3], "yet two of them are the identical gated constant"


def test_the_first_reading_of_a_run_has_no_previous_to_compare_with():
    """`identical_to(None)` is False by construction, so reading 1 is unguarded
    by that check. On a unit whose tile constant differs from ours, reading 1 of
    a gated run is accepted outright."""
    assert Measurement(WL, GATED).identical_to(None) is False


# --------------------------------------------------------------- gap 3
def _vendor_white():
    """The second CR30's white reference, from the vendor's own traffic."""
    doc = json.loads((PUB / "PRIORART-001-vendor-usb-frames.json").read_text())
    frames = {s["capture"]: s["frames"] for s in doc["sequences"]}
    vals = {}
    for h in frames["Calibrate White and Black and Test Target.spm"]:
        b = bytes.fromhex(h)
        if b[0] == 0xBB and b[1] == 0x01 and b[2] in (0x10, 0x11, 0x12):
            f = list(struct.unpack("<12f", b[6:54]))
            if any(abs(x) > 1e-9 for x in f):
                vals[b[2]] = f
    return vals[0x10] + vals[0x11] + vals[0x12][:7]


def test_TILE_SIGNATURE_is_inert_on_the_only_other_CR30_we_have_data_for():
    """A hard-coded per-unit constant is not a defence on anyone else's device.

    The vendor corpus contains a second CR30's reading of a white target taken
    immediately after `BB 11` white calibration -- i.e. that unit's own stored
    reference, by definition. It has the same shape as ours (flat, ~77 %, a
    400 nm rolloff) and differs from `TILE_SIGNATURE` by up to **4.69 %R**,
    which is **94x** the 0.05 tolerance.

    So on that unit `looks_like_calibration_tile()` returns False for what is
    almost certainly its gated constant, and the magnet defence silently
    degrades to `identical_to` alone -- which the two tests above already show
    is defeated by the first reading and by intermittent gating.

    The fix is not a wider tolerance (4.69 %R would swallow real patches). It is
    to LEARN the constant per unit at calibration time.
    """
    other = _vendor_white()
    worst = max(abs(a - b) for a, b in zip(other, TILE_SIGNATURE))
    assert worst > 4.0, f"expected a large cross-unit difference, got {worst:.3f}"
    assert not Measurement(WL, other).looks_like_calibration_tile()
    assert worst / 0.05 > 90                      # 94x the tolerance


# --------------------------------------------------------------- the fix
def test_the_protocol_flag_catches_what_the_spectrum_cannot():
    """Offset 24 of the unsolicited BUTTON header, on real captured frames.

    This is unit-independent, works on the first reading of a run, and is
    immune to intermittent gating -- everything the two behavioural checks are
    not. It is only present on button-originated headers, which is exactly the
    workflow this project recommends.
    """
    gated = [M2["button press with magnet, attempt 1"]["unsolicited"],
             M3["gate confirmation button press"]["unsolicited"]]
    for hex_frame in gated:
        assert usb_measure.button_header_is_gated(bytes.fromhex(hex_frame)) is True

    ungated = json.loads(
        (PUB / "EXP-CAL-001-EXP-MEAS-001-human-session.json").read_text())
    press = [p for p in ungated["phases"] if p.get("unsolicited")]
    assert press, "the ungated button press must be in this capture"
    for p in press:
        assert usb_measure.button_header_is_gated(
            bytes.fromhex(p["unsolicited"])) is False


def test_the_flag_refuses_to_answer_for_a_host_triggered_header():
    """Offset 24 is 0x00 on host-triggered headers whether gated or not, so the
    helper must return None -- "cannot tell" -- rather than False -- "safe"."""
    for ph in ("measure: HOST-TRIGGERED with magnet engaged",
               "measure: distinctive patch, cap OFF"):
        hdr = [s["rx"] for s in M3[ph]["steps"] if s["rx"].startswith("bb0109")][0]
        assert usb_measure.button_header_is_gated(bytes.fromhex(hdr)) is None


def test_a_set_gate_flag_rejects_the_reading():
    m = Measurement(WL, HEALTHY, gate_flag=True)
    with pytest.raises(MeasurementError, match="offset 24"):
        m.check_usable()
    Measurement(WL, HEALTHY, gate_flag=False).check_usable()      # must not raise
