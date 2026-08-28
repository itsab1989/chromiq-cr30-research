# PLATFORM_SUPPORT.md

## The headline: macOS needs no driver

**VERIFIED, macOS 15.7.9 (24G830), arm64, 2026-08-28.**

The CR30 enumerates and is driven **natively by macOS with nothing installed**:

```
USB device : "CH554_CDC"  idVendor 0x1A86  idProduct 0x7523
             bDeviceClass 0xFF (vendor-specific), bDeviceProtocol 0x02
driver     : com.apple.DriverKit-AppleUSBCHCOM   <- Apple's own, built in
             IOUserSerial -> IOSerialBSDClient
node       : /dev/cu.usbserial-10
```

`systemextensionsctl list` shows **no third-party system extension** for this
device, and `kmutil showloaded` shows **no CH34x/CP210x/FTDI kext**. The
matching personality is Apple's shipped DriverKit CH34x driver.

### This falsifies ChromIQ issue #159 §9b

Issue #159 states the device "is not natively supported on macOS", that a
CH340/CP210x bridge "needs a kernel extension", and that the protocol work
should therefore **start on Windows**. On macOS 15.7.9 that is **DISPROVEN**:
the bridge is a CH34x, Apple ships the driver, and the serial node appears on
plug-in.

**Recommendation: macOS is the USB reverse-engineering platform.** It is where
the device works with fewest moving parts and where the eventual ChromIQ user
runs anyway.

### ⚠ Scope, corrected 2026-08-28 by `[CR30-SKEPTIC]`

The dext is **a hard-coded allow-list of exactly two product IDs**, not general
CH34x support. From
`/System/Library/DriverExtensions/com.apple.DriverKit-AppleUSBCHCOM.dext/Info.plist`
on this machine:

```
DriverKit-AppleUSBCHCOM        idVendor 6790 (0x1A86)   idProduct 29987 (0x7523)
DriverKit-AppleUSBCHCOM-1A86   idVendor 6790 (0x1A86)   idProduct 21972 (0x55D4)
OSMinimumDriverKitVersion      24.6
```

It works for us **solely because this unit's bridge reports `0x7523`**. A CR30
shipped with a CH343/CH347 bridge on a third PID would not bind and would need
a vendor driver.

The previous claim that Apple's driver "has shipped since macOS 11" is
**withdrawn** — nothing on this machine supports it, and the part that matters
is the *PID list*, which may differ between releases. Any host can check in one
line:

```bash
plutil -p /System/Library/DriverExtensions/com.apple.DriverKit-AppleUSBCHCOM.dext/Info.plist \
  | grep -E 'idVendor|idProduct'
```

Correct wording: **no driver is needed on macOS 15.7.9 arm64 for VID `0x1A86`
PID `0x7523`, because Apple's shipped DriverKit dext matches that PID
explicitly.** That is still enough to falsify #159 §9b for this unit.

## Transport × platform

| | Windows (ARM VM) | macOS 15.7.9 | Linux |
|---|---|---|---|
| **USB serial** | untested here; prior art works on x64 COM ports | **VERIFIED working, no driver** | expected — `ch341` is in-kernel (untested) |
| **BLE** | VMware passthrough is a known risk | untested; `bleak` is native, no driver needed | untested |

## Windows ARM

Not yet characterised. Two things to establish, in this order of value:

1. Does the CR30 enumerate at all, and as what? (Device Manager → hardware IDs.)
   Windows ARM64 ships an inbox `usbser`/CH34x driver in recent builds; whether
   it binds to PID 0x7523 is the question.
2. Only then: what exactly does the ColorQC2 driver install fail with?

**A ColorQC2 driver failure is not a CR30 protocol failure**, and with USB
already working on macOS, Windows is no longer on the critical path for USB.
Its remaining value is (a) sniffing the vendor application to find the
undecoded parameter commands, and (b) confirming cross-platform portability.

## Implementation consequences

- Device discovery must not hard-code `COM3` (every published capture does).
- On macOS, match on `/dev/cu.usbserial-*` **plus** VID/PID `0x1A86:0x7523`.
  The product string `CH554_CDC` is a bridge identifier, not a CR30 identifier —
  any CH34x device shows it, so it must not be used to identify a CR30.
  **The only trustworthy identification is asking the device: `AA 0A 00 00`
  returns the ASCII model string `CR30`.**
- Baud rate must not be exposed as a setting (`PROTOCOL.md` §4). Note the
  *observation* (identical replies at five rates) is VERIFIED while the
  *conclusion* (the device discards line coding) is only PROBABLE — it is
  equally explained by Apple's driver never emitting the CH34x divisor request.
  `EXP-USB-007` decides. The implementation consequence is the same either way.
- **The port must be excluded from Argyll's serial scan once identified.**
  ChromIQ deliberately keeps `/dev/cu.usbserial-*` in that scan
  (`ChromIQ/core/argyll_runner.py:43`), so Argyll writes foreign ASCII probes
  to a plugged-in CR30 on every measurement start. `ARGYLL_EXCLUDE_SERIAL_SCAN`
  already exists as the mitigation. See `INTEGRATION.md` §8 and `EXP-USB-008`.
