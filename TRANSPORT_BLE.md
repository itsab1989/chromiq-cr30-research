# TRANSPORT_BLE.md

**Status: the device is FOUND and its GATT tree is mapped. It does not answer
— yet.** `EXP-BLE-001` / `-002` / `-003`, 2026-08-28, macOS host.

## The device advertises, and its own USB identity is the name — VERIFIED

```
advertised name : CM454M0223       <- byte-for-byte the string AA 0A 01 returns over USB
services (adv)  : ffe0, fee7
negotiated MTU  : 244              <- a 60-byte frame fits in ONE write; no fragmentation needed
```

**The advertised name is the device-id string we read over USB.** That is how it
was identified, and it is the cleanest possible link between the two transports.

⚠ **My name heuristic failed and would have produced a false negative.** It
flagged `65" Crystal UHD` (the substring "cr") and did **not** flag the real
device. Discovery came from recognising the USB identity string, not from the
search. Recorded because a wider hint list would not have helped — the fix is to
match on the device's own reported id, which only the USB work made available.

`fee7` is a Tencent/WeChat IoT service UUID, consistent with the manufacturer's
advertised **WeChat mini program** support. Only `ffe0` appeared in the connected
GATT tree.

## GATT — VERIFIED

| Characteristic | Properties |
|---|---|
| `ffe1` | write · **notify** · write-without-response |
| `ffe2` | write · **notify** · write-without-response |
| `ffe3` | write · write-without-response |

**No characteristic has `read`.** This is a write/notify transport — commands
out by write, responses back by notification — the conventional BLE-UART shape
(`ffe0`/`ffe1` is the classic HM-10 style profile). Three characteristics rather
than one is unusual and unexplained.

## It does not respond — DISPROVEN that BLE is simply "the same, over BLE"

The identity command `AA 0A 00 00` — read-only, no side effects, sent hundreds
of times over USB — was written to **every** characteristic in **both** write
modes, with notifications subscribed on `ffe1` and `ffe2`:

| Channel | write-without-response | write-with-response |
|---|---|---|
| `ffe1` | 0 bytes | 0 bytes |
| `ffe2` | 0 bytes | rejected (ATT error 14) |
| `ffe3` | 0 bytes | 0 bytes |

A 4-second passive listen returned nothing either. **Every write was accepted;
nothing ever came back.**

So the claim in ChromIQ issue #159 that BLE "probably" carries the same 60-byte
packets is **not supported** on present evidence. It is not yet *disproven*
either — see below. This is exactly why the standing rule is that it must be
proved, not assumed.

## The untested variable, and it is the obvious one

**The device was connected to USB throughout.** Devices of this class commonly
route the protocol to whichever transport is active, with USB taking priority —
which would explain accepted writes and total silence perfectly.

`EXP-BLE-004` is therefore: **unplug USB, leave the device on battery, retry the
identical sweep.** It needs a human, it takes one minute, and it is the single
highest-value BLE experiment available. Until it has run, no conclusion about
BLE framing is safe in either direction.

Other hypotheses, in descending plausibility, if USB-off does not fix it:
pairing/bonding required · a wake or handshake sequence must precede commands ·
Bluetooth must be enabled from the device or the vendor app first · the protocol
differs on BLE · `fee7` is the real channel and macOS is not exposing it.

The manufacturer lists USB **and** Bluetooth, with Android, iOS and WeChat
clients. iOS support **strongly implies BLE rather than Bluetooth Classic**,
because Apple restricts Classic SPP to MFi-certified hardware while BLE is open
to any app. That is an inference, not a fact.

## Why this matters less than issue #159 assumed

Issue #159 treats BLE as strategically important *because* macOS USB was
believed to need a kernel extension. **That premise is now DISPROVEN** — see
`PLATFORM_SUPPORT.md`. BLE is still worth investigating (cable-free operation,
and it is the only transport the mobile apps use), but it is **no longer on the
critical path for macOS support**.

## What must be established — none of it assumed

1. Does the device advertise at all, and under what name?
2. Must Bluetooth be enabled on the device by a button or menu action first?
3. Service and characteristic UUIDs; read/write/notify properties.
4. Pairing/bonding requirements.
5. **Whether the same 60-byte framing is carried, or whether BLE adds its own
   framing layer.** A 60-byte frame does not fit the 20-byte default ATT MTU,
   so *some* fragmentation scheme must exist. Its shape is unknown.
6. Whether commands and responses use the same characteristic pair as USB uses
   directions, and whether button events arrive as notifications.

⚠ **"BLE probably uses the same protocol" is not a result.** It must be proved
or disproved against captured traffic.

## Method

Confirmed: macOS is BLE-capable natively (controller `BCM_4388`, GATT among its supported
services) and `bleak` needs no driver, so discovery can start on the macOS host.
If GATT enumeration proves insufficient, an Android HCI snoop log from the
vendor app is the next step — and that requires a phone, which is a human action.

**Do not fight VMware Bluetooth passthrough.** If Windows BLE is unreliable,
move the experiment to the macOS host and record the transition.

## Redaction

The device's Bluetooth address is a unique identifier. It goes in
`LOCAL_DEVICE_IDS.md` (gitignored), never into a committed document.
