#!/usr/bin/env python3
"""EXP-BLE-005 -- does the CR30 ever PUSH anything over BLE?

Every host-initiated write has been accepted and answered with silence
(EXP-BLE-002/003), with USB connected and with USB unplugged. So the question
becomes: does the notify path work at all, in the other direction?

This subscribes to every characteristic that will accept a subscription --
including ffe3, which carries a CCCD despite not advertising notify -- and then
just LISTENS while the operator uses the device.

READ-ONLY: not one byte is written to the device. Safe by construction.
"""
import asyncio, sys, json, pathlib, datetime, hashlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient
from cr30.frame import checksum

U = {n: f"0000{n}-0000-1000-8000-00805f9b34fb" for n in ("ffe1", "ffe2", "ffe3")}

STEPS = [
    ("Press the MEASURE button once, on any surface.", 12),
    ("LONG-PRESS the button until the display changes to the other view.", 15),
    ("While in that other view, press the button once.", 12),
    ("Long-press again to return to the normal view.", 10),
    ("Press the measure button once more, normally.", 12),
]


def addr_of():
    d = json.loads((OUT / "EXP-BLE-001-scan.json").read_text())
    return [r["address"] for r in d["scan"] if r["name"] == "CM454M0223"][0]


async def main():
    addr = sys.argv[1] if len(sys.argv) > 1 else addr_of()
    log = {"experiment": "EXP-BLE-005", "read_only": True,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "pseudonym": "BLE-" + hashlib.sha256(addr.encode()).hexdigest()[:8].upper(),
           "steps": []}
    events = []

    def cb(who):
        def f(_, data):
            events.append((time.time(), who, bytes(data)))
            b = bytes(data)
            ok = len(b) == 60 and b[59] == checksum(b)
            print(f"      <<< {who}  {len(b):3d} bytes  {b[:8].hex(' ')}"
                  + ("  [VALID CR30 FRAME]" if ok else ""))
        return f

    print("EXP-BLE-005 -- listening only. Nothing is sent to the device.\n")
    async with BleakClient(addr, timeout=20.0) as c:
        print(f"connected: {c.is_connected}  mtu {c.mtu_size}")
        subbed = []
        for n, u in U.items():
            try:
                await c.start_notify(u, cb(n)); subbed.append(n)
            except Exception as e:
                print(f"  {n}: cannot subscribe ({type(e).__name__})")
        print(f"  subscribed: {', '.join(subbed) or 'NONE'}\n")
        log["subscribed"] = subbed

        for i, (instruction, secs) in enumerate(STEPS, 1):
            print("-" * 72)
            print(f"  STEP {i}/{len(STEPS)}: {instruction}")
            input(f"  press Enter, then do it -- listening {secs}s > ")
            start = len(events); t0 = time.time()
            while time.time() - t0 < secs:
                await asyncio.sleep(0.05)
            new = events[start:]
            print(f"    -> {len(new)} notification(s), "
                  f"{sum(len(e[2]) for e in new)} bytes")
            log["steps"].append({
                "step": i, "instruction": instruction, "seconds": secs,
                "notifications": [{"t": round(t - t0, 3), "char": w,
                                   "len": len(b), "hex": b.hex()}
                                  for t, w, b in new]})
        for n in subbed:
            try: await c.stop_notify(U[n])
            except Exception: pass

    total = sum(len(s["notifications"]) for s in log["steps"])
    log["total_notifications"] = total
    if total:
        log["verdict"] = "THE NOTIFY PATH WORKS -- the device pushes data over BLE."
    else:
        log["verdict"] = ("SILENT in both directions. BLE is advertised and "
                          "connectable but carries no CR30 traffic under any "
                          "condition tested.")
    print("\n" + "=" * 72)
    print("  VERDICT: " + log["verdict"])
    p = OUT / "EXP-BLE-005-listen.json"
    p.write_text(json.dumps(log, indent=2)); print(f"\nwrote {p}")


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\ninterrupted")
