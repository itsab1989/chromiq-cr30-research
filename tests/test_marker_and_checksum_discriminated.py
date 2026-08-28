"""The one test that separates our checksum rule from the published one.

Both rules agree on every frame whose marker byte 58 is 0xFF, which is every
frame this project's own hardware has ever emitted. They differ by exactly 1
when the marker is 0x00.

`captures/public/PRIORART-001-vendor-usb-frames.json` -- the vendor
application's own traffic, from a DIFFERENT CR30 -- contains that case: the
measurement header `BB 01 09` carries marker 0x00. Those frames decide it.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30.frame import checksum  # noqa: E402

CAP = ROOT / "captures" / "public"
PRIOR = CAP / "PRIORART-001-vendor-usb-frames.json"


def prior_frames():
    if not PRIOR.exists():
        return []
    d = json.loads(PRIOR.read_text())
    return [bytes.fromhex(h) for s in d.get("sequences", []) for h in s["frames"]]


def itohio(d):
    """itohio/color-science cr30reader/protocol/packets.py::calculate_checksum."""
    return (sum(d[:58]) - (1 if d[0] == 0xBB else 0)) % 256


FRAMES = prior_frames()
DISCRIMINATING = [f for f in FRAMES if f[58] != 0xFF]


@pytest.mark.skipif(not FRAMES, reason="vendor corpus not present")
def test_the_marker_byte_is_not_always_ff():
    """DISPROVEN: 'byte 58 = 0xFF' as a protocol-wide constant."""
    assert DISCRIMINATING, "no marker != 0xFF frames -- the rules cannot be separated"
    assert {f[58] for f in DISCRIMINATING} == {0x00}
    assert {f[:3] for f in DISCRIMINATING} == {bytes([0xBB, 0x01, 0x09])}, \
        "marker 0x00 was expected only on the measurement header"


@pytest.mark.skipif(not DISCRIMINATING, reason="vendor corpus not present")
def test_our_rule_wins_on_every_discriminating_frame():
    assert all(f[59] == checksum(f) for f in DISCRIMINATING)


@pytest.mark.skipif(not DISCRIMINATING, reason="vendor corpus not present")
def test_the_published_rule_loses_on_every_discriminating_frame():
    """The narrow, true claim -- replaces the broad, false one.

    The old guard asserted the published rule matches NO real frame. That is
    wrong: on a 0xFF-marker frame the two rules are arithmetically identical,
    so it matches 617 of the 637 vendor frames. It fails exactly where it can
    be told apart, which is the claim worth guarding.
    """
    assert all(f[59] != itohio(f) for f in DISCRIMINATING)


@pytest.mark.skipif(not FRAMES, reason="vendor corpus not present")
def test_the_two_rules_are_indistinguishable_on_ff_marker_frames():
    """Why session 1 could not have settled this, and why the claim was overstated."""
    ff = [f for f in FRAMES if f[58] == 0xFF]
    assert ff
    assert all(checksum(f) == itohio(f) for f in ff if f[0] == 0xBB)


@pytest.mark.skipif(not FRAMES, reason="vendor corpus not present")
def test_our_rule_holds_on_the_whole_second_unit_corpus():
    """CORROBORATION: a different unit, a different OS, the vendor's own software."""
    bad = [f.hex() for f in FRAMES if f[59] != checksum(f)]
    assert not bad, f"{len(bad)} of {len(FRAMES)} vendor frames fail our rule"
