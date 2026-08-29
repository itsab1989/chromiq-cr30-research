#!/usr/bin/env python3
"""EXP-BLE-014 -- does the MAGNET ALONE make the instrument act?

The owner's hypothesis, in his words: *"maybe the magnet alone triggers the
calibration without presing a button at all. or maybe not that but sometimes you
can see the lights of the device flashing although there is no beep and no
button pressed"*.

EXP-BLE-013 established that a button press pushes an unsolicited 10-byte
`bb 01 00 ...` frame over Bluetooth -- an EVENT. That gives us a way to ask his
question with no commands at all: if seating the cap makes the device act, it
should announce it the same way.

If it does, a great deal follows. The Calibrate button ChromIQ now ships would be
theatre; the safety rule about never sending the trigger command would have been
aimed at the wrong thing entirely; and an instrument stored with its cap on would
be recalibrating itself, repeatedly, against whichever face meets the aperture.

## Safety

PASSIVE: this connects, subscribes, and **sends the instrument nothing**. It
cannot command a calibration.

The cap goes on **WHITE TILE toward the opening**. That is the correct reference
surface, so if the magnet does cause a calibration, calibrating against the white
tile is exactly what the instrument is supposed to do -- harmless, and if
anything restorative. **Never the green face**: that is what corrupted this unit
during the research, and the error is invisible afterwards.

## Phases -- all timed, no prompts once the link is live

  A  10 s  cap OFF, do not touch          CONTROL: must be silent
  B  15 s  seat the cap, WHITE side in    the question
  C  10 s  leave it seated, do not touch  is it once, or does it repeat?
  D  15 s  take the cap OFF               does removing the magnet act too?
  E  10 s  do not touch                   CONTROL: must be silent
  F  15 s  press the button ONCE          POSITIVE CONTROL: proves the
                                          listener is alive this run

Phase F is the one that makes a null result meaningful. Without it, "no frames in
B" could just as well mean the probe was broken -- and a broken probe reporting
itself as a fact is how you end up believing something false.
"""
import asyncio
import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError:
    sys.exit("bleak is not installed for this interpreter.\n"
             "  ./.venv/bin/python tools/probe_ble_magnet_event.py\n")

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"

PHASES = [
    ("A", 10, "cap OFF — do NOT touch the instrument", "control"),
    ("B", 15, "SEAT THE CAP NOW — white tile toward the opening", "magnet on"),
    ("C", 10, "leave the cap on — do NOT touch it", "magnet resting"),
    ("D", 15, "TAKE THE CAP OFF NOW", "magnet off"),
    ("E", 10, "do NOT touch the instrument", "control"),
    ("F", 15, "PRESS THE BUTTON ONCE, flat on a patch", "positive control"),
]


async def main():
    print(__doc__)
    print("=" * 72)
    print("ChromIQ must be CLOSED. Start with the cap OFF.")
    print("Watch the instrument's LIGHTS and note when they flash.")
    await asyncio.to_thread(input, "Press Return when ready: ")

    print("\nScanning …")
    dev = None
    for d, adv in (await BleakScanner.discover(timeout=8.0,
                                               return_adv=True)).values():
        if FFE0 in [u.lower() for u in (adv.service_uuids or [])]:
            dev = d
            break
    if dev is None:
        print("No CR30 found. Is ChromIQ or the phone app holding it?")
        return
    print(f"Found {dev.address}\n")

    events, t0 = [], time.monotonic()

    def on_notify(_sender, data: bytearray):
        events.append({"t": round(time.monotonic() - t0, 3),
                       "len": len(data), "hex": bytes(data[:12]).hex()})
        print(f"      ← FRAME at {events[-1]['t']:6.2f} s   "
              f"{len(data)} bytes   {events[-1]['hex']}")

    counts = {}
    async with BleakClient(dev.address, timeout=20.0) as c:
        await c.start_notify(FFE1, on_notify)
        for name, secs, what, kind in PHASES:
            before = len(events)
            print(f"\n--- PHASE {name} ({secs} s) — {what}")
            for left in range(secs, 0, -1):
                print(f"      {left:2d} …", end="\r", flush=True)
                await asyncio.sleep(1)
            counts[name] = len(events) - before
            print(f"      phase {name}: {counts[name]} frame(s)          ")

    print("\n" + "=" * 72)
    if counts["F"] == 0:
        verdict = ("PROBE NOT PROVEN — the positive control saw no frame from a "
                   "button press, so this run says NOTHING about the magnet. "
                   "Re-run it; do not read anything into phases B or D.")
    elif counts["A"] or counts["E"]:
        verdict = ("INCONCLUSIVE — the device sent frames while nobody touched "
                   "it, so nothing here can be attributed to the magnet.")
    elif counts["B"] or counts["C"] or counts["D"]:
        verdict = (f"THE MAGNET ALONE MAKES THE INSTRUMENT ACT — "
                   f"seating it: {counts['B']} frame(s), resting: {counts['C']}, "
                   f"removing it: {counts['D']}, with both controls silent and "
                   f"nothing sent to the device.")
    else:
        verdict = ("THE MAGNET ALONE DOES NOTHING — the controls were silent, "
                   "the button press was seen, and seating, resting and "
                   "removing the cap produced no frame at all.")
    print(verdict + "\n" + "=" * 72)

    out = {"experiment": "EXP-BLE-014",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "phase_counts": counts, "events": events, "verdict": verdict}
    dest = ROOT / "captures" / "raw" / "EXP-BLE-014-magnet-event.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    asyncio.run(main())
