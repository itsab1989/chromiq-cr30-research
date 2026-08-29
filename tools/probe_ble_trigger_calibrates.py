#!/usr/bin/env python3
"""EXP-BLE-015 -- does the BLE HOST TRIGGER calibrate when a magnet is present?

The open question behind the owner's report that ChromIQ's Calibrate button
produces no beep, and that he has to press the instrument's own button by hand.

What is already established:
  * EXP-BLE-012 -- the host trigger `bb 01 00` takes a MEASUREMENT over BLE with
    NO magnet present. Never tested WITH one.
  * EXP-MEAS-003 -- a measurement taken with a magnet at the aperture is not a
    measurement: the device performs a white calibration against whatever is
    under the cap and returns the firmware's nominal tile constant as its
    "reading".
  * EXP-BLE-014 -- the magnet ALONE does nothing; some action must be triggered.

So if the host trigger reaches the gated path, the reading it leaves behind will
be the tile constant. If it does not, the reading will be something else. That is
the whole experiment, and it needs no risky surface.

## How this is SAFE

The cap goes on **WHITE TILE toward the opening**, and only ever that way. If a
calibration does happen it happens against the instrument's correct reference
surface -- which is what calibration is supposed to do. It cannot corrupt
anything. **Never the green face.**

Steps 1 and 6 read the SAME piece of paper before and after, so any accidental
shift is measured rather than assumed. If the ratio moves, you will see it here
rather than discover it in a chart three weeks from now.

Only `bb 01 00` (trigger) and `bb 02 10` (read stored) are ever sent. Never
`bb 10` or `bb 11` -- the vendor calibration commands, which have never been
sent to this unit.

## The positive control, and why the result is worthless without it

Step 5 is a BUTTON PRESS with the cap on. EXP-MEAS-003 established that this
engages the gate, so it MUST come back as the tile constant. If it does not, the
gate is not engaging today at all, and step 4 proves nothing about the trigger --
a null result there would be the probe failing, not a fact about the device.
"""
import asyncio
import datetime
import json
import pathlib
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError:
    sys.exit("  ./.venv/bin/python tools/probe_ble_trigger_calibrates.py\n")

from cr30.measurement import TILE_SIGNATURE          # noqa: E402

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])
HDR = bytes([0xBB, 0x02, 0x10, 0x00])
SPECTRUM_AT, MIN_REPLY = 8, 196


def frame10(cmd, sub=0):
    d = bytearray(10)
    d[0], d[1], d[2] = 0xBB, cmd, sub
    d[8] = 0xFF
    d[9] = sum(d[:9]) % 256
    return bytes(d)


TRIGGER = frame10(0x01, 0x00)
READ = frame10(0x02, 0x10)


def spectrum(raw):
    offs, k = [], raw.find(HDR)
    while k >= 0:
        offs.append(k)
        k = raw.find(HDR, k + 1)
    for i in reversed(offs):
        if len(raw) - i < MIN_REPLY or raw[i + 7] != 31:
            continue
        v = list(struct.unpack_from("<31f", raw, i + SPECTRUM_AT))
        if sum(1 for x in v if x == 0.0) > 4:
            continue                       # the truncated, zero-filled form
        return v
    return None


def mean(v):
    return sum(v) / len(v)


def maxdiff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def is_tile(v):
    """The canned constant, to the tolerance the corpus uses."""
    return v is not None and maxdiff(v, TILE_SIGNATURE) < 0.5


class Link:
    def __init__(self, c):
        self.c, self.buf, self.pushes = c, bytearray(), []
        self.t0 = time.monotonic()

    def on_notify(self, _s, data):
        b = bytes(data)
        self.buf.extend(b)
        if len(b) == 10 and b[:3] == bytes([0xBB, 0x01, 0x00]):
            self.pushes.append(round(time.monotonic() - self.t0, 2))
            print(f"      ← the instrument announced a press/action "
                  f"at {self.pushes[-1]} s")

    async def ask(self, req, polls=12, wait=0.35):
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

    async def read_spectrum(self, tries=3):
        for _ in range(tries):
            v = spectrum(await self.ask(READ))
            if v is not None:
                return v
            await asyncio.sleep(1.0)       # it was still busy; give it a moment
        return None


async def confirm(msg):
    """A step the operator performs by hand. WAIT for them, never a timer.

    The first version of this probe used countdowns, and it marched past steps
    the operator had not finished and then reported what it found as a fact.
    A probe that does not wait is not measuring the thing it claims to measure.
    `to_thread` keeps the prompt off the event loop, so notifications keep
    arriving while it waits — the bug that spoiled EXP-BLE-013.
    """
    print(f"\n--- {msg}")
    await asyncio.to_thread(input, "      …then press Return here: ")


async def wait_for_press(link, msg, timeout=180.0):
    """Wait for the instrument to ANNOUNCE a press, not for a clock to run out.

    EXP-BLE-013 established that a press pushes an unsolicited 10-byte frame.
    So the probe can wait for the real thing: the operator takes as long as
    they like, and a step can no longer be recorded as done when it was not.
    """
    print(f"\n--- {msg}")
    n = len(link.pushes)
    deadline = time.monotonic() + timeout
    print("      waiting for the instrument …", end="", flush=True)
    while len(link.pushes) == n:
        if time.monotonic() > deadline:
            print("  no press seen.")
            return False
        await asyncio.sleep(0.1)
    print("  got it.")
    await asyncio.sleep(1.5)          # let the reading settle before reading it
    return True


async def main():
    print(__doc__)
    print("=" * 72)
    print("ChromIQ must be CLOSED. Start with the cap OFF and the instrument")
    print("flat on a piece of plain paper — and DO NOT MOVE IT until step 6.")
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
    print(f"Found {dev.address}")

    out = {"experiment": "EXP-BLE-015",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "tile_mean": round(mean(TILE_SIGNATURE), 4), "steps": {}}

    async with BleakClient(dev.address, timeout=20.0) as c:
        link = Link(c)
        await c.start_notify(FFE1, link.on_notify)

        if not await wait_for_press(
                link, "STEP 1 — PRESS THE BUTTON ONCE on the paper."):
            print("  No press was seen, so there is no baseline. Stopping.")
            return
        p0 = await link.read_spectrum()
        if p0 is None:
            print("  Could not read the paper at all. Stopping — nothing after "
                  "this would mean anything.")
            return
        print(f"  paper before : mean {mean(p0):8.4f} %R")
        out["steps"]["paper_before"] = {"mean": round(mean(p0), 4), "values": p0}

        await confirm("STEP 2 — SEAT THE CAP NOW, white tile toward the "
                      "opening.\n      Press nothing on the instrument.")

        print("\n--- STEP 3 — sending the host trigger: exactly what ChromIQ's"
       "\n    Calibrate button does. Watch the lights and listen for a beep.")
        pushes_before = len(link.pushes)
        await link.ask(TRIGGER, polls=6)
        await asyncio.sleep(2.0)           # let it finish before reading back
        m_trig = await link.read_spectrum()
        announced = len(link.pushes) > pushes_before
        print(f"  after trigger: mean {mean(m_trig):8.4f} %R" if m_trig
              else "  after trigger: NO READABLE REPLY")
        print(f"  is that the tile constant? {is_tile(m_trig)}")
        print(f"  did the instrument announce anything? {announced}")
        out["steps"]["after_trigger"] = {
            "mean": round(mean(m_trig), 4) if m_trig else None,
            "is_tile": is_tile(m_trig), "announced": announced,
            "values": m_trig}

        if not await wait_for_press(
                link, "STEP 4 — the POSITIVE CONTROL. Cap STILL ON.\n"
                      "         PRESS THE INSTRUMENT'S BUTTON ONCE."):
            print("  No press was seen, so the control failed. Stopping — "
                  "step 3 would prove nothing without it.")
            return
        m_press = await link.read_spectrum()
        print(f"  after press  : mean {mean(m_press):8.4f} %R" if m_press
              else "  after press  : NO READABLE REPLY")
        print(f"  is that the tile constant? {is_tile(m_press)}")
        out["steps"]["after_press"] = {
            "mean": round(mean(m_press), 4) if m_press else None,
            "is_tile": is_tile(m_press), "values": m_press}

        await confirm("STEP 5 — TAKE THE CAP OFF.")

        if not await wait_for_press(
                link, "STEP 6 — PRESS THE BUTTON ONCE on the SAME paper,\n"
                      "         the same spot as step 1."):
            print("  No press was seen; the before/after comparison is void.")
        p1 = await link.read_spectrum()
        print(f"  paper after  : mean {mean(p1):8.4f} %R" if p1
              else "  paper after  : NO READABLE REPLY")
        out["steps"]["paper_after"] = {
            "mean": round(mean(p1), 4) if p1 else None, "values": p1}

    print("\n" + "=" * 72)
    if not is_tile(m_press):
        verdict = ("PROBE NOT PROVEN — a button press WITH the cap on did not "
                   "return the tile constant, so the magnet gate is not "
                   "engaging today. Step 3 therefore says NOTHING about the "
                   "trigger. Do not read anything into it.")
    elif is_tile(m_trig):
        verdict = ("THE HOST TRIGGER DOES CALIBRATE OVER BLUETOOTH — it "
                   "returned the tile constant with a magnet present, exactly "
                   "as the button press did. ChromIQ's Calibrate button works; "
                   "the missing beep is a separate matter.")
    else:
        verdict = ("THE HOST TRIGGER DOES **NOT** CALIBRATE OVER BLUETOOTH — "
                   "the button press engaged the gate and the trigger did not. "
                   "ChromIQ's Calibrate button cannot do the job on this "
                   "transport and must say so, or ask for a press.")
    print(verdict)
    if p0 and p1:
        r = mean(p1) / mean(p0)
        print(f"\nSame paper before and after: {mean(p0):.4f} -> {mean(p1):.4f} "
              f"%R, ratio {r:.4f}, max band change {maxdiff(p0, p1):.4f}")
        print("  ratio near 1.000 = nothing was disturbed." if abs(r - 1) < 0.02
              else "  ⚠ THE READING SHIFTED — tell Claude before measuring "
                   "anything for real.")
        out["paper_ratio"] = round(r, 4)
    print("=" * 72)
    out["verdict"] = verdict
    out["pushes"] = link.pushes
    dest = ROOT / "captures" / "raw" / "EXP-BLE-015-trigger-calibrates.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    asyncio.run(main())
