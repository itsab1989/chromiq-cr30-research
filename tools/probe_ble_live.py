#!/usr/bin/env python3
"""EXP-BLE-010 -- speak the REAL BLE protocol, learned from the vendor capture.

What EXP-BLE-009 revealed, and why every earlier attempt failed:

  * BLE frames are **10 bytes**, not the 60 bytes USB uses.
  * The host must write a **single 0x01 byte** to poll. That is what makes the
    device talk. We never sent it, so it never answered -- nothing to do with
    channel, chunking or sleep.
  * The checksum rule GENERALISES: sum(bytes 0..n-2) mod 256, marker included.
  * Responses arrive as notifications, fragmented at the ATT MTU.

Sends only a measurement-read (bb 02 10) and polls. No calibration command.
"""
import asyncio, sys, json, pathlib, datetime, struct, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient, BleakScanner

FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
FFE2 = "0000ffe2-0000-1000-8000-00805f9b34fb"
POLL = bytes([0x01])


def frame10(cmd, sub=0, param=0, data=b""):
    d = bytearray(10)
    d[0], d[1], d[2], d[3] = 0xBB, cmd, sub, param
    d[4:4 + len(data)] = data
    d[8] = 0xFF
    d[9] = sum(d[:9]) % 256
    return bytes(d)


READ_MEASUREMENT = frame10(0x02, 0x10)      # bb 02 10 00 00 00 00 00 ff cc


async def main():
    print(__doc__)
    print("The vendor app must be DISCONNECTED (the device stops advertising"
          " while it is held).\n")
    dev = await BleakScanner.find_device_by_name("CM454M0223", timeout=20.0)
    if dev is None:
        sys.exit("not advertising -- disconnect the app and/or wake the device")

    log = {"experiment": "EXP-BLE-010",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "events": []}
    buf = bytearray(); frames = []

    def cb(who):
        def f(_, data):
            b = bytes(data); buf.extend(b)
            frames.append((who, b))
            log["events"].append({"char": who, "len": len(b), "hex": b.hex()})
            print(f"  <<< {who} {len(b):3d}B  {b[:14].hex(' ')}")
        return f

    async with BleakClient(dev, timeout=20.0) as c:
        print(f"connected  mtu {c.mtu_size}")
        for u, n in ((FFE1, "ffe1"), (FFE2, "ffe2")):
            try: await c.start_notify(u, cb(n))
            except Exception: pass

        print("\n-- writing the single 0x01 poll byte (the missing ingredient)")
        await c.write_gatt_char(FFE1, POLL, response=False)
        await asyncio.sleep(1.5)

        print("\n-- requesting the stored measurement (bb 02 10)")
        buf.clear()
        await c.write_gatt_char(FFE1, READ_MEASUREMENT, response=False)
        await asyncio.sleep(0.4)
        # Keep polling until TWO consecutive polls add nothing. One quiet poll
        # is not enough: the device pauses between fragments, and stopping on
        # the first gap truncated the payload at 200 bytes on the first run.
        quiet = 0
        for _ in range(25):
            before = len(buf)
            await c.write_gatt_char(FFE1, POLL, response=False)
            await asyncio.sleep(0.5)
            quiet = quiet + 1 if len(buf) == before else 0
            if quiet >= 3 and len(buf) > 0:
                break
        for u in (FFE1, FFE2):
            try: await c.stop_notify(u)
            except Exception: pass

    big = bytes(buf)
    log["reassembled_len"] = len(big); log["reassembled"] = big.hex()
    print(f"\nreassembled {len(big)} bytes")
    if len(big) >= 396:
        spec = list(struct.unpack_from("<31f", big, 208))
        L, a, b = struct.unpack_from("<3f", big, 384)
        log["spectrum"] = [round(x, 6) for x in spec]
        log["lab_from_device"] = [round(L, 4), round(a, 4), round(b, 4)]
        print(f"  spectrum 400-700nm: {spec[0]:.2f} .. {spec[-1]:.2f} "
              f"(min {min(spec):.2f} max {max(spec):.2f})")
        print(f"  device Lab: L*={L:.4f} a*={a:.4f} b*={b:.4f}")
        log["verdict"] = "BLE WORKS -- spectrum and Lab decoded over Bluetooth."
    else:
        log["verdict"] = (f"partial: {len(big)} bytes; layout offsets are from a "
                          "single vendor capture and may differ per message")
    print("\n VERDICT:", log["verdict"])
    p = ROOT / "captures/raw/EXP-BLE-010-live.json"
    p.write_text(json.dumps(log, indent=2)); print("wrote", p)

try: asyncio.run(main())
except KeyboardInterrupt: print("\ninterrupted")
