#!/usr/bin/env python3
"""EXP-BLE-015 -- one corrected run (renumbered: EXP-BLE-014 is the passive magnet-event listener): press events, magnet events, magnet-alone
calibration, and a possible BLE gate flag.

Builds on EXP-BLE-013 (2026-08-29), which PROVED a button press pushes an
unsolicited, checksum-valid 10-byte frame over BLE with zero host writes:

    bb 01 00 00 01 90 0a 1f ff 75     (cmd 01, axis 400/10/31, cs 0x75)

-- byte-identical to the frame the vendor capture logged as "hello / axis
announcement". EXP-BLE-013's phase arithmetic was broken (input() blocked the
event loop), so this run uses asyncio.to_thread for every prompt: notifications
keep flowing while the operator reads instructions.

One run, seven phases, answers four open questions:

  A  control silence 15 s                 -> connect alone emits nothing?
  B  2 presses on paper, read after each  -> event per press; fresh-reading
                                             control (B1 != B2 in low bits)
  C  control silence 10 s
  D  cap ON (WHITE tile toward the aperture), NO press, 25 s, then read
     with the cap still on:
       * a push here          -> the MAGNET reaches the wire over BLE
       * stored value becomes the tile constant with no press
                              -> the magnet ALONE performs the gated event (O1)
  E  cap OFF, 2 presses on the SAME paper spot, read after each.
     Band ratio E/B isolates phase D:
       * ~1.000 +/- 0.002     -> no white-reference write during D
       * neutral 1-3 % shift  -> a calibration WAS written during D
     (the seating signature between two known calibrations is 1.032 +/- 0.010,
      EXP-CAL-002; plain repeatability is 0.056 % worst-band SD, EXP-MEAS-001)
  F  cap ON white-face, ONE press (a gated press -- safe: the white tile is
     the correct reference). Watch the frame bytes: over USB a gated press
     sets a flag the host can read; if the BLE push differs in ANY byte from
     phase B's, Bluetooth gains magnet detection. Then read: the stored value
     should be the tile constant (confirm the gate on the device display --
     L* about 91.6 -- the hall sensor is POSITIONAL and may need reseating).
  G  cap OFF, 1 press on paper, read. Ratio G/E shows what a known gated
     press does to the calibration, for comparison against D's verdict.

WRITES: bb 02 10 (read stored measurement) and 0x01 polls ONLY. No trigger,
no bb 10 / bb 11, ever. All magnet events use the WHITE tile face; even if a
calibration fires it fires against the correct reference.

Output: captures/raw/EXP-BLE-015-press-magnet.json
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
    sys.exit("bleak is not installed for this interpreter.\n"
             "Run:  .venv/bin/python tools/probe_ble_press_magnet_suite.py")

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])
HDR = bytes([0xBB, 0x02, 0x10, 0x00])
READ_MEASUREMENT = bytes([0xBB, 0x02, 0x10, 0, 0, 0, 0, 0, 0xFF, 0xCC])
PRESS_EVENT = bytes.fromhex("bb01000001900a1fff75")   # EXP-BLE-013


async def ask(prompt):
    """input() OFF the event loop -- EXP-BLE-013's bug, fixed."""
    return await asyncio.to_thread(input, prompt)


class Run:
    def __init__(self):
        self.t0 = time.monotonic()
        self.events = []          # every notification, timestamped, full hex
        self.buf = bytearray()    # reply assembly for read_stored
        self.reading = False
        self.log = {"experiment": "EXP-BLE-015",
                    "utc": datetime.datetime.now(
                        datetime.timezone.utc).isoformat(),
                    "writes": "bb 02 10 + 0x01 polls only",
                    "phases": [], "notifications": []}

    def now(self):
        return round(time.monotonic() - self.t0, 3)

    def on_notify(self, _s, data):
        b = bytes(data)
        ev = {"t": self.now(), "len": len(b), "hex": b.hex(),
              "during_read": self.reading}
        self.log["notifications"].append(ev)
        if self.reading:
            self.buf.extend(b)
        tag = ""
        if b == PRESS_EVENT:
            tag = "  <- THE PRESS/MEASUREMENT EVENT"
        elif len(b) == 10 and b[0] == 0xBB and b[9] == sum(b[:9]) % 256:
            tag = "  <- valid 10-byte frame, NOT the known event (interesting!)"
        if not self.reading or tag:
            print(f"      <<< {ev['t']:8.3f}s  {len(b):3d}B  "
                  f"{b[:12].hex(' ')}{tag}")

    def phase(self, name):
        p = {"phase": name, "t_start": self.now(), "notes": []}
        self.log["phases"].append(p)
        print(f"\n--- PHASE {name}  (t={p['t_start']:.1f}s)")
        return p

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
            print(f"    (read attempt {attempt + 1}: incomplete, retrying)")
            await asyncio.sleep(1.0)
        return None


def show(tag, vals):
    if vals is None:
        print(f"    {tag}: NO USABLE REPLY")
    else:
        print(f"    {tag}: mean {sum(vals)/31:7.3f} %R   first bands "
              f"{vals[0]:.3f} {vals[1]:.3f} {vals[2]:.3f}")


def ratio(a, b):
    rs = [x / y for x, y in zip(a, b) if y > 0.5]
    return statistics.fmean(rs), statistics.pstdev(rs)


async def main():
    print(__doc__)
    print("=" * 72)
    print("ChromIQ must be CLOSED. Phone app disconnected. Cap OFF to start.")
    print("Have one sheet of plain paper on the desk and the cap within reach.")
    await ask("Press Return when ready: ")

    print("\nScanning ...")
    dev = None
    for d, adv in (await BleakScanner.discover(timeout=8.0,
                                               return_adv=True)).values():
        if FFE0 in [u.lower() for u in (adv.service_uuids or [])]:
            dev = d
            break
    if dev is None:
        sys.exit("No CR30 found. Is something holding it? Is it awake?")
    print(f"Found {dev.address}")

    r = Run()
    readings = {}
    async with BleakClient(dev.address, timeout=20.0) as c:
        await c.start_notify(FFE1, r.on_notify)

        p = r.phase("A control 15 s -- touch nothing")
        await asyncio.sleep(15)
        p["notes"].append(f"notifications: "
                          f"{len([e for e in r.log['notifications']])}")

        p = r.phase("B baseline -- cap OFF, instrument flat on the paper")
        for i in (1, 2):
            await ask(f"    Press Return here, THEN press the DEVICE button "
                      f"once ({i}/2): ")
            p["notes"].append({"press": i, "t": r.now()})
            await asyncio.sleep(2.0)
            readings[f"B{i}"] = await r.read_stored(c)
            show(f"B{i} paper", readings[f"B{i}"])
        same = readings.get("B1") == readings.get("B2")
        print(f"    B1 == B2 bit-identical: {same}  (must be False)")
        p["notes"].append({"b1_equals_b2": same})

        p = r.phase("C control 10 s -- touch nothing")
        await asyncio.sleep(10)

        p = r.phase("D cap ON, WHITE tile toward the aperture, NO press")
        await ask("    Seat the cap the CORRECT way (white tile in), press "
                  "NOTHING,\n    then press Return here: ")
        p["notes"].append({"cap_on": r.now()})
        print("    ...waiting 25 s. Watch the device: any beep, light flash,"
              " display change?")
        await asyncio.sleep(25)
        readings["D"] = await r.read_stored(c)   # cap still ON
        show("D stored (cap on, no press)", readings["D"])
        obs = await ask("    What did you observe while it was on "
                        "(beep/flash/display/nothing)? ")
        p["notes"].append({"operator_observed": obs})
        changed = readings["D"] != readings.get("B2")
        print(f"    stored value changed with no press: {changed}")

        p = r.phase("E cap OFF, same paper spot, two presses")
        await ask("    Take the cap OFF (watch for any light flash as it "
                  "comes off),\n    seat the instrument on the SAME paper "
                  "spot, press Return: ")
        # E0: read BEFORE any press. EXP-BLE-014 saw the lights flash at
        # cap REMOVAL with no frame; if removal takes a hidden measurement,
        # the stored value changes between D and here.
        readings["E0"] = await r.read_stored(c)
        show("E0 stored right after cap-off (no press yet)", readings["E0"])
        print(f"    changed vs D: {readings['E0'] != readings.get('D')}"
              "   (True -> cap REMOVAL itself acted)")
        for i in (1, 2):
            await ask(f"    Press Return here, THEN press the DEVICE button "
                      f"once ({i}/2): ")
            p["notes"].append({"press": i, "t": r.now()})
            await asyncio.sleep(2.0)
            readings[f"E{i}"] = await r.read_stored(c)
            show(f"E{i} paper", readings[f"E{i}"])
        if readings.get("B1") and readings.get("E1"):
            m, sd = ratio(readings["E1"], readings["B1"])
            r.log["ratio_E_over_B"] = {"mean": m, "sd": sd}
            print(f"    paper ratio E1/B1 = {m:.4f} +/- {sd:.4f}")
            print("      ~1.000+/-0.002 -> phase D wrote NO calibration;"
                  " 1-3 % neutral -> it DID.")

        p = r.phase("F cap ON white tile, ONE press (gated -- safe)")
        await ask("    Seat the cap correctly again (white tile in). Check "
                  "the DISPLAY shows the\n    tile value (L* near 91.6) if "
                  "it updates; the magnet may need reseating.\n    Press "
                  "Return here, THEN press the DEVICE button once: ")
        p["notes"].append({"gated_press": r.now()})
        await asyncio.sleep(2.5)
        readings["F"] = await r.read_stored(c)   # cap still ON
        show("F stored (gated press)", readings["F"])
        obs = await ask("    Did that press beep / flash? What does the "
                        "display show? ")
        p["notes"].append({"operator_observed": obs})

        p = r.phase("G cap OFF, one press on the paper")
        await ask("    Cap OFF, instrument on the same paper spot. Press "
                  "Return, THEN the button: ")
        await asyncio.sleep(2.0)
        readings["G"] = await r.read_stored(c)
        show("G paper", readings["G"])
        if readings.get("E2") and readings.get("G"):
            m, sd = ratio(readings["G"], readings["E2"])
            r.log["ratio_G_over_E"] = {"mean": m, "sd": sd}
            print(f"    paper ratio G/E2 = {m:.4f} +/- {sd:.4f}   "
                  "(what a KNOWN gated press does -- compare with E/B)")

    r.log["readings"] = {k: v for k, v in readings.items()}
    out = OUT / "EXP-BLE-015-press-magnet.json"
    out.write_text(json.dumps(r.log, indent=1))
    print(f"\nwrote {out}")
    print("\nSend the console output and the JSON back for analysis.")


if __name__ == "__main__":
    asyncio.run(main())
