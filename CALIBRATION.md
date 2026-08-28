# CALIBRATION.md

**Status: not started.**

Prior-art claim (untested here): `BB 10 00 00` = black calibration,
`BB 11 00 00` = white calibration; response payload byte 1 is a status, `0x01`
meaning success. The device ships with a white tile and a cap, and the write-up
claims cap presence is detected by a hall sensor.

## To establish by experiment

- Exact command and response for each calibration.
- Prerequisites and required order (black first, then white — per Pharmacist).
- Is calibration stored in the device, and does it survive a power cycle?
- Does it expire, and is staleness reported?
- Is white-tile presence actually detected, and how does the device respond if
  the tile is absent or the cap is left on?
- What happens if calibration is interrupted?
- What does a measurement return when calibration has never been done?

**Make calibration failures reproducible** — the failure modes matter more than
the happy path, because they are what a user will actually hit.

## Human dependency

Calibration requires physically placing the device on the black and white tiles.
That is a HUMAN ACTION (see `CLAUDE.md` §17) and must be requested with a
precise procedure. Design the experiment so that one human interaction yields
the maximum number of answers.
