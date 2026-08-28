#!/usr/bin/env python3
"""EXP-MAC-USB-001 -- baseline identity probe.

Read-only. Sends only the published device-identity query (AA 0A ss 00) and
records every byte received verbatim. Never interprets before recording.
"""
import sys, time, json, pathlib, datetime
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
OUT = pathlib.Path(__file__).resolve().parent.parent / "captures" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

def build(start, cmd, subcmd, param):
    """Prior-art framing (itohio). Under test, not assumed correct."""
    d = bytearray(60)
    d[0], d[1], d[2], d[3] = start, cmd, subcmd, param
    d[58] = 0xFF
    cs = sum(d[:58]) % 256
    if start == 0xBB:
        cs = (cs - 1) % 256
    d[59] = cs
    return bytes(d)

def drain(ser, seconds):
    buf = bytearray()
    end = time.time() + seconds
    while time.time() < end:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            end = time.time() + 0.35   # extend while data still flowing
        else:
            time.sleep(0.02)
    return bytes(buf)

log = {"experiment": "EXP-MAC-USB-001",
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 arm64", "trials": []}

for baud in (115200, 19200, 9600, 57600, 38400):
    trial = {"baud": baud}
    try:
        ser = serial.Serial(PORT, baud, timeout=0.2,
                            bytesize=8, parity="N", stopbits=1, rtscts=False, dsrdtr=False)
    except Exception as e:
        trial["error"] = f"open failed: {e!r}"
        log["trials"].append(trial); continue
    with ser:
        time.sleep(0.30)
        ser.reset_input_buffer()
        trial["passive"] = drain(ser, 1.0).hex()
        probes = []
        for sub in (0x00, 0x01, 0x02, 0x03):
            pkt = build(0xAA, 0x0A, sub, 0x00)
            ser.reset_input_buffer()
            ser.write(pkt); ser.flush()
            rx = drain(ser, 1.2)
            probes.append({"tx": pkt.hex(), "subcmd": sub,
                           "rx_len": len(rx), "rx": rx.hex()})
        trial["probes"] = probes
    log["trials"].append(trial)
    print(f"baud {baud:>6}: " + " ".join(f"s{p['subcmd']}={p['rx_len']}B" for p in trial.get("probes", [])),
          flush=True)

p = OUT / "EXP-MAC-USB-001-identity.json"
p.write_text(json.dumps(log, indent=2))
print("\nwrote", p)
