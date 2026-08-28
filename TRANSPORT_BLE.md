# TRANSPORT_BLE.md

**Status: not started.** Nothing here is verified.

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

macOS is BLE-capable natively (controller `BCM_4388`, GATT among its supported
services) and `bleak` needs no driver, so discovery can start on the macOS host.
If GATT enumeration proves insufficient, an Android HCI snoop log from the
vendor app is the next step — and that requires a phone, which is a human action.

**Do not fight VMware Bluetooth passthrough.** If Windows BLE is unreliable,
move the experiment to the macOS host and record the transition.

## Redaction

The device's Bluetooth address is a unique identifier. It goes in
`LOCAL_DEVICE_IDS.md` (gitignored), never into a committed document.
