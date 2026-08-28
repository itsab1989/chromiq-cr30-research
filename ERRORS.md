# ERRORS.md

**Status: one finding.**

## VERIFIED

**The device does not validate request checksums** (`EXP-USB-002`). Requests
with correct, prior-art, and three garbage checksum values all produced normal
replies. Implication: the transport gives **no transmit-side error detection**.
Corruption on the way to the device will be silently acted upon.

This raises the importance of receive-side validation and of the device's own
state reporting.

## Robustness requirements for the reference implementation

Non-negotiable, from `CLAUDE.md` §14:

- A short, truncated or malformed frame **fails loudly and diagnostically**.
- A checksum mismatch on a received frame is an error, never a warning.
- Partial spectral data is **never** rounded up into a valid measurement. The
  prior art's `_read_all_chunks` `break`s on a missing chunk and
  `_parse_spd_data` then silently returns without setting `result["spd"]` —
  a caller that does not check gets a measurement with no spectrum. **This
  pattern must not be reproduced.**

## To test safely

Unplug/reconnect · device sleep/wake · premature read · timeout · truncated
response · injected checksum failure · repeated trigger · trigger while already
measuring · stale calibration · calibration cap left on · communication
interrupted mid-chunk.

Nothing destructive: no firmware writes, no blind calibration-storage writes,
no high-volume garbage traffic (`CLAUDE.md` §11).
