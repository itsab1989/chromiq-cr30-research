"""Everything TRANSPORT_BLE.md asserts, tested against the bytes it was written from.

`[CR30-SKEPTIC]`, 2026-08-28. The whole BLE evidence base is one ~30 s vendor
PacketLogger trace (`EXP-BLE-009`) plus our own client's replies
(`EXP-BLE-010`, `EXP-MEAS-005`). These tests establish which claims that base
can and cannot carry.
"""
import json
import pathlib
import struct
import pytest
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30 import ble  # noqa: E402

PUB = ROOT / "captures" / "public"
ATT = json.loads((PUB / "EXP-BLE-009-att.json").read_text())["att"]

FRAMES = sorted({
    bytes.fromhex(r["payload"])[2:]                       # strip the ATT handle
    for r in ATT
    if r["opname"] in ("WRITE_CMD", "NOTIFY") and len(r["payload"]) // 2 == 12
})


def test_the_entire_BLE_frame_corpus_is_five_frames():
    """Scale check before any claim is believed. USB needed 260."""
    assert len(FRAMES) == 5
    assert all(len(f) == ble.FRAME_LEN for f in FRAMES)


def test_the_checksum_rule_is_NOT_uniquely_determined_on_BLE():
    """TRANSPORT_BLE.md: "the same checksum rule generalised ... a genuine
    unification". Four contiguous additive rules fit this corpus, not one.

    One of the survivors is `sum[0:8]+0xff` -- arithmetically itohio's 0xBB
    branch, the rule 260 USB frames were needed to eliminate. It is eliminated
    on USB only by the `BB 01 09` headers that carry marker 0x00; every BLE
    frame observed carries 0xFF at byte 8, so the same confound is intact and
    the discriminating case has never been seen over BLE.
    """
    survivors = [(i, j)
                 for i in range(9) for j in range(i + 1, 10)
                 if len({(sum(f[i:j]) - f[9]) % 256 for f in FRAMES}) == 1]
    assert (0, 9) in survivors, "our rule must be among them"
    assert len(survivors) == 4, survivors
    assert (0, 8) in survivors, "itohio's 0xBB branch survives on BLE"
    assert len({f[8] for f in FRAMES}) == 1 == len({f[0] for f in FRAMES})


def test_bb14_echoes_the_CALLERS_OWN_payload_two_payloads_proven():
    """MEASUREMENT.md: "A constant echo means our call was malformed, not that
    the command is empty. HYPOTHESIS still open."

    DISPROVEN by the vendor capture that was already in this repository. The
    vendor sent a NON-zero 4-byte field and got that same field back with only
    the sub-command byte cleared. Our probe sent a zero field and got zeros
    back. Two different payloads, the same transformation: the reply carries no
    device data whatsoever, and the 4-byte field is host-supplied.
    """
    sent = [f for f in FRAMES if f[1] == 0x14 and f[2] in (0x08, 0x09)]
    got = [f for f in FRAMES if f[1] == 0x14 and f[2] == 0x00]
    assert len(sent) == 2 and len(got) == 1
    for req in sent:
        assert req[3:9] == got[0][3:9], "payload comes straight back"
        assert req[:2] == got[0][:2]
    assert got[0][2] == 0x00, "only the sub-command byte is cleared"
    assert got[0][4:8] != b"\0\0\0\0", "and the field is non-zero, so this is not a nil reply"


def _replies():
    stream = b"".join(bytes.fromhex(r["payload"])[2:] for r in ATT
                      if r["opname"] == "NOTIFY" and len(r["payload"]) // 2 > 100)
    hdr, out, i = bytes.fromhex("bb02100001900a1f"), [], stream.find(bytes.fromhex("bb02100001900a1f"))
    while i >= 0:
        out.append(stream[i:i + 200])
        i = stream.find(hdr, i + 1)
    return out


def test_the_vendor_stream_contains_a_TRUNCATED_reply_zero_filled():
    """The most dangerous byte pattern in the BLE corpus.

    TRANSPORT_BLE.md describes the reply as "one 200-byte notification". The
    vendor's own 410-byte notification stream is **110 bytes of a truncated
    reply, 90 bytes of zero fill, a complete 200-byte reply, and the 10-byte
    `bb 14` echo**. In the truncated one, bands 0-24 are intact, band 25 is
    half-written (two bytes, then zeros) and bands 26-30 and the whole L*a*b*
    are zero.

    Reconstruction caveat, stated because it matters: this is a concatenation
    of two PacketLogger records (241 + 169 bytes). A LOST record would explain
    the zeros too -- but it would also misalign everything after it, and the
    second reply parses byte-perfectly at offset 200 and the arithmetic closes
    exactly at 110 + 90 + 200 + 10 = 410. Alignment is the control.
    """
    reps = _replies()
    assert len(reps) == 2
    bad, good = (struct.unpack_from("<31f", r, ble.SPECTRUM_AT) for r in reps)
    assert bad[:25] == good[:25], "the head of the truncated reply is genuine"
    assert bad[26:] == (0.0,) * 5, "and the tail is zero fill"
    assert good[26:] != (0.0,) * 5
    assert struct.unpack_from("<3f", reps[0], ble.LAB_AT) == (0.0, 0.0, 0.0)
    assert round(struct.unpack_from("<3f", reps[1], ble.LAB_AT)[0], 3) == 91.642


def test_the_truncated_reply_is_now_REJECTED():
    """Was `..._ACCEPTS_the_truncated_reply`, pinning the defect. Now pins the fix.

    [CR30-SKEPTIC] found that the vendor's 410-byte stream is a truncated,
    zero-filled reply followed by a complete one, and that the shipped decoder's
    `raw.find()` took the FIRST hit -- returning five bands of exactly 0.0 %R
    and a Lab of pure black, with every length and range check passing.

    Two fixes, both asserted here: `Measurement.zero_run()` rejects a run of
    exact zeros as a truncation signature (a real dark patch reads a few
    percent, never exactly 0.0), and the decoder now enumerates EVERY candidate
    header and keeps the last one that survives validation.
    """
    from cr30.measurement import Measurement, MeasurementError

    stream = b"".join(bytes.fromhex(r["payload"])[2:] for r in ATT
                      if r["opname"] == "NOTIFY" and len(r["payload"]) // 2 > 100)
    i = stream.find(ble.MEASUREMENT_HDR)
    assert i == 0 and len(stream) - i >= ble.MIN_REPLY   # the naive checks still pass

    axis = ble.BleAxis.parse(stream[i:i + 8])
    vals = list(struct.unpack_from(f"<{axis.bands}f", stream, i + ble.SPECTRUM_AT))
    lab = list(struct.unpack_from("<3f", stream, i + ble.LAB_AT))
    m = Measurement(wavelengths=axis.wavelengths(),
                    values=[round(v, 6) for v in vals],
                    lab=[round(v, 4) for v in lab])
    # the mutation is proven to be present before the guard is trusted
    assert m.values[-5:] == [0.0] * 5 and m.lab == [0.0, 0.0, 0.0]
    with pytest.raises(MeasurementError, match="0.0 %R"):
        m.check_usable(None)


def test_a_genuinely_dark_patch_is_not_mistaken_for_truncation():
    """The zero-run guard must not reject real dark readings.

    Proven on every real reading captured on this unit, the darkest of which
    (EXP-MEAS-005 rank corpus) means 5.53 %R.
    """
    from cr30.measurement import Measurement
    d = json.loads((PUB / "EXP-MEAS-005-spot-workflow.json").read_text())
    wl = list(range(400, 701, 10))
    for r in d["readings"]:
        assert Measurement(wl, r["spectrum"]).zero_run() < 3

def test_the_terminator_claim_is_false():
    """TRANSPORT_BLE.md: "offset 196: 4 bytes 0x7FFF0000 (NaN) -- terminator".

    Our unit puts NaN there. The vendor unit puts 0.0 there, on BOTH replies.
    It is not a constant and it is not a terminator, and an implementation that
    validated a reply with it would reject every reply from that unit.
    """
    for r in _replies():
        assert r[196:200] == b"\x00\x00\x00\x00"
    ours = bytes.fromhex(json.loads(
        (PUB / "EXP-BLE-010-live.json").read_text())["reassembled"])
    assert ours[196:200] == b"\x00\x00\xff\x7f"           # float32 LE NaN
    assert ours[196:200] != _replies()[0][196:200]
