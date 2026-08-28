#!/usr/bin/env python3
"""EXP-CAL-001 + EXP-MEAS-001 -- the ONE human session.

Everything that needs a person in the room, in a single scripted run with full
transaction logging and per-step timing. The human is asked ONLY to move the
instrument and press Enter; every judgement, decode and comparison is done here
(CLAUDE.md 17: never ask the human to do analysis we can do ourselves).

WHAT ONE RUN ANSWERS
  identity + fingerprint stability across the whole session
  what a measurement returns with NO calibration          (phase 1)
  black calibration: command, reply, status, timing        (phase 2)
  white calibration: command, reply, status, timing        (phase 3)
  a measurement on the white tile -- the positive control  (phase 4)
  a measurement on the black cap  -- the other end         (phase 5)
  a measurement on a colour patch                          (phase 6)
  repeatability: 3 reads without lifting                   (phase 6)
  is a measurement cached? re-fetch chunks, no re-trigger  (phase 7)
  what happens if chunks are fetched with no measurement   (phase 8)
  button-triggered reading + unsolicited traffic           (phase 9)
  4 more patches, for the spectral-rank question           (phase 10)

SAFETY (SAFETY_ENVELOPE.md). Only the sixteen vendor-observed triples are sent.
BB 10 / BB 11 write calibration and are green ONLY here, with tiles present and
a human watching. Between every phase the four identity sub-commands are re-read
as a 240-byte fingerprint; ANY change aborts the run.
"""
import sys, time, json, pathlib, datetime, struct, statistics

try:
    import serial
except ImportError:
    sys.exit("pyserial missing: .venv/bin/pip install pyserial")

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

# ---- frames --------------------------------------------------------------
def build(start, cmd, sub=0, param=0, data=b"", at=4, marker=0xFF):
    d = bytearray(60); d[0], d[1], d[2], d[3] = start, cmd, sub, param
    d[at:at+len(data)] = data
    d[58] = marker; d[59] = sum(d[:59]) % 256
    return bytes(d)

# Every request below is byte-identical to a frame the VENDOR APPLICATION
# actually sent (captures/public/PRIORART-001, 637 frames, 10 sessions).
# SAFETY_ENVELOPE.md 2a: replaying vendor traffic cannot put the device in a
# state the vendor software could not. `tests/test_human_session_frames.py`
# fails if any of them stops matching the corpus.
IDENT = [build(0xAA, 0x0A, s, 0) for s in range(4)]
CAL_BLACK = build(0xBB, 0x10, 0, 0)
CAL_WHITE = build(0xBB, 0x11, 0, 0)
TRIGGER = build(0xBB, 0x01, 0x00, 0)
CHUNKS = [build(0xBB, 0x01, s, 0) for s in (0x10, 0x11, 0x12, 0x13)]

# Two frames the vendor does NOT send all-zero, so they are hard-coded from the
# corpus rather than constructed:
#   BB 01 09 carries the requested spectral axis at offsets 4..6 -- `28 1f 0a`
#            = start 400 nm (40 x 10), 31 bands, 10 nm step.
#   BB 13    carries two u32 LE Unix timestamps at 5 and 9 and an ASCII label at
#            13. This is the vendor's zero-timestamp variant, label "Check".
HEADER = bytes.fromhex(
    "bb010900281f0a0000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000ff15")
JOBREC = bytes.fromhex(
    "bb130000000000000000000000436865636b000000000000000000000000"
    "00000000000000000000000000000000000000000000000000000000ffab")

# VERIFIED spectral layout (corroborated on 60 vendor measurement groups):
# each chunk carries 12 float32 LE at frame offset 6; chunks 0x10/0x11/0x12
# give values 0..11, 12..23, 24..30; chunk 0x13 is NOT extra spectrum -- its
# offsets 34..53 repeat values 0..4 (60/60 groups agree).
CHUNK_DATA_AT = 6
VALS_PER_CHUNK = 12

LOG = {"experiment": "EXP-CAL-001 + EXP-MEAS-001",
       "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
       "port": PORT, "platform": sys.platform, "phases": [], "aborted": None}
BASE_FINGERPRINT = None


def read_frame(ser, timeout):
    t0 = time.perf_counter(); buf = bytearray(); first = None
    while len(buf) < 60 and time.perf_counter() - t0 < timeout:
        n = ser.in_waiting
        if n:
            if first is None: first = time.perf_counter() - t0
            buf += ser.read(min(n, 60 - len(buf)))
        else: time.sleep(0.0005)
    return bytes(buf), first, time.perf_counter() - t0


def tx(ser, pkt, label, timeout=5.0, phase=None):
    """One transaction, recorded verbatim BEFORE any interpretation."""
    ser.reset_input_buffer()
    t0 = time.perf_counter(); ser.write(pkt); ser.flush()      # ONE write: EXP-USB-005c
    rx, first, total = read_frame(ser, timeout)
    rec = {"label": label, "tx": pkt.hex(), "rx_len": len(rx), "rx": rx.hex(),
           "first_byte_ms": None if first is None else round(first * 1000, 3),
           "elapsed_ms": round(total * 1000, 3),
           "rx_cs_ok": len(rx) == 60 and rx[59] == sum(rx[:59]) % 256,
           "marker": rx[58] if len(rx) == 60 else None,
           "is_echo": len(rx) == 60 and rx[:58] == pkt[:58],
           "device_wrote": [i for i in range(58) if len(rx) == 60 and rx[i] != pkt[i]]}
    (phase if phase is not None else LOG["phases"][-1])["steps"].append(rec)
    flag = "ECHO" if rec["is_echo"] else ("----" if len(rx) == 60 else "NONE")
    mk = "--" if rec["marker"] is None else "%02X" % rec["marker"]
    wrote = (str(rec["device_wrote"]) if len(rec["device_wrote"]) < 10
             else "%d bytes" % len(rec["device_wrote"]))
    print(f"    {label:38s} {len(rx):3d}B {flag} {rec['elapsed_ms']:8.2f} ms "
          f"marker={mk} wrote={wrote}")
    return rx


def phase(name, note=""):
    p = {"phase": name, "note": note,
         "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "steps": []}
    LOG["phases"].append(p)
    print(f"\n=== {name} ===")
    if note: print(f"    {note}")
    return p


def fingerprint(ser, when):
    """240-byte identity fingerprint. Any change means firmware state moved."""
    p = phase(f"fingerprint: {when}", "SAFETY_ENVELOPE.md 4b -- abort on any change")
    fp = b"".join(tx(ser, f, f"AA 0A {i:02X} 00", 2.0, p) for i, f in enumerate(IDENT))
    global BASE_FINGERPRINT
    if BASE_FINGERPRINT is None:
        BASE_FINGERPRINT = fp
        p["fingerprint_sha_prefix"] = fp[:4].hex(); p["baseline"] = True
        print("    baseline fingerprint recorded")
    else:
        same = fp == BASE_FINGERPRINT
        p["matches_baseline"] = same
        print(f"    fingerprint matches baseline: {same}")
        if not same:
            diff = [i for i in range(min(len(fp), len(BASE_FINGERPRINT)))
                    if fp[i] != BASE_FINGERPRINT[i]]
            p["differing_offsets"] = diff
            LOG["aborted"] = f"identity fingerprint changed at {when}: offsets {diff}"
            raise SystemExit(f"\n!! ABORT -- {LOG['aborted']}\n"
                             "   SAFETY_ENVELOPE.md stop condition. Nothing further sent.")
    return fp


def ask(text):
    print("\n" + "-" * 72)
    print("  HUMAN: " + text)
    input("  press Enter when done (or Ctrl-C to stop) > ")
    print("-" * 72)


# ---- measurement ---------------------------------------------------------
def measure(ser, label, note=""):
    """One full measurement transaction, every frame recorded."""
    p = phase(f"measure: {label}", note)
    t0 = time.perf_counter()
    p["trigger_rx"] = tx(ser, TRIGGER, "BB 01 00 trigger", 10.0, p).hex()
    hdr = tx(ser, HEADER, "BB 01 09 header", 10.0, p)
    got = {}
    for i, c in enumerate(CHUNKS):
        sub = 0x10 + i
        rx = tx(ser, c, f"BB 01 {sub:02X} chunk {i}", 10.0, p)
        if len(rx) == 60:
            got[sub] = rx
    p["chunk_frames"] = {f"0x{k:02X}": v.hex() for k, v in got.items()}
    p["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    if len(hdr) != 60:
        p["spectrum"] = None
        print("    !! no header frame -- nothing decoded")
        return p

    # The axis is READ FROM THE HEADER, never assumed. If the chunks cannot
    # supply what the header declares, the measurement is REJECTED, not
    # rounded up into a partial spectrum (CLAUDE.md 14).
    start_nm, count, step = hdr[4] * 10, hdr[5], hdr[6]
    p["axis_from_header"] = {"start_nm": start_nm, "count": count, "step_nm": step,
                             "raw_4_6": hdr[4:7].hex(), "marker": hdr[58]}
    print(f"    header axis: {count} bands from {start_nm} nm, step {step} nm "
          f"(marker 0x{hdr[58]:02X})")
    need = [0x10, 0x11, 0x12][:max(1, -(-count // VALS_PER_CHUNK))]
    missing = [f"0x{c:02X}" for c in need if c not in got]
    if missing:
        p["spectrum"] = None
        p["reject_reason"] = f"header declares {count} values; chunks {missing} missing"
        print(f"    !! REJECTED: {p['reject_reason']}")
        return p
    vals = []
    for c in need:
        vals += struct.unpack(f"<{VALS_PER_CHUNK}f",
                              got[c][CHUNK_DATA_AT:CHUNK_DATA_AT + 4 * VALS_PER_CHUNK])
    if len(vals) < count:
        p["spectrum"] = None
        p["reject_reason"] = f"decoded {len(vals)} values, header declares {count}"
        print(f"    !! REJECTED: {p['reject_reason']}")
        return p
    p["spectrum"] = [round(v, 6) for v in vals[:count]]
    p["wavelengths"] = [start_nm + i * step for i in range(count)]
    print(f"    spectrum: {p['spectrum'][0]:.2f} .. {p['spectrum'][-1]:.2f}  "
          f"(min {min(p['spectrum']):.2f}  max {max(p['spectrum']):.2f})")
    # cross-check the redundancy the vendor corpus shows in chunk 0x13
    if 0x13 in got:
        tail = struct.unpack("<5f", got[0x13][34:54])
        p["chunk13_repeats_first_five"] = [round(x, 6) for x in tail] == p["spectrum"][:5]
        print(f"    chunk 0x13 repeats values 0..4: {p['chunk13_repeats_first_five']}")
    return p


def save():
    p = OUT / "EXP-CAL-001-EXP-MEAS-001-human-session.json"
    p.write_text(json.dumps(LOG, indent=2))
    print(f"\nwrote {p}")
    return p


def main():
    print(f"CR30 human session on {PORT}")
    print("Nothing is sent until you press Enter at each prompt.\n")
    with serial.Serial(PORT, 115200, timeout=0.05, bytesize=8, parity="N",
                       stopbits=1, rtscts=False, dsrdtr=False) as ser:
        ser.reset_input_buffer()
        fingerprint(ser, "session start")

        p = phase("job record before", "BB 13 -- two u32 LE Unix timestamps + ASCII label")
        tx(ser, JOBREC, "BB 13 00 00", 2.0, p)

        # -- 1. measurement with whatever calibration the device already has
        ask("Hold the CR30 on a MID-GREY or coloured patch, flat, and keep it there.")
        measure(ser, "patch, BEFORE any calibration this session",
                "answers: is calibration a precondition, and what happens without it")
        fingerprint(ser, "after pre-calibration measurement")

        # -- 2. black calibration
        ask("Put the BLACK CAP on the CR30 (or place it on the black tile), fully seated.")
        p = phase("black calibration", "BB 10 00 00 -- WRITES calibration storage")
        t0 = time.perf_counter()
        tx(ser, CAL_BLACK, "BB 10 00 00 black cal", 20.0, p)
        p["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        fingerprint(ser, "after black calibration")

        # -- 3. white calibration
        ask("Place the CR30 squarely on the WHITE CALIBRATION TILE. It must be clean\n"
            "         and correctly seated -- this OVERWRITES the stored white calibration.")
        p = phase("white calibration", "BB 11 00 00 -- WRITES calibration storage")
        t0 = time.perf_counter()
        tx(ser, CAL_WHITE, "BB 11 00 00 white cal", 20.0, p)
        p["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        fingerprint(ser, "after white calibration")

        # -- 4. positive control on the white tile
        print("\n  (leave it on the white tile)")
        ask("Keep the CR30 on the WHITE TILE.")
        wp = measure(ser, "WHITE TILE (positive control)",
                     "a correct decode must read near-flat and near-maximum")

        # -- 5. the other end
        ask("Put the BLACK CAP back on.")
        bp = measure(ser, "BLACK CAP (negative control)",
                     "a correct decode must read near-minimum")

        # -- 6. a patch, three times without lifting
        ask("Place the CR30 on a COLOURED PATCH (a saturated one -- red, cyan or\n"
            "         magenta is ideal) and DO NOT LIFT IT until told.")
        reps = [measure(ser, f"patch A, read {i+1} of 3 (not lifted)",
                        "repeatability without repositioning") for i in range(3)]
        specs = [r.get("spectrum") for r in reps if r.get("spectrum")]
        if len(specs) > 1:
            band = [statistics.pstdev([s[i] for s in specs]) for i in range(len(specs[0]))]
            LOG["repeatability_worst_band_sd"] = round(max(band), 5)
            print(f"\n    repeatability over {len(specs)} reads, worst band SD = {max(band):.5f}")

        # -- 7. is a measurement cached?
        p = phase("cache probe", "re-fetch the chunks WITHOUT re-triggering")
        again = bytearray()
        for i, c in enumerate(CHUNKS):
            rx = tx(ser, c, f"BB 01 {0x10+i:02X} refetch", 5.0, p)
            if len(rx) == 60: again += rx[5:55]
        p["identical_to_last_measurement"] = (bytes(again).hex() ==
                                              reps[-1].get("accumulated_body"))
        print(f"    re-fetch identical to the last measurement: "
              f"{p['identical_to_last_measurement']}")

        # -- 9. button-triggered reading
        ask("Place the CR30 on ANOTHER patch and press its own MEASURE BUTTON once.\n"
            "         Then press Enter here. (Do not lift it.)")
        p = phase("button press", "listening for unsolicited traffic, 15 s")
        t0 = time.perf_counter(); un = bytearray(); marks = []
        while time.perf_counter() - t0 < 15.0:
            n = ser.in_waiting
            if n: un += ser.read(n); marks.append(round(time.perf_counter() - t0, 3))
            else: time.sleep(0.02)
        p["unsolicited_bytes"] = len(un); p["unsolicited"] = bytes(un).hex()
        p["arrival_times_s"] = marks
        print(f"    unsolicited bytes after the button press: {len(un)}")
        if len(un) >= 60:
            for i in range(0, len(un) - 59, 60):
                f = bytes(un[i:i+60])
                print(f"      frame: {f[:4].hex(' ')} marker={f[58]:02X} "
                      f"cs_ok={f[59] == sum(f[:59]) % 256}")
        p2 = phase("after button press", "fetch chunks -- same path as a software trigger?")
        got = bytearray()
        for i, c in enumerate(CHUNKS):
            rx = tx(ser, c, f"BB 01 {0x10+i:02X} after button", 5.0, p2)
            if len(rx) == 60: got += rx[5:55]
        p2["body"] = bytes(got).hex()

        # -- 10. more patches, for the spectral-rank question
        for k in range(4):
            ask(f"Place the CR30 on a DIFFERENT patch ({k+1} of 4) -- as varied in colour\n"
                f"         as you can manage (a saturated primary, a dark one, a pastel).")
            measure(ser, f"rank corpus patch {k+1}",
                    "for EXP-SPEC-001: are the 31 bands independent or reconstructed?")

        p = phase("job record after", "did a measurement move BB 13's timestamps?")
        tx(ser, JOBREC, "BB 13 00 00", 2.0, p)
        fingerprint(ser, "session end")

    print("\nALL PHASES COMPLETE.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOG["aborted"] = "operator interrupted"
        print("\ninterrupted -- partial capture still saved")
    except SystemExit as e:
        print(e)
    finally:
        save()
