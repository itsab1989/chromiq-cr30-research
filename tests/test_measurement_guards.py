"""The guards that keep a gated or corrupt reading out of a profile.

Every threshold here is calibrated against REAL captured data, named in the
test. These are not synthetic examples (CLAUDE.md 14).
"""
import json, pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30.measurement import (Measurement, MeasurementError, TILE_SIGNATURE,  # noqa: E402
                              MAX_REFLECTANCE, SUSPICIOUS_REFLECTANCE)

WL = list(range(400, 701, 10))
# See the note in tests/test_usb_measure.py: `captures/raw/` is gitignored and
# absent on a fresh clone. Spectra are identical in the redacted public copies.
RAW, PUB = ROOT / "captures" / "raw", ROOT / "captures" / "public"


class _Captures:
    def __truediv__(self, name):
        p = RAW / name
        return p if p.exists() else PUB / name


CAP = _Captures()


def real(path, pred):
    d = json.loads((CAP / path).read_text())
    for ph in d.get("phases", []):
        if pred(ph) and ph.get("spectrum"):
            return ph["spectrum"]
    return None


def test_tile_signature_matches_the_real_gated_reading():
    s = real("EXP-MEAS-002-magnet-gating.json",
             lambda p: "gated button measurement" in p["phase"])
    assert s is not None
    assert Measurement(WL, s).looks_like_calibration_tile()


def test_a_real_patch_is_not_mistaken_for_the_tile():
    """The guard must not reject genuine readings — proven on 15 real ones."""
    d = json.loads((CAP / "EXP-MEAS-005-spot-workflow.json").read_text())
    reals = [r["spectrum"] for r in d["readings"]]
    assert len(reals) >= 14
    flagged = [s for s in reals if Measurement(WL, s).looks_like_calibration_tile()]
    assert flagged == [], f"{len(flagged)} genuine readings wrongly flagged"


def test_real_readings_all_pass_validation():
    d = json.loads((CAP / "EXP-MEAS-005-spot-workflow.json").read_text())
    for r in d["readings"]:
        Measurement(WL, r["spectrum"], lab=r["lab_device"]).validate()


def test_corrupted_calibration_reading_is_rejected():
    """EXP-CAL-002: plain paper read 156.8 % mean with a green white-reference."""
    d = json.loads((CAP / "EXP-CAL-002-calibration-check.json").read_text())
    runs = [p["spectrum"] for p in d["phases"] if p.get("spectrum")]
    corrupt = [s for s in runs if max(s) > 150]
    if not corrupt:
        pytest.skip("this capture holds the restored run only")
    with pytest.raises(MeasurementError, match="physical range"):
        Measurement(WL, corrupt[0]).validate()


def test_bound_sits_between_healthy_and_corrupted():
    """A threshold nobody can breach, or everybody can, is not a threshold."""
    healthy = real("EXP-CAL-001-EXP-MEAS-001-human-session.json",
                   lambda p: "WHITE PAPER" in p["phase"])
    assert healthy is not None
    assert max(healthy) < SUSPICIOUS_REFLECTANCE < MAX_REFLECTANCE < 156.0


def test_bit_identical_repeat_is_rejected():
    a = Measurement(WL, [42.0] * 31)
    b = Measurement(WL, [42.0] * 31)
    a.check_usable()
    with pytest.raises(MeasurementError, match="bit-identical"):
        b.check_usable(a)


def test_genuine_consecutive_readings_are_accepted():
    """Real no-lift repeats differ in the low bits (0.056 %R SD)."""
    d = json.loads((CAP / "EXP-CAL-001-EXP-MEAS-001-human-session.json").read_text())
    reps = [p["spectrum"] for p in d["phases"] if "patch A, read" in p["phase"]]
    assert len(reps) == 3
    prev = None
    for s in reps:
        m = Measurement(WL, s)
        m.check_usable(prev)          # must NOT raise
        prev = m


def test_non_finite_is_rejected():
    with pytest.raises(MeasurementError, match="non-finite"):
        Measurement(WL, [float("nan")] * 31).validate()


def test_length_mismatch_is_rejected():
    with pytest.raises(MeasurementError):
        Measurement(WL, [50.0] * 30).validate()
