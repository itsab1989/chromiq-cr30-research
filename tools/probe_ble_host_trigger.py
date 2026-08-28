#!/usr/bin/env python3
"""EXP-BLE-012 -- does a HOST TRIGGER exist over Bluetooth?

TRANSPORT_BLE.md:282 says "No BLE host trigger is known". That is an honest
statement about the vendor capture, which contains no trigger -- but it was
never TESTED. The device owner asked for it to be tested, and he is right to:
"not seen in a 30 s vendor session" is not "does not exist".

There is a specific reason to doubt the negative. `bb 01 00` is the USB TRIGGER
(src/cr30/usb_measure.py). The same frame already exists in the BLE command set
under the name STATUS (src/cr30/ble.py:56) and is already SENT over BLE, both
during discovery (ble.py:100) and by identify() (device.py:98). So the trigger
command is not merely plausible over BLE -- we may already be sending it and
calling it something else.

## SAFETY -- read this before running

Run this with **NO CAP AND NO MAGNET ANYWHERE NEAR THE APERTURE.**

With a magnet present, a trigger does not measure: it performs a WHITE
CALIBRATION against whatever is under the aperture, and that is what corrupted
this unit's white reference during EXP-MEAS-003. With no magnet, the very worst
a trigger can do is take an ordinary reading of the surface it is sitting on.
That is why this experiment is safe, and it is only safe under that condition.

This script sends `bb 01 00` and `bb 02 10`. It sends nothing else, and in
particular it never sends `bb 10` or `bb 11` (the vendor's dedicated black and
white calibration commands), which have never been sent to this unit.

## The method, and why it has a control

A 10-byte reply is NOT evidence: this device echoes commands it does not
implement, so "it answered" proves nothing. The only proof is the STORED
READING CHANGING to match a surface the device has not been asked to read.

  1. read the stored measurement                     -> M0
  2. operator moves the instrument to a CLEARLY different surface,
     and does NOT press its button
  3. send the candidate trigger, wait, read stored    -> M1
  4. operator presses the instrument's own button, read stored -> M2

  M1 != M0  =>  the host trigger WORKS over BLE.
  M1 == M0 AND M2 != M0  =>  it genuinely does not, and the probe is PROVEN
                             working by the control -- without step 4 a null
                             result could just mean a broken probe.
  M1 == M0 AND M2 == M0  =>  the probe or the surface is at fault. INCONCLUSIVE:
                             report nothing.
"""
import asyncio
import datetime
import json
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from bleak import BleakClient, BleakScanner    # noqa: E402
except ModuleNotFoundError:                        # a bare `python3` misses it
    sys.exit("bleak is not installed for this interpreter.\n"
             "Run the probe with the repo's own venv:\n\n"
             "  ./.venv/bin/python tools/probe_ble_host_trigger.py\n")

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])
HDR = bytes([0xBB, 0x02, 0x10, 0x00])
SPECTRUM_AT, MIN_REPLY = 8, 196


def frame10(cmd, sub=0, param=0):
    d = bytearray(10)
    d[0], d[1], d[2], d[3] = 0xBB, cmd, sub, param
    d[8] = 0xFF
    d[9] = sum(d[:9]) % 256
    return bytes(d)


READ_MEASUREMENT = frame10(0x02, 0x10)
CANDIDATES = [("bb 01 00  (the USB trigger; BLE calls it STATUS)", frame10(0x01, 0x00))]


class Link:
    def __init__(self, client):
        self.c, self.buf = client, bytearray()

    async def start(self):
        await self.c.start_notify(FFE1, lambda _s, d: self.buf.extend(bytes(d)))

    async def ask(self, req, polls=10, wait=0.35):
        self.buf.clear()
        await self.c.write_gatt_char(FFE1, req, response=False)
        await asyncio.sleep(wait)
        quiet = 0
        for _ in range(polls):
            n = len(self.buf)
            await self.c.write_gatt_char(FFE1, POLL, response=False)
            await asyncio.sleep(wait)
            quiet = quiet + 1 if len(self.buf) == n else 0
            if quiet >= 3 and self.buf:
                break
        return bytes(self.buf)


def spectrum(raw):
    """Last valid measurement in the buffer, as 31 percent-reflectance floats."""
    offs, k = [], raw.find(HDR)
    while k >= 0:
        offs.append(k)
        k = raw.find(HDR, k + 1)
    for i in reversed(offs):
        if len(raw) - i < MIN_REPLY:
            continue
        bands = raw[i + 7]
        if bands != 31:
            continue
        return list(struct.unpack_from("<31f", raw, i + SPECTRUM_AT))
    return None


def summarise(v):
    return None if v is None else round(sum(v) / len(v), 4)


def differs(a, b):
    if a is None or b is None:
        return None
    return max(abs(x - y) for x, y in zip(a, b))


async def main():
    print(__doc__)
    print("=" * 72)
    print("SAFETY CHECK: there must be NO CAP and NO MAGNET near the aperture.")
    if input("Type 'no magnet' to continue: ").strip().lower() != "no magnet":
        print("Aborted."); return

    print("\nScanning for the CR30 over Bluetooth …")
    dev = None
    for d, adv in (await BleakScanner.discover(timeout=8.0, return_adv=True)).values():
        if FFE0 in [u.lower() for u in (adv.service_uuids or [])]:
            dev = d
            break
    if dev is None:
        print("No CR30 found. Is the vendor app connected to it? Disconnect it.")
        return
    print(f"Found {dev.address}")

    out = {"experiment": "EXP-BLE-012",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "steps": []}

    async with BleakClient(dev.address, timeout=20.0) as c:
        link = Link(c)
        await link.start()

        print("\nSTEP 1 — reading what the device currently holds …")
        m0 = spectrum(await link.ask(READ_MEASUREMENT))
        if m0 is None:
            print("Could not read a measurement at all. Stopping — a null "
                  "result now would prove nothing.")
            return
        print(f"  M0 mean reflectance: {summarise(m0)} %")
        out["steps"].append({"step": "M0", "mean": summarise(m0), "values": m0})

        print("\nSTEP 2 — put the instrument on a CLEARLY DIFFERENT surface")
        print("         (a strong colour, or white paper if it was on colour).")
        print("         Do NOT press its button. Do NOT put the cap on.")
        input("         Press Return when it is in place: ")

        for name, req in CANDIDATES:
            print(f"\nSTEP 3 — sending {name}")
            await link.ask(req, polls=6)
            await asyncio.sleep(1.0)
            m1 = spectrum(await link.ask(READ_MEASUREMENT))
            d = differs(m0, m1)
            print(f"  M1 mean reflectance: {summarise(m1)} %   "
                  f"max band change vs M0: {d}")
            out["steps"].append({"step": "M1", "command": name,
                                 "mean": summarise(m1), "max_change": d,
                                 "values": m1})

        print("\nSTEP 4 — the control. Press the instrument's OWN button now,")
        print("         on the SAME surface, without moving it.")
        input("         Press Return once you have pressed it: ")
        m2 = spectrum(await link.ask(READ_MEASUREMENT))
        d2 = differs(m0, m2)
        print(f"  M2 mean reflectance: {summarise(m2)} %   "
              f"max band change vs M0: {d2}")
        out["steps"].append({"step": "M2", "mean": summarise(m2),
                            "max_change": d2, "values": m2})

    changed_by_host = (differs(m0, out["steps"][1]["values"]) or 0) > 0.5
    changed_by_button = (d2 or 0) > 0.5
    if changed_by_host:
        verdict = ("HOST TRIGGER WORKS OVER BLE — the stored reading changed "
                   "with no button press.")
    elif changed_by_button:
        verdict = ("NO HOST TRIGGER OVER BLE — the command did nothing, and "
                   "the control proves the probe and the surface were fine.")
    else:
        verdict = ("INCONCLUSIVE — even the button press did not change the "
                   "reading. The probe or the surface is at fault; this says "
                   "NOTHING about the trigger.")
    out["verdict"] = verdict
    print("\n" + "=" * 72 + f"\n{verdict}\n" + "=" * 72)

    dest = ROOT / "captures" / "raw" / "EXP-BLE-012-host-trigger.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    asyncio.run(main())
