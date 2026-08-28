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

Scope note: verified on macOS 15.7.9 arm64. Apple's CH34x DriverKit driver has
shipped since macOS 11, but the minimum version supporting *this* PID has not
been tested here.

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
- Baud rate is irrelevant (`PROTOCOL.md` §3) — do not expose it as a setting.
