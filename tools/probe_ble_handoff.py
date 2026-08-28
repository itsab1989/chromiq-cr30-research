#!/usr/bin/env python3
"""EXP-BLE-008 -- get in during the window the vendor app leaves open.

OBSERVATIONS THIS IS BUILT ON
  * The app connects and the Bluetooth indicator lights ~1 s LATER, so the app
    sends something on connect and the device activates in response.
  * The indicator stayed lit ~10 s after USB was unplugged, so activation
    persists briefly rather than ending instantly.
  * Our own GATT connections never light it, and are never answered.
  * The device STOPS ADVERTISING while the app holds it -- one connection only.
    So it must be resolved before the app takes it (this cost one run).

IF activation persists for a few seconds after the app lets go, then connecting
in that window should find a device that is awake and willing to talk. That
distinguishes "we cannot activate it" from "we cannot talk to it at all" --
two very different problems.

The device is resolved BEFORE the prompt so the connection happens with minimum
delay after the operator lets the app go.

Writes only AA 0A ss 00 -- read-only, no side effects.
"""
import asyncio, sys, json, pathlib, datetime, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient, BleakScanner
from cr30.frame import Frame, checksum

U = {n: f"0000{n}-0000-1000-8000-00805f9b34fb" for n in ("ffe1", "ffe2", "ffe3")}
WINDOW = 40


async def main():
    print("EXP-BLE-008 -- catching the device while it is still activated\n")
    print("  The CR30 STOPS ADVERTISING while the phone app is connected: it is a")
    print("  single-connection peripheral. So it must be resolved BEFORE the app")
    print("  takes it, and the handle reused afterwards.\n")

    print("  Step 1: make sure the app is NOT connected (close it, or turn the")
    print("          phone's Bluetooth off).")
    input("\n  press Enter when the app is disconnected > ")

    print("\n  resolving the device ...")
    dev = await BleakScanner.find_device_by_name("CM454M0223", timeout=20.0)
    if dev is None:
        print("  Not advertising even with the app disconnected.")
        print("  Wake the device (press its button) and re-run.")
        return
    print("  resolved and cached.\n")

    print("  Step 2: NOW connect the CR30 in the phone app.")
    print("          Wait until the Bluetooth indicator is lit on the device.")
    input("\n  press Enter once the indicator is LIT > ")

    print("\n  Step 3: DISCONNECT the app (or force-quit it / phone Bluetooth off).")
    print("          Do NOT power the device off.")
    print("          Press Enter here IMMEDIATELY -- the window is short.")
    input("\n  press Enter the moment the app is disconnected > ")

    log = {"experiment": "EXP-BLE-008",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "events": [], "writes": 0}
    hits = []
    T0 = time.time()

    def cb(who):
        def f(_, d):
            b = bytes(d); t = round(time.time() - T0, 2)
            ok = len(b) == 60 and b[59] == checksum(b)
            hits.append(b)
            log["events"].append({"t": t, "char": who, "len": len(b),
                                  "hex": b.hex(), "valid_cr30_frame": ok})
            print(f"\n  <<< t={t:5.2f}s {who} {len(b)}B {b[:12].hex(' ')}"
                  + ("   *** VALID CR30 FRAME ***" if ok else ""))
        return f

    try:
        async with BleakClient(dev, timeout=15.0) as c:
            log["connect_latency_s"] = round(time.time() - T0, 2)
            print(f"  connected in {log['connect_latency_s']}s  mtu {c.mtu_size}")
            for u in U.values():
                try: await c.start_notify(u, cb(u[4:8]))
                except Exception: pass
            sub = 0
            while time.time() - T0 < WINDOW:
                pkt = Frame.build(0xAA, 0x0A, sub % 4, 0).to_bytes()
                try:
                    await c.write_gatt_char(U["ffe1"], pkt, response=False)
                    log["writes"] += 1
                except Exception as e:
                    print(f"\n  write failed: {type(e).__name__}"); break
                sub += 1
                print(f"\r  polling... {int(time.time()-T0):2d}/{WINDOW}s  "
                      f"writes {log['writes']}  replies {len(hits)}", end="", flush=True)
                await asyncio.sleep(1.0)
            for u in U.values():
                try: await c.stop_notify(u)
                except Exception: pass
    except Exception as e:
        log["connect_error"] = f"{type(e).__name__}: {e}"
        print(f"\n  could not connect: {type(e).__name__}")

    print()
    log["verdict"] = (f"ANSWERED -- {len(hits)} reply/replies. The device CAN be "
                      "talked to once activated; activation is the only gap."
                      if hits else
                      "silent even immediately after the app let go")
    print("\n  VERDICT:", log["verdict"])
    ind = input("\n  Was the Bluetooth indicator lit while this ran? [y/n/partly] > ").strip().lower()
    log["indicator_during_run"] = ind
    p = ROOT / "captures/raw/EXP-BLE-008-handoff.json"
    p.write_text(json.dumps(log, indent=2)); print(f"\nwrote {p}")

try: asyncio.run(main())
except KeyboardInterrupt: print("\ninterrupted")
