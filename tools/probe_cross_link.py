#!/usr/bin/env python3
"""EXP-021 -- does the instrument mirror activity across USB and Bluetooth?

The owner noticed the CR30 shows its "u" and "b" indicators at the same time, so
it holds a USB link and a Bluetooth link at once. That matters more than it
sounds: if what happens on one link is announced on the other, then a phone app
connected over Bluetooth could drop a reading into a ChromIQ measurement running
over the cable — or, far worse, rewrite a calibration reference mid-chart.

This LISTENS on the USB cable and says nothing. Not one byte is written. While
it listens, the operator drives the vendor app over Bluetooth. Anything that
appears on the cable came from the instrument unprompted.

## Why this is safe

It opens the instrument the way ChromIQ does — connect, then ask who you are —
and after that it only LISTENS. It never triggers a measurement, never
calibrates, and never changes a setting. Whatever the phone app does is the
phone app's doing.

The identify step is not optional and the first version of this probe learned
that the hard way: opening the serial port alone left the instrument silent even
when the operator pressed its own button. It does not speak to a host that has
not introduced itself, so a listener that skips the introduction is deaf and
would have reported "the links are independent" as a fact.

## What each outcome means

  Frames on USB while the phone acts   -> the links MIRROR. A second app can
      reach into a ChromIQ session, and ChromIQ's USB wait treats any
      unsolicited button header as the operator's press — so a phone-side
      trigger would land as a mis-attributed patch. Earns a warning in the app.
  Nothing on USB                       -> the links are independent. The hazard
      is theoretical and needs no words in the interface.

## The controls, and why there are two

  Phase 1 QUIET: nobody touches anything. Frames here mean the instrument
      chatters on its own, and nothing later could be attributed to the phone.
  Phase 3 POSITIVE: the operator presses the instrument's OWN button. That MUST
      appear on the cable — it is how ChromIQ reads a patch over USB. If it does
      not, the listener is deaf and the silence in phase 2 proves nothing.

## Doing double duty

Phase 2's phone steps are also exactly what a Bluetooth trace should capture:
both calibrations in the vendor's own framing (we hold those commands only in
their USB form, and Bluetooth frames are 10 bytes against 60), and the Average
setting, which is the only device option that could change what a reading
returns. Start the trace before running this and one session answers both.
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30.device import CR30                     # noqa: E402


def listen(ser, seconds, label):
    print(f"\n--- {label}  ({seconds} s)")
    got, t0 = [], time.monotonic()
    while time.monotonic() - t0 < seconds:
        n = ser.in_waiting
        if n:
            data = ser.read(n)
            got.append({"t": round(time.monotonic() - t0, 3),
                        "len": len(data), "hex": data[:60].hex()})
            print(f"      <- {len(data)} bytes at {got[-1]['t']:6.2f} s  "
                  f"{data[:12].hex(' ')}")
        else:
            time.sleep(0.02)
    print(f"      {len(got)} frame(s)")
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    a = ap.parse_args()

    print(__doc__)
    print("=" * 72)
    print("BEFORE YOU START")
    print("  1. Plug the CR30 in over USB.")
    print("  2. QUIT ChromIQ — an armed reader would eat the very frames we")
    print("     are trying to see.")
    print("  3. Have the cap to hand. It goes ON for one step and OFF again.")
    print("  4. OPTIONAL, and worth it: start your iOS Bluetooth trace now.")
    print("     The phone steps below are exactly the ones worth capturing —")
    print("     one session then answers two questions at once.")
    print()
    print("WHAT THIS SCRIPT DOES: it listens on the USB cable and writes")
    print("nothing. It cannot measure, calibrate or change a setting. Every")
    print("action is yours, on the phone or on the instrument itself.")
    input("\nPress Return when ready: ")

    print("\nOpening the instrument the way ChromIQ does …")
    dev = CR30.open_usb(a.port)
    ser = dev._t._ser
    print(f"Connected ({dev.model or 'CR30'}). Listening — writing nothing "
          f"from here on.")

    out = {"experiment": "EXP-021",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        out["quiet"] = listen(
            ser, 15, "PHASE 1 — CONTROL. Touch nothing at all.")

        # The phone steps are ordered so that ONE run serves both purposes:
        # the cable is listened to throughout (the cross-link question), and if
        # a Bluetooth trace is running these are exactly the exchanges worth
        # having — both calibrations in the vendor's own framing, and the one
        # device setting that could change a reading.
        print("\n--- PHASE 2 — now drive the PHONE APP over Bluetooth.")
        print("    Do these IN ORDER, letting each finish, and note roughly")
        print("    the clock time of each — that is how they are found in a")
        print("    trace afterwards.")
        print()
        print("      a) Connect the app to the instrument.")
        print("      b) Calibration -> WHITE: cap ON, white tile toward the")
        print("         opening. Never the green side.")
        print("      c) Calibration -> BLACK: cap OFF, opening pointing at")
        print("         nothing — downward, a metre up, and NOT at a lamp or a")
        print("         window.")
        print("      d) Take one measurement from the app, on any patch.")
        print("      e) Settings -> Others -> Average: switch it, then")
        print("         'Sync to Instrument'.")
        print("      f) Switch Average BACK, and Sync again.")
        print()
        print("    Steps b and c really do recalibrate your instrument — by the")
        print("    manufacturer's own method, which is no bad thing. Steps e")
        print("    and f change one setting and put it back, so the difference")
        print("    between them is the command.")
        input("\n    Press Return HERE FIRST, then work through a-f: ")
        out["phone"] = listen(ser, 180,
                              "PHASE 2 — listening to the cable while you use the phone")

        print("\n--- PHASE 3 — the POSITIVE CONTROL.")
        input("    Press Return, then press the INSTRUMENT'S OWN button once: ")
        out["own_button"] = listen(ser, 20, "PHASE 3 — your own button press")
    finally:
        try:
            dev.close()
        except Exception:                    # noqa: BLE001
            pass

    q, p, b = len(out["quiet"]), len(out["phone"]), len(out["own_button"])
    print("\n" + "=" * 72)
    if b == 0:
        verdict = ("LISTENER PROVEN DEAF — your own button press produced "
                   "nothing on the cable, so the silence in phase 2 means "
                   "nothing at all. Re-run; do not read anything into this.")
    elif q:
        verdict = (f"INCONCLUSIVE — {q} frame(s) arrived while nobody touched "
                   f"anything, so phase 2 cannot be attributed to the phone.")
    elif p:
        verdict = (f"THE LINKS MIRROR — {p} frame(s) reached the cable while "
                   f"only the phone was in use. A second app can reach into a "
                   f"ChromIQ session over USB, and ChromIQ would read a "
                   f"phone-side trigger as the operator's own press.")
    else:
        verdict = ("THE LINKS ARE INDEPENDENT — nothing reached the cable while "
                   "the phone measured and changed a setting, and your own "
                   "button press did. The cross-link hazard is theoretical.")
    print(verdict + "\n" + "=" * 72)
    out["verdict"] = verdict
    dest = ROOT / "captures" / "raw" / "EXP-021-cross-link.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    main()
