#!/usr/bin/env python3
"""EXP-BLE-007 -- talk to the device WHILE its Bluetooth indicator is lit.

WHY. The operator reports the display's Bluetooth indicator was lit just after
USB was unplugged and went out about ten seconds later -- and was already out
during EXP-BLE-002/003/006. Those runs therefore tested a device whose
application-level Bluetooth was ASLEEP. Accepted writes and zero notifications
say nothing about framing under that condition.

The vendor iOS app connects with no special procedure, so the device's BLE
works. What is unknown is what brings it up.

This probe runs a long loop, re-sending the identity query every 2 s and
printing any notification the instant it arrives, so the operator can try things
on the device and watch for the moment it starts answering.

Writes only AA 0A 00 00 -- read-only on the device, no side effects.
"""
import asyncio, sys, json, pathlib, datetime, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient, BleakScanner
from cr30.frame import Frame, checksum

U = {n: f"0000{n}-0000-1000-8000-00805f9b34fb" for n in ("ffe1", "ffe2", "ffe3")}
PKT = Frame.build(0xAA, 0x0A, 0x00, 0).to_bytes()
SECONDS = 90


async def main():
    print(__doc__.split("Writes only")[0])
    print("=" * 72)
    print("  While this runs, on the DEVICE:")
    print("   - press the measure button every few seconds to keep it awake")
    print("   - try anything you think might switch Bluetooth on")
    print("   - watch the Bluetooth indicator and note WHEN it lights")
    print("  Any reply appears here instantly as '<<<'.  Ctrl-C to stop early.")
    print("=" * 72)
    input("\n  press Enter to begin > ")

    dev = await BleakScanner.find_device_by_name("CM454M0223", timeout=15.0)
    if dev is None:
        sys.exit("device is not advertising at all -- wake it and re-run")
    log = {"experiment": "EXP-BLE-007",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "events": [], "writes": 0}
    hits = []

    def cb(who):
        def f(_, d):
            b = bytes(d); t = round(time.time() - T0, 2)
            ok = len(b) == 60 and b[59] == checksum(b)
            hits.append((t, who, b))
            log["events"].append({"t": t, "char": who, "len": len(b), "hex": b.hex(),
                                  "valid_cr30_frame": ok})
            print(f"\n  <<< t={t:5.1f}s  {who}  {len(b)}B  {b[:12].hex(' ')}"
                  + ("   *** VALID CR30 FRAME ***" if ok else ""))
        return f

    async with BleakClient(dev, timeout=20.0) as c:
        print(f"\nconnected: {c.is_connected}  mtu {c.mtu_size}")
        for n, u in U.items():
            try: await c.start_notify(u, cb(n))
            except Exception: pass
        T0 = time.time()
        while time.time() - T0 < SECONDS:
            try:
                await c.write_gatt_char(U["ffe1"], PKT, response=False)
                log["writes"] += 1
            except Exception as e:
                print(f"  write failed: {type(e).__name__}")
                break
            el = int(time.time() - T0)
            print(f"\r  listening... {el:3d}/{SECONDS}s   "
                  f"writes {log['writes']}   replies {len(hits)}", end="", flush=True)
            await asyncio.sleep(2.0)
        for u in U.values():
            try: await c.stop_notify(u)
            except Exception: pass

    print()
    log["verdict"] = (f"ANSWERED -- {len(hits)} notification(s); BLE works once the "
                      "device is in the right state"
                      if hits else
                      "silent for the whole window despite continuous polling")
    print("\n VERDICT:", log["verdict"])
    ind = input("\n  Did the Bluetooth indicator light at ANY point? [y/n] > ").strip().lower()
    log["indicator_lit_at_any_point"] = ind.startswith("y")
    if ind.startswith("y"):
        log["what_lit_it"] = input("  What made it light? (free text) > ").strip()
    p = ROOT / "captures/raw/EXP-BLE-007-keepalive.json"
    p.write_text(json.dumps(log, indent=2)); print(f"\nwrote {p}")

try: asyncio.run(main())
except KeyboardInterrupt: print("\ninterrupted")
