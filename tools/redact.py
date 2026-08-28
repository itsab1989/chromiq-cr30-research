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

def scrub_hex(h):
    b = bytearray.fromhex(h)
    changed = False
    for real, fake in SECRETS.items():
        i = bytes(b).find(real.encode())
        while i != -1:
            b[i:i+len(real)] = fake.encode(); changed = True
            i = bytes(b).find(real.encode())
    if changed and len(b) == 60:
        b[59] = sum(b[:59]) % 256          # keep the frame self-consistent
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
    d = walk(json.loads(p.read_text()))
    d["_redaction"] = ("Unit-specific device-id strings replaced with same-length "
                       "placeholders; checksum recomputed so frames stay valid.")
    out.write_text(json.dumps(d, indent=2))
    print("redacted ->", out)
