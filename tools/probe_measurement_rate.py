#!/usr/bin/env python3
"""EXP-018 -- how many readings per second, and can they track a moving head?

The owner's idea: strip reading on a CR30. Press the button once on paper
white, then let ChromIQ trigger the instrument as fast as it can while the head
is drawn along the strip, detect paper white again at the far end, and assign
the readings to patches.

Everything in that plan rests on two numbers nobody has measured:

  1. HOW FAST can a trigger-and-read cycle complete, on each transport?
     A strip of 26 patches drawn over ~6 seconds needs well over 4 readings a
     second just to touch each patch once, and several times that to place the
     boundaries with any confidence.
  2. DOES EACH TRIGGER ACTUALLY MEASURE, or does it sometimes hand back the
     value it already held? A rate is worthless if half the readings are
     repeats -- and a repeat is indistinguishable from a genuinely uniform
     patch unless the head is moving over something that changes.

## Safety

Cap OFF for the whole run, and it stays off. With no magnet at the aperture a
trigger is an ordinary measurement and nothing can touch the white reference.
Only `bb 01 00` (measure) and `bb 02 10` (read stored) are sent -- never
`bb 10` / `bb 11`.

## Phases

  A  STATIC. Instrument still, on one patch. Trigger flat out for 12 s.
     -> the ceiling: cycles per second, and how many were genuinely new.
  B  MOVING. Same thing, but draw the head slowly along a row of DIFFERENT
     patches while it runs.
     -> do the readings follow the surface? If phase B's readings change no
        more often than phase A's, the head is outrunning the instrument and
        strip reading cannot work at this speed.

Phase A is also the control for phase B: on one uniform patch the readings
SHOULD repeat, and if they do not, the instrument's own noise is large enough
to matter and the report says so.
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

from cr30.colour import spectrum_to_lab               # noqa: E402
from cr30.device import CR30                          # noqa: E402


def de(a, b):
    """CIE76 between two L*a*b* readings. Crude on purpose: we are asking
    "did the surface change", not "by how much perceptually"."""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def run_phase(dev, name, seconds, what):
    print(f"\n--- PHASE {name} ({seconds} s) — {what}")
    input("    Press Return to start this phase: ")
    t0 = time.monotonic()
    cycles, labs, errors, gaps = 0, [], 0, []
    last = t0
    while time.monotonic() - t0 < seconds:
        try:
            dev.trigger_unsafe()
            m = dev.read_measurement(enforce=False)
            now = time.monotonic()
            gaps.append(now - last)
            last = now
            cycles += 1
            labs.append(spectrum_to_lab([v / 100.0 for v in m.values]))
        except Exception as exc:                  # noqa: BLE001
            errors += 1
            if errors <= 3:
                print(f"    (a cycle failed: {exc})")
    elapsed = time.monotonic() - t0
    rate = cycles / elapsed if elapsed else 0.0
    # HOW MUCH consecutive readings differ, not whether they differ at all.
    # The first version of this counted any difference as a change, and
    # instrument noise in the fourth decimal made every reading unique — so it
    # read 100 % in BOTH phases and could not tell them apart. A statistic that
    # saturates answers nothing.
    steps = [de(a, b) for a, b in zip(labs, labs[1:])]
    med = statistics.median(steps) if steps else 0.0
    print(f"    {cycles} readings in {elapsed:.1f} s  =  {rate:.2f} per second")
    if gaps:
        print(f"    per reading: median {statistics.median(gaps)*1000:.0f} ms, "
              f"fastest {min(gaps)*1000:.0f} ms, slowest {max(gaps)*1000:.0f} ms")
    print(f"    change between consecutive readings: median dE {med:.3f}, "
          f"largest {max(steps) if steps else 0:.3f}")
    print(f"    {errors} failed")
    return {"phase": name, "cycles": cycles, "seconds": round(elapsed, 2),
            "per_second": round(rate, 2), "errors": errors,
            "median_step_de": round(med, 4),
            "max_step_de": round(max(steps), 4) if steps else 0.0,
            "steps": [round(x, 4) for x in steps],
            "labs": [[round(x, 3) for x in l] for l in labs],
            "median_ms": round(statistics.median(gaps) * 1000, 1) if gaps else None,
            "fastest_ms": round(min(gaps) * 1000, 1) if gaps else None,
            "slowest_ms": round(max(gaps) * 1000, 1) if gaps else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=("usb", "ble"), required=True)
    a = ap.parse_args()

    print(__doc__)
    print("=" * 72)
    print("THE CAP MUST BE OFF and must stay off for the whole run.")
    if input("Type 'cap off' to continue: ").strip().lower() != "cap off":
        print("Aborted."); return

    print(f"\nOpening over {a.transport} …")
    dev = CR30.open_usb() if a.transport == "usb" else CR30.open_ble()
    print("Connected.")

    out = {"experiment": "EXP-018", "transport": a.transport,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "phases": []}
    try:
        out["phases"].append(run_phase(
            dev, "A", 12, "hold the instrument STILL on ONE patch"))
        out["phases"].append(run_phase(
            dev, "B", 12, "draw the instrument SLOWLY along a row of\n"
                          "         DIFFERENT patches while this runs"))
    finally:
        try:
            dev.close()
        except Exception:                          # noqa: BLE001
            pass

    A, B = out["phases"]
    print("\n" + "=" * 72)
    rate = A["per_second"]
    noise, moving = A["median_step_de"], B["median_step_de"]
    if A["cycles"] < 5 or B["cycles"] < 5:
        verdict = "TOO FEW READINGS to say anything. Something is wrong."
    elif moving < noise * 3:
        verdict = (f"THE READINGS DO NOT FOLLOW THE SURFACE. Held still, "
                   f"consecutive readings differ by dE {noise:.2f} — that is "
                   f"the instrument's own noise. Moving across different "
                   f"patches they differ by only dE {moving:.2f}, which is not "
                   f"meaningfully more. At {rate:.1f} readings a second the "
                   f"head outruns the instrument, so strip reading cannot work "
                   f"this way on this transport.")
    else:
        per_patch = rate * (8.0 / 26)
        verdict = (f"THE READINGS DO FOLLOW THE SURFACE: dE {noise:.2f} between "
                   f"readings held still (the noise floor) against dE "
                   f"{moving:.2f} while moving — {moving/max(noise, 1e-9):.0f}x. "
                   f"At {rate:.1f} readings a second, a 26-patch strip drawn "
                   f"over eight seconds gets about {per_patch:.1f} readings per "
                   f"patch. Fewer than ~2 and a patch boundary cannot be "
                   f"placed; fewer than ~1 and patches are missed outright.")
    print(verdict + "\n" + "=" * 72)
    out["verdict"] = verdict
    dest = ROOT / "captures" / "raw" / f"EXP-018-rate-{a.transport}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    main()
