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
