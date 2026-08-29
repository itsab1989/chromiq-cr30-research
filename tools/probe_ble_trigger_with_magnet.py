#!/usr/bin/env python3
"""EXP-BLE-016 -- does the BLE HOST TRIGGER calibrate when a magnet is present?

The last big unknown after EXP-BLE-013/-014 (2026-08-29):

  * EXP-BLE-013: a button press pushes an unsolicited bb 01 00 event.
  * EXP-BLE-014: the magnet ALONE does nothing announced -- seating, resting
    and removing the cap emit no frame (positive control fired). So the
    calibration needs a trigger or a press; the Calibrate button is not
    theatre.
  * EXP-BLE-012: the BLE host trigger takes a real MEASUREMENT with no
    magnet.
  * EXP-MEAS-004 (USB): trigger-with-cap changed the white reference -- but
    the cap attach itself was uncontrolled, so it proved "trigger-or-magnet".
    EXP-BLE-014 has now removed the magnet-alone half: on THIS unit the
    remaining candidates are the trigger and the press.

What nobody has tested: `bb 01 00` over BLE **with the magnet engaged**.
That is exactly what ChromIQ's Calibrate button does, and the owner reports
it produces no beep -- so either it calibrates SILENTLY (beep = button-only
feedback) or it does nothing. This probe measures which, with a before/after
paper reading so the effect is a number, not an assumption.

## ⚠ SAFETY -- read before running

This is the ONE experiment tonight that can write the white reference.

  * The cap must be seated the CORRECT way: **WHITE TILE toward the
    aperture**. Then even a successful calibration writes the correct
    reference -- harmless, at worst the ~1-3 % seating offset two
    calibrations always differ by (EXP-CAL-002).
  * **NEVER the green face.** That is what corrupted this unit once.
  * The probe ends with the VERIFIED restore either way: cap seated
    correctly + one button press, then a confirmation reading of the paper.
  * It never sends bb 10 / bb 11.

## Phases

  P1  cap OFF: two button presses on paper, read after each  (baseline;
      also re-proves fresh readings differ in the low bits)
  T   cap ON, white tile in, gate confirmed on the display if it shows the
      tile value; host sends ONE bb 01 00. Listen and watch:
        - unsolicited/reply frames (does a trigger announce like a press?)
        - beep? lamp?           <- the owner's missing feedback, measured
      then read the stored value (tile constant = gated path taken).
  P2  cap OFF: two presses on the SAME paper spot, read after each.
        ratio P2/P1 ~ 1.000 +/- 0.002  -> the trigger wrote NOTHING: the
            Calibrate button is ineffective over BLE with a magnet, and the
            app must instruct the user to press the button instead.
        ratio P2/P1 = neutral 1-3 %    -> the trigger DID calibrate,
            silently: the button works, and the beep is button-only
            feedback the UI must stop relying on.
  R   restore: cap seated correctly, one button press (beep expected),
      cap off, one last paper reading -- must sit within ~3 % of P1.

Output: captures/raw/EXP-BLE-016-trigger-with-magnet.json
"""
import asyncio
import datetime
import json
import pathlib
import statistics
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError:
    sys.exit("bleak missing -- run with .venv/bin/python")

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])
HDR = bytes([0xBB, 0x02, 0x10, 0x00])
READ_MEASUREMENT = bytes([0xBB, 0x02, 0x10, 0, 0, 0, 0, 0, 0xFF, 0xCC])
TRIGGER = bytes([0xBB, 0x01, 0x00, 0, 0, 0, 0, 0, 0xFF, 0xBB])


async def ask(prompt):
    return await asyncio.to_thread(input, prompt)


class Run:
    def __init__(self):
        self.t0 = time.monotonic()
        self.buf = bytearray()
        self.reading = False
        self.log = {"experiment": "EXP-BLE-016",
                    "utc": datetime.datetime.now(
                        datetime.timezone.utc).isoformat(),
                    "cap_face": "WHITE tile toward the aperture, always",
                    "notifications": [], "steps": []}

    def now(self):
        return round(time.monotonic() - self.t0, 3)

    def on_notify(self, _s, data):
        b = bytes(data)
        self.log["notifications"].append(
            {"t": self.now(), "len": len(b), "hex": b.hex(),
             "during_read": self.reading})
        if self.reading:
            self.buf.extend(b)
        else:
            print(f"      <<< {self.now():8.3f}s  {len(b):3d}B  "
                  f"{b[:12].hex(' ')}")

    async def read_stored(self, c, tries=8):
        for attempt in range(tries):
            self.reading = True
            self.buf.clear()
            await asyncio.sleep(0.3)
            self.buf.clear()
            await c.write_gatt_char(FFE1, READ_MEASUREMENT, response=False)
            await asyncio.sleep(0.4)
            quiet = 0
            for _ in range(10):
                n = len(self.buf)
                await c.write_gatt_char(FFE1, POLL, response=False)
                await asyncio.sleep(0.35)
                quiet = quiet + 1 if len(self.buf) == n else 0
                if quiet >= 3 and self.buf:
                    break
            raw = bytes(self.buf)
            self.reading = False
            i = raw.rfind(HDR)
            while i >= 0:
                if len(raw) - i >= 196:
                    vals = list(struct.unpack_from("<31f", raw, i + 8))
                    run = best = 0
                    for v in vals:
                        run = run + 1 if v == 0.0 else 0
                        best = max(best, run)
                    if best < 3:
                        return vals
                i = raw.rfind(HDR, 0, i)
            print(f"    (read {attempt + 1} incomplete -- device busy?"
                  " retrying)")
            await asyncio.sleep(1.0)
        return None


def show(tag, vals):
    if vals is None:
        print(f"    {tag}: NO USABLE REPLY")
    else:
        print(f"    {tag}: mean {sum(vals)/31:7.3f} %R")


def ratio(a, b):
    rs = [x / y for x, y in zip(a, b) if y > 0.5]
    return statistics.fmean(rs), statistics.pstdev(rs)


async def main():
    print(__doc__)
    print("=" * 72)
    print("SAFETY CHECK: you will only ever seat the cap WHITE TILE toward")
    print("the aperture. If you are not sure which face that is, stop now.")
    if (await ask("Type WHITE and press Return to continue: ")).strip()\
            .lower() != "white":
        sys.exit("stopped -- nothing was sent")

    print("\nScanning ...")
    dev = None
    for d, adv in (await BleakScanner.discover(timeout=8.0,
                                               return_adv=True)).values():
        if FFE0 in [u.lower() for u in (adv.service_uuids or [])]:
            dev = d
            break
    if dev is None:
        sys.exit("No CR30 found.")
    print(f"Found {dev.address}")

    r = Run()
    rd = {}
    async with BleakClient(dev.address, timeout=20.0) as c:
        await c.start_notify(FFE1, r.on_notify)

        print("\n--- P1  baseline: cap OFF, instrument flat on plain paper")
        for i in (1, 2):
            await ask(f"    Press Return, THEN the DEVICE button once "
                      f"({i}/2): ")
            await asyncio.sleep(2.0)
            rd[f"P1_{i}"] = await r.read_stored(c)
            show(f"P1.{i} paper", rd[f"P1_{i}"])
        r.log["steps"].append({"step": "P1", "values": [rd.get("P1_1"),
                                                        rd.get("P1_2")]})

        print("\n--- T  the trigger, with the magnet engaged")
        await ask("    Seat the cap the CORRECT way (WHITE tile in). If the "
                  "display updates,\n    it should show about L* 91.6. "
                  "Press Return when seated: ")
        print("    Sending ONE bb 01 00 in 2 s -- WATCH the aperture and "
              "LISTEN for a beep...")
        await asyncio.sleep(2.0)
        t_trig = r.now()
        await c.write_gatt_char(FFE1, TRIGGER, response=False)
        await asyncio.sleep(3.0)
        obs = await ask("    Did it BEEP? Did the LAMP flash? Display "
                        "change? (describe): ")
        rd["T"] = await r.read_stored(c)
        show("T stored after trigger (cap on)", rd["T"])
        r.log["steps"].append({"step": "T", "t_trigger": t_trig,
                               "operator_observed": obs,
                               "stored_after": rd["T"]})

        print("\n--- P2  cap OFF, same paper spot")
        await ask("    Take the cap OFF, seat on the SAME paper spot, "
                  "press Return: ")
        for i in (1, 2):
            await ask(f"    Press Return, THEN the DEVICE button once "
                      f"({i}/2): ")
            await asyncio.sleep(2.0)
            rd[f"P2_{i}"] = await r.read_stored(c)
            show(f"P2.{i} paper", rd[f"P2_{i}"])
        r.log["steps"].append({"step": "P2", "values": [rd.get("P2_1"),
                                                        rd.get("P2_2")]})
        if rd.get("P1_1") and rd.get("P2_1"):
            m, sd = ratio(rd["P2_1"], rd["P1_1"])
            r.log["ratio_P2_over_P1"] = {"mean": m, "sd": sd}
            print(f"\n    paper ratio P2/P1 = {m:.4f} +/- {sd:.4f}")
            print("      ~1.000 +/- 0.002 -> the trigger wrote NOTHING "
                  "(Calibrate button ineffective over BLE);")
            print("      neutral 1-3 %    -> the trigger CALIBRATED, "
                  "silently (beep is button-only feedback).")

        print("\n--- R  restore (do this regardless of the result)")
        await ask("    Seat the cap CORRECTLY (white tile in) and press the "
                  "DEVICE button once\n    -- this is the known-good "
                  "calibration; it should beep. Then press Return: ")
        await ask("    Cap OFF, instrument on the paper spot, press Return, "
                  "THEN the button once: ")
        await asyncio.sleep(2.0)
        rd["R"] = await r.read_stored(c)
        show("R paper after restore", rd["R"])
        if rd.get("P1_1") and rd.get("R"):
            m, sd = ratio(rd["R"], rd["P1_1"])
            r.log["ratio_R_over_P1"] = {"mean": m, "sd": sd}
            print(f"    restore check R/P1 = {m:.4f} +/- {sd:.4f} "
                  "(within ~3 % of 1.0 = healthy)")

    r.log["readings"] = rd
    out = OUT / "EXP-BLE-016-trigger-with-magnet.json"
    out.write_text(json.dumps(r.log, indent=1))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
