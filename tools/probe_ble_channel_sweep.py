import asyncio, sys, json, pathlib, datetime
ROOT = pathlib.Path("/Users/Basti/develop/chromiq-cr30-research")
sys.path.insert(0, str(ROOT / "src"))
from bleak import BleakClient
from cr30.frame import Frame, checksum

U = {n: f"0000{n}-0000-1000-8000-00805f9b34fb" for n in ("ffe1","ffe2","ffe3")}
PKT = Frame.build(0xAA, 0x0A, 0x00, 0).to_bytes()

async def main():
    addr = sys.argv[1]
    log = {"experiment":"EXP-BLE-003","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "note":"sweep write channel x write mode; identity command only","trials":[]}
    rx=bytearray(); chunks=[]
    def cb(who):
        def f(_,d): rx.extend(d); chunks.append((who,bytes(d).hex()))
        return f
    async with BleakClient(addr, timeout=20.0) as c:
        print("connected:", c.is_connected, " mtu:", c.mtu_size)
        for n in ("ffe1","ffe2"):
            try: await c.start_notify(U[n], cb(n))
            except Exception as e: print(f"  subscribe {n}: {type(e).__name__}")
        # passive first: does it push anything unprompted?
        rx.clear(); chunks.clear(); await asyncio.sleep(4.0)
        print(f"  passive 4s: {len(rx)} bytes")
        log["passive_bytes"]=len(rx); log["passive"]=bytes(rx).hex()
        for ch in ("ffe1","ffe2","ffe3"):
            for resp in (False, True):
                rx.clear(); chunks.clear()
                try:
                    await c.write_gatt_char(U[ch], PKT, response=resp)
                    err=None
                except Exception as e:
                    err=f"{type(e).__name__}: {e}"
                await asyncio.sleep(1.5)
                got=bytes(rx)
                ok = len(got)==60 and got[59]==checksum(got)
                log["trials"].append({"char":ch,"response":resp,"error":err,
                                      "rx_len":len(got),"rx":got.hex(),
                                      "frame_ok":ok,
                                      "chunks":[{"char":w,"hex":h} for w,h in chunks]})
                print(f"  write {ch} response={str(resp):5s} -> "
                      f"{'ERR '+err[:34] if err else f'{len(got):3d} bytes'}"
                      + ("  FRAME OK" if ok else ""))
        for n in ("ffe1","ffe2"):
            try: await c.stop_notify(U[n])
            except Exception: pass
    hit=[t for t in log["trials"] if t["frame_ok"]]
    log["verdict"]=("responds on "+", ".join(f"{t['char']}(response={t['response']})" for t in hit)
                    if hit else "NO channel/mode produced a CR30 frame")
    print("\n verdict:", log["verdict"])
    p=ROOT/"captures"/"raw"/"EXP-BLE-003-channel-sweep.json"
    p.write_text(json.dumps(log,indent=2)); print("wrote",p)

asyncio.run(main())
