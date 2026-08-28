#!/usr/bin/env python3
"""EXP-USB-005c -- write granularity, and the slow drift in BB 13's u16 field.

Part 1 (fast). EXP-USB-005b showed a 120-byte write (two frames) gets NO reply
at all, while a 60-byte write always does. This asks the portability question
that matters for a cross-platform implementation: must a frame be delivered as
ONE write, or may it be split? Any implementation that buffers or chunks its
writes depends on the answer.

Part 2 (slow). BB 13's u16 at offsets 9..10 was 1084, then 1445 fifteen minutes
later, yet is stable across 20 back-to-back reads, 50 intervening commands, a
port reopen and 30 s of idle. Sample it every 30 s to see whether it drifts on
its own. Read-only.
"""
import sys, time, json, pathlib, datetime, serial
PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
MINUTES = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

def build(start, cmd, sub=0, param=0, data=b""):
    d=bytearray(60); d[0],d[1],d[2],d[3]=start,cmd,sub,param
    d[4:4+len(data)]=data; d[58]=0xFF; d[59]=sum(d[:59])%256
    return bytes(d)
IDENT=build(0xAA,0x0A,0,0); CHECK=build(0xBB,0x13,0,0,data=b"Check"+b"\x00"*7)

def read_frame(ser, timeout=1.0):
    t0=time.perf_counter(); buf=bytearray()
    while len(buf)<60 and time.perf_counter()-t0<timeout:
        n=ser.in_waiting
        if n: buf+=ser.read(n)
        else: time.sleep(0.0005)
    return bytes(buf)

log={"experiment":"EXP-USB-005c","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "port":PORT,"platform":"macOS 15.7.9 (24G830) arm64","parts":{}}

print("1. write granularity: is one frame == one write() required?")
gran=[]
cases=[("one write of 60 B",[60]),("30 + 30",[30,30]),("59 + 1",[59,1]),
       ("1 + 59",[1,59]),("20 + 20 + 20",[20,20,20])]
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); ser.reset_input_buffer()
    for label,chunks in cases:
        ser.reset_input_buffer()
        off=0
        for c in chunks:
            ser.write(IDENT[off:off+c]); ser.flush(); off+=c
        rx=read_frame(ser,1.5)
        ok = len(rx)==60 and rx[59]==sum(rx[:59])%256
        gran.append({"label":label,"chunks":chunks,"rx_len":len(rx),"valid":ok,"rx":rx.hex()})
        print(f"   {label:20s} -> {len(rx):3d} B  valid={ok}")
        # resync guard so a failure cannot contaminate the next case
        ser.reset_input_buffer(); ser.write(IDENT); ser.flush(); read_frame(ser,1.0)
        time.sleep(0.1)
log["parts"]["write_granularity"]=gran

print(f"\n2. sampling BB 13 every 30 s for {MINUTES:.0f} min (no other traffic)")
samples=[]
t0=time.time()
while time.time()-t0 < MINUTES*60:
    with serial.Serial(PORT,115200,timeout=0.2) as ser:
        time.sleep(0.05); ser.reset_input_buffer()
        ser.write(CHECK); ser.flush(); rx=read_frame(ser,1.0)
    if len(rx)==60:
        u=int.from_bytes(rx[9:11],'little')
        s={"t_s":round(time.time()-t0,1),
           "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "byte5":rx[5],"u16_9_10":u,"field_5_10":rx[5:11].hex()}
        samples.append(s)
        print(f"   t={s['t_s']:7.1f}s  byte5=0x{rx[5]:02X}  u16={u}", flush=True)
    time.sleep(30)
log["parts"]["bb13_drift"]=samples
if samples:
    vs=[s["u16_9_10"] for s in samples]
    log["parts"]["bb13_drift_summary"]={"n":len(vs),"min":min(vs),"max":max(vs),
                                        "first":vs[0],"last":vs[-1],"changed":min(vs)!=max(vs)}
    print(f"\n   u16 over {MINUTES:.0f} min: min={min(vs)} max={max(vs)} changed={min(vs)!=max(vs)}")

p=OUT/"EXP-USB-005c-write-granularity-and-drift.json"; p.write_text(json.dumps(log,indent=2))
print("wrote",p)
