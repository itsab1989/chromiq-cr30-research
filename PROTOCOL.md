# PROTOCOL.md — CR30 wire protocol

Confidence levels per `CLAUDE.md` §4. Every VERIFIED line names its capture.

## 1. Frame format

**VERIFIED** (`captures/public/EXP-MAC-USB-001-identity.json`) — every frame
observed so far, in both directions, is exactly **60 bytes**.

| Byte | Field | Observed |
|---|---|---|
| 0 | Start | `0xAA` (identity/handshake class). `0xBB` reported by prior art for command class — **not yet verified here** |
| 1 | Command | `0x0A` = device information |
| 2 | Sub-command | `0x00`…`0x03` for identity fields |
| 3 | Parameter | `0x00` in all frames observed |
| 4–57 | Payload | 54 bytes. *(Prior art calls this 4–55 / 52 bytes; the extra two bytes at 56–57 have not been shown to be a separate field — see §6.)* |
| 58 | Marker | `0xFF` in every frame observed, both directions |
| 59 | Checksum | see §2 |

## 2. Checksum — prior art is DISPROVEN

**VERIFIED rule:**

```
checksum = sum(frame[0..58]) mod 256        # 59 bytes, marker INCLUDED
```

All four device-originated frames in `EXP-MAC-USB-001` satisfy this exactly.

**DISPROVEN:** `itohio/color-science`
(`cr30reader/protocol/packets.py::calculate_checksum`) computes
`sum(frame[0..57]) mod 256`, then subtracts 1 when the start byte is `0xBB`.
Against real device frames this is wrong by exactly `+1` on all four, because
it omits the marker byte `0xFF` (`0xFF ≡ -1 mod 256`). Its `0xBB` special case
is a coincidental patch for the same off-by-one on the other frame class, in
the wrong place.

The simple unified rule explains both classes without a special case.

**VERIFIED, and it is why the bug survived** (`EXP-USB-002`): the CR30 **does
not validate the checksum of a request.** The identical identity request was
sent with the correct checksum, the prior-art checksum, `0x00`, `0xFF` and
`0x42`; all five produced a normal, correctly-checksummed 60-byte reply. A
transmit-side checksum error therefore has no observable consequence — so the
published rule was never exercised where it would fail.

**The checksum still matters, in the receive direction.** Device replies are
consistently checksummed, so it is the available integrity check on inbound
spectral data. Per `CLAUDE.md` §14, a checksum failure must fail loudly.

## 3. Baud rate is not a protocol parameter

**VERIFIED** (`EXP-MAC-USB-001`): identical byte-for-byte replies at **9600,
19200, 38400, 57600 and 115200** baud.

This resolves a documented inconsistency in the prior art, where captures showed
115200 and one showed 9600 while the implementation defaults to 19200. All are
correct because none of them reach a UART: the bridge is a CH55x microcontroller
presenting a serial interface, and line coding is discarded.

**Consequence:** any baud rate may be used. An implementation must not "detect"
or negotiate one, and a wrong baud rate is not a plausible failure cause.

## 4. Device information — command `0xAA 0x0A ss 0x00`

**VERIFIED** (`EXP-MAC-USB-001`). Offsets are absolute frame offsets.

| Sub | Field | Offset | Length | Observed on this unit |
|---|---|---|---|---|
| `0x00` | Device id | 9 | 10 | `<DEVICE-ID-1>` (redacted) |
| `0x00` | **Model** | 39 | 4 | **`CR30`** |
| `0x00` | Unknown | 5–8 | 4 | `56 00 19 03` |
| `0x01` | Second id | 19 | 10 | `<DEVICE-ID-2>` (redacted) |
| `0x01` | Version | 49 | 8 | `V11.3.` |
| `0x02` | Build date | 5 | 12 | `0.0.20231219` |
| `0x02` | Version | 29 | 9 | `V10.0.0.0` |
| `0x03` | Unknown | 19 | 1 | `0x02` |

**Model confirmation is VERIFIED**: the device reports the ASCII string `CR30`,
independently confirming the model without relying on the seller's listing.

The reply echoes the request's start, command and sub-command bytes in
positions 0–2, which gives free request/response correlation.

### Open on this command
- `56 00 19 03` at offset 5 (sub `0x00`) — **HYPOTHESIS**: `0x56` = 'V' may
  begin a version string; `19 03` may be a hardware or sensor revision. Untested.
- Two version strings (`V11.3.` and `V10.0.0.0`) at different sub-commands —
  **HYPOTHESIS**: firmware vs. protocol/algorithm version. Untested.
- Sub `0x03` returning a single `0x02` — **HYPOTHESIS**: a status or capability
  byte. Untested; the prior art labels it "status / build info, optional".

## 5. Not yet verified here

Everything below is **prior-art claim only**, carried for testing, not asserted:

| Claim | Source | Status |
|---|---|---|
| `0xBB 0x10` black calibration | itohio | untested here |
| `0xBB 0x11` white calibration | itohio | untested here |
| `0xBB 0x01 0x00` measurement trigger | itohio | untested here |
| `0xBB 0x01 0x10..0x13` spectrum chunk fetch | itohio | untested here |
| Unsolicited frame on button press | itohio | untested here |
| 31 little-endian `float32`, 400–700 nm @ 10 nm | itohio + beerjongen CSV | untested here |
| Values are percent reflectance | beerjongen sample CSV | untested here |
| M0 / D50 / 1931 2° measurement condition | Pharmacist write-up | untested here |

## 6. Known open structural questions

1. **Payload extent.** Prior art treats bytes 4–55 as payload and ignores 56–57.
   In `EXP-MAC-USB-001` bytes 56–57 are `0x00` in every frame, so the two
   readings are indistinguishable on present evidence. A frame carrying data
   near the end (a spectrum chunk) will separate them.
2. **Is `0xAA` vs `0xBB` a class distinction or a direction marker?** Only `0xAA`
   traffic has been observed here.
3. **Marker byte 58.** Constant `0xFF` so far. Prior art claims `0xBB` frames may
   carry `0x00`. If true, "marker" may be a length, flag or terminator field
   rather than a constant.
4. **Parameter/configuration commands.** Unresolved upstream and unresolved here.
   The highest-value unknown, because it is where integration time and averaging
   would live — the only things that could change the ~1 s/reading verdict.
