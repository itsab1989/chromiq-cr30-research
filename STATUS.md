# STATUS.md

**Updated:** 2026-08-28 · **Session:** 1 · **Platform:** macOS 15.7.9 arm64

## One line

USB communication with the CR30 is **established on macOS with no driver
install**; the device self-identifies as `CR30`; the published checksum rule has
been **disproven** and replaced. No measurement or calibration has been
attempted yet.

## Verified facts

| Fact | Evidence |
|---|---|
| macOS drives the device natively via Apple's built-in `AppleUSBCHCOM` DriverKit extension — no kext, no vendor driver | `ioreg` / `systemextensionsctl` / `kmutil`, `PLATFORM_SUPPORT.md` |
| USB id `0x1A86:0x7523`, product `CH554_CDC`, **no USB serial number** | `TRANSPORT_USB.md` |
| Serial node `/dev/cu.usbserial-10`, 8N1, no flow control | `EXP-MAC-USB-001` |
| **Baud rate is not a protocol parameter** — identical replies at 9600…115200 | `EXP-MAC-USB-001` |
| Frames are exactly 60 bytes; byte 58 = `0xFF`, byte 59 = checksum | `EXP-MAC-USB-001` |
| **Checksum = `sum(bytes 0..58) mod 256`** | `EXP-MAC-USB-001`, 4/4 device frames |
| **Published checksum rule is DISPROVEN** (off by +1, omits the marker) | `PROTOCOL.md` §2 |
| **The device does not validate request checksums** | `EXP-USB-002` |
| Device reports model string `CR30` via `AA 0A 00 00` | `EXP-MAC-USB-001` |
| Identity field offsets for sub-commands `0x00`–`0x03` | `PROTOCOL.md` §4 |
| Device is silent when idle (1 s window) | `EXP-MAC-USB-001` |
| **ArgyllCMS 3.5.0 contains no CR30 support at all** | `RESEARCH_LOG.md` |

## Contradictions found in ChromIQ issue #159

| Issue #159 says | Reality |
|---|---|
| §9b "not natively supported on macOS", needs a kernel extension | **DISPROVEN** — Apple ships the driver |
| §9b "start on Windows, and why" | **Superseded** — macOS is the better USB platform |
| §1 "captures show 115200 (one at 9600; code defaults to 19200)" — treated as ambiguity | **Resolved** — baud is ignored entirely |
| §1 "60-byte packets and a checksum" (via itohio) | Frame size confirmed; **checksum rule was wrong** |

These are recorded here, **not** written back to ChromIQ (`CLAUDE.md` §2).

## Not yet established

Calibration · measurement · spectral decoding · button behaviour · parameter
and configuration commands · `0xBB` command class · error and timeout behaviour ·
reconnect and sleep/wake · BLE anything · whether the 31 bands are independent
measurements or a reconstruction · the ChromIQ integration boundary.

## Blockers

**None technical.** The next experiments (`EXP-CAL-001`, `EXP-MEAS-001`) need a
human to place the device on the calibration tiles and on a patch. Everything
that can be done without the human has been queued as non-hardware work.

## Hardware lease

Not held. `.hardware-lock/LEASE` is free.

## Reference implementation

`src/cr30/` — framing and identity only. 57 replay tests pass with **no hardware
attached**, built from real captures.

```bash
.venv/bin/python -m pytest tests/ -q
```
