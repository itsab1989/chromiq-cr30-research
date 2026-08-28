# CALIBRATION.md

**Status: not started.**

**CORROBORATED** (`PRIORART-001`, second unit, vendor traffic):
`BB 10 00 00` = black calibration, `BB 11 00 00` = white calibration. Both
appear **only** in the two vendor captures that perform a calibration, never in
a measurement or connect session. Both replies carry `0x01` at **frame offset 6
(payload index 2)** on all four occurrences.

⚠ itohio calls this "payload byte 1"; the offset is 2. And reading `0x01` as
*success* is **HYPOTHESIS**, not corroboration: **no failed calibration has ever
been captured**, so `0x01` has never been contrasted with anything. A value
that is always the same carries no information until something makes it change.
Deliberately provoking a failure (§below) is worth more than ten successes. The device ships with a white tile and a cap, and the write-up
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

⚠ **`BB 10 00` and `BB 11 00` WRITE calibration state.** They are GREEN under
`SAFETY_ENVELOPE.md` only inside `EXP-CAL-001`, with the tiles present and a
human watching — **never inside a command probe**. A survey that "just tries
them" destroys the stored calibration. They also sit numerically between the
harmless `BB 01`/`BB 0A` and the harmless `BB 13`/`BB 17`, so no "start low and
work up" heuristic protects them.

**Argyll's shape is the one to copy.** `dtp41_calibrate()` returns an
`inst_calc_cond` telling the caller what the *user* must physically do
(`inst_calc_uop_ref_white`) and the caller loops — calibration is a
negotiation, not a call. ChromIQ's engine already speaks exactly this
vocabulary, 17 conditions at
`native/chartread_helper/chromiq_cal.c:32-55`, of which `man_ref_dark` and
`man_ref_white` are the CR30's two. See `INTEGRATION.md` §9.

**Make calibration failures reproducible** — the failure modes matter more than
the happy path, because they are what a user will actually hit.

## Human dependency

Calibration requires physically placing the device on the black and white tiles.
That is a HUMAN ACTION (see `CLAUDE.md` §17) and must be requested with a
precise procedure. Design the experiment so that one human interaction yields
the maximum number of answers.
