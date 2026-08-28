# STATUS.md

**Updated:** 2026-08-28 · **Session:** 2 (`[CR30-SKEPTIC]` audit) · **Platform:** macOS 15.7.9 arm64

## One line

USB communication is established on macOS with no driver install and the device
self-identifies as `CR30`; a **260-frame corpus of the vendor application's own
traffic** has been mined from prior art, which settles the checksum rule,
supplies the complete vendor command vocabulary, resolves three open structural
questions, and **disproves the linear form of the "31 bands are reconstructed
from ~11 channels" hypothesis**. Four session-1 findings were filed at a
confidence their evidence did not buy and have been re-worded.

## Verified facts — this unit, our own captures

| Fact | Evidence | Confidence |
|---|---|---|
| macOS drives the device natively; Apple's `AppleUSBCHCOM` dext matches VID `0x1A86` **PID `0x7523` explicitly**, by a two-entry allow-list | `PLATFORM_SUPPORT.md` | VERIFIED, narrowly scoped |
| USB id `0x1A86:0x7523`, product `CH554_CDC`, **no USB serial number** | `TRANSPORT_USB.md` | VERIFIED |
| Serial node `/dev/cu.usbserial-10`, 8N1, no flow control | `EXP-MAC-USB-001` | VERIFIED |
| Frames are exactly 60 bytes | `EXP-MAC-USB-001` + 260 vendor frames | VERIFIED |
| Device reports model string `CR30` via `AA 0A 00 00` | `EXP-MAC-USB-001` | VERIFIED |
| Identity field offsets for sub-commands `0x00`–`0x03` | `PROTOCOL.md` §6 | VERIFIED **on one unit**; lengths are lower bounds |
| Device is silent when idle | `EXP-MAC-USB-001` | VERIFIED, 1 s window only |
| Replies byte-identical at 9600…115200 | `EXP-MAC-USB-001` | VERIFIED **as an observation** |
| ArgyllCMS 3.5.0 contains no CR30 support | registry enum + zero VID/PID hits + serial-probe path | VERIFIED, three grounds |

## Corroborated — vendor traffic, a second unit

| Fact | Evidence |
|---|---|
| **Checksum = `sum(bytes 0..58) mod 256`** — the **only** contiguous additive rule surviving 260 frames spanning both start classes, both marker values and 8 command bytes | `PRIORART-001`, `tests/test_checksum_rule_space.py` |
| The complete vendor command vocabulary is 8 `cmd` bytes | `PROTOCOL.md` §5 |
| `BB 10 00` black cal, `BB 11 00` white cal; status `0x01` at frame offset 6 | `PROTOCOL.md` §5 |
| The `BB 01 09` header declares the spectral axis (`28 1f 0a` = 400 nm, 31 bands, 10 nm), matching the vendor app's own `wave_start`/`wave_number`/`wave_interval` export | `PROTOCOL.md` §7.2 |
| Chunks carry **12/12/7** floats; chunk `0x13` is not spectral | `PROTOCOL.md` §7.3 |
| Payload extends to byte **57** | `PROTOCOL.md` §7.1 |
| **The 31 bands are not a linear reconstruction from 8/11/13/14 channels** | `MEASUREMENT.md`, `tests/test_spectral_independence.py` |

## Downgraded by the session-2 audit

| Was | Now | Why |
|---|---|---|
| "Baud rate is not a protocol parameter" — VERIFIED | **PROBABLE** | host-side evidence only; equally explained by Apple's driver never emitting the divisor. `EXP-USB-007` decides |
| "The device does not validate request checksums" — VERIFIED | **PROBABLE** | cannot exclude a cached reply; every case used the same sub-command. `EXP-USB-006` decides |
| "`sum(0..58)` — 4/4 device frames" | **2/4, and 15 rules fit those** | `tools/redact.py` recomputes byte 59, so two published frames are self-consistent by construction. Settled instead by `PRIORART-001` |
| "The simple unified rule explains both classes without a special case" | withdrawn | no `0xBB` frame had been observed when it was written |
| "macOS needs no driver" | scoped to **macOS 15.7.9 arm64, PID `0x7523`** | the dext is a two-PID allow-list |
| "Parameter commands are the highest-value unknown" | **negative result** | the vendor capture named `param change.spm` contains only a job record — timestamps and a label. No sensor-parameter command exists in ten vendor sessions |

## Disproven

- itohio's `0xAA` checksum branch (`sum(0..57)`) — off by +1 on real frames.
  Its `0xBB` branch (`sum(0..57) − 1`) is **not** wrong in the way session 1
  said; it is one of the rules our own four frames could not distinguish.
- itohio's payload extent (bytes 4–55) — vendor frames carry data at byte 56.
- The prior art's "20 unexplained bytes" — they are chunk `0x12`'s padding.
- "Byte 58 is a constant marker" — `0x00` occurs on `BB 01 09` headers.
- ChromIQ #159 §9b (macOS needs a kext, start on Windows).
- ChromIQ #159's framing of instrument selection — `MeasureParams.instrument`
  is a comm-port number, not a device name (`INTEGRATION.md` §1).

## Not yet established

Calibration and measurement **on our unit** · error and timeout behaviour ·
reconnect and sleep/wake · what `BB 21 01` is · whether any sensor-parameter
command exists · BLE anything · whether the bands survive a *nonlinear*
reconstruction test · everything about accuracy.

## Blockers

**`EXP-USB-004` is unblocked** — `SAFETY_ENVELOPE.md` is published, and the
experiment is re-scoped from a sweep to individually logged single probes.
`EXP-USB-005` must run first.

`EXP-CAL-001` / `EXP-MEAS-001` / `EXP-SPEC-001a` need a human at the device.

## Hardware lease

**FREE.** `[CR30-USB]` held it through session 2 and released it. Device state
at release: plugged in, idle, port free, **identity fingerprint byte-identical
to the session-start baseline**. Nothing was written to the device — no
firmware, no calibration, no parameter. `BB 10` / `BB 11` (the calibration
writes) were never sent.

## BLE — ✅ WORKING

Read over Bluetooth from macOS with no driver and no cable. The missing
ingredient was a **single `0x01` poll byte**; BLE uses **10-byte** frames, not
USB's 60, and the same checksum rule generalises. The device transmits its own
L\*a\*b\*. BLE spectrum matches USB to 4.7e-7. See `TRANSPORT_BLE.md`.

Open: the `bb 14` command family, unexplained.

## superseded — BLE was located, mapped, not talking

Advertises as its own USB device-id · `ffe0` with `ffe1`/`ffe2` (write+notify)
and `ffe3` (write) · MTU 244 · one connection only · stops advertising when
taken. **Never answers.** Activation is a handshake the vendor app performs and
we cannot guess; six variables eliminated, capture is the next step
(`EXP-BLE-009`). See `TRANSPORT_BLE.md`.

## Reference implementation

`src/cr30/` — framing, identity, **transport (ABC + serial + replay)**,
**discovery** (the only OS-aware module) and **session** (commands, with an echo
guard). `import cr30` does not import pyserial, and a test enforces it.

**All four defects filed by `[CR30-SKEPTIC]` are fixed**, each with a regression
test: silent frame repair (`Frame.is_intact()` / `to_bytes_as_received()`);
fixed-length identity fields (now read to the NUL, with a `suspect_fields`
list and `is_cr30()` refusing a merely-`CR30`-prefixed model);
`parse_identity()` now rejects a reply whose echoed sub-command does not match
the request, and any frame known to be corrupt; `test_roundtrip_is_byte_exact`
now compares the 59 informative bytes and proves the comparison has teeth.

**`tools/redact.py` objection 1 is fixed**: every capture now publishes
`_synthesised_checksums`, naming each frame whose byte 59 the redactor rewrote,
so nobody has to rediscover that those frames are not checksum evidence. Of the
nine `EXP-*` captures, seven contain exactly one such frame and one contains none.

**406 tests pass with no hardware attached.**

```bash
.venv/bin/pip install pyserial bleak pytest numpy
.venv/bin/python -m pytest tests/ -q
```


---

## Session 2, hardware — `[CR30-USB]`, 2026-08-28

Six experiments, ~380 device transactions, no writes to the device.

| Fact | Evidence | Confidence |
|---|---|---|
| **The checksum is not enforced on the `0xBB` class either** — proved on `BB 13`, a command the device demonstrably acts on | `EXP-USB-003` | VERIFIED |
| **The device ECHOES commands it does not implement.** A 60-byte reply is not evidence a command exists | `EXP-USB-003` | VERIFIED |
| `BB 28` ("query parameters") and `BB 17` ("initialize") are echoes on this firmware — itohio's handshake is calling two commands that do nothing | `EXP-USB-003` | PROBABLE |
| `BB 13` is a real command: it writes frame offsets 5–10 | `EXP-USB-003` | VERIFIED |
| **A reply is the request buffer mutated in place.** For `AA 0A` the device writes 5–54; offsets 4, 55, 56, 57 come back holding the caller's own bytes | `EXP-USB-006` | VERIFIED |
| **Byte 58 is device-set, never echoed, never validated on the request side** | `EXP-USB-006` | VERIFIED |
| **A frame must be one `write()` of exactly 60 bytes**, or the device answers with silence | `EXP-USB-005c`, 4/4 splits | VERIFIED |
| **Two frames in one write get no reply**; recovery is immediate, no reopen | `EXP-USB-005b` | VERIFIED |
| **The 300 ms post-open settle delay is unnecessary** (10/10 at 0 ms) | `EXP-USB-005` | VERIFIED |
| **No inter-command delay is needed** (30/30 at 0 ms) | `EXP-USB-005` | VERIFIED |
| Round trip **0.767 ms** median, 1.49 ms max, over 100 transactions | `EXP-USB-005` | VERIFIED |
| **No UART is in the path**: a frame completes in 0.77 ms where 115200 baud needs 5.2 ms, and at 300 baud (2 s on the wire) it still took 0.97 ms. 7E1/8N2/7N1/8O1 byte-identical | `EXP-USB-005` | VERIFIED |
| Silent when idle over **90 s** and over 12 min of polling | `EXP-USB-005/-005c` | VERIFIED |
| **ArgyllCMS's serial device-scan probe strings are inert on a CR30** — 8 strings × 4 baud rates = 32 probes, 0 bytes back, fingerprint unchanged 32/32 | `EXP-USB-007` | VERIFIED |
| `BB 13`'s second `u32` is not a command counter, not a connection counter, not a fast clock; it steps **+361 every ~361 s** | `EXP-USB-005b/c` | DISPROVEN (three readings) / PROBABLE (slow clock) |
| What byte 5 of the `BB 13` reply (`0x51`) means | — | **NOT DETERMINED** |
