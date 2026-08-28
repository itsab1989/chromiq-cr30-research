#!/usr/bin/env python3
"""EXP-BLE-006 -- is the BLE write CHUNKED?

HM-10 / CC254x style modules commonly cap a characteristic write at 20 bytes
regardless of the negotiated MTU, and drop longer writes SILENTLY. Every BLE
attempt so far wrote all 60 bytes at once, which is the rule that is REQUIRED on
USB (EXP-USB-005) and may be exactly wrong here.

The operator reports the vendor iOS app connects and works with no special
procedure, so the device's BLE is functional and the fault is on our side.

Writes only the identity command AA 0A ss 00 -- read-only on the device.
"""
import asyncio, sys, json, pathlib, datetime, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient
from cr30.frame import Frame, checksum

U = {n: f"0000{n}-0000-1000-8000-00805f9b34fb" for n in ("ffe1", "ffe2", "ffe3")}
PKT = Frame.build(0xAA, 0x0A, 0x00, 0).to_bytes()
STRATEGIES = [("single 60", 60), ("3 x 20", 20), ("4 x 15", 15),
              ("2 x 30", 30), ("6 x 10", 10)]


def addr_of():
    d = json.loads((ROOT / "captures/raw/EXP-BLE-001-scan.json").read_text())
    return [r["address"] for r in d["scan"] if r["name"] == "CM454M0223"][0]


async def main():
    addr = sys.argv[1] if len(sys.argv) > 1 else addr_of()
    log = {"experiment": "EXP-BLE-006",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "note": "identity command only; sweeping write chunk size x channel",
           "trials": []}
    rx = bytearray(); got = []

    def cb(who):
        def f(_, d):
            rx.extend(d); got.append((who, bytes(d)))
            print(f"        <<< {who} {len(d)}B {bytes(d)[:10].hex(' ')}")
        return f

    async with BleakClient(addr, timeout=20.0) as c:
        print(f"connected: {c.is_connected}  mtu {c.mtu_size}")
        subbed = []
        for n, u in U.items():
            try:
                await c.start_notify(u, cb(n)); subbed.append(n)
            except Exception:
                pass
        print(f"subscribed: {', '.join(subbed)}\n")
        for ch in ("ffe1", "ffe2", "ffe3"):
            for name, size in STRATEGIES:
                rx.clear(); got.clear()
                err = None
                try:
                    for i in range(0, len(PKT), size):
                        await c.write_gatt_char(U[ch], PKT[i:i+size], response=False)
                        if size < 60:
                            await asyncio.sleep(0.03)
                except Exception as e:
                    err = f"{type(e).__name__}"
                await asyncio.sleep(1.2)
                b = bytes(rx)
                ok = len(b) == 60 and b[59] == checksum(b)
                log["trials"].append({"char": ch, "strategy": name, "chunk": size,
                                      "error": err, "rx_len": len(b), "rx": b.hex(),
                                      "frame_ok": ok})
                flag = "  *** VALID CR30 FRAME ***" if ok else ""
                print(f"  {ch} {name:10s} -> {('ERR ' + err) if err else f'{len(b):3d} bytes'}{flag}")
        for n in subbed:
            try: await c.stop_notify(U[n])
            except Exception: pass

    hit = [t for t in log["trials"] if t["frame_ok"]]
    log["verdict"] = ("BLE ANSWERS with " + ", ".join(f"{t['char']}/{t['strategy']}" for t in hit)
                      if hit else
                      "still silent under every chunk size on every channel")
    print("\n VERDICT:", log["verdict"])
    p = ROOT / "captures/raw/EXP-BLE-006-chunked.json"
    p.write_text(json.dumps(log, indent=2)); print("wrote", p)

asyncio.run(main())
