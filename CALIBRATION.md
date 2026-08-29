# CALIBRATION.md

**Status: not started — and the prior art's premise is already wrong.**

## 🔴 THE OPERATOR WAS RIGHT: magnet + measurement = WHITE CALIBRATION

**VERIFIED 2026-08-28, the hard way — we corrupted the unit's calibration.**

After `EXP-MEAS-003` (cap **reversed**, green face under the aperture), the same
plain paper that read **85.84 %** mean in `EXP-MEAS-001` reads **156.8 %**, with
bands up to 193 %. Reflectance above 100 % is physically impossible for paper.

Reconstructing the implied stored white reference from the band-by-band ratio
gives a curve peaking at **500 nm** and falling to ~70 % at 400 nm and 620–700 nm.
**That is a green spectrum.** The device's white reference was overwritten with
a measurement of the green face of the cap.

The distortion in `EXP-MEAS-003`'s own before/after patch pair and the distortion
in `EXP-CAL-002`'s paper reading have a normalised shape correlation of
**+0.964** — the same distortion, so **one event** during `EXP-MEAS-003` caused
it, and it persists.

### This reframes the "gating" result completely

The device is **not** "returning a canned value instead of measuring". It is
**performing a white calibration against whatever is under the aperture, and
reporting the nominal tile value as confirmation.** That is why the returned
spectrum is a bit-identical constant: a surface just used as the white reference
reads as the nominal reference *by definition*.

Supporting evidence: `EXP-MEAS-002` ran with the cap the **correct** way round,
did both a button press and a host trigger, and the patch afterwards was fine
(ΔE 0.438). Calibrating against the actual white tile is harmless — it restores
the correct reference. Calibrating against green is not.

### 🔴 The unresolved question, and it is the critical one for ChromIQ

`EXP-MEAS-003` performed **both** a host trigger (step 3) and a button press
(step 4) with green under the aperture. **Either could have written the
calibration**, and the data cannot separate them.

If a **host-triggered** measurement can overwrite the white reference, then a
live ChromIQ backend that sends a trigger while a magnet is nearby **destroys
the user's calibration** — far worse than merely returning wrong data, and
silent. Until this is separated, **no host trigger may be sent with a magnet
present.**

### ⚠ My own analysis error, recorded so it is not repeated

`EXP-CAL-002` classified this as *"different spot, NOT a calibration shift"*, and
before that I called the `EXP-MEAS-003` before/after difference "probable
repositioning". Both were wrong, for the same reason: **the heuristic assumed a
calibration change is spectrally neutral**, so a varying band ratio was read as
evidence *against* one. Calibrating against a **coloured** reference produces
exactly a spectrally shaped ratio.

The check that would have caught it instantly was staring at the output:
**paper cannot read above 100 %**. A physical-plausibility bound is worth more
than a clever ratio statistic. `tools/probe_calibration_check.py` must test that
first.

## ✅ RESTORED, and the restore procedure is now VERIFIED

Cap attached the **correct** way round (white tile toward the aperture) plus one
press of the device's own button. `EXP-CAL-002`, second run:

| | mean %R | min | max | over 100 %? |
|---|---|---|---|---|
| Baseline (`EXP-MEAS-001`) | 85.84 | 63.70 | 96.44 | no |
| Corrupted (green reference) | **156.78** | — | **193.79** | **yes** |
| **After restore** | **88.54** | 67.73 | 98.96 | no |

Band ratio against baseline: **1.032 ± 0.010**, ΔE₇₆ **1.05**.

**This is the white-calibration procedure for this unit, established
empirically**: there is no menu, no command, and no black tile — you seat the
cap correctly and press the button. It is what the operator described in the
very first exchange.

⚠ **The restored calibration is not bit-identical to the original: a uniform
+3.2 % offset remains**, with a band-ratio spread of only 0.010, i.e.
spectrally **neutral**. That is the expected difference between two independent
white calibrations with slightly different cap seating — not damage. But it
means readings from before and after the corruption are offset by a scalar.
For `EXP-SPEC-001` rank analysis a scalar factor is harmless; for absolute
comparisons it must be accounted for.

**Corpus note:** `EXP-MEAS-001` and `EXP-MEAS-002` were taken under the original
calibration, `EXP-CAL-002`'s second run under the restored one. `EXP-MEAS-003`'s
`patch_after` was taken under the **green** reference and is unusable for
anything but the corruption analysis.

## ⚠ DO NOT recalibrate this unit — standing instruction

**Superseded for the specific case of restoring the white tile** — see above.
The reasoning below still applies to *speculative* recalibration.

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

## ✅ THE MAGNET ALONE DOES NOTHING — VERIFIED 2026-08-29, `EXP-BLE-014`

The owner's hypothesis, and a serious one: *"maybe the magnet alone triggers the
calibration without presing a button at all."* If true, an instrument stored
capped would recalibrate itself repeatedly against whichever face met the
aperture, and the rule against sending the trigger would have been aimed at the
wrong thing entirely.

A passive listener, **nothing sent to the device**:

```
A  cap OFF, untouched     : 0 frames    (control)
B  cap SEATED, white in   : 0 frames
C  cap resting on         : 0 frames
D  cap REMOVED            : 0 frames
E  untouched              : 0 frames    (control)
F  one button press       : 1 frame     (positive control — the listener was alive)
```

Seating, resting and removing the magnet produce no announced action. **A
measurement must still be TRIGGERED**, by the button or by the host; the magnet
only changes what that measurement means. `EXP-MEAS-003`'s original framing
stands.

⚠ **Limit of this result.** It proves nothing is ANNOUNCED. A wholly silent
calibration would look identical from the host. What makes that unlikely is that
a press announces, so a magnet-driven measurement presumably would too — but
that is inference, not measurement.

**Observed and unexplained:** the lights flashed when the cap was REMOVED, with
no frame accompanying them. The lamp is decoupled from anything host-observable
and must not be used as a cue for whether the device acted.

## ✅ THE HOST TRIGGER DOES CALIBRATE OVER BLUETOOTH — VERIFIED 2026-08-29, `EXP-BLE-015`

`EXP-BLE-012` established the BLE host trigger takes a measurement with **no**
magnet. This tested it **with** one, cap seated white-tile-in:

| step | mean %R | is it the tile constant? |
|---|---|---|
| paper, before | 88.3327 | no — a real reading |
| **after the host trigger** | **79.0678** | **yes** |
| after a button press (positive control) | 79.0678 | yes |
| paper, after | 87.6836 | no — a real reading |

The trigger returned `TILE_SIGNATURE` exactly, as the button press did, so it
reaches the gated path: **a host-triggered calibration over BLE is real.** The
control proves the gate was engaging that day, so a null result could not have
been the probe failing.

### ⚠ CORRECTION — the "no beep" claim was never measured, and is WRONG

This section previously stated that the device does not beep for a host trigger
with the cap on. **It does, on both transports.** The owner, 2026-08-29, after
running the same calibration over USB and Bluetooth:

> *"it beeps, but so did it via bluetooth as well, usb was just much faster,
> near instant."*

No capture ever recorded sound. `EXP-BLE-015`'s JSON has no field for it, and
the probe asked the operator to listen while never recording the answer — its
success text had "the missing beep" written into it before the run. The claim
came from his first impression alone, and was published as a finding.

What actually happened is **latency, not silence**: over Bluetooth a
trigger-and-read cycle took ~1.85 s, so the Calibrate button felt dead. Over USB
the same operation is near-instant and obviously works.

The lesson is the one this corpus keeps teaching: an impression is a hypothesis,
and a probe that does not record an observation cannot confirm one.

### The 0.73 % that followed, and why it is not a shift

Paper read 88.3327 before and 87.6836 after — 0.73 % darker — which is far above
this unit's 0.056 % worst-band repeatability and looked like a calibration
error. `EXP-BLE-017` settles it:

```
A  five readings, nothing moved      mean 89.7233  sd 0.0760
B  five readings, lifted and replaced mean 89.3039  sd 0.0733
```

Every reading in B is below every reading in A. **Lifting the instrument and
setting it back down shifts the result by −0.47 %, at 5.6 σ**, and worst-case
A-max to B-min is −0.63 %. The cap went on and came off between the two paper
readings, so handling accounts for it. The paper was thin over an uneven
backing, which is the owner's own explanation and is consistent.

⚠ The probe's own printed verdict said the opposite, because it compared spread
*within* each phase rather than the two phases as groups — the wrong statistic
for a repositioning. The numbers above are the correct comparison.

**Practical consequence:** on thin paper, a patch is not re-measurable to better
than about half a percent. Judge repeat readings on thick opaque backing.

## To establish by experiment

- Exact command and response for each calibration.
- Prerequisites and required order (black first, then white — **DISPROVEN, see EXP-BLE-016: the vendor app does WHITE then BLACK, twice, captured 2026-08-29**; the old note said black first — per Pharmacist).
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


---

# 🔴 ADVERSARIAL REVIEW — `[CR30-SKEPTIC]`, 2026-08-28

## 1. The attribution question: **NOT POSSIBLE TO DETERMINE** from existing captures

I tried to settle it without hardware, as instructed. It does not close. Here is
the whole attempt, so nobody repeats it.

**What the captures contain.** `EXP-MEAS-003`'s order is: patch (cap off) →
magnet on → **host trigger** → **button press** → patch (cap off). Both candidate
writers precede the damaged reading, so the before/after pair cannot separate
them. That much the document already says.

**The route I thought would work, and why it fails.** `EXP-MEAS-002` ran the same
two events with the **white tile** under the aperture, and its before/after
reference patch is:

| | ratio after/before | ΔE₇₆ | worst band |
|---|---|---|---|
| `EXP-MEAS-002`, both gated events, tile under aperture | **1.00193 ± 0.00823** | 0.438 | 0.447 %R |
| a **known** white-calibration write (`EXP-CAL-002` restore) | **1.0318 ± 0.010** | 1.047 | — |

The mean shift is **16× smaller** than the one write we can point at. That reads
like evidence that *neither* event wrote a calibration in `EXP-MEAS-002`.

**Why that is not good enough.** The two stories are both self-consistent:

- *No write happened*, so nothing moved; or
- *a write happened against the true tile in the same seating as the state it
  replaced*, so nothing moved — and the restore's +3.2 % is then the difference
  between a hand-seated cap and whatever set the previous state, not the size of
  a re-calibration.

Nothing in the corpus separates those, because seating repeatability has never
been measured. **It is measurable, cheaply, and it would settle this**: calibrate
twice in a row without disturbing the cap, then twice more re-seating between,
and compare. If seating repeatability is ~0.2 %, `EXP-MEAS-002` proves no write
occurred; if it is ~3 %, `EXP-MEAS-002` proves nothing.

**Confidence: NOT DETERMINED.** The standing rule stands.

## 2. But the standing rule is not the right rule for ChromIQ

"No host trigger with a magnet present" is unenforceable in software, because
**the host cannot see the magnet** — that is the whole finding. A rule a program
cannot evaluate is not a safety measure.

The correct rule for a shipping backend is stronger and costs nothing:

> **A ChromIQ CR30 backend must never send `BB 01 00` at all.**

`usb_measure.read_stored()` reads the device's cached reading and sends no
trigger; the operator's own button press is the trigger. That is the workflow
`EXP-MEAS-005` already ran end to end, fifteen readings, zero rejections. The
trigger buys nothing and risks the user's calibration.

**Requested action:** `CR30.trigger()` (`src/cr30/device.py:74`) should not be
reachable from the ChromIQ-facing API. It may stay in the research package as an
experiment primitive; it must not be part of the integration surface. Filed in
`INTEGRATION.md`.

## 3. What the gated read returns is a FACTORY constant, and that has consequences

New, and it follows from the captures rather than from reasoning about firmware:
the gated value is **bit-identical before and after the calibration was
destroyed**, and identical again after the restore (`EXP-MEAS-002`, `-003`,
`EXP-BLE-010`). A value that survives having the stored white reference
overwritten with green is not derived from the stored white reference. It is the
tile's **nominal / certified characterisation, held in firmware**.

Two consequences:

1. It is **per-unit factory data**. The only other CR30 we have data for reads
   its white reference up to **4.69 %R** differently (`PRIORART-001`, band ratio
   0.9703 ± 0.0161, ΔE₇₆ 1.73). So `TILE_SIGNATURE` cannot be hard-coded — see
   `MEASUREMENT.md` §"Adversarial review".
2. It is a **free calibration check**. If the firmware holds the nominal tile
   values, then measuring the actual tile with the gate *disengaged* and
   comparing against them is a real calibration test — the thing §"To establish
   by experiment" asks for. Worth an experiment; needs no new command.

## 4. ⚠ Two superseded sections in this file still read as current

The section *"With a magnet attached, the device stops measuring"* concludes
**"This is good news for calibration safety. If the device does not calibrate
against whatever the magnet is holding, then an accidental cap attachment cannot
corrupt the stored white reference."** That is **DISPROVEN** by the section at
the top of this file, written later. A reader arriving at the middle of the
document gets the opposite of the finding.

Likewise *"it is not 'taking the reading as a calibration' in the sense of
recalibrating to the target — it is entering a mode where the optical path is
ignored"* is exactly the inference the top of the file records as wrong.

**Requested action for `[CR30-USB]`:** mark both DISPROVEN in place. `CLAUDE.md`
§4 requires it, and the operator's original imprecise report was right both
times.
