"""Every frame the human-session driver sends must be vendor-observed.

SAFETY_ENVELOPE.md 2a permits only the sixteen triples the vendor application
uses, with the payloads it used. This test fails if `tools/run_human_session.py`
ever grows a frame the vendor never sent -- which is the only automated guard
between an experiment design and an out-of-envelope probe.
"""
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIOR = ROOT / "captures" / "public" / "PRIORART-001-vendor-usb-frames.json"


def load_driver():
    spec = importlib.util.spec_from_file_location(
        "run_human_session", ROOT / "tools" / "run_human_session.py")
    mod = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["run_human_session.py"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


pytest.importorskip("serial", reason="driver imports pyserial")
DRV = load_driver()


def vendor_frames():
    if not PRIOR.exists():
        return set()
    d = json.loads(PRIOR.read_text())
    return {bytes.fromhex(h) for s in d.get("sequences", []) for h in s["frames"]}


VENDOR = vendor_frames()

BB_FRAMES = [("BB 01 00 trigger", DRV.TRIGGER),
             ("BB 01 09 header", DRV.HEADER),
             ("BB 10 00 black cal", DRV.CAL_BLACK),
             ("BB 11 00 white cal", DRV.CAL_WHITE),
             ("BB 13 00 job record", DRV.JOBREC)] + \
            [(f"BB 01 {0x10+i:02X} chunk", f) for i, f in enumerate(DRV.CHUNKS)]


@pytest.mark.skipif(not VENDOR, reason="vendor corpus not present")
@pytest.mark.parametrize("name,frame", BB_FRAMES)
def test_every_0xbb_frame_is_byte_identical_to_vendor_traffic(name, frame):
    assert frame in VENDOR, f"{name} is NOT in the vendor corpus: {frame.hex()}"


@pytest.mark.parametrize("name,frame", BB_FRAMES + [(f"AA 0A {i:02X}", f)
                                                    for i, f in enumerate(DRV.IDENT)])
def test_frames_are_60_bytes_with_a_valid_checksum(name, frame):
    assert len(frame) == 60
    assert frame[59] == sum(frame[:59]) % 256


def test_driver_sends_no_command_outside_the_green_list():
    """SAFETY_ENVELOPE.md 2a. RED rule 2: param byte must be zero."""
    green = {(0xAA, 0x0A, 0x00), (0xAA, 0x0A, 0x01), (0xAA, 0x0A, 0x02), (0xAA, 0x0A, 0x03),
             (0xBB, 0x01, 0x00), (0xBB, 0x01, 0x09), (0xBB, 0x01, 0x10), (0xBB, 0x01, 0x11),
             (0xBB, 0x01, 0x12), (0xBB, 0x01, 0x13), (0xBB, 0x10, 0x00), (0xBB, 0x11, 0x00),
             (0xBB, 0x13, 0x00), (0xBB, 0x17, 0x00), (0xBB, 0x28, 0x00), (0xBB, 0x21, 0x01)}
    for name, f in BB_FRAMES + [(f"AA 0A {i:02X}", x) for i, x in enumerate(DRV.IDENT)]:
        assert (f[0], f[1], f[2]) in green, f"{name} is outside the green list"
        assert f[3] == 0x00, f"{name} has a non-zero param byte (RED rule 2)"
