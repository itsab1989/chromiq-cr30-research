#!/usr/bin/env python3
"""EXP-USB-003 stage 2 -- is the checksum enforced on the 0xBB command class?

Commands used are EXACTLY the three 0xBB frames that itohio/color-science's
`CR30Device.handshake()` sends on every connect, byte-for-byte:

    BB 17 00 00                       "Initialize device"
    BB 13 00 00 + b'Check'+00*7       "Simple 'Check' command"
    BB 28 00 <idx>                    "Query parameters"

Reproducing observed vendor handshake traffic is not a command-space sweep.
EXP-USB-004 (the sweep) remains BLOCKED (CLAUDE.md 11).

Every step is followed by an AA 0A 00 00 re-baseline so that any state change
the 0xBB traffic causes is detected, not assumed absent.
"""
import sys, time, json, pathlib, datetime, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

def build(start, cmd, sub, param, data=b"", marker=0xFF, cs=None, payload=None):
    d = bytearray(60)
    d[0], d[1], d[2], d[3] = start, cmd, sub, param
    if payload is not None: d[4:58] = payload
    elif data: d[4:4+len(data)] = data
    d[58] = marker
    d[59] = sum(d[:59]) % 256 if cs is None else cs
    return bytes(d)

def drain(ser, first_wait=1.5, quiet=0.30):
    buf = bytearray(); t0 = time.perf_counter(); first = None; dl = t0 + first_wait
    while time.perf_counter() < dl:
        n = ser.in_waiting
        if n:
            if first is None: first = time.perf_counter() - t0
            buf += ser.read(n); dl = time.perf_counter() + quiet
        else: time.sleep(0.005)
    return bytes(buf), first

log = {"experiment": "EXP-USB-003-stage2",
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 (24G830) arm64", "steps": []}

BASE = None
def go(ser, label, pkt, note=""):
    global BASE
    ser.reset_input_buffer(); ser.write(pkt); ser.flush()
    rx, first = drain(ser)
    echo = (rx == pkt)
    # which bytes did the device WRITE, vs leave as our request?
    written = [i for i in range(60) if len(rx) == 60 and rx[i] != pkt[i]]
    rec = {"label": label, "note": note, "tx": pkt.hex(), "rx_len": len(rx), "rx": rx.hex(),
           "first_byte_s": first, "rx_equals_tx": echo, "bytes_device_changed": written,
           "rx_cs_ok_ours": (len(rx) == 60 and rx[59] == sum(rx[:59]) % 256)}
    log["steps"].append(rec)
    print(f"  {label:38s} rx={len(rx):3d}B echo={echo!s:5s} "
          f"device-changed={written if len(written)<12 else str(len(written))+' bytes'}")
    return rx

with serial.Serial(PORT, 115200, timeout=0.2) as ser:
    time.sleep(0.30); ser.reset_input_buffer()

    print("0. baseline")
    BASE = go(ser, "AA 0A 00 00", build(0xAA, 0x0A, 0, 0)); time.sleep(0.2)

    print("\n1. is BB 28 producing response CONTENT, or nothing at all?")
    p = bytearray(54); p[49], p[50] = 0xA5, 0x5A          # frame offsets 53,54
    go(ser, "BB 28 00 00, bytes 53,54 = A5 5A", build(0xBB, 0x28, 0, 0, payload=bytes(p)),
       "if A5 5A survive, the device wrote no response block"); time.sleep(0.2)
    go(ser, "AA 0A 00 00 re-baseline", build(0xAA, 0x0A, 0, 0)); time.sleep(0.2)

    print("\n2. the other two vendor-handshake 0xBB commands")
    go(ser, "BB 13 00 00 'Check'", build(0xBB, 0x13, 0, 0, data=b"Check" + b"\x00" * 7)); time.sleep(0.3)
    go(ser, "AA 0A 00 00 re-baseline", build(0xAA, 0x0A, 0, 0)); time.sleep(0.2)
    go(ser, "BB 17 00 00 'Initialize'", build(0xBB, 0x17, 0, 0)); time.sleep(0.5)
    go(ser, "AA 0A 00 00 re-baseline", build(0xAA, 0x0A, 0, 0)); time.sleep(0.2)

    print("\n3. EXP-USB-003: vary ONLY byte 59 on BB 28 00 00")
    ctrl = build(0xBB, 0x28, 0, 0)
    print(f"     (correct checksum for this frame = 0x{ctrl[59]:02X};"
          f" itohio's 0xBB rule gives the SAME value -- they only differ if marker != 0xFF)")
    for name, cs in [("correct", ctrl[59]), ("off-by-one -1", (ctrl[59] - 1) % 256),
                     ("off-by-one +1", (ctrl[59] + 1) % 256),
                     ("0x00", 0x00), ("0xFF", 0xFF), ("0x42", 0x42)]:
        go(ser, f"BB 28 00 00 cs={name} (0x{cs:02X})", build(0xBB, 0x28, 0, 0, cs=cs)); time.sleep(0.15)

    print("\n4. EXP-USB-003: vary ONLY byte 59 on BB 13 'Check'")
    c13 = build(0xBB, 0x13, 0, 0, data=b"Check" + b"\x00" * 7)
    for name, cs in [("correct", c13[59]), ("off-by-one -1", (c13[59] - 1) % 256),
                     ("0x00", 0x00), ("0xFF", 0xFF), ("0x42", 0x42)]:
        go(ser, f"BB 13 cs={name} (0x{cs:02X})",
           build(0xBB, 0x13, 0, 0, data=b"Check" + b"\x00" * 7, cs=cs)); time.sleep(0.15)

    print("\n5. final baseline -- device unchanged?")
    fin = go(ser, "AA 0A 00 00 final", build(0xAA, 0x0A, 0, 0))
    log["device_unchanged_end_to_end"] = (fin == BASE)
    print(f"  identity reply identical to the opening baseline: {fin == BASE}")

p = OUT / "EXP-USB-003-stage2-bb-checksum.json"
p.write_text(json.dumps(log, indent=2))
print("\nwrote", p)
