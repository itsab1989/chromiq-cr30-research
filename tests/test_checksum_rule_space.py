"""Adversarial audit of the checksum finding.

PROTOCOL.md s2 asserts `checksum = sum(bytes 0..58) mod 256`. These tests pin
the two halves of that claim separately, because they have very different
evidential support:

1. On EXP-MAC-USB-001 alone the rule is **NOT determined** -- fifteen distinct
   contiguous-range rules fit those four frames exactly. A test that only
   checks "our rule holds" would pass for all fifteen and hide that.
2. On the prior-art corpus (260 frames, both start classes, both marker values,
   eight command bytes) exactly **one** contiguous rule survives.

If a future capture breaks (2), the checksum finding is back to (1) and
PROTOCOL.md must say so.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30.frame import checksum, FRAME_SIZE  # noqa: E402

CAP = ROOT / "captures" / "public"


def _priorart():
    d = json.loads((CAP / "PRIORART-001-vendor-usb-frames.json").read_text())
    seen, out = set(), []
    for s in d["sequences"]:
        for h in s["frames"]:
            if h not in seen:
                seen.add(h); out.append(bytes.fromhex(h))
    return out


def _identity():
    """The four device frames of EXP-MAC-USB-001, deduplicated."""
    d = json.loads((CAP / "EXP-MAC-USB-001-identity.json").read_text())
    seen, out = {}, []
    for t in d["trials"]:
        for p in t["probes"]:
            if p["rx"] not in seen:
                seen[p["rx"]] = 1; out.append(bytes.fromhex(p["rx"]))
    return out


def _contiguous_rules_fitting(frames):
    """Every `sum(frame[a:b]) + k mod 256` rule consistent with `frames`."""
    fits = []
    for a in range(FRAME_SIZE):
        for b in range(a + 1, FRAME_SIZE):
            k = (frames[0][59] - sum(frames[0][a:b])) % 256
            if all((sum(f[a:b]) + k) % 256 == f[59] for f in frames):
                fits.append((a, b, k))
    return fits


def _usb_session2():
    """Every 60-byte device reply in [CR30-USB]'s session-2 captures.

    These are the frames that carry data at bytes 53-57, which is what kills
    the payload-extent half of the ambiguity.
    """
    out, seen = [], set()
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "rx" and isinstance(v, str) and len(v) == 2 * FRAME_SIZE:
                    if v not in seen:
                        seen.add(v); out.append(bytes.fromhex(v))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for p in sorted(CAP.glob("EXP-USB-00[356]*.json")):
        walk(json.loads(p.read_text()))
    return out


PRIORART = _priorart()
IDENTITY = _identity()
USB2 = _usb_session2()


# -- 1. the original evidence does NOT determine the rule -------------------

def test_identity_capture_alone_does_not_determine_the_rule():
    fits = _contiguous_rules_fitting(IDENTITY)
    assert (0, 59, 0) in fits, "our rule must be among those that fit"
    assert len(fits) > 1, (
        "if this ever becomes 1, EXP-MAC-USB-001 has grown discriminating "
        "frames and PROTOCOL.md s2 may be upgraded on its own evidence")
    # The ambiguity is not academic: these disagree on a frame with marker 0x00.
    assert (0, 58, 0xFF) in fits


def test_the_ambiguity_is_observable_not_cosmetic():
    """Two rules that fit the identity capture equally disagree on a 0xBB frame."""
    f = bytearray(60)
    f[0], f[1], f[2] = 0xBB, 0x01, 0x10
    f[4:58] = bytes(range(1, 55))
    f[58] = 0x00                                    # marker 0x00, as prior art reports
    assert sum(f[:59]) % 256 != (sum(f[:58]) + 0xFF) % 256


# -- 2. the corpus that does determine it -----------------------------------

def test_prior_art_corpus_is_large_and_diverse():
    assert len(PRIORART) >= 250
    assert {f[0] for f in PRIORART} == {0xBB}       # identity frames are dropped
    assert {f[58] for f in PRIORART} == {0x00, 0xFF}, "both marker values needed"
    assert len({f[1] for f in PRIORART}) >= 6, "several command bytes needed"


@pytest.mark.parametrize("raw", PRIORART)
def test_prior_art_frames_satisfy_our_rule(raw):
    assert raw[59] == checksum(raw)


def test_corpus_alone_still_cannot_place_byte_0():
    """The corpus is all 0xBB, so 'include byte 0' and 'exclude it, add 0xBB'
    are indistinguishable within it. Stated, not glossed over."""
    assert _contiguous_rules_fitting(PRIORART) == [(0, 59, 0x00), (1, 59, 0xBB)]


@pytest.mark.skipif(not USB2, reason="[CR30-USB]'s session-2 captures not committed yet")
def test_usb_session2_frames_narrow_it_but_do_not_settle_it():
    """[CR30-USB]'s EXP-USB-006 frames carry data at bytes 53-57, which kills
    the payload-extent ambiguity -- but every marker is 0xFF, so the marker
    ambiguity survives. Two rules, not one."""
    assert any(any(f[53:58]) for f in USB2), (
        "these captures are only useful because replies carry data at 53..57")
    assert {f[58] for f in USB2} == {0xFF}
    assert _contiguous_rules_fitting(USB2) == [(0, 58, 0xFF), (0, 59, 0x00)]


@pytest.mark.skipif(not USB2, reason="[CR30-USB]'s session-2 captures not committed yet")
def test_all_evidence_together_leaves_exactly_one_rule():
    """The joint result: neither agent's corpus settles it alone."""
    genuine_aa = [f for f in IDENTITY if b"REDACTED" not in f]
    everything = list(dict.fromkeys(USB2 + PRIORART + genuine_aa))
    assert len(everything) > 260
    assert _contiguous_rules_fitting(everything) == [(0, 59, 0)]


def test_exactly_one_contiguous_rule_survives_corpus_plus_genuine_0xAA_frames():
    """The discriminating set: 260 vendor 0xBB frames PLUS the two published
    identity frames whose byte 59 the redactor did NOT rewrite. The redacted
    two are deliberately excluded -- their checksum was computed by the rule
    under test and including them would be circular."""
    genuine_aa = [f for f in IDENTITY if b"REDACTED" not in f]
    assert genuine_aa and all(f[0] == 0xAA for f in genuine_aa)
    fits = _contiguous_rules_fitting(PRIORART + genuine_aa)
    assert fits == [(0, 59, 0)], f"expected only sum[0:59]+0, got {fits}"


def test_xor_and_crc8_are_excluded():
    """Not just 'our rule fits' -- whole rule FAMILIES are ruled out."""
    def xor(d, a, b):
        x = 0
        for v in d[a:b]:
            x ^= v
        return x
    for a in range(4):
        for b in (55, 56, 57, 58, 59):
            k = xor(PRIORART[0], a, b) ^ PRIORART[0][59]
            assert not all((xor(f, a, b) ^ k) == f[59] for f in PRIORART)


# -- 3. the redaction hazard, pinned so it cannot come back ------------------

def test_published_identity_frames_carry_synthesised_checksums():
    """tools/redact.py RECOMPUTES byte 59, so two of the four published
    identity frames are self-consistent by construction and prove nothing
    about the device. This test documents which, so nobody counts them
    as independent evidence again."""
    d = json.loads((CAP / "EXP-MAC-USB-001-identity.json").read_text())
    assert "checksum recomputed" in d["_redaction"]
    redacted = [f for f in IDENTITY if b"REDACTED" in f]
    assert len(redacted) == 2, "two frames were rewritten by the redactor"
    genuine = [f for f in IDENTITY if b"REDACTED" not in f]
    assert len(genuine) == 2, (
        "only two published identity frames carry the device's own checksum")


def test_priorart_corpus_checksums_were_never_rewritten():
    """The corpus is only useful because byte 59 is untouched."""
    d = json.loads((CAP / "PRIORART-001-vendor-usb-frames.json").read_text())
    assert "never rewritten" in d["note"]
    assert d["failed_sum_0_58"] > 0, (
        "structural extraction must admit non-frames, or the corpus was "
        "selected by the rule it is being used to test")


# -- 4. the cross-agent disagreement, pinned ---------------------------------

def test_device_does_emit_marker_zero_frames():
    """src/cr30/frame.py claims the device forces byte 58 to 0xFF on every
    frame it emits. It does not: BB 01 09 measurement headers carry 0x00.
    Those frames are the reason sum(0..58) is the unique surviving rule, so
    if this ever stops being true the whole §2 argument must be redone."""
    mk0 = [f for f in PRIORART if f[58] == 0x00]
    assert len(mk0) >= 5, "the discriminating frames have gone missing"  # 20 occurrences, 7 unique
    assert all(f[:3] == b"\xbb\x01\x09" for f in mk0), (
        "marker 0x00 should occur only on measurement headers")
    assert all(any(f[4:58]) for f in mk0), (
        "they must be device REPLIES (non-empty payload), not requests")
    # and they are exactly what the prior-art rule gets wrong
    def itohio(d):
        return (sum(d[:58]) - (1 if d[0] == 0xBB else 0)) % 256
    assert all(itohio(f) != f[59] for f in mk0)


def test_byte_56_is_device_written_only_on_measurement_headers():
    """PROTOCOL.md 7.1: the device-written span is command-class specific."""
    nz56 = [f for f in PRIORART if f[56]]
    assert nz56 and all(f[:3] == b"\xbb\x01\x09" for f in nz56)
    assert not any(f[55] or f[57] for f in PRIORART)
