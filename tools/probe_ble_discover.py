#!/usr/bin/env python3
"""EXP-BLE-001 -- passive BLE discovery. READ-ONLY, no writes, ever.

Stage 1 scans and reports every advertiser. Stage 2 (--connect <address>)
connects to ONE device and enumerates its GATT tree without writing a byte.

Nothing here can change a device setting. Per CLAUDE.md 11 and the standing
rule in STATUS.md, no CR30 command is sent over any transport in this script.

Addresses are unique identifiers: the report redacts them, and the full values
go to captures/raw/ only (gitignored).
"""
import asyncio, sys, json, pathlib, datetime, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    sys.exit("bleak missing: .venv/bin/pip install bleak")

# Names/prefixes worth flagging. Kept deliberately WIDE -- a probe that only
# looks for "CR30" would miss a device advertising as anything else, and a
# null result would then be meaningless.
HINTS = ("cr", "chn", "spec", "color", "colour", "cs-", "cm-", "bt", "hc-")


def tag(addr):
    """Stable pseudonym so the same device is recognisable across runs."""
    return "BLE-" + hashlib.sha256(addr.encode()).hexdigest()[:8].upper()


async def scan(seconds):
    print(f"scanning {seconds}s ...\n")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = []
    for dev, adv in found.values():
        name = adv.local_name or dev.name or ""
        rows.append({
            "pseudonym": tag(dev.address), "address": dev.address,
            "name": name, "rssi": adv.rssi,
            "service_uuids": list(adv.service_uuids or []),
            "manufacturer_data": {str(k): v.hex()
                                  for k, v in (adv.manufacturer_data or {}).items()},
            "service_data": {str(k): v.hex()
                             for k, v in (adv.service_data or {}).items()},
            "candidate": any(h in name.lower() for h in HINTS) if name else False,
        })
    rows.sort(key=lambda r: (-r["candidate"], -(r["rssi"] or -999)))
    print(f"{len(rows)} advertisers seen\n")
    print(f"{'pseudonym':14s} {'rssi':>5s}  {'name':28s} services")
    print("-" * 78)
    for r in rows:
        mark = "*" if r["candidate"] else " "
        svc = ",".join(u[4:8] for u in r["service_uuids"][:4]) or "-"
        print(f"{mark}{r['pseudonym']:13s} {r['rssi']:5d}  "
              f"{(r['name'] or '(unnamed)')[:28]:28s} {svc}")
    cands = [r for r in rows if r["candidate"]]
    print(f"\n{len(cands)} flagged as possible CR30 by name.")
    if not cands:
        print("  NOTE: a null result here does NOT mean the CR30 has no BLE.")
        print("  It may advertise unnamed, may need Bluetooth enabled on the")
        print("  device, or may only advertise while not on USB power.")
    return rows


async def enumerate_gatt(address):
    print(f"\nconnecting to {tag(address)} (read-only) ...")
    out = {"pseudonym": tag(address), "address": address, "services": []}
    async with BleakClient(address, timeout=20.0) as c:
        print(f"connected: {c.is_connected}\n")
        for s in c.services:
            svc = {"uuid": s.uuid, "description": s.description, "characteristics": []}
            print(f"service {s.uuid}  {s.description}")
            for ch in s.characteristics:
                props = ",".join(ch.properties)
                val = None
                if "read" in ch.properties:
                    try:
                        val = (await c.read_gatt_char(ch.uuid)).hex()
                    except Exception as e:
                        val = f"<read failed: {type(e).__name__}>"
                svc["characteristics"].append(
                    {"uuid": ch.uuid, "description": ch.description,
                     "properties": list(ch.properties), "value": val})
                shown = "" if val is None else f"  = {val[:48]}"
                print(f"    {ch.uuid}  [{props}]  {ch.description}{shown}")
            out["services"].append(svc)
    return out


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    log = {"experiment": "EXP-BLE-001",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "platform": sys.platform, "read_only": True}
    if "--connect" in sys.argv:
        addr = args[0]
        log["gatt"] = await enumerate_gatt(addr)
        name = "EXP-BLE-001-gatt.json"
    else:
        secs = float(args[0]) if args else 12.0
        log["scan"] = await scan(secs)
        name = "EXP-BLE-001-scan.json"
    p = OUT / name
    p.write_text(json.dumps(log, indent=2))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    asyncio.run(main())
