#!/usr/bin/env python3
"""Decode CR30 measurements out of a mined frame corpus -> captures/public/.

    tools/decode_spectra.py captures/public/PRIORART-001-vendor-usb-frames.json

A measurement is a header frame `BB 01 09` followed by data chunks
`BB 01 10/11/12`.  The header's payload declares the spectral axis; the chunks
carry float32 LE values, TWELVE per chunk starting at frame offset 6:

    chunk 0x10 -> values  0..11      (12)
    chunk 0x11 -> values 12..23      (12)
    chunk 0x12 -> values 24..30      ( 7, rest zero-padded)
                                     -- 31 total
    chunk 0x13 -> NOT spectral. Repeats values 0..4 at frame offset 34.

This differs from itohio, which concatenates 0x10..0x12 and slices 124 bytes.
That arrives at the same 31 numbers by accident: their "144 accumulated, 124
used, 20 unexplained" is chunk 0x12's zero padding, not a missing field.
See MEASUREMENT.md.

The axis is NOT hard-coded. It is read from the header and, if it disagrees
with what the chunks deliver, the measurement is REJECTED (CLAUDE.md s14).
"""
import json, pathlib, struct, sys

VALS_PER_CHUNK = 12
DATA_AT = 6                     # frame offset of the first float in a chunk


class SpectrumError(Exception):
    """A measurement that cannot be decoded is an error, never a partial result."""


def axis(header: bytes) -> tuple[int, int, int]:
    """(start_nm, count, step_nm) as DECLARED by the BB 01 09 header.

    HYPOTHESIS, corroborated twice: header[4:7] == 28 1f 0a == 40, 31, 10, and
    the vendor application's own export records wave_start 400, wave_number 31,
    wave_interval 10 for the same traffic. Byte 4 is therefore read as
    start_nm/10. Every capture seen so far carries the same three bytes, so
    this is consistent with -- not proof of -- a self-describing axis.
    """
    return header[4] * 10, header[5], header[6]


def decode(header: bytes, chunks: dict[int, bytes]) -> dict:
    start_nm, count, step_nm = axis(header)
    need = [0x10, 0x11, 0x12][: -(-count // VALS_PER_CHUNK) or None]
    missing = [c for c in need if c not in chunks]
    if missing:
        raise SpectrumError(
            f"header declares {count} values needing chunks {[hex(c) for c in need]}; "
            f"missing {[hex(c) for c in missing]} -- refusing to return a partial spectrum")
    vals: list[float] = []
    for c in need:
        f = chunks[c]
        vals += struct.unpack("<12f", f[DATA_AT:DATA_AT + 4 * VALS_PER_CHUNK])
    if len(vals) < count:
        raise SpectrumError(f"decoded {len(vals)} values, header declares {count}")
    return {
        "start_nm": start_nm, "count": count, "step_nm": step_nm,
        "wavelengths": [start_nm + i * step_nm for i in range(count)],
        "values": [round(v, 6) for v in vals[:count]],
        "header_marker": header[58],
    }


def main(argv):
    src = pathlib.Path(argv[1])
    doc_in = json.loads(src.read_text())
    frames = [(s["capture"], bytes.fromhex(h))
              for s in doc_in["sequences"] for h in s["frames"]]
    out, cur = [], None
    for cap, w in frames:
        empty = not any(w[4:58])
        if w[0] == 0xBB and w[1] == 0x01 and w[2] == 0x09 and not empty:
            if cur:
                out.append(cur)
            cur = {"hdr": w, "chunks": {}, "capture": cap}
        elif cur and w[0] == 0xBB and w[1] == 0x01 and w[2] in (0x10, 0x11, 0x12, 0x13) and not empty:
            cur["chunks"].setdefault(w[2], w)
    if cur:
        out.append(cur)

    spectra, rejected = [], 0
    for m in out:
        try:
            d = decode(m["hdr"], m["chunks"]); d["capture"] = m["capture"]
            spectra.append(d)
        except SpectrumError:
            rejected += 1

    seen, uniq = set(), []
    for s in spectra:
        k = tuple(s["values"])
        if k not in seen:
            seen.add(k); uniq.append(s)

    doc = {
        "experiment": "PRIORART-002",
        "provenance": f"decoded from {src.name} by tools/decode_spectra.py",
        "confidence": "CORROBORATION only -- a second unit, sniffed vendor traffic",
        "decoded": len(spectra), "rejected_incomplete": rejected, "unique": len(uniq),
        "spectra": uniq,
    }
    dst = src.parent / "PRIORART-002-spectra.json"
    dst.write_text(json.dumps(doc, indent=2))
    print(f"{len(spectra)} decoded ({rejected} rejected), {len(uniq)} unique -> {dst}")


if __name__ == "__main__":
    main(sys.argv)
