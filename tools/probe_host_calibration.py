#!/usr/bin/env python3
"""EXP-MEAS-004 -- can the HOST start a calibration, with no button press?

WHY. ChromIQ wants a "Calibrate" button that calibrates the instrument itself,
so the user only has to seat the cap. EXP-MEAS-003 showed a host trigger with a
magnet present caused a calibration write -- but that run also pressed the
device's button, so it could not say which one did it. Building the button on an
assumption risks reporting "calibrated" having calibrated nothing.

THE DISCRIMINATOR. Present the cap's GREEN face and send ONLY a host trigger,
never touching the instrument. Then measure paper:

  paper reads far above 100 %  -> the HOST TRIGGER calibrated (against green).
                                  Answer: YES, the button can work.
  paper reads normally         -> the trigger did NOT calibrate.
                                  Answer: NO, the user must press the button.

Deliberately mis-calibrating is safe here ONLY because the restore is verified:
seat the cap correctly, press the instrument's button. This script walks you
through that and confirms recovery before it exits.
"""
import sys, json, pathlib, datetime, time, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from cr30 import usb_measure
from cr30.transport import SerialTransport
from cr30.discovery import candidates
from cr30.measurement import Measurement, MeasurementError
from capture_io import save_capture

def read(t, label, enforce=False):
    m = usb_measure.read_stored(t)
    print(f"    {label:34s} mean {m.mean:7.3f} %R   peak {max(m.values):7.3f}")
    return m

def main():
    print(__doc__)
    found = candidates()
    if not found:
        sys.exit("No CH34x serial device. Plug the CR30 in by USB.")
    port = found[0].device
    log = {"experiment": "EXP-MEAS-004", "port": port,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "steps": []}
    t = SerialTransport(port); t.open()
    try:
        input("\n  1. Cap OFF. Put the CR30 on PLAIN WHITE PAPER. Enter > ")
        usb_measure.trigger(t); time.sleep(0.4)
        before = read(t, "paper BEFORE (baseline)")
        log["steps"].append({"step": "before", "values": before.values})

        print("\n  2. Put the cap on the WRONG WAY ROUND - GREEN face towards")
        print("     the instrument. Seat it so the magnet engages.")
        input("     Do NOT press the instrument's button. Enter > ")
        print("\n     sending a HOST TRIGGER only, no button press...")
        usb_measure.trigger(t); time.sleep(0.8)
        gated = read(t, "reading while capped (green)")
        log["steps"].append({"step": "host_trigger_capped", "values": gated.values})

        input("\n  3. Take the cap OFF. Put it back on the SAME PAPER. Enter > ")
        usb_measure.trigger(t); time.sleep(0.4)
        after = read(t, "paper AFTER the host trigger")
        log["steps"].append({"step": "after", "values": after.values})

        ratio = statistics.fmean(after.values) / statistics.fmean(before.values)
        log["ratio"] = round(ratio, 4)
        print(f"\n  paper moved by a factor of {ratio:.3f}")
        if max(after.values) > 110.0 or ratio > 1.25:
            v = ("YES -- the HOST TRIGGER performed the calibration. A "
                 "Calibrate button can work with no button press.")
        elif abs(ratio - 1.0) < 0.06:
            v = ("NO -- the host trigger did NOT calibrate. The user must press "
                 "the instrument's own button; a host-only Calibrate button "
                 "would report success having done nothing.")
        else:
            v = f"INCONCLUSIVE (ratio {ratio:.3f}). Tell me the numbers."
        log["verdict"] = v
        print("\n  VERDICT: " + v)

        if "YES" in v:
            print("\n  4. RESTORE: put the cap on the CORRECT way (white tile")
            print("     towards the instrument) and PRESS ITS BUTTON.")
            input("     Enter when done > ")
            input("     Cap off, back on the same paper. Enter > ")
            usb_measure.trigger(t); time.sleep(0.4)
            fixed = read(t, "paper AFTER restore")
            log["steps"].append({"step": "restored", "values": fixed.values})
            r2 = statistics.fmean(fixed.values) / statistics.fmean(before.values)
            log["restore_ratio"] = round(r2, 4)
            ok = abs(r2 - 1.0) < 0.06
            print(f"\n  restored to within {abs(r2-1)*100:.1f} % of baseline: "
                  f"{'YES' if ok else 'NO -- TELL ME, do not measure charts'}")
    finally:
        t.close()
    p = save_capture(ROOT, "EXP-MEAS-004-host-calibration", log)
    print(f"\n  wrote {p}")

if __name__ == "__main__":
    main()
