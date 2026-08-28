#!/usr/bin/env python3
"""EXP-BLE-002 -- does BLE carry the same 60-byte CR30 framing as USB?

"BLE probably uses the same protocol" is NOT a result (CLAUDE.md, TRANSPORT_BLE).
This proves or disproves it.

SAFETY. Writes ONE command: AA 0A ss 00, the device-identity query. It is
read-only on the device, has no side effects, and has been sent hundreds of
times over USB. It is NOT a measurement trigger, so the standing "no trigger
with a magnet present" rule is not engaged. Nothing is written to ffe3, whose
purpose is unknown -- only ffe1, the conventional BLE-UART data characteristic.
"""
import asyncio, sys, json, pathlib, datetime, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient
from cr30.frame import Frame, checksum, FRAME_SIZE
from cr30.identity import parse_identity

FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
FFE2 = "0000ffe2-0000-1000-8000-00805f9b34fb"


async def main():
    addr = sys.argv[1]
    log = {"experiment": "EXP-BLE-002",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "pseudonym": "BLE-" + hashlib.sha256(addr.encode()).hexdigest()[:8].upper(),
           "address": addr, "probes": []}
    rx = bytearray(); chunks = []

    def on_notify(who):
        def cb(_, data):
            rx.extend(data); chunks.append((who, len(data), bytes(data).hex()))
        return cb

    async with BleakClient(addr, timeout=20.0) as c:
        print(f"connected: {c.is_connected}")
        try:
            print(f"negotiated MTU: {c.mtu_size}")
            log["mtu"] = c.mtu_size
        except Exception:
            pass
        for u, n in ((FFE1, "ffe1"), (FFE2, "ffe2")):
            try:
                await c.start_notify(u, on_notify(n)); print(f"subscribed {n}")
            except Exception as e:
                print(f"subscribe {n} failed: {type(e).__name__}")

        frames = {}
        for sub in (0x00, 0x01, 0x02, 0x03):
            pkt = Frame.build(0xAA, 0x0A, sub, 0).to_bytes()
            rx.clear(); chunks.clear()
            await c.write_gatt_char(FFE1, pkt, response=False)
            await asyncio.sleep(1.5)
            got = bytes(rx)
            rec = {"subcmd": sub, "tx": pkt.hex(), "rx_len": len(got),
                   "rx": got.hex(),
                   "notify_chunks": [{"char": w, "len": l, "hex": h}
                                     for w, l, h in chunks]}
            if len(got) == FRAME_SIZE:
                rec["checksum_ok"] = got[59] == checksum(got)
                rec["matches_usb_framing"] = (got[0] == 0xAA and got[1] == 0x0A
                                              and got[2] == sub)
                try:
                    frames[sub] = Frame.parse(got)
                except Exception as e:
                    rec["parse_error"] = repr(e)
            log["probes"].append(rec)
            sizes = "+".join(str(l) for _, l, _ in chunks) or "0"
            print(f"  AA 0A {sub:02X}: {len(got):3d} bytes in {len(chunks)} "
                  f"notification(s) [{sizes}]"
                  + (f"  cs_ok={rec.get('checksum_ok')}" if len(got) == 60 else ""))

        for u in (FFE1, FFE2):
            try: await c.stop_notify(u)
            except Exception: pass

    print("\n--- verdict ---")
    ok = [p for p in log["probes"] if p.get("rx_len") == FRAME_SIZE]
    if len(ok) == 4 and all(p.get("checksum_ok") for p in ok):
        log["verdict"] = ("BLE CARRIES THE SAME 60-BYTE FRAMING with the same "
                          "checksum rule, reassembled from notifications.")
        ident = parse_identity(frames)
        log["identity_model"] = ident.model
        print(f"  {log['verdict']}")
        print(f"  device identifies over BLE as: {ident.model!r} "
              f"(is_cr30={ident.is_cr30()})")
    elif not ok:
        log["verdict"] = ("NO 60-byte reply on ffe1. BLE either uses a different "
                          "framing, a different characteristic, or needs pairing.")
        print(f"  {log['verdict']}")
    else:
        log["verdict"] = f"PARTIAL: {len(ok)}/4 well-formed replies -- investigate."
        print(f"  {log['verdict']}")

    p = ROOT / "captures" / "raw" / "EXP-BLE-002-protocol.json"
    p.write_text(json.dumps(log, indent=2)); print(f"\nwrote {p}")


if __name__ == "__main__":
    asyncio.run(main())
