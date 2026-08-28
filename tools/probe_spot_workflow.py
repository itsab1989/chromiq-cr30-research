#!/usr/bin/env python3
"""EXP-MEAS-005 -- the real ChromIQ spot workflow, over Bluetooth.

This is the workflow ChromIQ issue #159 section 3 describes: place the
instrument, press ITS OWN button, the host picks the reading up. No cable, no
keyboard. It now works, so this both DEMONSTRATES it and measures four things
at once:

  1. POSITIONING ERROR -- repeat readings of one patch, lifting between each.
     Sets the minimum patch size for a CR30 chart (aperture is 4 mm; the patch
     must exceed it by the positioning spread). Chart layout is blocked on this.
  2. A RANK CORPUS -- varied patches for EXP-SPEC-001, are the 31 bands
     independent or reconstructed?
  3. bb 14 SEMANTICS -- the one command class the vendor app used that we cannot
     explain. It carries a 4-byte field resembling a timestamp. If it advances
     with each new measurement it is how a backend tells a fresh reading from a
     stale one.
  4. NEW-READING DETECTION -- we read the STORED measurement, so a backend must
     know when a new one has arrived.

     WARNING, and it is a real design problem: "the reading did not change" is
     ALSO the magnet-gated signature (MEASUREMENT.md). Polling for change alone
     cannot distinguish "user has not measured yet" from "device is gated". If
     bb 14 carries a counter, that is the way out.

Read-only: bb 02 10 and bb 14 only. No calibration command, no trigger.
"""
import asyncio, sys, json, pathlib, datetime, struct, statistics, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient, BleakScanner
from cr30.colour import spectrum_to_lab, D65, use_observer

FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])


async def prompt(text):
    """input() BLOCKS the asyncio event loop, which stalls CoreBluetooth's
    delegate and drops the BLE link. Every prompt issued while connected must
    go through a thread. This cost one run."""
    return await asyncio.get_running_loop().run_in_executor(None, input, text)


def f10(cmd, sub=0, param=0, data=b""):
    d = bytearray(10); d[0], d[1], d[2], d[3] = 0xBB, cmd, sub, param
    d[4:4 + len(data)] = data; d[8] = 0xFF; d[9] = sum(d[:9]) % 256
    return bytes(d)


READ = f10(0x02, 0x10)
BB14 = {s: f10(0x14, s) for s in (0x00, 0x08, 0x09)}


HDR = bytes([0xBB, 0x02, 0x10, 0x00])          # reply header to resync on


class Link:
    def __init__(self, client): self.c = client; self.buf = bytearray()

    def cb(self, _, data): self.buf.extend(bytes(data))

    async def drain(self, wait=0.4):
        """Flush stragglers BEFORE a command.

        Notifications from the previous exchange keep arriving after we stop
        polling. Left in place they prefix the next reply, shifting every
        offset -- which produced fifteen garbage readings in the first run.
        """
        for _ in range(3):
            self.buf.clear()
            await asyncio.sleep(wait)
            if not self.buf:
                break
        self.buf.clear()

    async def ask(self, frame, polls=10, wait=0.35):
        await self.drain()
        await self.c.write_gatt_char(FFE1, frame, response=False)
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

    async def measurement(self):
        """Decode a stored measurement, or return a REASON it is not one.

        Never returns a half-parsed reading (ERRORS.md): it resyncs on the reply
        header rather than trusting offset 0, then bounds-checks every value.
        """
        b = await self.ask(READ)
        i = b.find(HDR)
        if i < 0:
            return None, b, f"reply header bb 02 10 00 not found in {len(b)} bytes"
        if len(b) - i < 196:
            return None, b, f"only {len(b)-i} bytes after header, need 196"
        spec = list(struct.unpack_from("<31f", b, i + 8))
        lab = list(struct.unpack_from("<3f", b, i + 184))
        import math
        if not all(math.isfinite(x) for x in spec + lab):
            return None, b, "non-finite value in spectrum or Lab"
        if not all(-1.0 <= x <= 200.0 for x in spec):
            return None, b, (f"reflectance out of physical range "
                             f"[{min(spec):.3g} .. {max(spec):.3g}] %")
        if not (0.0 <= lab[0] <= 100.0):
            return None, b, f"L* out of range: {lab[0]:.3g}"
        return ({"spectrum": [round(x, 6) for x in spec],
                 "lab_device": [round(x, 4) for x in lab],
                 "header_at": i, "raw_len": len(b)}, b, None)


SAVE = ROOT / "captures/raw/EXP-MEAS-005-spot-workflow.json"


def _save(log):
    SAVE.write_text(json.dumps(log, indent=2))


async def run(link, log, label, note):
    print(f"\n  reading ({label}) ...")
    for attempt in range(3):
        m, raw, why = await link.measurement()
        if m is not None:
            break
        print(f"    !! not a valid reading: {why}   (attempt {attempt+1}/3)")
    if m is None:
        print("    SKIPPED -- nothing recorded for this step, by design.")
        log.setdefault("rejected", []).append(
            {"label": label, "reason": why, "raw": raw.hex()})
        _save(log)
        return None
    s = m["spectrum"]; L = m["lab_device"]
    print(f"    mean {statistics.fmean(s):6.2f}%   device Lab "
          f"L*{L[0]:7.3f} a*{L[1]:+7.3f} b*{L[2]:+7.3f}")
    probes = {}
    for sub, fr in BB14.items():
        r = await link.ask(fr, polls=3)
        probes[f"bb14_{sub:02X}"] = r.hex()
    m.update({"label": label, "note": note, "bb14": probes,
              "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    log["readings"].append(m)
    _save(log)                      # incremental: a later crash costs nothing
    return m


async def main():
    print(__doc__)
    print("The phone app must be DISCONNECTED.\n")
    dev = await BleakScanner.find_device_by_name("CM454M0223", timeout=20.0)
    if dev is None: sys.exit("not advertising -- disconnect the app / wake the device")
    log = {"experiment": "EXP-MEAS-005", "transport": "BLE",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "readings": []}
    async with BleakClient(dev, timeout=20.0) as c:
        link = Link(c)
        await c.start_notify(FFE1, link.cb)
        print(f"connected  mtu {c.mtu_size}")

        await prompt("\n  Cap OFF. Ready? press Enter > ")
        await run(link, log, "baseline (whatever is stored)", "before any new reading")

        print("\n" + "=" * 72)
        print("  PART 1 -- positioning error. Same patch, LIFT between every read.")
        print("  This sets the minimum patch size for a CR30 chart.")
        print("=" * 72)
        for i in range(6):
            await prompt(f"\n  [{i+1}/6] LIFT the device, put it back on the SAME "
                         f"patch,\n        press its BUTTON, then press Enter > ")
            await run(link, log, f"positioning {i+1}/6", "lifted and replaced")

        print("\n" + "=" * 72)
        print("  PART 2 -- varied patches, for the spectral-rank question.")
        print("=" * 72)
        for i in range(8):
            await prompt(f"\n  [{i+1}/8] Place on a DIFFERENT patch (as varied as you\n"
                         f"        can: saturated primaries, a dark one, a pastel,\n"
                         f"        paper white), press its BUTTON, then Enter > ")
            await run(link, log, f"rank corpus {i+1}/8", "varied patch")
        try: await c.stop_notify(FFE1)
        except Exception: pass

    # ---- analysis --------------------------------------------------------
    if log.get("rejected"):
        print(f"\n  {len(log['rejected'])} reading(s) REJECTED as malformed -- "
              "recorded in the capture, not counted as data.")
    pos = [r for r in log["readings"] if r["label"].startswith("positioning")]
    if len(pos) > 1:
        use_observer("10")
        labs = [spectrum_to_lab(r["spectrum"], D65) for r in pos]
        mean = [statistics.fmean(x[i] for x in labs) for i in range(3)]
        des = [sum((x[i] - mean[i]) ** 2 for i in range(3)) ** 0.5 for x in labs]
        bands = [statistics.pstdev([r["spectrum"][i] for r in pos])
                 for i in range(31)]   # safe: every reading was bounds-checked
        log["positioning_mean_dE_from_centroid"] = round(statistics.fmean(des), 4)
        log["positioning_max_dE"] = round(max(des), 4)
        log["positioning_worst_band_sd"] = round(max(bands), 4)
        print(f"\n  POSITIONING ERROR over {len(pos)} lift-and-replace reads:")
        print(f"    mean dE from centroid {statistics.fmean(des):.3f}, "
              f"worst {max(des):.3f}")
        print(f"    worst-band SD {max(bands):.4f} %R")
        print(f"    (no-lift repeatability was 0.056 %R -- the difference is"
              f" positioning)")
    uniq = {tuple(r["spectrum"]) for r in log["readings"]}
    log["distinct_spectra"] = len(uniq)
    print(f"\n  {len(uniq)} distinct spectra out of {len(log['readings'])} readings")
    # did bb 14 move?
    keys = sorted({k for r in log["readings"] for k in r.get("bb14", {})})
    for k in keys:
        vals = [r["bb14"].get(k) for r in log["readings"] if r.get("bb14")]
        print(f"  {k}: {len(set(vals))} distinct value(s) across "
              f"{len(vals)} readings" + ("   <-- ADVANCES, candidate counter"
                                         if len(set(vals)) > 1 else ""))
    _save(log); print(f"\nwrote {SAVE}")

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\ninterrupted")
except Exception as e:
    import traceback
    print(f"\n!! {type(e).__name__}: {e}")
    traceback.print_exc()
    print("\nPaste the lines above to me -- partial data was still saved if any"
          " readings completed.")
