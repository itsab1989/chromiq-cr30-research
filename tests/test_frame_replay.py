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

from cr30.frame import (Frame, ChecksumError, ShortFrameError, FrameError,  # noqa: E402
                        checksum, FRAME_SIZE)
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
    assert Frame.parse(raw).to_bytes() == raw


def test_prior_art_checksum_is_disproven():
    """Regression guard for PROTOCOL.md §2.

    If this ever passes, the finding that the published rule is wrong has been
    invalidated and PROTOCOL.md must be revisited.
    """
    def itohio(d):
        return (sum(d[:58]) - (1 if d[0] == 0xBB else 0)) % 256

    mismatches = [r for _, r in FRAMES if itohio(r) != r[59]]
    assert len(mismatches) == len(FRAMES), (
        "the prior-art rule now matches some real frames; PROTOCOL.md §2 "
        "claims it matches none")


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
