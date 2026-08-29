#!/usr/bin/env python3
"""EXP-BLE-013 -- does a BUTTON PRESS push a notification over Bluetooth?

This is the question the whole reliability problem turns on.

Over USB the instrument emits an unsolicited `BB 01 09` frame when its button
is pressed. That is an EVENT: one press, one frame, unambiguous. Over BLE we
believe no such thing exists, so `read_next_measurement` infers a press by
polling the stored reading and noticing it changed. Inference cannot tell one
press from three, it attributes whatever it finds to whichever patch is armed at
that moment, and any latency slides a reading onto a later patch -- which is
exactly what the owner reports: "nothing for a while, then suddenly a few
measurements are recognized (and then for the wrong patches)".

There is direct reason to doubt the belief. In his session of 2026-08-28 three
notifications arrived at 22:32:57, 22:33:15 and 22:33:17 -- long after the app
had stopped polling -- and they line up with his button presses. Our own
transport clears its buffer at the start of every request, so unsolicited frames
are thrown away unread. If the device really does push on a press, a real event
exists on Bluetooth too and the poll-and-compare design is unnecessary.

## Safety

This probe is PASSIVE. It connects, subscribes to notifications, and **sends
nothing at all** -- no trigger, no poll byte, no calibration command. It cannot
change the instrument's stored reading or its white reference. Run it with the
cap off anyway, so that any reading the operator takes is an ordinary one.

## Method, and the control

  Phase 1 (10 s)  QUIET. Touch nothing. Any notification here is unsolicited
                  chatter and would make the result ambiguous -- so this
                  phase is the control, and it must be silent.
  Phase 2         THREE presses, spaced by a few seconds, with the instrument
                  flat on a patch.
  Phase 3 (10 s)  QUIET again.

  3 notifications in phase 2 and none in 1 or 3  ->  A BUTTON PRESS IS AN EVENT
      ON BLE. The reliability fix is to listen for it instead of polling.
  0 in phase 2                                    ->  no push; polling really is
      the only mechanism, and the fix has to be elsewhere.
  Traffic in phases 1 or 3                        ->  the device chatters on its
      own; INCONCLUSIVE about presses, and worth knowing separately.
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
             "Run the probe with the repo's own venv:\n\n"
             "  ./.venv/bin/python tools/probe_ble_button_notification.py\n")

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"


async def main():
    print(__doc__)
    print("=" * 72)
    print("ChromIQ must be CLOSED — it holds the Bluetooth link while it runs.")
    print("The cap should be OFF. This probe sends the instrument nothing.")
    input("Press Return when ready: ")

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

    events = []
    t0 = time.monotonic()

    def on_notify(_sender, data: bytearray):
        events.append({"t": round(time.monotonic() - t0, 3),
                       "len": len(data), "head": bytes(data[:10]).hex(),
                       "hex": bytes(data).hex()})
        print(f"    ← notification at {events[-1]['t']:6.2f} s   "
              f"{len(data)} bytes   {events[-1]['head']}")

    async with BleakClient(dev.address, timeout=20.0) as c:
        await c.start_notify(FFE1, on_notify)

        print("PHASE 1 — CONTROL. Do NOT touch the instrument for 10 seconds.")
        await asyncio.sleep(10)
        quiet_before = len(events)
        print(f"  phase 1 notifications: {quiet_before}"
              f"{'  <- should be 0' if quiet_before else '  ✓ silent'}\n")

        print("PHASE 2 — three presses, flat on the patch, one at a time.")
        press_marks = []
        for i in (1, 2, 3):
            input(f"          Press Return HERE first, then press the DEVICE "
                  f"button once ({i}/3): ")
            press_marks.append(round(time.monotonic() - t0, 3))
            await asyncio.sleep(8)
        during = len(events) - quiet_before
        print(f"\n  phase 2 notifications: {during}\n")

        print("PHASE 3 — CONTROL. Do NOT touch it for 10 seconds.")
        await asyncio.sleep(10)
        quiet_after = len(events) - quiet_before - during
        print(f"  phase 3 notifications: {quiet_after}"
              f"{'  <- should be 0' if quiet_after else '  ✓ silent'}")

    if quiet_before or quiet_after:
        verdict = ("INCONCLUSIVE — the device sent frames while nobody touched "
                   "it, so a notification cannot be attributed to a press. "
                   "Worth knowing on its own.")
    elif during >= 1:
        verdict = (f"A BUTTON PRESS IS AN EVENT ON BLE — {during} notification(s) "
                   f"arrived from {3} presses, and both control phases were "
                   f"silent. Nothing was sent to the device at any point.")
    else:
        verdict = ("NO PUSH ON A BUTTON PRESS — the controls were silent and so "
                   "was the press phase. Polling really is the only mechanism.")

    print("\n" + "=" * 72 + f"\n{verdict}\n" + "=" * 72)
    out = {"experiment": "EXP-BLE-013",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "quiet_before": quiet_before, "during_presses": during,
           "quiet_after": quiet_after, "presses_asked_for": 3,
           "press_marks": press_marks,
           "events": events, "verdict": verdict}
    dest = ROOT / "captures" / "raw" / "EXP-BLE-013-button-notification.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    asyncio.run(main())
