#!/usr/bin/env python3
"""EXP-MEAS-003 -- is a HOST-TRIGGERED measurement gated by the magnet?

WHY THIS EXISTS. EXP-MEAS-002 could not answer it. There, a gated button press
preceded the host trigger, so the chunk buffer already held the canned tile
value before we asked for one -- and measurements are cached (EXP-MEAS-001).
The identical result was therefore ambiguous.

THE FIX. Make sure the buffer holds a DISTINCTIVE PATCH at the moment the
magnet is engaged, with NO button press in between. Then the three hypotheses
give three different answers:

  host trigger returns the canned tile value   -> the USB path IS gated
  host trigger returns the previous patch      -> the trigger is IGNORED (cache)
  host trigger returns a real white-tile read  -> USB BYPASSES the gate
  (distinguishable from the canned value, which is a stored constant)

Only the trigger and the four chunk fetches are sent. BB 10 / BB 11 are never
sent. The patch is re-measured at the end as an integrity check.
"""
import sys, json, pathlib, datetime, statistics, struct, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "src"))
import run_human_session as hs
from cr30.colour import spectrum_to_lab, D65, validate_illuminants

CANNED_LAB = (91.661, -0.760, 1.305)     # measured in EXP-MEAS-002


def de(a, b): return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def lab(spec): return spectrum_to_lab(spec, D65) if spec else None


def show(tag, spec):
    if not spec:
        print(f"    {tag}: NO SPECTRUM"); return None
    L = lab(spec)
    print(f"    {tag:26s} mean {statistics.fmean(spec):6.2f}%  "
          f"L*{L[0]:6.2f} a*{L[1]:+6.2f} b*{L[2]:+6.2f}")
    return {"lab_d65": [round(v, 3) for v in L],
            "mean": round(statistics.fmean(spec), 4), "spectrum": spec}


def fetch(ser, note, tag):
    p = hs.phase(tag, note)
    vals = []
    for i, c in enumerate(hs.CHUNKS):
        rx = hs.tx(ser, c, f"BB 01 {0x10+i:02X}", 5.0, p)
        if len(rx) == 60 and rx[2] in (0x10, 0x11, 0x12):
            vals += list(struct.unpack("<12f", rx[6:54]))
    p["spectrum"] = [round(x, 6) for x in vals[:31]]
    return p["spectrum"]


def listen(ser, seconds, p):
    t0 = time.perf_counter(); buf = bytearray()
    while time.perf_counter() - t0 < seconds:
        n = ser.in_waiting
        if n: buf += ser.read(n)
        else: time.sleep(0.02)
    p["unsolicited_bytes"] = len(buf); p["unsolicited"] = bytes(buf).hex()
    if len(buf) >= 60:
        p["header_offset24"] = buf[24]
        print(f"    unsolicited {len(buf)}B, header offset24 = 0x{buf[24]:02X}")
    else:
        print(f"    unsolicited {len(buf)}B")
    return bytes(buf)


def main():
    if not all(x["ok"] for x in validate_illuminants().values()):
        sys.exit("illuminant self-check FAILED -- refusing to report Lab")
    hs.LOG.clear()
    hs.LOG.update({"experiment": "EXP-MEAS-003",
                   "question": "is a HOST-TRIGGERED measurement gated by the magnet?",
                   "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "port": hs.PORT, "canned_lab_from_exp002": CANNED_LAB,
                   "phases": [], "aborted": None})
    out = {}
    print(f"\nEXP-MEAS-003 on {hs.PORT}")
    print("Trigger + chunk fetch only. No calibration command is ever sent.\n")

    import serial
    with serial.Serial(hs.PORT, 115200, timeout=0.05, bytesize=8, parity="N",
                       stopbits=1, rtscts=False, dsrdtr=False) as ser:
        ser.reset_input_buffer()
        hs.fingerprint(ser, "session start")

        # 1. load the buffer with something UNMISTAKABLE
        hs.ask("Cap OFF. Place the CR30 on the MOST SATURATED patch you have\n"
               "         (deep red, deep blue, deep cyan). Keep it there.")
        patch = hs.measure(ser, "distinctive patch, cap OFF",
                           "loads the buffer with something unlike the tile value")
        out["patch"] = show("patch (buffer now)", patch.get("spectrum"))
        if out["patch"] and de(out["patch"]["lab_d65"], CANNED_LAB) < 20:
            print("    !! that patch is too close to the tile value to be a good"
                  " discriminator -- a more saturated one would be better")

        # 2. engage the magnet WITHOUT pressing the device button
        print("\n" + "=" * 72)
        print("  CRITICAL: do NOT press the device's button in this step.")
        print("  Pressing it would overwrite the buffer and recreate the exact")
        print("  confound that made EXP-MEAS-002 inconclusive.")
        print("=" * 72)
        hs.ask("Attach the CAP / magnet in the position that triggers the effect.\n"
               "         Do NOT press the device button. Just seat it and press Enter here.")
        p = hs.phase("magnet engaged, passive", "listening 3 s; nothing sent")
        listen(ser, 3.0, p)

        # 3. THE QUESTION
        tr = hs.measure(ser, "HOST-TRIGGERED with magnet engaged",
                        "the question EXP-MEAS-002 could not answer")
        out["host_triggered"] = show("host-triggered", tr.get("spectrum"))
        hdr = tr.get("trigger_rx")
        if hdr:
            p_off24 = bytes.fromhex(hdr)[24]
            out["trigger_header_offset24"] = p_off24
            print(f"    trigger header offset24 = 0x{p_off24:02X}")

        # 4. confirm the gate really was engaged, AFTER the question was asked
        hs.ask("NOW press the device's own BUTTON once, without moving anything.")
        p = hs.phase("gate confirmation button press", "listening 8 s")
        listen(ser, 8.0, p)
        gated = fetch(ser, "what the gated button produced",
                      "gated button measurement")
        out["gated_button"] = show("gated button", gated)
        ans = input("\n  Did the display show the WHITE-TILE value "
                    "(about L* 91.6)? [y/n] > ").strip().lower()
        out["operator_confirms_gate_was_engaged"] = ans.startswith("y")

        # 5. integrity
        hs.ask("Cap OFF. Put the CR30 back on the SAME saturated patch.")
        after = hs.measure(ser, "distinctive patch again, cap OFF", "integrity check")
        out["patch_after"] = show("patch after", after.get("spectrum"))
        hs.fingerprint(ser, "session end")

    # ---- verdict ---------------------------------------------------------
    hs.LOG["analysis"] = out
    print("\n" + "=" * 72)
    ht = out.get("host_triggered")
    if not ht or not out.get("operator_confirms_gate_was_engaged"):
        verdict = ("INCONCLUSIVE -- the gate was not confirmed engaged, so a "
                   "normal-looking measurement proves nothing.")
    else:
        d_canned = de(ht["lab_d65"], CANNED_LAB)
        d_patch = de(ht["lab_d65"], out["patch"]["lab_d65"]) if out.get("patch") else 999
        print(f"  host-triggered vs canned tile value : dE {d_canned:7.3f}")
        print(f"  host-triggered vs the patch         : dE {d_patch:7.3f}")
        if d_canned < 1.0:
            verdict = ("THE USB PATH IS GATED -- a host-triggered measurement "
                       "returns the canned tile value. A live backend MUST "
                       "detect this.")
        elif d_patch < 2.0:
            verdict = ("THE TRIGGER IS IGNORED while the magnet is engaged -- we "
                       "re-read the cached patch. Symptom for a backend: "
                       "consecutive identical readings.")
        else:
            verdict = ("USB BYPASSES THE GATE -- the host trigger produced a "
                       "genuine reading unlike both references. The magnet "
                       "affects only the device's own UI.")
        hs.LOG["delta_e_vs_canned"] = round(d_canned, 3)
        hs.LOG["delta_e_vs_patch"] = round(d_patch, 3)
    hs.LOG["verdict"] = verdict
    print("\n  VERDICT: " + verdict)
    print("=" * 72)

    q = ROOT / "captures" / "raw" / "EXP-MEAS-003-magnet-trigger.json"
    q.write_text(json.dumps(hs.LOG, indent=2))
    print(f"\nwrote {q}\nDONE -- just say it finished; I read the numbers from the file.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted")
