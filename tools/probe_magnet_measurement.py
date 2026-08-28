#!/usr/bin/env python3
"""EXP-MEAS-002 -- does the magnet gate the USB measurement path too?

QUESTION. With a magnet attached the device's own display stops responding to
what is under the aperture: the operator turned the cap upside down, presenting
GREEN instead of the white tile, and the displayed Lab did not move
(L*=91.64 a*=-0.78 b*=+1.36 both times). That rules out a measurement.

What is NOT known is whether the USB path is gated the same way. It matters:
if it is, a ChromIQ user who leaves the cap on gets silent, plausible, WRONG
data, and the backend has to detect it.

SAFETY. Only BB 01 (trigger) and BB 01 10..13 (chunk fetch) are sent -- both
green, both sent constantly by the vendor application. BB 10 and BB 11, the
calibration writes, are NEVER sent. The same patch is measured before and after
the capped phase and the two are compared, so if anything DID move the stored
calibration, this run reports it rather than hiding it.
"""
import sys, json, pathlib, datetime, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import run_human_session as hs          # reuse the audited helpers
from cr30.colour import spectrum_to_lab, D65, D50, validate_illuminants

SCREEN_LAB = (91.64, -0.78, 1.36)       # what the device shows with a magnet on


def de76(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def report(label, spec):
    if not spec:
        print(f"    {label}: NO SPECTRUM"); return None
    l65 = spectrum_to_lab(spec, D65)
    l50 = spectrum_to_lab(spec, D50)
    print(f"    {label}: mean {statistics.fmean(spec):6.2f}%   "
          f"D65 L*{l65[0]:6.2f} a*{l65[1]:+6.2f} b*{l65[2]:+6.2f}   "
          f"D50 L*{l50[0]:6.2f} a*{l50[1]:+6.2f} b*{l50[2]:+6.2f}")
    return {"lab_d65": [round(v, 3) for v in l65],
            "lab_d50": [round(v, 3) for v in l50],
            "mean_reflectance": round(statistics.fmean(spec), 4)}


def main():
    v = validate_illuminants()
    if not all(x["ok"] for x in v.values()):
        sys.exit(f"illuminant self-check FAILED: {v} -- refusing to report Lab")
    checks = "  ".join(f"{k} err {x['max_error']}" for k, x in v.items())
    print(f"colour self-check OK   {checks}")

    hs.LOG.clear()
    hs.LOG.update({"experiment": "EXP-MEAS-002",
                   "question": "is the USB measurement path gated by the magnet?",
                   "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "port": hs.PORT, "device_screen_lab_with_magnet": SCREEN_LAB,
                   "phases": [], "aborted": None})
    out = {}

    print(f"\nEXP-MEAS-002 on {hs.PORT}")
    print("Only trigger + chunk fetch are sent. NO calibration command. "
          "Your stored calibration is not written to.\n")

    import serial
    with serial.Serial(hs.PORT, 115200, timeout=0.05, bytesize=8, parity="N",
                       stopbits=1, rtscts=False, dsrdtr=False) as ser:
        ser.reset_input_buffer()
        hs.fingerprint(ser, "session start")

        # --- 1. reference reading, cap OFF
        hs.ask("Cap OFF. Place the CR30 on a patch you can return to EXACTLY --\n"
               "         a big flat one. Mark it if you need to. Do not lift it yet.")
        r1 = hs.measure(ser, "reference patch, cap OFF (before)",
                        "baseline for the calibration-integrity check")
        out["before"] = report("before ", r1.get("spectrum"))

        # --- 2. cap ON, READ-ONLY: what is already in the buffer?
        hs.ask("Attach the MAGNETIC CAP, correct way round (white tile inward).\n"
               "         Press NO button on the device.")
        p = hs.phase("capped: read-only chunk fetch",
                     "NO trigger sent -- what does the buffer already hold?")
        vals = []
        for i, c in enumerate(hs.CHUNKS):
            rx = hs.tx(ser, c, f"BB 01 {0x10+i:02X} refetch (no trigger)", 5.0, p)
            if len(rx) == 60 and rx[2] in (0x10, 0x11, 0x12):
                import struct
                vals += list(struct.unpack("<12f", rx[6:54]))
        p["spectrum"] = [round(x, 6) for x in vals[:31]]
        out["capped_no_trigger"] = report("capped, no trigger", p["spectrum"])

        # --- 3. cap ON, TRIGGERED: the actual question
        p2 = hs.phase("capped: TRIGGERED measurement",
                      "the question -- is the USB path gated like the display?")
        cap = hs.measure(ser, "CAPPED, host-triggered", "cap on, white tile inward")
        out["capped_triggered"] = report("capped, triggered", cap.get("spectrum"))
        hs.fingerprint(ser, "after capped measurement")

        # --- 4. same patch again, cap OFF -- integrity check
        hs.ask("Take the CAP OFF. Put the CR30 back on THE SAME patch as step 1,\n"
               "         as precisely as you can.")
        r2 = hs.measure(ser, "reference patch, cap OFF (after)",
                        "did anything move the stored calibration?")
        out["after"] = report("after  ", r2.get("spectrum"))

        if r1.get("spectrum") and r2.get("spectrum"):
            d = de76(spectrum_to_lab(r1["spectrum"], D65),
                     spectrum_to_lab(r2["spectrum"], D65))
            out["delta_e76_before_vs_after"] = round(d, 3)
            print(f"\n    CALIBRATION INTEGRITY: dE76 before vs after = {d:.3f}")
            print("      (repositioning alone gives a small non-zero value;")
            print("       a large one would mean calibration moved)")

        # --- 5. does the capped reading match what the SCREEN shows?
        cs = cap.get("spectrum")
        if cs:
            for nm, il in (("D65", D65), ("D50", D50)):
                d = de76(spectrum_to_lab(cs, il), SCREEN_LAB)
                out[f"capped_vs_screen_de76_{nm}"] = round(d, 3)
                print(f"    capped reading vs the device's own display, {nm}: "
                      f"dE76 = {d:.3f}")
            print("      (a small value means USB returns the SAME canned value")
            print("       the screen shows -- i.e. the USB path IS gated)")

        hs.fingerprint(ser, "session end")

    hs.LOG["analysis"] = out
    p = ROOT / "captures" / "raw" / "EXP-MEAS-002-magnet-gating.json"
    p.write_text(json.dumps(hs.LOG, indent=2))
    print(f"\nwrote {p}\nDONE -- tell me the numbers above, or just say it finished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted")
