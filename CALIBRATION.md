# CALIBRATION.md

**Status: not started — and the prior art's premise is already wrong.**

## ⚠ DO NOT recalibrate this unit — standing instruction

Not before `EXP-CAL-002`, and not casually at any point. Four reasons, and the
first is the one that bites:

1. **It destroys the evidence.** `EXP-CAL-002` exists to detect whether the
   stored calibration moved. Recalibrating first erases the very difference it
   measures, and the question becomes permanently unanswerable.
2. **It invalidates the corpus.** Every spectrum captured so far — the air and
   paper controls, the repeatability set, the rank-analysis patches, both gated
   runs — shares one calibration state. Recalibrating makes none of them
   comparable with anything measured afterwards, including the `EXP-SPEC-001`
   rank work that depends on a consistent set.
3. **Nothing indicates it is needed.** Air reads 0.002 %, paper 85.84 %, and
   repeatability is 0.056 % worst-band SD. That is a healthy instrument.
4. **The procedure is not established.** There is no calibration entry in the
   device UI, there is no black tile on this unit, and `BB 10` / `BB 11` have
   never been sent to it. Doing it blind is exactly what `CLAUDE.md` §11
   forbids.

If a genuine drift is ever demonstrated, recalibration becomes a *designed
experiment* with a recorded before-state — not a remedy applied on suspicion.

## ⚠ This unit has NO black tile — operator report, 2026-08-28

Reported by the device's owner:

> *"The cap that magnetically attaches to the instrument contains the white
> tile, but I don't see a black one anywhere. When the cap is attached, or any
> other magnet, the device takes the reading as a calibration (at least
> sometimes)."*

**Confidence: CORROBORATED** — a direct observation of the physical device,
consistent with the prior art's own claim that cap presence is sensed by a hall
sensor, but contradicting its assumption of a *separate black tile*.

Two consequences, both of which changed the experiment design:

1. **`BB 10` ("black calibration") has no established procedure on this unit.**
   Sending it blind, with no black reference to present, could leave the stored
   calibration in an unknown state. It is therefore **not sent** in the default
   session. `tools/run_human_session.py` gates both calibration writes behind
   `--stage-b-calibration`.
2. **The magnet is a confound for any control that uses the cap.** The original
   design used "measure on the white tile" as its positive control and "measure
   on the black cap" as its negative — both require the cap, so if attaching it
   converts a reading into a calibration, **both controls would have measured
   the wrong thing while appearing to work.** They were replaced with
   **open air** (low) and **plain paper** (high), neither of which involves a
   magnet.

**HYPOTHESIS** (untested): black/dark calibration on this device is not a user
action with a black tile at all — it may be performed internally with the
illumination off, either on demand or as part of every measurement. Many modern
45°/0° instruments work this way. If so, `BB 10` may do something other than
what the prior art labels it.

**HYPOTHESIS** (untested): the intended user flow is *attach cap → press button
→ device white-calibrates itself*, with the hall sensor telling the firmware
that what it is looking at is the white reference. The operator's report is
exactly what that design would feel like in use.

The passive magnet phase in stage A tests this **without sending anything**: the
cap goes on, we listen for unsolicited traffic and then re-read device state.
Result: **zero unsolicited bytes, no job-record change, unchanged fingerprint**
(`EXP-MEAS-001`). The magnet does not reach the wire.

## ⚠ With a magnet attached, the device stops measuring — operator report, 2026-08-28

> *"Whenever a magnet is attached the Lab values on the screen are the same.
> Even when I put on the cap upside down, although it is green on the other
> side instead of white like the tile."*

**Confidence: CORROBORATED** (direct observation, with a built-in control — the
operator changed the target from white to green and the reading did not move).

This is the strongest evidence yet about the hall sensor, and it **rules out the
reading being a measurement at all**. A device calibrating against what it sees
would produce a *different* result for a green surface than for a white one. An
identical result for both means the displayed value **does not depend on the
optical input**. So with a magnet present the device is either:

- displaying a **stored constant** (most likely the white reference, or a fixed
  "calibrated" result such as L\*=100, a\*=0, b\*=0), or
- **refusing to measure** and holding a previous or default value.

**Either way it is not measuring.** That reframes the operator's original report:
the device is not "taking the reading as a calibration" in the sense of
recalibrating to the target — it is entering a mode where the optical path is
ignored.

**This is good news for calibration safety.** If the device does not calibrate
against whatever the magnet is holding, then an accidental cap attachment cannot
corrupt the stored white reference — which was the risk that gated stage B.

**Open, and cheap to settle:** what *are* the Lab values shown with a magnet
attached? If they read approximately L\*=100, a\*=0, b\*=0 the "stored white
reference" reading is essentially confirmed. Asked of the operator.

## The hall sensor is POSITIONAL — operator refinement, 2026-08-28

> *"With the cap on the wrong way, or another magnet, it does not always show
> the values for the white tile. It seems the magnet must be in the correct
> position for this to happen. I might need a few attempts to reproduce this."*

**Confidence: CORROBORATED.** This explains the "at least sometimes" in the
original report: the behaviour is **positional, not intermittent**.

**It does not weaken the previous conclusion.** In the reversed-cap trials where
the effect *did* appear, green was under the aperture and the reading was still
the white-tile value — so when the sensor engages, the optical input is ignored.
What is new is that engagement depends on magnet placement.

⚠ **It does change the experiment.** `EXP-MEAS-002` originally assumed that
attaching the cap engages the gate. If it does not, a "USB measured normally"
result is **ambiguous** — bypassed gate, or gate never engaged? That is a probe
that cannot distinguish its own hypotheses. The experiment now **confirms
engagement on the device's own display first**, retrying as often as needed, and
records every attempt. A run that never engages is recorded as such rather than
reported as a measurement.

It also relocates the evidence: the operator sees the canned value after
**pressing the device's own button**, so a gated *button* measurement is
directly capturable over USB — the unsolicited frame is recorded, then the
chunks are fetched, before any host trigger is sent.

**Open, needs a protocol test** (`EXP-MEAS-002`, specified, unrun): does a
*host-triggered* measurement with the magnet present return a canned spectrum
too, or does the USB path bypass the hall-sensor logic entirely? The two answers
have opposite implications for a live ChromIQ backend — if the USB path is also
gated, a user who leaves the cap on gets silent, plausible, wrong data.


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
