#!/usr/bin/env python3
"""EXP-USB-007 -- does ChromIQ's Argyll serial scan disturb a CR30?

`ChromIQ/core/argyll_runner.py` deliberately keeps `/dev/cu.usbserial-*` in
Argyll's serial scan so serial SpectroScans keep working. Argyll then calls
`fast_ser_dev_type()` (`spectro/inst.c`) during plain port enumeration and
writes foreign ASCII probe strings to whatever is on that port, at 9600 /
921600 / 115200 / 38400 baud. A CR30 plugged into a machine running ChromIQ is
receiving that traffic today and nobody has checked what it does with it.

Strings verified against ArgyllCMS 3.5.0 `spectro/inst.c::fast_ser_dev_type`.

PREDICTION from EXP-USB-005c: nothing happens, because the CR30 answered
nothing to five writes that were not exactly 60 bytes in one call, and every
Argyll probe is 1-10 bytes. Confirming that is cheap; assuming it is not.

The identity fingerprint is taken before and after EVERY probe string
(SAFETY_ENVELOPE.md 4b); any change aborts.
"""
import sys, time, json, pathlib, datetime, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

ARGYLL_PROBES = [(";", "Spectrolino / generic"), ("D024\r\n", "Spectrolino"),
                 ("X", "Lumagen menu-off"), ("#ZQS00\r", "Lumagen Radiance"),
                 ("#0ZQS008E\r", "Lumagen Radiance"), ("#0ZQS018F\r", "Lumagen Radiance"),
                 ("P0\r", "Klein K10"), ("*idn?\r", "SCPI identify")]
ARGYLL_BAUDS = [9600, 921600, 115200, 38400]

def ident(sub): 
    d = bytearray(60); d[0], d[1], d[2] = 0xAA, 0x0A, sub
    d[58] = 0xFF; d[59] = sum(d[:59]) % 256; return bytes(d)

def read_frame(ser, timeout):
    t0 = time.perf_counter(); buf = bytearray()
    while len(buf) < 60 and time.perf_counter() - t0 < timeout:
        n = ser.in_waiting
        if n: buf += ser.read(min(n, 60 - len(buf)))
        else: time.sleep(0.0005)
    return bytes(buf)

def fingerprint(ser):
    out = b""
    for s in range(4):
        ser.reset_input_buffer(); ser.write(ident(s)); ser.flush()
        out += read_frame(ser, 2.0)
    return out

log = {"experiment": "EXP-USB-007", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 (24G830) arm64",
       "source": "ArgyllCMS 3.5.0 spectro/inst.c::fast_ser_dev_type",
       "prediction": "no effect -- probes are not 60-byte single writes (EXP-USB-005c)",
       "probes": []}

with serial.Serial(PORT, 115200, timeout=0.05) as ser:
    ser.reset_input_buffer()
    base = fingerprint(ser)
    log["fingerprint_bytes"] = len(base)
    print(f"baseline fingerprint: {len(base)} bytes")
    if len(base) != 240:
        sys.exit("baseline fingerprint incomplete -- aborting")

    for baud in ARGYLL_BAUDS:
        for text, who in ARGYLL_PROBES:
            data = text.encode("ascii")
            with serial.Serial(PORT, baud, timeout=0.05) as s2:
                s2.reset_input_buffer(); s2.write(data); s2.flush()
                t0 = time.perf_counter(); back = bytearray()
                while time.perf_counter() - t0 < 0.35:
                    n = s2.in_waiting
                    if n: back += s2.read(n)
                    else: time.sleep(0.005)
            fp = fingerprint(ser)
            same = (fp == base)
            rec = {"baud": baud, "probe": text.encode("unicode_escape").decode(),
                   "who": who, "bytes_written": len(data),
                   "bytes_back": len(back), "back": bytes(back).hex(),
                   "fingerprint_unchanged": same}
            log["probes"].append(rec)
            mark = "ok " if (same and not back) else "!! "
            print(f"  {mark}{baud:>7} baud  {text!r:16s} ({len(data)} B) -> "
                  f"{len(back)} B back, fingerprint unchanged={same}")
            if not same:
                log["aborted"] = f"fingerprint changed after {text!r} at {baud}"
                print("!! ABORT --", log["aborted"]); break
        if "aborted" in log: break

    log["final_fingerprint_unchanged"] = (fingerprint(ser) == base)
    print(f"\nfinal fingerprint unchanged: {log['final_fingerprint_unchanged']}")
    log["probes_that_produced_output"] = sum(1 for p in log["probes"] if p["bytes_back"])
    log["probes_that_changed_fingerprint"] = sum(1 for p in log["probes"]
                                                 if not p["fingerprint_unchanged"])

p = OUT / "EXP-USB-007-argyll-serial-scan.json"; p.write_text(json.dumps(log, indent=2))
print(f"\n{len(log['probes'])} probes; {log['probes_that_produced_output']} produced output; "
      f"{log['probes_that_changed_fingerprint']} changed the fingerprint")
print("wrote", p)
