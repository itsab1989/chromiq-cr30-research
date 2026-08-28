#!/usr/bin/env python3
"""EXP-USB-005 -- timing and transport characterisation. Measure, do not quote.

Answers, with numbers:
  1 response latency, first byte and last byte, distribution over many trials
  2 is the 300 ms post-open settle delay in tools/probe_identity.py necessary?
  3 is an inter-command delay necessary?
  4 does a close/open cycle behave?
  5 does the device emit anything unsolicited over a long idle window?
  6 does LINE CODING matter (7E1 / 8N2 / 7N1)?  <- falsifies PROTOCOL.md 3's
    stated MECHANISM ("line coding is discarded, never reaches a UART")
  7 can two requests be pipelined without reading between them?

Read-only commands throughout (AA 0A device info, BB 13 vendor 'Check').
"""
import sys, time, json, pathlib, datetime, statistics, serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
IDLE_S = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

def build(start, cmd, sub=0, param=0, data=b""):
    d = bytearray(60); d[0], d[1], d[2], d[3] = start, cmd, sub, param
    d[4:4+len(data)] = data; d[58] = 0xFF; d[59] = sum(d[:59]) % 256
    return bytes(d)

IDENT = build(0xAA, 0x0A, 0, 0)
CHECK = build(0xBB, 0x13, 0, 0, data=b"Check" + b"\x00" * 7)

def txrx(ser, pkt, timeout=1.0):
    """Send and time. Returns (rx, t_first_byte, t_last_byte) in seconds."""
    ser.reset_input_buffer()
    t0 = time.perf_counter(); ser.write(pkt); ser.flush()
    buf = bytearray(); first = None; dl = t0 + timeout
    while len(buf) < 60 and time.perf_counter() < dl:
        n = ser.in_waiting
        if n:
            if first is None: first = time.perf_counter() - t0
            buf += ser.read(n)
        else: time.sleep(0.0005)
    return bytes(buf), first, time.perf_counter() - t0

def stats(v):
    v = [x for x in v if x is not None]
    if not v: return None
    return {"n": len(v), "min_ms": round(min(v)*1000, 3), "median_ms": round(statistics.median(v)*1000, 3),
            "mean_ms": round(statistics.fmean(v)*1000, 3), "max_ms": round(max(v)*1000, 3),
            "stdev_ms": round(statistics.pstdev(v)*1000, 3)}

log = {"experiment": "EXP-USB-005", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": "macOS 15.7.9 (24G830) arm64", "results": {}}
R = log["results"]

# ---------------------------------------------------------------- 1 latency
print("1. latency, 50 round trips per command")
with serial.Serial(PORT, 115200, timeout=0.2) as ser:
    time.sleep(0.3); ser.reset_input_buffer()
    for name, pkt in (("AA 0A 00 00", IDENT), ("BB 13 Check", CHECK)):
        f, l, ok = [], [], 0
        for _ in range(50):
            rx, tf, tl = txrx(ser, pkt)
            if len(rx) == 60: ok += 1; f.append(tf); l.append(tl)
            time.sleep(0.03)
        R.setdefault("latency", {})[name] = {"replies": ok, "of": 50,
                                             "first_byte": stats(f), "last_byte": stats(l)}
        print(f"   {name:14s} {ok}/50 ok  first byte {stats(f)['median_ms']:.2f} ms median"
              f"  complete {stats(l)['median_ms']:.2f} ms median (max {stats(l)['max_ms']:.2f})")

# --------------------------------------------------- 2 post-open settle delay
print("\n2. is a settle delay after opening the port needed? (10 reps each)")
R["settle_delay"] = {}
for delay in (0.0, 0.005, 0.025, 0.050, 0.100, 0.300):
    ok = 0; firsts = []
    for _ in range(10):
        with serial.Serial(PORT, 115200, timeout=0.2) as ser:
            if delay: time.sleep(delay)
            rx, tf, tl = txrx(ser, IDENT, timeout=1.5)
            if len(rx) == 60 and rx[59] == sum(rx[:59]) % 256: ok += 1; firsts.append(tf)
        time.sleep(0.05)
    R["settle_delay"][f"{int(delay*1000)}ms"] = {"ok": ok, "of": 10, "first_byte": stats(firsts)}
    print(f"   settle {int(delay*1000):3d} ms -> {ok}/10 valid replies"
          f"{'' if not firsts else f'  (first byte median {stats(firsts)[chr(39)+chr(39)] if False else stats(firsts)['median_ms']:.2f} ms)'}")

# ------------------------------------------------- 3 inter-command delay
print("\n3. is an inter-command delay needed? (30 commands each)")
R["inter_command_delay"] = {}
with serial.Serial(PORT, 115200, timeout=0.2) as ser:
    time.sleep(0.3); ser.reset_input_buffer()
    for gap in (0.0, 0.001, 0.005, 0.020):
        ok = 0
        for _ in range(30):
            rx, _, _ = txrx(ser, IDENT)
            if len(rx) == 60 and rx[59] == sum(rx[:59]) % 256: ok += 1
            if gap: time.sleep(gap)
        R["inter_command_delay"][f"{gap*1000:.0f}ms"] = {"ok": ok, "of": 30}
        print(f"   gap {gap*1000:5.0f} ms -> {ok}/30 valid replies")

# ------------------------------------------------------------ 4 port reopen
print("\n4. port close/reopen, 20 cycles")
ok = 0; errs = []
for i in range(20):
    try:
        with serial.Serial(PORT, 115200, timeout=0.2) as ser:
            time.sleep(0.02)
            rx, _, _ = txrx(ser, IDENT, timeout=1.5)
            if len(rx) == 60: ok += 1
    except Exception as e:
        errs.append(f"cycle {i}: {e!r}")
R["port_reopen"] = {"ok": ok, "of": 20, "errors": errs}
print(f"   {ok}/20 cycles answered; open errors: {len(errs)}")

# ----------------------------------------------------------- 6 line coding
print("\n6. LINE CODING falsifier -- does framing reach a UART?")
R["line_coding"] = {}
ref = None
for label, kw in (("8N1 (reference)", dict(bytesize=8, parity="N", stopbits=1)),
                  ("7E1", dict(bytesize=7, parity="E", stopbits=1)),
                  ("8N2", dict(bytesize=8, parity="N", stopbits=2)),
                  ("7N1", dict(bytesize=7, parity="N", stopbits=1)),
                  ("8O1", dict(bytesize=8, parity="O", stopbits=1)),
                  ("300 baud 8N1", dict(bytesize=8, parity="N", stopbits=1, _baud=300)),
                  ("1000000 baud 8N1", dict(bytesize=8, parity="N", stopbits=1, _baud=1000000))):
    baud = kw.pop("_baud", 115200)
    try:
        with serial.Serial(PORT, baud, timeout=0.2, **kw) as ser:
            time.sleep(0.3); ser.reset_input_buffer()
            rx, tf, tl = txrx(ser, IDENT, timeout=2.0)
    except Exception as e:
        R["line_coding"][label] = {"error": repr(e)}; print(f"   {label:18s} ERROR {e!r}"); continue
    if ref is None: ref = rx
    R["line_coding"][label] = {"baud": baud, "rx_len": len(rx), "rx": rx.hex(),
                               "identical_to_8N1": rx == ref,
                               "last_byte_ms": None if tl is None else round(tl*1000, 3)}
    print(f"   {label:18s} {len(rx):3d} B  identical_to_8N1={rx == ref}"
          f"  complete={tl*1000:.2f} ms")
    time.sleep(0.1)

# ------------------------------------------------------------ 7 pipelining
print("\n7. pipelining -- two requests written back to back, then read")
with serial.Serial(PORT, 115200, timeout=0.2) as ser:
    time.sleep(0.3); ser.reset_input_buffer()
    t0 = time.perf_counter()
    ser.write(build(0xAA, 0x0A, 0, 0) + build(0xAA, 0x0A, 2, 0)); ser.flush()
    buf = bytearray(); dl = t0 + 2.0
    while len(buf) < 120 and time.perf_counter() < dl:
        n = ser.in_waiting
        if n: buf += ser.read(n)
        else: time.sleep(0.001)
    R["pipelining"] = {"bytes_back": len(buf), "rx": bytes(buf).hex(),
                       "elapsed_ms": round((time.perf_counter()-t0)*1000, 2)}
    print(f"   sent 120 B of requests -> got {len(buf)} B back in "
          f"{R['pipelining']['elapsed_ms']:.1f} ms")
    if len(buf) >= 120:
        print(f"   frame2 subcmd byte = 0x{buf[62]:02X} (expect 0x02 if both were answered)")

# ---------------------------------------------------------- 5 long idle
print(f"\n5. unsolicited traffic over a {IDLE_S:.0f} s idle window (also brackets BB 13)")
with serial.Serial(PORT, 115200, timeout=0.5) as ser:
    time.sleep(0.3); ser.reset_input_buffer()
    before, _, _ = txrx(ser, CHECK)
    ser.reset_input_buffer()
    t0 = time.perf_counter(); unsolicited = bytearray(); marks = []
    while time.perf_counter() - t0 < IDLE_S:
        n = ser.in_waiting
        if n:
            unsolicited += ser.read(n); marks.append(round(time.perf_counter()-t0, 3))
        else: time.sleep(0.05)
    after, _, _ = txrx(ser, CHECK)
R["idle"] = {"window_s": IDLE_S, "unsolicited_bytes": len(unsolicited),
             "unsolicited": bytes(unsolicited).hex(), "arrival_times_s": marks,
             "bb13_before": before.hex(), "bb13_after": after.hex(),
             "bb13_changed": before != after,
             "bb13_before_5_10": before[5:11].hex() if len(before) == 60 else None,
             "bb13_after_5_10": after[5:11].hex() if len(after) == 60 else None}
print(f"   unsolicited bytes in {IDLE_S:.0f} s: {len(unsolicited)}")
print(f"   BB 13 device field before: {R['idle']['bb13_before_5_10']}")
print(f"   BB 13 device field after : {R['idle']['bb13_after_5_10']}  changed={before != after}")

p = OUT / "EXP-USB-005-timing.json"
p.write_text(json.dumps(log, indent=2))
print("\nwrote", p)
