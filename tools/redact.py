#!/usr/bin/env python3
"""Redact unit-specific identifiers from a raw capture -> captures/public/.

Replaces the ASCII device-id strings with same-length placeholders so byte
offsets, lengths and structure are preserved. The checksum is RECOMPUTED and
the original checksum recorded, so a redacted frame stays self-consistent and
is still a usable test fixture.
"""
import json, sys, pathlib, re
SECRETS = {}
loc = pathlib.Path(__file__).resolve().parent.parent / "LOCAL_DEVICE_IDS.md"
if loc.exists():
    for m in re.finditer(r":\s{2,}([A-Z0-9]{8,})\s*$", loc.read_text(), re.M):
        s = m.group(1)
        SECRETS[s] = ("REDACTED" + "X" * (len(s) - 8))[:len(s)]

SYNTHESISED = []          # hex of every frame whose checksum we rewrote


def scrub_hex(h):
    b = bytearray.fromhex(h)
    changed = False
    for real, fake in SECRETS.items():
        i = bytes(b).find(real.encode())
        while i != -1:
            b[i:i+len(real)] = fake.encode(); changed = True
            i = bytes(b).find(real.encode())
    if changed and len(b) == 60:
        # The frame must stay self-consistent to be a usable fixture, so byte 59
        # is recomputed -- WITH THE RULE UNDER TEST.
        #
        # `[CR30-SKEPTIC]` OBJECTION 1: that makes such a frame satisfy the
        # checksum rule BY CONSTRUCTION. It would satisfy it if the device had
        # used CRC-32. It is a valid framing/parsing fixture and is NOT evidence
        # for any checksum rule, and the published claim "4/4 device frames" was
        # really 2/4 because of it.
        #
        # Fixed: every rewritten frame is now recorded in the capture under
        # `_synthesised_checksums`, so an auditor -- and
        # `tests/test_checksum_rule_space.py` -- can exclude them by name
        # instead of having to notice the problem.
        b[59] = sum(b[:59]) % 256
        SYNTHESISED.append(b.hex())
    return b.hex(), changed

def walk(o):
    if isinstance(o, dict):  return {k: walk(v) for k, v in o.items()}
    if isinstance(o, list):  return [walk(v) for v in o]
    if isinstance(o, str) and re.fullmatch(r"(?:[0-9a-f]{2})+", o) and len(o) >= 40:
        return scrub_hex(o)[0]
    return o

for src in sys.argv[1:]:
    p = pathlib.Path(src)
    out = p.parent.parent / "public" / p.name
    out.parent.mkdir(parents=True, exist_ok=True)
    SYNTHESISED.clear()
    d = walk(json.loads(p.read_text()))
    d["_redaction"] = ("Unit-specific device-id strings replaced with same-length "
                       "placeholders; checksum recomputed so frames stay valid.")
    d["_synthesised_checksums"] = sorted(set(SYNTHESISED))
    d["_synthesised_checksums_note"] = (
        "Byte 59 of these frames was recomputed by tools/redact.py using "
        "sum(0..58) mod 256. They satisfy that rule BY CONSTRUCTION and are NOT "
        "evidence for it. Use them as framing fixtures only. The device's own "
        "bytes are in captures/raw/ (gitignored). Raised by [CR30-SKEPTIC], "
        "objection 1.")
    out.write_text(json.dumps(d, indent=2))
    n = len(d["_synthesised_checksums"])
    print(f"redacted -> {out}" + (f"  ({n} frame(s) have a SYNTHESISED checksum)" if n else ""))
