#!/usr/bin/env python3
"""Extract CR30 frames from the itohio prior-art Eltima Serial-Port-Monitor dumps.

    tools/mine_priorart_frames.py <dir-with-*.spm>

Source: https://github.com/itohio/color-science  (MIT, (c) 2025 itohio),
`reverse-engineer-c30/serial-sniffer/*.spm` -- Windows sniffs of the VENDOR
application talking to a DIFFERENT CR30 unit.  Prior art is evidence, never
ground truth (CLAUDE.md s10): frames mined here are CORROBORATION, never
VERIFIED-class on their own.

Extraction is deliberately STRUCTURAL, not checksum-driven, so the corpus can
be used to TEST checksum hypotheses without circularity.  A window qualifies as
a candidate frame on four criteria that say nothing about byte 59:

    byte 0  in {0xAA, 0xBB}      byte 3  == 0x00
    byte 58 in {0x00, 0xFF}      the next 60 bytes chain or the window ends

`--all-windows` emits every structural candidate including the ~57% that are
sniffer scaffolding, so a reviewer can measure the false-positive rate of any
rule for themselves.  By default only frames that survive `sum(0..58) % 256`
are emitted, and the header records how many did not.

NOTHING IS EVER REWRITTEN.  Unlike tools/redact.py this tool must not touch
byte 59 -- a recomputed checksum would destroy the only evidence the corpus
carries.  Identity frames (0xAA 0x0A) carry that unit's ASCII device ids, so
they are DROPPED rather than redacted, for the same reason.
"""
import json, pathlib, sys, collections

FRAME = 60


def candidates(b: bytes):
    """Every structurally plausible 60-byte window. No checksum filter."""
    out, i = [], 0
    while i < len(b) - FRAME:
        if b[i] in (0xAA, 0xBB) and b[i + 58] in (0x00, 0xFF) and b[i + 3] == 0x00:
            out.append(b[i:i + FRAME]); i += FRAME
        else:
            i += 1
    return out


def main(argv):
    src = pathlib.Path(argv[1] if len(argv) > 1 else ".")
    keep_all = "--all-windows" in argv
    files = sorted(src.glob("*.spm"))
    if not files:
        sys.exit(f"no *.spm under {src}")

    seqs, dropped_id, failed_cs, total, uniq = [], 0, 0, 0, set()
    for p in files:
        seq, prev = [], None
        for w in candidates(p.read_bytes()):
            total += 1
            if w[59] != sum(w[:59]) % 256:
                failed_cs += 1
                if not keep_all:
                    continue
            if w[0] == 0xAA and w[1] == 0x0A:
                dropped_id += 1          # carries that unit's ASCII device ids
                continue
            h = w.hex()
            if h == prev:                # Eltima logs each IRP twice
                continue
            prev = h; seq.append(h); uniq.add(h)
        if seq:
            seqs.append({"capture": p.name, "frames": seq})

    doc = {
        "experiment": "PRIORART-001",
        "provenance": "itohio/color-science reverse-engineer-c30/serial-sniffer/*.spm (MIT)",
        "unit": "NOT the unit in EXP-MAC-USB-001 -- a second, third-party CR30",
        "platform": "Windows, vendor application, Eltima Serial Port Monitor v3",
        "confidence": "CORROBORATION only. Prior art is evidence, not ground truth.",
        "extraction": "structural (start/param/marker + chaining); byte 59 NOT used to select",
        "note": "byte 59 is never rewritten; 0xAA 0x0A identity frames dropped (device ids)",
        "structural_windows": total,
        "failed_sum_0_58": failed_cs,
        "identity_frames_dropped": dropped_id,
        "unique_frames": len(uniq),
        "note2": "ORDER IS PRESERVED per capture (consecutive duplicates removed) "
                 "so request/reply and measurement grouping survive.",
        "sequences": seqs,
    }
    out = pathlib.Path(__file__).resolve().parent.parent / "captures" / "public" / "PRIORART-001-vendor-usb-frames.json"
    out.write_text(json.dumps(doc, indent=2))
    print(f"{total} structural windows, {failed_cs} failed sum(0..58), "
          f"{dropped_id} identity frames dropped -> {len(uniq)} unique -> {out}")


if __name__ == "__main__":
    main(sys.argv)
