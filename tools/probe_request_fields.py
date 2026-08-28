#!/usr/bin/env python3
"""EXP-USB-006 -- how much of a REQUEST does the CR30 actually parse?

Attacks PROTOCOL.md 6 Q1 (payload extent) and Q3 (is byte 58 a constant
marker, or something else) without sending any new command.

Only ONE byte-group changes per case; everything else is byte-identical.
The script PROVES each mutation landed (asserts the tx bytes differ from the
control) before drawing any conclusion -- a probe that finds nothing may be a
broken probe.

SAFETY: the AA 0A battery is a device-info READ and carries no risk. The BB 28
battery varies only the framing byte 58, never payload semantics.
"""
import sys, time, json, pathlib, datetime, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)
STAGE = sys.argv[2] if len(sys.argv) > 2 else "AB"


def build(start, cmd, sub, param, payload=None, marker=0xFF):
    d = bytearray(60)
    d[0], d[1], d[2], d[3] = start, cmd, sub, param
    if payload:
        d[4:58] = payload
    d[58] = marker
    d[59] = sum(d[:59]) % 256          # always the VERIFIED rule; checksum is not the variable here
    return bytes(d)


def drain(ser, first_wait=1.2, quiet=0.25):
    buf = bytearray(); t0 = time.perf_counter(); first = None
    dl = t0 + first_wait
    while time.perf_counter() < dl:
        n = ser.in_waiting
        if n:
            if first is None: first = time.perf_counter() - t0
            buf += ser.read(n); dl = time.perf_counter() + quiet
        else: time.sleep(0.005)
    return bytes(buf), first


RAMP = bytes(((i * 7 + 1) & 0xFF) or 1 for i in range(54))   # distinctive, no 0x00

def cases_for(start, cmd, sub, param, with_payload):
    c = [("control  (zero payload, marker 0xFF)", build(start, cmd, sub, param))]
    if with_payload:
        c.append(("payload 4..57 = ramp", build(start, cmd, sub, param, payload=RAMP)))
        p = bytearray(54); p[52], p[53] = 0xA5, 0x5A          # frame offsets 56,57
        c.append(("bytes 56,57 = A5 5A only", build(start, cmd, sub, param, payload=bytes(p))))
    c += [("marker byte58 = 0x00", build(start, cmd, sub, param, marker=0x00)),
          ("marker byte58 = 0x5A", build(start, cmd, sub, param, marker=0x5A)),
          ("control again (regression)", build(start, cmd, sub, param))]
    return c


log = {"experiment": "EXP-USB-006",
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 (24G830) arm64",
       "stage": STAGE, "batteries": []}

batteries = []
if "A" in STAGE:
    batteries.append(("A: AA 0A 00 00 (device-info READ, zero risk)", 0xAA, 0x0A, 0x00, 0x00, True))
if "B" in STAGE:
    batteries.append(("B: BB 28 00 00 (framing byte only)", 0xBB, 0x28, 0x00, 0x00, False))
if "C" in STAGE:   # only after B proves BB 28 is an echo
    batteries.append(("C: BB 28 00 00 payload probe (echo confirmed)", 0xBB, 0x28, 0x00, 0x00, True))

with serial.Serial(PORT, 115200, timeout=0.2, bytesize=8, parity="N",
                   stopbits=1, rtscts=False, dsrdtr=False) as ser:
    time.sleep(0.30); ser.reset_input_buffer()
    for title, start, cmd, sub, param, wp in batteries:
        print(f"\n{title}")
        bat = {"title": title, "cases": []}
        ctrl_tx = ctrl_rx = None
        for label, pkt in cases_for(start, cmd, sub, param, wp):
            ser.reset_input_buffer(); ser.write(pkt); ser.flush()
            rx, first = drain(ser)
            if ctrl_tx is None:
                ctrl_tx, ctrl_rx = pkt, rx
                mutated = None
            else:
                mutated = pkt != ctrl_tx
            rec = {"label": label, "tx": pkt.hex(), "rx_len": len(rx), "rx": rx.hex(),
                   "first_byte_s": first, "tx_differs_from_control": mutated,
                   "rx_equals_control_rx": (rx == ctrl_rx), "rx_equals_tx": (rx == pkt)}
            bat["cases"].append(rec)
            m = "n/a " if mutated is None else ("YES " if mutated else "!!NO")
            print(f"  {label:34s} tx-mutated={m} rx={len(rx):3d}B "
                  f"rx==ctrl_rx={rec['rx_equals_control_rx']!s:5s} rx==tx={rec['rx_equals_tx']}")
            if len(rx) == 60 and rx != ctrl_rx:
                print(f"      rx = {rx.hex(' ')}")
            time.sleep(0.15)
        log["batteries"].append(bat)

p = OUT / f"EXP-USB-006-request-fields-{STAGE}.json"
p.write_text(json.dumps(log, indent=2))
print("\nwrote", p)
