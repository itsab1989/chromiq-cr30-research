#!/usr/bin/env python3
"""EXP-022 -- the designed calibration session: send bb 11 and bb 10 ourselves.

The owner lifted the standing "never send these" instruction on 2026-08-29 for
one designed session. This is it.

## What we are trying to learn

1. **Do the vendor's dedicated calibration commands work when WE send them?**
   ChromIQ currently calibrates white by putting a magnet at the aperture and
   firing an ordinary trigger — which works, but is a side effect. The vendor
   sends `bb 11` (white) and `bb 10` (black), each performing its own
   acquisition with no trigger involved.
2. **Does black calibration change anything measurable?** Nobody has ever taken
   one on this unit through our software.
3. **Is the reply's timestamp decode right?** Bytes [3..6] of the reply are
   believed to be a device-clock u32. His clock was set by the vendor app
   tonight, so the value should track wall clock. That decode is what killed the
   "0x01 means success" reading, so it is worth confirming.

## Why this is reversible

Every calibration is taken against the CORRECT surface: white against the cap's
white tile, black against open air. If a reference moves, taking the same
calibration again correctly restores it — that is what a calibration IS. The
danger with this instrument has only ever been calibrating against the WRONG
thing (the cap's green face), and no step here does that.

Paper is read before and after, on the same spot, so any shift is measured
rather than assumed. A change there is the signal to stop.

## What is NOT claimed

There is no success check. The reply carries a timestamp, not a result code, and
the instrument reports the same canned value whatever is under the cap. The only
evidence this run produces is what the readings do afterwards.
"""
import datetime
import json
import pathlib
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30.device import CR30                      # noqa: E402
from cr30 import usb_measure                      # noqa: E402
from cr30.frame import Frame                      # noqa: E402

WHITE_CAL = 0x11
BLACK_CAL = 0x10


def cal(dev, cmd, name):
    """Send one calibration command and return its reply, decoded."""
    f = Frame.build(0xBB, cmd, 0x00, 0)
    print(f"    sending {name}: {f.to_bytes()[:4].hex(' ')} …")
    t0 = time.monotonic()
    dev._t.send(f)
    try:
        reply = dev._t.receive(timeout=6.0)
    except Exception as exc:                       # noqa: BLE001
        print(f"    no reply: {exc}")
        return {"command": name, "reply": None, "error": str(exc)}
    b = reply.to_bytes()
    took = time.monotonic() - t0
    stamp = struct.unpack_from("<I", b, 3)[0]
    print(f"    reply in {took*1000:.0f} ms: {b[:8].hex(' ')}")
    print(f"    bytes[3..6] as u32 LE = {stamp}  "
          f"(as a unix time: {datetime.datetime.fromtimestamp(stamp)})")
    return {"command": name, "reply": b[:12].hex(), "ms": round(took * 1000),
            "stamp_u32": stamp,
            "stamp_as_time": str(datetime.datetime.fromtimestamp(stamp)),
            "wall_clock": datetime.datetime.now().isoformat()}


def press_and_read(dev, n, of, surface, setup):
    """One reading, with the surface named IN THE SAME BREATH as the press.

    The first version of this asked for a press and named the surface in a
    separate earlier prompt — so a reading recorded as "air" was taken on
    paper, and every magnitude in the run became unattributable. A prompt that
    does not say what is under the instrument at the moment of the press is not
    an instruction, it is a guess about what the operator remembered.
    """
    print(f"\n    ── PRESS {n} of {of} — {surface.upper()} ──")
    print(f"    {setup}")
    input(f"    Press Return when the instrument is {surface}: ")
    print(f"    Now press the instrument's own button — it is {surface}.")
    print("    waiting …", end="", flush=True)
    hdr = usb_measure.wait_for_button_header(dev._t, timeout=180.0)
    print(" got it.")
    m = dev.read_measurement(button_header=hdr, enforce=False)
    mean = sum(m.values) / len(m.values)
    print(f"    mean {mean:9.5f} %R   ({surface})")
    return {"mean": round(mean, 5), "surface": surface,
            "values": [round(v, 5) for v in m.values]}


def main():
    print(__doc__)
    print("=" * 72)
    print("USB cable in. ChromIQ CLOSED. Have the cap and a sheet of paper.")
    print()
    print("⚠ TURN BLUETOOTH OFF ON YOUR PHONE FIRST. Measured tonight: a")
    print("  connected phone app takes the button press and the cable never")
    print("  sees it — the reading simply never arrives.")
    print("This SENDS two calibration commands — the owner has authorised it.")
    if input("Type 'go' to continue: ").strip().lower() != "go":
        print("Aborted."); return

    dev = CR30.open_usb()
    print(f"Connected ({dev.model or 'CR30'}).")
    out = {"experiment": "EXP-022",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "steps": {}}
    try:
        print("\n--- STEP 1 — BEFORE the calibrations. Cap OFF for both.")
        out["steps"]["paper_before"] = press_and_read(
            dev, 1, 4, "on the paper",
            "Lay the instrument flat on the paper. Remember this exact spot —\n"
            "    press 4 has to be the same one.")
        out["steps"]["air_before"] = press_and_read(
            dev, 2, 4, "pointing at nothing",
            "Lift it and hold it with the opening pointing DOWNWARD into open\n"
            "    space — not at the desk, not at a lamp. Nothing in front of it.")

        print("\n--- STEP 2 — WHITE calibration, the vendor's own command.")
        input("    Seat the cap, WHITE TILE toward the opening — never the"
              "\n    green side. Press Return: ")
        out["steps"]["white_cal"] = cal(dev, WHITE_CAL, "bb 11 (white)")

        print("\n--- STEP 3 — BLACK calibration, the vendor's own command.")
        input("    Take the cap OFF. Hold the instrument pointing at nothing,"
              "\n    downward, about a metre up, not at a lamp. Press Return: ")
        out["steps"]["black_cal"] = cal(dev, BLACK_CAL, "bb 10 (black)")

        print("\n--- STEP 4 — AFTER. The same two readings, in the same order.")
        out["steps"]["air_after"] = press_and_read(
            dev, 3, 4, "pointing at nothing",
            "Cap still OFF. Hold it with the opening pointing DOWNWARD into\n"
            "    open space again — exactly as for press 2.")
        out["steps"]["paper_after"] = press_and_read(
            dev, 4, 4, "on the paper",
            "Lay it back on the paper — the SAME spot as press 1, as close as\n"
            "    you can manage.")
    finally:
        try:
            dev.close()
        except Exception:                          # noqa: BLE001
            pass

    s = out["steps"]
    print("\n" + "=" * 72)
    pb, pa = s.get("paper_before"), s.get("paper_after")
    ab, aa = s.get("air_before"), s.get("air_after")
    if pb and pa:
        ratio = pa["mean"] / pb["mean"] if pb["mean"] else 0
        print(f"paper  {pb['mean']:9.5f} -> {pa['mean']:9.5f} %R   "
              f"ratio {ratio:.4f}")
        out["paper_ratio"] = round(ratio, 4)
    if ab and aa:
        print(f"air    {ab['mean']:9.5f} -> {aa['mean']:9.5f} %R")
    print()
    if pb and pa and abs(out.get("paper_ratio", 1) - 1) > 0.02:
        print("⚠ THE PAPER READING MOVED by more than 2 %. Tell Claude BEFORE")
        print("  measuring anything for real. The restore is to repeat the same")
        print("  calibrations correctly — white against the white tile, black")
        print("  against open air.")
    else:
        print("The paper reading is unchanged, so the references still agree")
        print("with what they were. Nothing here claims the calibrations")
        print("'succeeded' — the instrument gives no such signal — only that")
        print("they did no harm.")
    print("=" * 72)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = ROOT / "captures" / "raw" / f"EXP-022-calibration-session-{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    main()
