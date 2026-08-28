#!/usr/bin/env python3
"""EXP-USB-005b -- what makes BB 13's device field move, and does the device
recover from the pipelining desync without a port reopen?

BB 13 'Check' writes six bytes at frame offsets 5..10. Byte 5 has been 0x51 in
every observation; offsets 9..10 read as a little-endian u16 that CHANGED
between sessions but did NOT change across a 90 s idle window (EXP-USB-005).
So it is not a clock. This isolates what does move it. Read-only throughout.
"""
import sys, time, json, pathlib, datetime, serial
PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

def build(start, cmd, sub=0, param=0, data=b""):
    d = bytearray(60); d[0], d[1], d[2], d[3] = start, cmd, sub, param
    d[4:4+len(data)] = data; d[58] = 0xFF; d[59] = sum(d[:59]) % 256
    return bytes(d)
IDENT = build(0xAA, 0x0A, 0, 0)
CHECK = build(0xBB, 0x13, 0, 0, data=b"Check" + b"\x00"*7)

def txrx(ser, pkt, timeout=1.0):
    ser.reset_input_buffer(); t0=time.perf_counter(); ser.write(pkt); ser.flush()
    buf=bytearray(); dl=t0+timeout
    while len(buf)<60 and time.perf_counter()<dl:
        n=ser.in_waiting
        if n: buf+=ser.read(n)
        else: time.sleep(0.0002)
    return bytes(buf), time.perf_counter()-t0

def field(rx): return None if len(rx)!=60 else (rx[5], int.from_bytes(rx[9:11],'little'), rx[5:11].hex())

log={"experiment":"EXP-USB-005b","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "port":PORT,"platform":"macOS 15.7.9 (24G830) arm64","parts":{}}

print("a. BB 13 x 20, back to back, nothing else in between")
seq=[]
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); ser.reset_input_buffer()
    for i in range(20):
        rx,_=txrx(ser,CHECK); seq.append(field(rx)); time.sleep(0.02)
log["parts"]["repeat_bb13"]=seq
print("   u16 values:", [s[1] for s in seq])
print("   byte5 values:", sorted({s[0] for s in seq}))

print("\nb. BB 13, then 50 x AA 0A, then BB 13 (same open port)")
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); ser.reset_input_buffer()
    b0,_=txrx(ser,CHECK)
    for _ in range(50): txrx(ser,IDENT)
    b1,_=txrx(ser,CHECK)
log["parts"]["after_50_ident"]={"before":field(b0),"after":field(b1)}
print(f"   before={field(b0)[1]}  after 50 AA 0A ={field(b1)[1]}  delta={field(b1)[1]-field(b0)[1]}")

print("\nc. BB 13, close port, reopen, BB 13")
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); c0,_=txrx(ser,CHECK)
time.sleep(0.5)
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); c1,_=txrx(ser,CHECK)
log["parts"]["across_reopen"]={"before":field(c0),"after":field(c1)}
print(f"   before={field(c0)[1]}  after reopen={field(c1)[1]}  delta={field(c1)[1]-field(c0)[1]}")

print("\nd. 30 s wall-clock idle with the port OPEN and no traffic")
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); d0,_=txrx(ser,CHECK); time.sleep(30.0); d1,_=txrx(ser,CHECK)
log["parts"]["idle_30s"]={"before":field(d0),"after":field(d1)}
print(f"   before={field(d0)[1]}  after 30 s idle={field(d1)[1]}  delta={field(d1)[1]-field(d0)[1]}")

print("\ne. pipelining desync: does the device recover WITHOUT a reopen?")
rec={"pipelined_reply_bytes":None,"recovery":[]}
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.1); ser.reset_input_buffer()
    ser.write(IDENT+IDENT); ser.flush()
    t0=time.perf_counter(); buf=bytearray()
    while time.perf_counter()-t0<1.5:
        n=ser.in_waiting
        if n: buf+=ser.read(n)
        else: time.sleep(0.002)
    rec["pipelined_reply_bytes"]=len(buf); rec["pipelined_rx"]=bytes(buf).hex()
    print(f"   two frames in one write -> {len(buf)} bytes back")
    for i in range(6):
        rx,_=txrx(ser,IDENT,timeout=1.0)
        ok = len(rx)==60 and rx[59]==sum(rx[:59])%256
        rec["recovery"].append({"attempt":i+1,"rx_len":len(rx),"valid":ok,"rx":rx.hex()})
        print(f"   recovery attempt {i+1}: {len(rx):3d} B valid={ok}")
        if ok: break
log["parts"]["pipelining"]=rec

print("\nf. how many frames in ONE write does the device tolerate?")
tol=[]
for n_frames in (1,2,3):
    with serial.Serial(PORT,115200,timeout=0.2) as ser:
        time.sleep(0.1); ser.reset_input_buffer()
        ser.write(IDENT*n_frames); ser.flush()
        t0=time.perf_counter(); buf=bytearray()
        while time.perf_counter()-t0<1.5:
            k=ser.in_waiting
            if k: buf+=ser.read(k)
            else: time.sleep(0.002)
    tol.append({"frames_in_one_write":n_frames,"bytes_back":len(buf),"rx":bytes(buf).hex()})
    print(f"   {n_frames} frame(s) ({n_frames*60} B) in one write -> {len(buf)} B back")
    time.sleep(0.2)
log["parts"]["write_size_tolerance"]=tol

p=OUT/"EXP-USB-005b-bb13-field.json"; p.write_text(json.dumps(log,indent=2))
print("\nwrote",p)
