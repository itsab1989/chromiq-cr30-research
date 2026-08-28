"""The colour tables, and a positive control that can actually fail.

`[CR30-SKEPTIC]`, 2026-08-28. `validate_illuminants()` advertised itself as
catching "a mistyped coefficient". It did not: it passed a D50 table whose
660-700 nm entries were D65's 600-640 nm entries, copied in, an error reaching
13.4 units (13 %) at 670 nm. The tolerance was 6e-3 and the corrupt table
scored 1.5e-3.

A control is only a control if the mutation is proven to land, so that is what
these tests do.
"""
import json
import pathlib
import struct
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30 import colour  # noqa: E402

PUB = ROOT / "captures" / "public"

# The table exactly as it shipped before 2026-08-28, kept so the mutation is
# a real historical defect and not one invented for the test.
D50_AS_SHIPPED = [
    49.3084, 56.5089, 60.0998, 57.8213, 74.8246, 87.2504, 90.6117, 91.3680,
    95.1082, 91.9526, 95.7237, 96.6137, 97.1292, 102.0980, 100.7550,
    102.3170, 100.0000, 97.7357, 98.9182, 93.5905, 97.1382, 99.9576,
    97.3918, 94.4276, 95.7787, 88.6489, 90.0062, 89.5991, 87.6987, 83.2886,
    83.6992]


@pytest.fixture(autouse=True)
def _restore():
    yield
    colour.use_observer("10")


def test_the_illuminant_control_can_actually_fail():
    """Proof the mutation lands: the old D50 table must now be REJECTED."""
    colour.use_observer("10")
    good = colour.validate_illuminants()
    assert good["D50"]["ok"] and good["D65"]["ok"]

    real_d50, colour.D50 = colour.D50, D50_AS_SHIPPED
    try:
        bad = colour.validate_illuminants()
    finally:
        colour.D50 = real_d50
    assert not bad["D50"]["ok"], (
        "the control still passes the table that was 13 % wrong at 670 nm")
    assert bad["D65"]["ok"], "and it must not become a blanket failure"


def test_the_shipped_D50_tail_was_a_copy_of_D65():
    """Name the defect precisely so nobody 'fixes' it back."""
    assert D50_AS_SHIPPED[26:31] == colour.D65[20:25]
    assert colour.D50[26:31] != colour.D65[20:25]


def _vendor_cyan():
    doc = json.loads((PUB / "PRIORART-001-vendor-usb-frames.json").read_text())
    frames = {s["capture"]: s["frames"] for s in doc["sequences"]}
    vals = {}
    for h in frames["Test Sample 36.61 -20.75 -2.86.spm"]:
        b = bytes.fromhex(h)
        if b[0] == 0xBB and b[1] == 0x01 and b[2] in (0x10, 0x11, 0x12):
            f = list(struct.unpack("<12f", b[6:54]))
            if any(abs(x) > 1e-9 for x in f):
                vals[b[2]] = f
    return vals[0x10] + vals[0x11] + vals[0x12][:7]


def test_D65_10_is_settled_by_a_CHROMATIC_vendor_sample_not_by_the_screen_label():
    """MEASUREMENT.md says the arithmetic "does NOT discriminate 2 from 10".

    That was true of the near-neutral tile it was computed on -- the worst
    possible sample for separating observers. The vendor corpus contains a
    SATURATED CYAN whose own L*a*b* is in its file name, measured on a second
    unit by the vendor's own application. On that sample the four combinations
    separate by 60:1, and D65/10 wins.
    """
    sp = _vendor_cyan()
    labelled = (36.61, -20.75, -2.86)

    def dE(obs, ill):
        colour.use_observer(obs)
        got = colour.spectrum_to_lab(sp, ill)
        return sum((a - b) ** 2 for a, b in zip(got, labelled)) ** 0.5

    best = dE("10", colour.D65)
    others = [dE("2", colour.D65), dE("10", colour.D50), dE("2", colour.D50)]
    assert best < 0.05, f"D65/10 should reproduce the vendor's own Lab, got {best:.3f}"
    assert min(others) > 20 * best, "and it must win by a wide margin"
