#!/usr/bin/env python3
"""EXP-020 -- does room light get into a reading of nothing?

The owner's question, and it is the right one: the vendor's black calibration is
done by pointing the instrument at nothing — port downward, a metre above the
floor. *"is such a way of black calibration even reliable? what if i am in a
bright environment with a reflective floor?"*

Two separate worries, and only one of them is hard to answer.

The FLOOR is probably irrelevant: the optics are built for contact, focused at
the aperture plane millimetres away, so at a metre almost nothing the lamp emits
finds its way back whatever the floor is made of. That is very likely why the
vendor specifies a metre.

AMBIENT LIGHT is the real question. A 4 mm hole pointed at a bright room
collects room light directly. Whether that matters depends on something nobody
has established: does the CR30 measure lamp-on minus lamp-off? Most
spectrophotometers do, exactly to cancel ambient. If it does, the room is
irrelevant. If it does not, a black calibration done under a window is a
DIFFERENT calibration from one done in a cupboard — and the vendor's instruction
says nothing about lighting, which would then be a trap.

## What this does

Reads AIR — port pointed at nothing — under different lighting, and compares.
Nothing else changes between the readings.

  A  bright: a phone torch shone straight into the opening
  B  dark:   torch off, and as dark as you can make it

A phone torch on purpose, rather than the room. Room lighting in the evening is
dim, and if a DIM light fails to move the reading all that proves is that dim
light does not get in — a sunlit room would still be an open question. A torch
pointed straight into a 4 mm hole is far brighter than any room, so if THAT
changes nothing, no realistic lighting ever will. It cannot harm the instrument:
it is a light sensor built to look at its own lamp.

If A and B agree, ambient is rejected and where you stand does not matter.
If they differ, ambient leaks in, and any black calibration must specify the
lighting — which is a finding in its own right.

## Safety

Cap OFF throughout, so every trigger is an ordinary measurement and nothing can
touch the white reference. Only `bb 01 00` (measure) and `bb 02 10` (read) are
sent. Never `bb 10` / `bb 11`.

## The control

Phase C re-reads under the FIRST condition again. If the instrument has simply
drifted during the run, C will disagree with A — and then the A-vs-B difference
cannot be blamed on the light. Without that, a warm-up drift would look exactly
like an ambient effect.
"""
import argparse
import datetime
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cr30.device import CR30                              # noqa: E402

N = 5


def read_set(dev, label, instruction):
    print(f"\n--- {label}")
    print(f"    {instruction}")
    input("    Press Return when it is set up (then keep still): ")
    means, spectra = [], []
    for i in range(1, N + 1):
        try:
            dev.trigger_unsafe()
            time.sleep(0.4)
            m = dev.read_measurement(enforce=False)
            mean = sum(m.values) / len(m.values)
            means.append(mean)
            spectra.append([round(v, 5) for v in m.values])
            print(f"      reading {i}: mean {mean:9.5f} %R")
        except Exception as exc:                          # noqa: BLE001
            print(f"      reading {i} failed: {exc}")
    return means, spectra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=("usb", "ble"), default="usb")
    a = ap.parse_args()

    print(__doc__)
    print("=" * 72)
    print("THE CAP MUST BE OFF for the whole run.")
    if input("Type 'cap off' to continue: ").strip().lower() != "cap off":
        print("Aborted."); return

    dev = (CR30.open_usb() if a.transport == "usb" else CR30.open_ble())
    print(f"Connected over {a.transport}.")

    out = {"experiment": "EXP-020", "transport": a.transport,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        bright, sb = read_set(
            dev, "PHASE A — BRIGHT",
            "Hold the instrument with the opening pointing at nothing —\n"
            "    out into the room, well away from any surface.\n"
            "    Now shine your PHONE TORCH straight into the opening,\n"
            "    10-20 cm away. Note roughly where you are holding it;\n"
            "    phase C has to repeat this.")
        dark, sd = read_set(
            dev, "PHASE B — DARK",
            "Torch OFF. Same position, same direction — do not move the\n"
            "    instrument if you can help it. Make it as dark as you can:\n"
            "    lights off, or the opening inside a drawer or under a coat.")
        again, sa = read_set(
            dev, "PHASE C — BRIGHT AGAIN (the control)",
            "Torch back ON, same distance and angle as phase A.\n"
            "    This is the control: if the instrument has drifted during the\n"
            "    run, this catches it, and the result says so instead of\n"
            "    blaming the light.")
    finally:
        try:
            dev.close()
        except Exception:                                  # noqa: BLE001
            pass

    out["bright"] = bright; out["dark"] = dark; out["bright_again"] = again
    out["spectra"] = {"bright": sb, "dark": sd, "bright_again": sa}

    print("\n" + "=" * 72)
    if min(len(bright), len(dark), len(again)) < 3:
        verdict = "TOO FEW READINGS to say anything."
    else:
        mb, md, ma = (statistics.mean(x) for x in (bright, dark, again))
        noise = max(statistics.pstdev(bright), statistics.pstdev(dark))
        drift = abs(ma - mb)
        effect = abs(mb - md)
        print(f"bright      mean {mb:9.5f} %R   (sd {statistics.pstdev(bright):.5f})")
        print(f"dark        mean {md:9.5f} %R   (sd {statistics.pstdev(dark):.5f})")
        print(f"bright again mean {ma:9.5f} %R  -> drift over the run {drift:.5f}")
        print(f"\nlight effect {effect:.5f} %R, noise {noise:.5f}, drift {drift:.5f}")
        if drift > effect:
            verdict = ("INCONCLUSIVE — the instrument moved more between the "
                       "two bright phases than the light itself changed "
                       "anything. Nothing here can be blamed on the room.")
        elif effect <= max(noise * 3, 0.01):
            verdict = (f"LIGHT DOES NOT GET IN. A torch shone into the opening "
                       f"and full darkness agree to {effect:.5f} %R, within the "
                       f"instrument's own noise. Pointing it at nothing is a "
                       f"sound way to read zero, and no realistic room lighting "
                       f"will ever matter.")
        else:
            verdict = (f"LIGHT DOES GET IN — {effect:.5f} %R between torch and "
                       f"darkness, well outside the noise. A black calibration "
                       f"would depend on the lighting it was done under, and "
                       f"any instruction for it must say so. How much a normal "
                       f"room matters is then a separate question, since a "
                       f"torch is far brighter than one.")
    print("\n" + verdict + "\n" + "=" * 72)
    out["verdict"] = verdict
    dest = ROOT / "captures" / "raw" / "EXP-020-ambient-light.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    main()
