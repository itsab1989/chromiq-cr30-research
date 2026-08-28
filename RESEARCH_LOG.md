# RESEARCH_LOG.md

Chronological. Newest last.

---

## 2026-08-28 — Session 1 (coordinator, macOS host)

**Starting position.** ChromIQ issue #159 says nobody has the device, nothing is
hardware-verified, macOS probably needs a kernel extension, and the protocol
work should start on Windows.

**What actually happened.** Within the first environment check the device turned
out to be **already plugged into the macOS host and already enumerated**, with a
serial node present. Three of the issue's platform assumptions fell in the first
ten minutes.

### Findings, in order

1. **macOS needs no driver.** `ioreg` shows the serial node is provided by
   `com.apple.DriverKit-AppleUSBCHCOM` — Apple's own built-in CH34x DriverKit
   extension. `systemextensionsctl` shows no third-party extension;
   `kmutil showloaded` shows no CH34x kext. VID/PID `0x1A86:0x7523`, product
   string `CH554_CDC`. → **DISPROVES ChromIQ #159 §9b.**

2. **ArgyllCMS 3.5.0 has no CR30 support.** No CHNSpec, no `0x1A86`, no driver.
   The only `cr30` grep hits are autotools `config.sub` noise. Argyll is prior
   art for serial-transport *patterns* only, not for this protocol. Recorded as
   a firm negative so nobody re-runs the search.

3. **The device answers, and says `CR30`.** `EXP-MAC-USB-001`. Four identity
   sub-commands, four 60-byte replies, model string `CR30` at offset 39. First
   hardware-verified fact in the whole effort.

4. **Baud rate is not a protocol parameter.** Byte-identical replies at
   9600/19200/38400/57600/115200. This resolves the prior art's own internal
   inconsistency (captures at 115200 and 9600, code defaulting to 19200): all
   are right, because none reach a UART.

5. **The published checksum is wrong.** All four device frames fail the itohio
   rule by exactly +1 and satisfy `sum(0..58) mod 256`. The prior art omits the
   marker byte (`0xFF ≡ -1`) and patches the resulting off-by-one with a
   `0xBB`-only special case, in the wrong place.

6. **The device ignores request checksums entirely.** `EXP-USB-002`: correct,
   prior-art, and three garbage checksum values all produce normal replies.
   This is *why* finding 5 went unnoticed for so long — on transmit the error
   has no consequence. Verified for `AA 0A 00` only; not generalised to `0xBB`.

**Method note.** The first redaction leak-check was worthless — it grepped a
hex-encoded capture for an ASCII string, which can never match and therefore
"passes" unconditionally. Re-run against the hex form it showed 5 hits in raw
and 0 in public, i.e. the redaction was proven to actually do something.

**Repository established**, documents written, coordination issue opened, two
expert agents briefed.
