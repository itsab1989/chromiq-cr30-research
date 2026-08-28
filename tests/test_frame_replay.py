"""Replay tests built from REAL captured device traffic.

Golden fixtures come from captures/public/. They are never edited to make a
test pass (CLAUDE.md §14). These tests need no hardware.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30.frame import (CHECKSUM, Frame, ChecksumError, ShortFrameError,  # noqa: E402
                        FrameError, checksum, FRAME_SIZE)
from cr30.identity import parse_identity  # noqa: E402

CAP = ROOT / "captures" / "public"


def device_frames():
    """Every device-originated frame in every public capture."""
    out = []
    for p in sorted(CAP.glob("*.json")):
        d = json.loads(p.read_text())
        for t in d.get("trials", []):
            for probe in t.get("probes", []):
                if probe["rx_len"] == FRAME_SIZE:
                    out.append((p.name, bytes.fromhex(probe["rx"])))
        for c in d.get("cases", []):
            if c["rx_len"] == FRAME_SIZE:
                out.append((p.name, bytes.fromhex(c["rx"])))
    return out


FRAMES = device_frames()


def test_capture_fixtures_exist():
    assert FRAMES, "no captured device frames found -- fixtures missing"


@pytest.mark.parametrize("name,raw", FRAMES)
def test_real_device_frames_pass_our_checksum(name, raw):
    """The VERIFIED rule must hold on every real frame."""
    assert raw[59] == checksum(raw), f"{name}: {raw.hex()}"


@pytest.mark.parametrize("name,raw", FRAMES)
def test_roundtrip_is_byte_exact(name, raw):
    """Structural roundtrip: header, payload and marker survive unchanged.

    Defect filed by `[CR30-SKEPTIC]`: as written this test was near-vacuous.
    `parse()` already rejects any frame whose checksum does not match, and
    `to_bytes()` recomputes byte 59, so byte 59 could never disagree and the
    test could only ever restate the checksum test. It now compares the 59
    bytes that carry information, and separately asserts that a field-level
    edit DOES change the output -- so the comparison is proved to have teeth.
    """
    f = Frame.parse(raw)
    assert f.to_bytes()[:CHECKSUM] == raw[:CHECKSUM]
    assert f.to_bytes() == raw
    mutated = Frame(f.start, f.cmd, f.subcmd, f.param,
                    bytes([f.payload[0] ^ 0xFF]) + f.payload[1:], f.marker)
    assert mutated.to_bytes() != raw, "roundtrip comparison has no teeth"


@pytest.mark.parametrize("name,raw", FRAMES)
def test_parse_without_verify_never_launders_a_corrupt_frame(name, raw):
    """Defect filed by `[CR30-SKEPTIC]` and fixed in frame.py.

    `parse(verify=False).to_bytes()` used to turn a corrupt frame into a
    checksum-valid one with no trace. The frame must remember what it received.
    """
    bad = bytearray(raw); bad[59] ^= 0xFF
    assert bytes(bad) != raw                       # the mutation must land
    f = Frame.parse(bytes(bad), verify=False)
    assert not f.is_intact()
    assert f.to_bytes_as_received() == bytes(bad)  # verbatim, never repaired
    assert f.to_bytes() != bytes(bad)              # and the repair is visible
    good = Frame.parse(raw)
    assert good.is_intact()


def itohio(d):
    """itohio/color-science cr30reader/protocol/packets.py::calculate_checksum."""
    return (sum(d[:58]) - (1 if d[0] == 0xBB else 0)) % 256


def test_prior_art_checksum_fails_on_every_0xAA_frame():
    """Regression guard for PROTOCOL.md §2 -- the NARROW, true claim.

    This test used to assert the published rule matches NO frame in the corpus.
    That claim is false and the test was a trap: on a 0xFF-marker frame the two
    rules are arithmetically identical, so the published rule matches 617 of the
    637 vendor frames, and the first 0xBB reply added to this corpus would have
    failed a test while the protocol layer was correct. Raised by `[CR30-USB]`
    in the session-2 opening assessment; the discriminating evidence is in
    tests/test_marker_and_checksum_discriminated.py.
    """
    aa = [r for _, r in FRAMES if r[0] == 0xAA]
    assert aa, "no 0xAA frames in the corpus"
    assert all(itohio(r) != r[59] for r in aa)


def test_the_two_rules_agree_wherever_the_marker_is_0xFF():
    """Why the corpus in THIS file cannot settle the checksum question."""
    ff = [r for _, r in FRAMES if r[58] == 0xFF and r[0] == 0xBB]
    assert all(checksum(r) == itohio(r) for r in ff)


def test_short_frame_raises_not_repairs():
    with pytest.raises(ShortFrameError):
        Frame.parse(FRAMES[0][1][:59])


def test_long_frame_refuses_to_guess():
    with pytest.raises(FrameError):
        Frame.parse(FRAMES[0][1] + b"\x00")


def test_corrupt_frame_raises():
    raw = bytearray(FRAMES[0][1])
    raw[10] ^= 0xFF                      # corrupt a payload byte
    with pytest.raises(ChecksumError):
        Frame.parse(bytes(raw))


def test_corruption_mutation_actually_lands():
    """A mutation test only counts if the mutation is proven to change bytes."""
    raw = bytearray(FRAMES[0][1])
    before = bytes(raw)
    raw[10] ^= 0xFF
    assert bytes(raw) != before
    assert checksum(bytes(raw)) != raw[59]


def test_identity_reports_cr30():
    d = json.loads((CAP / "EXP-MAC-USB-001-identity.json").read_text())
    probes = d["trials"][0]["probes"]
    frames = {p["subcmd"]: Frame.parse(bytes.fromhex(p["rx"])) for p in probes}
    ident = parse_identity(frames)
    assert ident.model == "CR30"
    assert ident.is_cr30()
    assert ident.build == "0.0.20231219"
    assert ident.version_b == "V10.0.0.0"
    assert ident.version_a == "V11.3."
