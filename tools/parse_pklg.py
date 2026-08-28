#!/usr/bin/env python3
"""Parse an Apple PacketLogger .pklg trace and extract the ATT layer.

Record: uint32 length | uint32 secs | uint32 usecs | uint8 type | payload
(length covers the 9-byte header + payload). Endianness is detected, because
Apple has shipped both.

type 0x00 HCI cmd (host->ctrl) · 0x01 HCI event · 0x02 ACL out · 0x03 ACL in
"""
import struct, sys, pathlib, json, collections

ATT_OPS = {0x01:"ERROR_RSP",0x02:"MTU_REQ",0x03:"MTU_RSP",0x04:"FIND_INFO_REQ",
 0x05:"FIND_INFO_RSP",0x08:"READ_BY_TYPE_REQ",0x09:"READ_BY_TYPE_RSP",
 0x0A:"READ_REQ",0x0B:"READ_RSP",0x10:"READ_BY_GRP_REQ",0x11:"READ_BY_GRP_RSP",
 0x12:"WRITE_REQ",0x13:"WRITE_RSP",0x52:"WRITE_CMD",0x1B:"NOTIFY",0x1D:"INDICATE",
 0x1E:"CONFIRM"}


def records(data):
    """length field EXCLUDES itself: record = 4 + len bytes, 9-byte header."""
    for endian in ("<", ">"):
        off, out, ok = 0, [], True
        while off + 13 <= len(data):
            (ln,) = struct.unpack_from(endian + "I", data, off)
            if ln < 9 or off + 4 + ln > len(data):
                ok = False; break
            s, us = struct.unpack_from(endian + "II", data, off + 4)
            out.append((s + us / 1e6, data[off + 12], data[off + 13: off + 4 + ln]))
            off += 4 + ln
        if ok and len(out) > 5:
            return endian, out
    return None, []


def main():
    raw = pathlib.Path(sys.argv[1]).read_bytes()
    endian, recs = records(raw)
    if not recs:
        sys.exit("could not parse -- unexpected pklg layout")
    print(f"parsed {len(recs)} records (endian {endian})")
    print("types:", dict(collections.Counter(t for _, t, _ in recs)))

    frag = {}
    atts = []
    for ts, typ, p in recs:
        if typ not in (0x02, 0x03) or len(p) < 4:
            continue
        d = "out" if typ == 0x02 else "in"
        hdr, dlen = struct.unpack_from("<HH", p, 0)
        handle, pb = hdr & 0x0FFF, (hdr >> 12) & 0x3
        body = p[4:4 + dlen]
        key = (handle, d)
        if pb == 0x02 or pb == 0x00:          # start of L2CAP PDU
            frag[key] = bytearray(body)
        elif pb == 0x01:                       # continuation
            frag.setdefault(key, bytearray()).extend(body)
        buf = frag.get(key, bytearray())
        if len(buf) < 4:
            continue
        l2len, cid = struct.unpack_from("<HH", buf, 0)
        if len(buf) - 4 < l2len:
            continue
        pdu = bytes(buf[4:4 + l2len]); frag.pop(key, None)
        if cid != 0x0004 or not pdu:
            continue
        atts.append({"t": round(ts, 4), "dir": d, "op": pdu[0],
                     "opname": ATT_OPS.get(pdu[0], f"0x{pdu[0]:02X}"),
                     "payload": pdu[1:].hex()})
    print(f"\n{len(atts)} ATT PDUs\n")
    t0 = atts[0]["t"] if atts else 0
    for a in atts:
        pl = bytes.fromhex(a["payload"])
        extra = ""
        if a["opname"] in ("WRITE_REQ", "WRITE_CMD", "NOTIFY", "INDICATE") and len(pl) >= 2:
            h = struct.unpack_from("<H", pl, 0)[0]
            v = pl[2:]
            extra = f" handle=0x{h:04X} len={len(v)} {v.hex(' ')[:80]}"
        elif a["opname"] == "MTU_REQ" or a["opname"] == "MTU_RSP":
            extra = f" mtu={struct.unpack_from('<H', pl, 0)[0]}" if len(pl) >= 2 else ""
        print(f"{a['t']-t0:8.3f} {a['dir']:3s} {a['opname']:16s}{extra}")
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
    if out:
        out.write_text(json.dumps({"att": atts}, indent=2))
        print("\nwrote", out)


main()
