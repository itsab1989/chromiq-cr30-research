"""USB measurement reassembly, replayed from real captured chunk frames."""
import json, pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from cr30.usb_measure import (CHUNK_SUBS, assemble, chunk_values, parse_axis)  # noqa: E402
from cr30.measurement import MeasurementError  # noqa: E402

CAP = ROOT / "captures" / "raw" / "EXP-CAL-001-EXP-MEAS-001-human-session.json"


def measurements():
    d = json.loads(CAP.read_text())
    out = []
    for p in d["phases"]:
        if p["phase"].startswith("measure:") and p.get("chunk_frames") and p.get("spectrum"):
            out.append((p["phase"], {int(k, 16): bytes.fromhex(v)
                                     for k, v in p["chunk_frames"].items()},
                        p["spectrum"], p.get("trigger_rx")))
    return out


CASES = measurements()


def test_have_real_captures():
    assert len(CASES) >= 5


@pytest.mark.parametrize("name,chunks,spectrum,_t", CASES)
def test_assemble_reproduces_the_captured_spectrum(name, chunks, spectrum, _t):
    assert assemble(chunks) == [round(v, 6) for v in spectrum]


@pytest.mark.parametrize("name,chunks,spectrum,trig", CASES)
def test_axis_is_400_10_31(name, chunks, spectrum, trig):
    if not trig:
        pytest.skip("no trigger frame recorded")
    assert parse_axis(bytes.fromhex(trig)) == (400, 10, 31)


def test_chunk_13_is_not_spectrum_but_repeats_the_first_five():
    """Guards the correction to itohio's '20 unexplained bytes'."""
    import struct
    for name, chunks, spectrum, _ in CASES:
        if 0x13 not in chunks:
            continue
        tail = struct.unpack_from("<5f", chunks[0x13], 34)
        assert [round(x, 4) for x in tail] == [round(x, 4) for x in spectrum[:5]]
        return
    pytest.fail("no 0x13 chunk in any capture")


def test_missing_chunk_fails_loudly():
    name, chunks, spectrum, _ = CASES[0]
    partial = {k: v for k, v in chunks.items() if k != 0x11}
    with pytest.raises(MeasurementError, match="0x11"):
        assemble(partial)


def test_mutation_lands():
    """A missing-chunk test only counts if the chunk really was removed."""
    name, chunks, spectrum, _ = CASES[0]
    assert 0x11 in chunks
    partial = {k: v for k, v in chunks.items() if k != 0x11}
    assert 0x11 not in partial and len(partial) == len(chunks) - 1
    assert assemble(chunks) == [round(v, 6) for v in spectrum]
