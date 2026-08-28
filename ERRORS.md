# ERRORS.md

**Status: one finding.**

## PROBABLE — downgraded by the session-2 audit

**The device does not validate request checksums** (`EXP-USB-002`). Requests
with correct, prior-art, and three garbage checksum values all produced normal
replies. Implication: the transport gives **no transmit-side error detection**.
Corruption on the way to the device will be silently acted upon.

⚠ **The experiment cannot exclude its strongest rival.** All five cases used
the same sub-command (`AA 0A 00`), so a device that validated, rejected, and
replayed its last reply produces a byte-identical transcript. A second rival:
the device may never read byte 59 at all. `EXP-USB-006` decides both — vary the
sub-command, then truncate the request.

**The implementation consequence is unchanged either way:** there is no
transmit-side error detection to rely on. Corruption on the way to the device
will be silently acted upon, whether because the checksum is ignored or because
a stale reply is returned. Receive-side validation and the device's own state
reporting carry the whole load.

## Robustness requirements for the reference implementation

Non-negotiable, from `CLAUDE.md` §14:

- A short, truncated or malformed frame **fails loudly and diagnostically**.
- A checksum mismatch on a received frame is an error, never a warning.
- Partial spectral data is **never** rounded up into a valid measurement. The
  prior art's `_read_all_chunks` `break`s on a missing chunk and
  `_parse_spd_data` then silently returns without setting `result["spd"]` —
  a caller that does not check gets a measurement with no spectrum. **This
  pattern must not be reproduced.** `tools/decode_spectra.py` shows the
  alternative: it raises `SpectrumError` naming the missing chunks rather than
  returning a short list.
- **The spectral axis is read from the frame, never assumed.** The `BB 01 09`
  header declares start/count/step (`PROTOCOL.md` §7.2). A decoder that
  hard-codes 400–700 nm at 10 nm will silently mislabel every band on a device
  that reports anything else. Assert the header; fail on a mismatch.
- **A checksum rule that is right on every frame we have seen can still be
  wrong.** Fifteen rules fitted session 1's four frames. `src/cr30/frame.py`
  says "VERIFIED against every device-originated frame captured so far", which
  is true and was not sufficient. Keep `tests/test_checksum_rule_space.py`
  alive: it fails if a future capture makes more than one rule fit again.

## Four open defects in `src/cr30/` — filed by `[CR30-SKEPTIC]`

1. **`Frame.parse(data, verify=False).to_bytes()` silently repairs a corrupt
   frame.** `Frame` does not store the received checksum and `to_bytes()`
   recomputes it. Demonstrated: a frame with a corrupted payload byte comes back
   out with a *valid* checksum (`0x09` → `0x7E`). This is exactly what
   `CLAUDE.md` §14 forbids, one keyword argument away.
2. **Identity fields are fixed-length because this unit's values are.**
   `_ascii(payload, 39, 4)` makes `is_cr30()` true for any model whose name
   merely *starts* with `CR30`; `_ascii(payload, 9, 10)` truncates a longer
   device id silently; `errors="replace"` substitutes silently. Read to the NUL
   inside a bounded region and compare the whole field.
3. **`parse_identity()` never checks the echoed sub-command**, though
   `PROTOCOL.md` §6 records that the reply echoes it and calls it free
   request/response correlation. A mis-keyed dict parses fields from the wrong
   frame, silently.
4. **`test_roundtrip_is_byte_exact` is near-vacuous** — `parse` has already
   verified the checksum and `to_bytes` regenerates it, so the test can only
   catch a field-slicing error.

## To test safely

Unplug/reconnect · device sleep/wake · premature read · timeout · truncated
response · injected checksum failure · repeated trigger · trigger while already
measuring · stale calibration · calibration cap left on · communication
interrupted mid-chunk.

Nothing destructive: no firmware writes, no blind calibration-storage writes,
no high-volume garbage traffic (`CLAUDE.md` §11).


---

## Session 2 additions — `[CR30-USB]`, 2026-08-28

### VERIFIED — the checksum is not validated on `0xBB` either

`EXP-USB-002`'s caveat ("verified for one command; a side-effecting command
might be validated") is **discharged**. `EXP-USB-003` varied only byte 59 across
correct / ±1 / `0x00` / `0xFF` / `0x42` on `BB 28` and on `BB 13` — the latter a
command the device demonstrably acts on — and every case returned a
**byte-identical reply body**. There is no transmit-side error detection
anywhere in this protocol.

### VERIFIED — the device ECHOES commands it does not implement

The worst failure mode found this session, because it does not look like a
failure. `BB 28 00 xx` and `BB 17 00 00` return an exact copy of the request
with byte 58 set and byte 59 recomputed. **The device wrote nothing**: a request
carrying `A5 5A` at offsets 53–54 got those bytes back.

Consequences, all of them non-obvious:

- **A 60-byte reply is not evidence a command exists.** Any survey that counts
  replies invents a command set. This is why `EXP-USB-004` must compare
  *content*, not reply presence.
- **A caller that reads a field out of an echo reads its own request back.**
  If the request was all-zero, the "response" is a plausible-looking block of
  zeros — a status of `0x00`, a count of 0, an empty parameter list.
- itohio's "query parameters" (`BB 28`) and "initialize device" (`BB 17`) are
  echoes on this firmware. They are in the published handshake because they
  reply, not because they work.

`src/cr30/session.py::is_echo()` is the discriminator and
`Session.transact_checked()` raises `EchoedCommandError` rather than returning
an echo. **Any new command decoder must call it first.**

### VERIFIED — silence is the failure mode for a malformed write

Not an error, not a NAK: **silence**. A frame split across two `write()` calls,
or two frames in one call, produce **zero bytes**. An implementation that
retries on timeout will loop; one that reports "wrong baud rate" will send the
user chasing a setting that does not exist (`PROTOCOL.md` §3). The transport
must name the real cause: *the frame did not reach the device as one 60-byte
write*.

Recovery is clean — the very next single-frame write is answered normally, with
no port reopen (`EXP-USB-005b`).

### VERIFIED — a reply's unwritten bytes are the caller's own

`EXP-USB-006`. A reply is the request buffer mutated in place. Before calling
any offset a device field, **check what the request had there**. A decoder
tested only with all-zero requests cannot tell a device zero from its own.


---

## Session 3 — defects filed by `[CR30-SKEPTIC]`, 2026-08-28

Each has a regression test built from a real capture. Numbered for the record so
they cannot quietly disappear.

| # | Defect | Where | State |
|---|---|---|---|
| 5 | `read_stored()` **assumed the spectral axis** (400/31/10) and never fetched the header — the exact thing this file's own "Robustness requirements" forbids by name | `usb_measure.py` | **FIXED** — takes `button_header`, reads the axis from it, refuses an unknown axis; records `axis_source` when none is supplied |
| 6 | The unsolicited button header's **offset-24 magnet flag was discarded**, though it is the only unit-independent magnet check and the only one that works on the first reading | `usb_measure.py`, `measurement.py` | **FIXED** — `button_header_is_gated()`, `Measurement.gate_flag`, checked first in `check_usable()` |
| 7 | The magnet error message told the user to **"read again"** after an event that may have destroyed their white reference | `measurement.py` | **FIXED** — now STOP + RECALIBRATE, with the reason |
| 8 | The **D50 illuminant table was wrong from 610 nm**; its last five entries were D65's 600–640 nm values, copied in. Error 13.4 units (13 %) at 670 nm | `colour.py` | **FIXED**, with a mutation test |
| 9 | `validate_illuminants()` **passed that table** at `tol=0.006` (it scored 1.5e-3 where a correct table scores ~1e-4). A control that cannot fail is not a control | `colour.py` | **FIXED** — `tol=0.001`, and `tests/test_colour_tables.py` proves the mutation lands |
| 10 | `colour.py`'s docstring said the observer was **CIE 1931 2°** while the code selected **10°** | `colour.py` | **FIXED**, and 10° is now proved rather than asserted |
| 11 | **The test suite did not run at all on a fresh clone.** Three modules read `captures/raw/`, which is gitignored; `pytest` aborted at collection with `FileNotFoundError` and executed **zero** tests | `tests/` | **FIXED** — fall back to the redacted public copies; 455 pass on a public-only tree |
| 12 | `TILE_SIGNATURE` is a **per-unit factory constant** hard-coded with a 0.05 tolerance; the only other CR30 we have data for differs by 4.69 %R | `measurement.py` | **DOCUMENTED, not fixed** — needs a per-unit learn step, which is a design decision |
| 13 | The **reflectance bounds accept a real corrupted reading** (105.47 %R) and cannot see the deflating half of the failure at all | `measurement.py` | **DOCUMENTED, not fixed** — deliberately: retuning a one-sided test does not make it two-sided |
| 14 | The **BLE reply has no integrity check** — no checksum, no length equality, `find()` takes the first header in the buffer — and the vendor capture contains a truncated zero-filled reply that passes all of it | `ble.py`, `device.py` | **OPEN — `[CR30-USB]`.** Four concrete fixes in `TRANSPORT_BLE.md` |
| 15 | `LAB_AT`/`MIN_REPLY` are hard-coded for 31 bands while the spectrum uses the device-declared count | `ble.py` | **OPEN** |
| 16 | `Measurement.validate()` accepts a device `L*a*b*` of exactly `(0,0,0)` and a spectrum with trailing exact zeros | `measurement.py` | **OPEN** |
| 17 | `metadata["warning"]` is set by `validate()` and **no caller ever reads it** | `measurement.py`, `device.py` | **OPEN** |

⚠ Defects 12 and 13 are left open **on purpose**. Both are threshold/behaviour
questions that change what the library refuses, and `CLAUDE.md`'s standing
practice is that a fault which contradicts a documented decision is reported and
approved, not silently corrected. The evidence for both is in
`MEASUREMENT.md` and pinned in `tests/test_skeptic_guard_gaps.py`.


---

## The device can accept commands over USB and do nothing with them

**VERIFIED 2026-08-28**, live, after a session of repeated open/close cycles.

Symptoms, in the order they misled us:

| Observation | What it seemed to mean | What it actually meant |
|---|---|---|
| 0 bytes to `AA 0A 00 00` | the instrument is asleep | it was awake — advertising, and a BLE read worked |
| display shows `U` | the USB link is up | a cable is plugged in, nothing more |
| the port node exists | there is a device to talk to | the node belongs to the CH34x bridge, not the CR30 |
| **the instrument BEEPS on a trigger** | it received and measured | it received; it did **not** measure |

The last row is the one that matters. A beep looked like proof the command had
been acted on, so the fault seemed to be in the reply path only. But reading the
device's **stored measurement over BLE** showed it unchanged — still the tile
constant from hours earlier. The trigger produced no reading at all.

So the instrument had entered a state where its USB command interface **accepts
bytes, acknowledges audibly, and processes nothing**. Neither a cable replug nor
any DTR/RTS combination cleared it (all four states tested, 0 bytes each).

### What this means for an implementation

1. **A beep is not an acknowledgement.** Nothing audible tells the host a
   command was honoured. Only a reply does.
2. **Verify by reading back, not by the absence of an error.** The check that
   diagnosed this — take the reading the device believes it holds and see
   whether it changed — is the only one that distinguished "did nothing" from
   "did it and could not tell me".
3. **The two transports fail independently.** BLE stayed perfectly healthy
   throughout, which is both the diagnostic that cracked this and a genuine
   robustness option: a backend that can fall back to the other transport is
   strictly better placed than one that cannot.
4. **A power cycle of the instrument clears it — CONFIRMED.** Long-press to
   power off, press to power on, USB cable left connected: the identity query
   answered 60 bytes with the model string immediately afterwards. A cable
   replug does NOT clear it, because it resets the host end and not the
   instrument's firmware state.

**Not established:** what puts it in this state — repeated open/close cycles, a
specific command, or a BLE session overlapping a USB one. It followed an
afternoon of heavy probing plus several ChromIQ launches whose bridge opened the
port, so frequency is the leading suspect.

**For the user-facing message**, the order that matches the evidence is:
power-cycle the instrument first (the confirmed cure), then the cable, then the
phone app, then permissions. The current wording leads with the cable and does
not mention a power cycle at all.
