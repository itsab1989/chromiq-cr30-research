#!/usr/bin/env python3
"""EXP-BLE-017 -- is a 0.7 % difference normal for this setup?

EXP-BLE-015 read the same paper before and after two white calibrations:
88.3327 %R then 87.6836 %R, a ratio of 0.9927. That is 0.73 % darker, and it
was flagged because it is far larger than this instrument's published
repeatability (0.056 % worst-band SD, CALIBRATION.md).

Two explanations, and they have opposite consequences:

  * HANDLING. The cap went on and came off between the two readings, so the
    instrument was lifted and replaced. The owner also notes the paper was thin
    with objects underneath it -- and thin paper is partly transparent, so what
    lies beneath it becomes part of the measurement. Move the sheet a
    millimetre and the backing changes.
  * A REAL SHIFT from the calibrations. That would mean every reading afterwards
    is scaled, invisibly, and a chart measured now would be wrong in a way no
    later check could see.

This tells them apart WITHOUT touching the calibration, by measuring how much
this setup varies on its own.

  Phase A  five readings, NOTHING MOVED between them
           -> the instrument's own repeatability, here, today.
  Phase B  five readings, LIFTING AND REPLACING the instrument each time
           -> what handling alone costs on this paper and this backing.

If phase B's spread covers 0.73 %, handling and paper explain it and there is
nothing to chase. If phase B is tight and phase A is tighter still, 0.73 % is
not ordinary variation and the calibration is worth re-examining before any real
chart is measured.

Sends the instrument NOTHING except a read of what it already holds. No trigger,
no calibration command. Cap OFF throughout.
"""
import asyncio
import datetime
import json
import pathlib
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError:
    sys.exit("  ./.venv/bin/python tools/probe_repeatability.py\n")

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
            continue
        return v
    return None


def mean(v):
    return sum(v) / len(v)


def spread(ms):
    """Peak-to-peak as a percentage of the mean — the number that is directly
    comparable with the 0.73 % we are trying to explain."""
    if len(ms) < 2:
        return 0.0
    return 100.0 * (max(ms) - min(ms)) / (sum(ms) / len(ms))


class Link:
    def __init__(self, c):
        self.c, self.buf, self.pushes = c, bytearray(), 0

    def on_notify(self, _s, data):
        b = bytes(data)
        if len(b) == 10 and b[:2] == bytes([0xBB, 0x01]):
            self.pushes += 1
            return
        self.buf.extend(b)

    async def read(self, tries=4):
        for _ in range(tries):
            self.buf.clear()
            await self.c.write_gatt_char(FFE1, READ, response=False)
            await asyncio.sleep(0.35)
            for _ in range(10):
                n = len(self.buf)
                await self.c.write_gatt_char(FFE1, POLL, response=False)
                await asyncio.sleep(0.35)
                if len(self.buf) == n and self.buf:
                    break
            v = spectrum(bytes(self.buf))
            if v is not None:
                return v
            await asyncio.sleep(0.8)
        return None

    async def wait_press(self, timeout=180.0):
        n, deadline = self.pushes, time.monotonic() + timeout
        print("      waiting for the press …", end="", flush=True)
        while self.pushes == n:
            if time.monotonic() > deadline:
                print("  nothing.")
                return False
            await asyncio.sleep(0.1)
        print("  got it.")
        await asyncio.sleep(0.8)
        return True


async def run_phase(link, name, instruction, n=5):
    print(f"\n=== PHASE {name} — {instruction}")
    means, values = [], []
    for i in range(1, n + 1):
        print(f"\n  reading {i} of {n}")
        if not await link.wait_press():
            print("  giving up on this phase.")
            break
        v = await link.read()
        if v is None:
            print("    could not read it back; skipping this one")
            continue
        means.append(mean(v))
        values.append(v)
        print(f"    mean {mean(v):8.4f} %R")
    if means:
        print(f"\n  PHASE {name}: {len(means)} readings, "
              f"mean {sum(means)/len(means):8.4f} %R, "
              f"spread {spread(means):.3f} %")
    return means, values


async def main():
    print(__doc__)
    print("=" * 72)
    print("ChromIQ must be CLOSED. Cap OFF. Put the instrument on the SAME")
    print("paper and the SAME spot you used before, if you still can.")
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

    async with BleakClient(dev.address, timeout=20.0) as c:
        link = Link(c)
        await c.start_notify(FFE1, link.on_notify)
        a_means, _ = await run_phase(
            link, "A", "press five times, and DO NOT MOVE ANYTHING at all")
        print("\n" + "-" * 72)
        b_means, _ = await run_phase(
            link, "B", "press five times, LIFTING the instrument clear and\n"
                       "          setting it back down on the same spot each time")

    print("\n" + "=" * 72)
    observed = 0.73
    if len(a_means) < 2 or len(b_means) < 2:
        verdict = ("NOT ENOUGH READINGS — too few came back to say anything. "
                   "Nothing here should be believed.")
    elif spread(b_means) >= observed:
        verdict = (f"HANDLING AND PAPER EXPLAIN IT. Simply lifting and "
                   f"replacing the instrument moves the reading by "
                   f"{spread(b_means):.2f} %, which covers the {observed} % seen "
                   f"across the calibrations. There is nothing to chase.")
    elif spread(a_means) >= observed:
        verdict = (f"THE SETUP ITSELF IS UNSTABLE — even untouched, readings "
                   f"vary by {spread(a_means):.2f} %. The {observed} % says "
                   f"nothing about the calibration, but this paper is not a "
                   f"surface to judge anything by.")
    else:
        verdict = (f"NOT EXPLAINED BY HANDLING — untouched varies "
                   f"{spread(a_means):.2f} %, lifting varies "
                   f"{spread(b_means):.2f} %, and neither reaches {observed} %. "
                   f"The shift across the calibrations looks real; do not "
                   f"measure a chart for real until it is understood.")
    print(verdict + "\n" + "=" * 72)

    out = {"experiment": "EXP-BLE-017",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "observed_pct_to_explain": observed,
           "phase_a_means": a_means, "phase_a_spread_pct": spread(a_means),
           "phase_b_means": b_means, "phase_b_spread_pct": spread(b_means),
           "verdict": verdict}
    dest = ROOT / "captures" / "raw" / "EXP-BLE-017-repeatability.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {dest}")


if __name__ == "__main__":
    asyncio.run(main())
