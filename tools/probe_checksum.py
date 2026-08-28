#!/usr/bin/env python3
"""EXP-USB-002 -- does the CR30 validate the request checksum?

Controlled: identical identity request (AA 0A 00 00), three checksum values.
Read-only command. Only byte 59 varies.
"""
import sys, time, json, pathlib, datetime, serial
PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
def frame(cs):
    d = bytearray(60); d[0],d[1],d[2],d[3] = 0xAA,0x0A,0x00,0x00; d[58]=0xFF; d[59]=cs
    return bytes(d)
def drain(ser, s=1.0):
    buf=bytearray(); end=time.time()+s
    while time.time()<end:
        n=ser.in_waiting
        if n: buf+=ser.read(n); end=time.time()+0.3
        else: time.sleep(0.02)
    return bytes(buf)
base=bytearray(60); base[0],base[1],base[2],base[3]=0xAA,0x0A,0x00,0x00; base[58]=0xFF
correct=sum(base[:59])%256          # unified rule -> 0xB3
itohio=sum(base[:58])%256           # prior-art rule -> 0xB4
cases=[("correct sum(0..58)",correct),("itohio sum(0..57)",itohio),
       ("garbage 0x00",0x00),("garbage 0xFF",0xFF),("garbage 0x42",0x42)]
out={"experiment":"EXP-USB-002","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
     "port":PORT,"note":"only byte 59 varies","cases":[]}
with serial.Serial(PORT,115200,timeout=0.2) as ser:
    time.sleep(0.3); ser.reset_input_buffer()
    for name,cs in cases:
        ser.reset_input_buffer(); ser.write(frame(cs)); ser.flush()
        rx=drain(ser)
        ok = len(rx)==60 and rx[59]==sum(rx[:59])%256
        out["cases"].append({"case":name,"cs":cs,"rx_len":len(rx),"rx":rx.hex(),"rx_cs_valid":ok})
        print(f"  cs=0x{cs:02X} ({name:20s}) -> {len(rx):3d} bytes, reply-cs-valid={ok}")
        time.sleep(0.2)
pathlib.Path("captures/raw/EXP-USB-002-checksum.json").write_text(json.dumps(out,indent=2))
print("wrote captures/raw/EXP-USB-002-checksum.json")
