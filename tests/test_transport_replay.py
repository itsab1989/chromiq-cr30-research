"""Replay tests for the transport layer -- REAL captures, no hardware.

Every fixture here is device traffic recorded by tools/probe_*.py and redacted
by tools/redact.py. Fixtures are never edited to make a test pass (CLAUDE.md 14).
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30 import (Frame, ReplayTransport, Session, TransportError,  # noqa: E402
                  EchoedCommandError, is_echo, device_written_bytes)
from cr30.session import RESPONSE_BODY_END, RESPONSE_BODY_START  # noqa: E402

CAP = ROOT / "captures" / "public"


def load(name):
    return json.loads((CAP / name).read_text())


def test_import_cr30_does_not_import_pyserial():
    """The decoder must run where pyserial is not installed (CLAUDE.md 14).

    Guards the layering: frame/identity/session/transport must never import
    serial at module scope.
    """
    import subprocess
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import cr30, cr30.session, cr30.transport;"
         "print('serial' in sys.modules)" % str(ROOT / "src")],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False", out.stdout


# ---------------------------------------------------------------- replay
def test_replay_drives_a_full_identity_with_no_hardware():
    doc = load("EXP-MAC-USB-001-identity.json")
    probes = doc["trials"][0]["probes"]
    from cr30.transport import Exchange
    ex = [Exchange(bytes.fromhex(p["tx"]), bytes.fromhex(p["rx"]), f"sub {p['subcmd']}")
          for p in probes]
    # session-1's probe used the prior-art checksum on transmit; our Frame
    # builder uses the corrected rule, so the requests differ in byte 59 only.
    with Session(ReplayTransport(ex, strict=False)) as s:
        ident = s.identify()
    assert ident.is_cr30()
    assert ident.model == "CR30"
    assert ident.build == "0.0.20231219"


def test_replay_is_strict_about_what_we_send():
    """A replay that accepts any request proves nothing."""
    from cr30.transport import Exchange
    good = Frame.build(0xAA, 0x0A, 0x00, 0x00).to_bytes()
    t = ReplayTransport([Exchange(good, good, "x")], strict=True)
    t.open()
    with pytest.raises(TransportError, match="replay mismatch"):
        t.send(Frame.build(0xAA, 0x0A, 0x01, 0x00))


def test_replay_exhaustion_is_an_error_not_silence():
    t = ReplayTransport([]); t.open()
    with pytest.raises(TransportError, match="replay exhausted"):
        t.send(Frame.build(0xAA, 0x0A, 0x00, 0x00))


def test_transport_refuses_to_write_two_frames():
    """VERIFIED EXP-USB-005b: 120 bytes in one write is answered with silence."""
    t = ReplayTransport([]); t.open()
    two = Frame.build(0xAA, 0x0A, 0x00, 0x00).to_bytes() * 2
    with pytest.raises(TransportError, match="single 60-byte frame"):
        t.send(two)


# ------------------------------------------------- the echo trap (EXP-USB-003)
def test_echoed_commands_are_recognised_as_echoes():
    """BB 28 and BB 17 come back as our own frame. VERIFIED EXP-USB-003."""
    doc = load("EXP-USB-003-stage2-bb-checksum.json")
    echoed = [s for s in doc["steps"]
              if s["label"].startswith(("BB 28", "BB 17")) and s["rx_len"] == 60]
    assert echoed, "fixture missing"
    for s in echoed:
        tx, rx = bytes.fromhex(s["tx"]), bytes.fromhex(s["rx"])
        assert is_echo(tx, rx), s["label"]
        assert device_written_bytes(tx, rx) == [], s["label"]


def test_bb13_is_a_real_command_not_an_echo():
    """BB 13 writes frame offsets 5..10. VERIFIED EXP-USB-003."""
    doc = load("EXP-USB-003-stage2-bb-checksum.json")
    s = next(x for x in doc["steps"] if x["label"].startswith("BB 13 00 00"))
    tx, rx = bytes.fromhex(s["tx"]), bytes.fromhex(s["rx"])
    assert not is_echo(tx, rx)
    assert device_written_bytes(tx, rx) == [5, 6, 7, 8, 9, 10]


def test_session_refuses_to_report_an_echo_as_a_result():
    """The library must not let an unimplemented command look like a working one."""
    from cr30.transport import Exchange
    req = Frame.build(0xBB, 0x28, 0x00, 0x00)
    echo = bytearray(req.to_bytes()); echo[59] = sum(echo[:59]) % 256
    t = ReplayTransport([Exchange(req.to_bytes(), bytes(echo), "BB 28 echo")])
    with Session(t) as s:
        with pytest.raises(EchoedCommandError):
            s.transact_checked(req)


# ---------------------------------------- response extent (EXP-USB-006, Q1)
def test_device_leaves_request_bytes_at_offsets_4_and_55_to_57():
    """PROTOCOL.md 6 Q1. The device writes 5..54 and nothing else."""
    doc = load("EXP-USB-006-request-fields-AB.json")
    bat = doc["batteries"][0]
    ramp = next(c for c in bat["cases"] if "ramp" in c["label"])
    tx, rx = bytes.fromhex(ramp["tx"]), bytes.fromhex(ramp["rx"])
    for off in (4, 55, 56, 57):
        assert rx[off] == tx[off] != 0, f"offset {off} was expected to survive"
    written = set(device_written_bytes(tx, rx))
    assert written <= set(range(RESPONSE_BODY_START, RESPONSE_BODY_END))
    assert len(written) > 40, "the mutation must actually have landed"


def test_the_56_57_probe_mutation_actually_landed():
    """A probe that finds nothing may be a broken probe."""
    doc = load("EXP-USB-006-request-fields-AB.json")
    bat = doc["batteries"][0]
    ctrl = next(c for c in bat["cases"] if c["label"].startswith("control  "))
    tail = next(c for c in bat["cases"] if "56,57" in c["label"])
    assert bytes.fromhex(tail["tx"]) != bytes.fromhex(ctrl["tx"])
    rx, crx = bytes.fromhex(tail["rx"]), bytes.fromhex(ctrl["rx"])
    assert [i for i in range(60) if rx[i] != crx[i]] == [56, 57, 59]


def test_marker_byte_is_device_set_not_echoed():
    """PROTOCOL.md 6 Q3: request marker 0x00 / 0x5A -> reply marker still 0xFF."""
    doc = load("EXP-USB-006-request-fields-AB.json")
    for bat in doc["batteries"]:
        for c in bat["cases"]:
            if "marker byte58" in c["label"]:
                assert bytes.fromhex(c["tx"])[58] != 0xFF     # mutation landed
                assert bytes.fromhex(c["rx"])[58] == 0xFF, c["label"]


# ----------------------------------------------- checksum not enforced (003)
@pytest.mark.parametrize("cmd", ["BB 28", "BB 13"])
def test_checksum_is_not_enforced_on_the_bb_class(cmd):
    """EXP-USB-003. Extends EXP-USB-002's one-command result to 0xBB."""
    doc = load("EXP-USB-003-stage2-bb-checksum.json")
    cases = [s for s in doc["steps"] if s["label"].startswith(cmd + " ") and "cs=" in s["label"]]
    assert len(cases) >= 5, f"fixture missing for {cmd}"
    assert len({bytes.fromhex(s["tx"])[59] for s in cases}) == len(cases), \
        "the checksum byte must actually have varied"
    assert all(s["rx_len"] == 60 for s in cases)
    bodies = {bytes.fromhex(s["rx"])[:58] for s in cases}
    assert len(bodies) == 1, "reply content changed with the request checksum"


# --------------------------------- identity defects filed by [CR30-SKEPTIC]
def test_identity_rejects_a_reply_whose_subcommand_does_not_match():
    """The device echoes the request's sub-command; it was not being checked.

    If replies are out of step, fields get attributed to the wrong query and
    every value is silently wrong.
    """
    from cr30.identity import IdentityError, parse_identity as pid
    doc = load("EXP-MAC-USB-001-identity.json")
    probes = doc["trials"][0]["probes"]
    frames = {p["subcmd"]: Frame.parse(bytes.fromhex(p["rx"])) for p in probes}
    pid(frames)                                   # in-step: fine
    shifted = {0: frames[1], 1: frames[0], 2: frames[2], 3: frames[3]}
    with pytest.raises(IdentityError, match="reply/request mismatch"):
        pid(shifted)


def test_identity_fields_are_read_to_the_nul_not_a_fixed_width():
    """A longer model string on another unit must not be silently truncated."""
    from cr30.identity import parse_identity as pid
    doc = load("EXP-MAC-USB-001-identity.json")
    probes = doc["trials"][0]["probes"]
    frames = {p["subcmd"]: Frame.parse(bytes.fromhex(p["rx"])) for p in probes}
    assert pid(frames).model == "CR30"

    # same frame, but the model field holds a LONGER name
    raw = bytearray(frames[0].to_bytes())
    raw[39:48] = b"CR30PLUS\x00"
    raw[59] = sum(raw[:59]) % 256
    frames[0] = Frame.parse(bytes(raw))
    ident = pid(frames)
    assert ident.model == "CR30PLUS", "a 4-byte read would have returned 'CR30'"
    assert not ident.is_cr30(), "a CR30PLUS must not be identified as a CR30"


def test_identity_refuses_a_frame_known_to_be_corrupt():
    from cr30.identity import IdentityError, parse_identity as pid
    doc = load("EXP-MAC-USB-001-identity.json")
    probes = doc["trials"][0]["probes"]
    frames = {p["subcmd"]: Frame.parse(bytes.fromhex(p["rx"])) for p in probes}
    bad = bytearray(frames[0].to_bytes()); bad[59] ^= 0xFF
    frames[0] = Frame.parse(bytes(bad), verify=False)
    with pytest.raises(IdentityError, match="failed its checksum"):
        pid(frames)


def test_published_captures_declare_their_synthesised_checksums():
    """`[CR30-SKEPTIC]` objection 1: redaction rewrites byte 59 with the rule
    under test. Those frames must be named in the capture, not left for an
    auditor to discover."""
    import json as _json
    for p in sorted(CAP.glob("EXP-*.json")):
        doc = _json.loads(p.read_text())
        assert "_synthesised_checksums" in doc, f"{p.name} does not declare them"
        for h in doc["_synthesised_checksums"]:
            b = bytes.fromhex(h)
            assert len(b) == 60 and b[59] == sum(b[:59]) % 256
