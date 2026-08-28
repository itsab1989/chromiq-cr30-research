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

---

## Session 2 — 2026-08-28 — `[CR30-SKEPTIC]` adversarial audit (no hardware)

Attacked all nine session-1 "VERIFIED" findings by re-deriving them from raw
evidence. **Seven conclusions survive; four were filed above the confidence
their evidence bought; one piece of published evidence is circular.**

**The circular evidence.** `tools/redact.py` recomputes byte 59 with the rule
under test, so two of the four published identity frames prove nothing about
the checksum. The public claim "4/4 device frames" is really 2/4, one of them
56/60 zero bytes. The raw frames do satisfy the rule — the *published evidence*
was manufactured by our own tool.

**The checksum was not determined by that capture.** Fifteen contiguous
additive rules fit the four frames exactly, plus 2^12 subset variants, because
bytes 0/1/3 are constant, byte 58 is constant `0xFF` and bytes 55–57 are zero.
Whole families *were* excluded — XOR, negated sums, Fletcher, position-weighted
sums, and CRC-8 over 14 080 parameterisations — so "an additive byte sum" was
earned; "this range with this constant" was not.

**What settled it.** Mined ten Eltima sniffer dumps in `itohio/color-science`
that session 1 never opened: **6252 structural windows → 2721 frames, 260
unique**, vendor application, second unit, Windows. Exactly **one** contiguous
rule survives. The discriminating frames are the `0xBB 0x01 0x09` headers with
marker `0x00`, a case our own captures could never produce.

**Everything else the corpus gave, free:** the complete vendor command
vocabulary (8 `cmd` bytes — the basis of `SAFETY_ENVELOPE.md`); calibration
commands corroborated; the payload extends to byte 57 (prior art disproven);
the "20 unexplained bytes" are chunk padding and do not exist; the measurement
header declares the spectral axis, matching the vendor app's own JSON export;
byte 58 is a flag, not a constant; and **no sensor-parameter command exists
anywhere in ten vendor sessions, including the one named `param change.spm`** —
which turned the "highest-value unknown" into a negative result.

**EXP-SPEC-001.** 58 unique spectra decoded from that corpus. No singular-value
cliff at 8, 11, 13 or 14 channels (largest gap anywhere 0.63 decades), and
high-order basis vectors alternating band-to-band where a ~20 nm FWHM filter
basis cannot exceed ~0.1. **The linear form of the AS7341 reconstruction
hypothesis is disproven.** Nonlinear reconstruction is not excluded by a rank
test; EXP-SPEC-001a/b are specified in `MEASUREMENT.md` to close it.

**Argyll.** Verified the "no CR30 support" negative three ways: the `devType`
registry every instrument must join, zero VID/PID/vendor-string hits tree-wide,
and the serial identification path. It also exposed a live hazard —
`fast_ser_dev_type()` writes foreign ASCII probes to any `/dev/cu.*usbserial*`
during plain enumeration, and ChromIQ deliberately keeps that port in the scan.
**A CR30 is already being probed on every ChromIQ measurement start.**

**ChromIQ.** Read the source rather than issue #159. Two of #159's claims are
confirmed, two disproven. `INTEGRATION.md` written from scratch with file and
line citations; the recommended seam is an import, not a driver, and it is
challenged in §7 of that document.

**Delivered:** `SAFETY_ENVELOPE.md` (unblocks EXP-USB-004, re-scoped from a
sweep to attended single probes); three hardware-free tools; two public
captures; `tests/test_checksum_rule_space.py` and
`tests/test_spectral_independence.py`; 331 tests pass.

**Next:** `EXP-USB-005` (latency baseline — a precondition of the envelope),
then `EXP-USB-006`/`007` (the two downgraded findings, cheap), then
`EXP-CAL-001`/`EXP-MEAS-001` on our unit. Highest value for lowest risk:
**more vendor sniffing on Windows**, which widens the envelope without sending
a byte.
