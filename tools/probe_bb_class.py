#!/usr/bin/env python3
"""EXP-USB-003 stage 1 -- does the 0xBB command class answer, and how?

SAFETY. This does NOT sweep the command space (that is EXP-USB-004, BLOCKED).
It sends exactly ONE 0xBB command: `BB 28 00 xx`, which itohio/color-science's
`CR30Device.handshake()` issues on every single connect, labelled there as
"Query parameters". A read-only query issued unconditionally by working prior
art is the least side-effecting 0xBB command that exists in any source we have.

Recorded verbatim before any interpretation (CLAUDE.md 13).
"""
import sys, time, json, pathlib, datetime, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)


def frame(start, cmd, subcmd, param, data=b"", marker=0xFF, cs=None):
    d = bytearray(60)
    d[0], d[1], d[2], d[3] = start, cmd, subcmd, param
    d[4:4 + len(data)] = data
    d[58] = marker
    d[59] = sum(d[:59]) % 256 if cs is None else cs
    return bytes(d)


def drain(ser, first_wait=1.5, quiet=0.30):
    """Collect bytes until `quiet` seconds pass with nothing, or first_wait elapses empty."""
    buf = bytearray()
    t0 = time.perf_counter()
    first_byte_at = None
    deadline = t0 + first_wait
    while time.perf_counter() < deadline:
        n = ser.in_waiting
        if n:
            if first_byte_at is None:
                first_byte_at = time.perf_counter() - t0
            buf += ser.read(n)
            deadline = time.perf_counter() + quiet
        else:
            time.sleep(0.005)
    return bytes(buf), first_byte_at, time.perf_counter() - t0


log = {"experiment": "EXP-USB-003-stage1",
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 (24G830) arm64",
       "safety_note": "one prior-art handshake QUERY command only; no sweep",
       "steps": []}


def step(ser, label, pkt, note=""):
    ser.reset_input_buffer()
    ser.write(pkt); ser.flush()
    rx, first, total = drain(ser)
    rec = {"label": label, "note": note, "tx": pkt.hex(),
           "rx_len": len(rx), "rx": rx.hex(),
           "first_byte_s": first, "window_s": round(total, 4)}
    log["steps"].append(rec)
    print(f"  {label:28s} tx={pkt[:4].hex(' ')} -> {len(rx):3d} B"
          f"  first_byte={'-' if first is None else f'{first*1000:.1f} ms'}")
    if len(rx) == 60:
        print(f"      rx = {rx.hex(' ')}")
    return rx


with serial.Serial(PORT, 115200, timeout=0.2, bytesize=8, parity="N",
                   stopbits=1, rtscts=False, dsrdtr=False) as ser:
    time.sleep(0.30)
    ser.reset_input_buffer()

    print("A. baseline -- device alive? (known-good identity command)")
    base = step(ser, "AA 0A 00 00 (baseline)", frame(0xAA, 0x0A, 0x00, 0x00))
    log["baseline_ok"] = len(base) == 60 and base[59] == sum(base[:59]) % 256
    if not log["baseline_ok"]:
        print("!! baseline failed -- aborting before sending any 0xBB traffic")
    else:
        time.sleep(0.2)
        print("\nB. the one 0xBB command under test: BB 28 00 xx (parameter QUERY)")
        for idx in (0x00, 0x01, 0x02, 0x03, 0xFF):
            step(ser, f"BB 28 00 {idx:02X} (param query)", frame(0xBB, 0x28, 0x00, idx))
            time.sleep(0.2)

        print("\nC. baseline again -- did the 0xBB traffic disturb the device?")
        after = step(ser, "AA 0A 00 00 (re-baseline)", frame(0xAA, 0x0A, 0x00, 0x00))
        log["device_unchanged"] = (after == base)
        print(f"  identity reply identical to before: {after == base}")

p = OUT / "EXP-USB-003-stage1-bb-class.json"
p.write_text(json.dumps(log, indent=2))
print("\nwrote", p)
