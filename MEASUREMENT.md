# MEASUREMENT.md

**Status: no measurement has been taken by this project.** What follows is
partly decoded from the vendor application's own traffic on a *second* CR30
(`captures/public/PRIORART-001`, `PRIORART-002`), which is CORROBORATION, never
VERIFIED. See `PROTOCOL.md` §0.

## 1. The sequence, as observed in vendor traffic

```
trigger:  BB 01 00 00      -> (empty request)
header:   BB 01 09 00      -> declares the axis: frame[4:7] = 28 1f 0a
                              = start 400 nm, 31 bands, 10 nm step
                              byte 58 flags button-triggered (PROTOCOL.md 7.4)
fetch:    BB 01 10 00      -> values  0..11   (12 float32 LE at frame offset 6)
          BB 01 11 00      -> values 12..23   (12)
          BB 01 12 00      -> values 24..30   ( 7, rest zero-padded)
          BB 01 13 00      -> NOT spectral; copy of values 0..4 at offset 34
```

The **"20 unexplained bytes" of the prior art do not exist** — see
`PROTOCOL.md` §7.3. That question is closed.

Implemented in `tools/decode_spectra.py`, which **rejects** a measurement whose
chunks do not deliver what the header declares rather than returning a partial
spectrum (`CLAUDE.md` §14).

## 2. Questions still to be answered by experiment

1. Real end-to-end time, measured rather than quoted (`EXP-USB-005`).
2. Does the device reject commands while busy? Can measurements overlap?
3. Is a measurement cached — does re-fetching chunks return the same data?
4. Is calibration a precondition, and what happens without it?
5. What does a *failed* read return? Nothing observed has ever failed.
6. What is `BB 21 01` (1745 frames in one vendor session)?
7. Are the values percent reflectance, or reflectance ×100 of something else?
   Vendor exports label them alongside `L*a*b*` at **D50/10°** — note that the
   Pharmacist write-up's "1931 2°" claim is contradicted by the vendor's own
   export header, which says 10°. Neither is established.

---

# EXP-SPEC-001 — are the 31 bands 31 measurements, or a reconstruction?

**Why it matters.** Writing 31 `SPEC_*` columns into a `.ti3` tells `colprof`
it has 31 independent measurements. If they are interpolated from ~11 physical
sensor channels — the prior-art write-up *estimates* an AS7341/AS7343 — the
profile is built on a false premise about its own information content.

## Status: the LINEAR form of the reconstruction hypothesis is **DISPROVEN**

Run `tools/spectral_rank.py captures/public/PRIORART-002-spectra.json`.
Pinned by `tests/test_spectral_independence.py`. No hardware needed.

**Corpus:** 58 unique spectra × 31 bands, decoded from vendor traffic
(60 measurements, 2 rejected as incomplete). More samples than bands, which is
a precondition — with fewer spectra than bands the test would "find" a rank
deficiency that is ours, not the device's.

**Result:**

| | |
|---|---|
| numerical rank (σ/σ₀ > 1e-6) | **25 of 31** |
| σ₈/σ₀ (AS7341 visible channels) | 4.7e-03 |
| σ₁₁/σ₀ (AS7341 total) | 3.0e-04 |
| σ₁₄/σ₀ (AS7343) | 5.1e-05 |
| largest gap between consecutive σ | **0.63 decades**, anywhere |
| float32 relative epsilon | 1.2e-07 |

**The number is not the evidence — the absence of a cliff is.** A linear map
from N channels forces every spectrum into an N-dimensional subspace, so
σ_{N+1}… sit at float32 round-off: a gap of five or more decades. The largest
gap anywhere in this spectrum of singular values is **0.63 decades**, and
σ₁₄ is 400× above float32 round-off. There is no N at which the data collapses.

**The direction of the argument matters and only one direction is usable.**
Sample diversity can only *lower* observed rank, never raise it — a set of
patches printed with four inks has intrinsic rank ~8 no matter how good the
instrument. So a **high** observed rank is strong evidence against a
low-channel reconstruction, while a **low** one would have been inconclusive.
We got the usable direction.

**A second statistic, which also bites the nonlinear case.** Roughness =
second-difference energy of each right singular vector as a fraction of its
total energy. A basis built from ~20 nm FWHM interference filters is
band-limited and physically cannot exceed ~0.1:

| component | 1 | 3 | 6 | 9 | 15 | 24 | 30 |
|---|---|---|---|---|---|---|---|
| σ/σ₀ | 1.0 | 2.4e-1 | 3.4e-2 | 4.7e-3 | 5.1e-5 | 1.3e-6 | 4.0e-8 |
| roughness | 0.000 | 0.033 | 0.077 | 0.989 | **6.53** | **10.98** | **14.69** |

Leading components look like reflectance spectra. From component ~9 onward the
basis is alternating band-to-band — the signature of **per-band independent
variation**, which no smooth filter basis can produce.

**Conclusion — CORROBORATED, not VERIFIED:** the 31 values are not a linear
reconstruction from 8, 11, 13 or 14 channels, and carry independent per-band
variation to ~25 dimensions well above float32 quantisation.

## What this does NOT establish — read before citing it

1. **A different unit.** This is prior-art traffic from a second CR30 sniffed
   on Windows, decoded by us. Confidence is CORROBORATION. It must be repeated
   on our unit before it is VERIFIED.
2. **Nonlinear reconstruction is not excluded by the rank test.** A LUT or
   polynomial map from an 11-dimensional input produces outputs on an
   11-dimensional *manifold*, which linear SVD reads as high rank. Only the
   roughness statistic argues against it, and it argues from a physical
   bandwidth limit rather than from a measurement.
3. **Independent is not accurate.** A band can vary independently and still be
   wrong. Nothing here says anything about the *quality* of the 31 values.
4. **Firmware-injected dither** would also produce per-band variation. It is
   implausible, and unfalsified.

## The decisive remaining test, ready to run

### EXP-SPEC-001a — noise-covariance rank (removes the sample-diversity confound entirely)

**Hypothesis.** If the 31 outputs are any *fixed* map of N physical channels,
then the measurement noise in the 31 outputs is also confined to N dimensions —
because there are only N noisy detectors upstream. **The rank of the noise
covariance equals the number of physical channels, regardless of what is being
measured.** This is the strongest form of the test: it needs no sample
diversity at all, so the confound that limits §1 vanishes.

**Procedure.**
1. Calibrate. Place the device on **one** mid-grey patch and clamp it — the
   device must not move at all between readings. Movement injects real
   spectral variation and inflates the rank, which would falsely support
   independence. *This is the one thing that can invalidate the experiment.*
2. Take **K ≥ 150** readings without lifting. Software-triggered, no averaging.
3. Repeat on a dark patch and a light patch (noise is usually signal-dependent;
   a rank found on only one level could be a coincidence of that level).

**Analysis.** Subtract the per-band mean, SVD the K×31 residual matrix.

**Decision threshold.** With K readings of 31 bands and i.i.d. noise of
standard deviation σ, pure noise produces singular values up to roughly
σ(√K + √31) (Marchenko–Pastur). Estimate σ from the median absolute deviation
of a single band's residuals. Then:

- **Reconstruction from N channels** — a cliff: σ_{N+1}…σ₃₁ at float32
  round-off of the reported values (≈1e-7 relative), *orders of magnitude*
  below the MP bound. Unmistakable.
- **31 independent detectors** — all 31 singular values within a factor of ~3
  of each other and all near the MP bound.
- **Inconclusive** — a soft shoulder with no float32 floor. This happens if
  the firmware averages internally (which shrinks noise without changing rank,
  so the floor is still detectable) or if noise falls below the float32
  quantisation of the reported values, which is the real failure mode: if the
  device reports 6 significant figures and repeats are *bit-identical*, the
  experiment yields nothing and must be repeated on a lower, noisier signal.

**Precondition, and it is a real one.** In the vendor corpus, repeated
measurements of the same target returned **byte-identical** spectra. If our
unit does the same, either the readings are cached (§2.3) or the noise is below
the reporting resolution — and EXP-SPEC-001a cannot run until that is
understood. Establish first, with 5 readings, that repeats *differ at all*.

### EXP-SPEC-001b — spiky-reflectance test (the only test that bites nonlinearity)

**Hypothesis.** A ~20 nm FWHM filter set cannot resolve a reflectance feature
narrower than its bandpass, whatever the reconstruction does downstream.
Bandwidth is a physical limit, not a fitting choice.

**Procedure.** Measure a target with sharp, *certified* spectral structure. The
standard choices are a **didymium (neodymium) glass filter** (sharp absorption
near 585 nm, sold as a wavelength-verification standard) or **holmium oxide**
(multiple narrow lines). Place it over the white calibration tile so the
instrument's own illuminant passes through it twice.

**Analysis.** Compare the measured feature's depth and width against the
filter's certificate. A true 31-band instrument with ~10 nm bandpass shows a
deep, narrow notch; an ~11-channel reconstruction shows a shallow, broadened
one, and typically rings on either side.

**Inconclusive if** the filter's own features are broader than 20 nm — then the
test cannot separate the hypotheses and a narrower standard is needed.

**Human action required** — this needs a purchased reference filter. It is the
only test in this document that costs money, and it is the one that closes the
nonlinear gap.

### EXP-SPEC-001c — channel-position test (positive identification, not falsification)

If a reconstruction *is* ever indicated, the AS7341's published filter centres
(415, 445, 480, 515, 555, 590, 630, 680 nm) should appear as knots in the
leading right singular vectors. Absence of knots is not evidence of absence;
presence would be strong positive identification of the sensor. Cheap, runs on
data already collected, worth doing whenever the corpus grows.

## On the AS7341/AS7343 claim itself

The prior art *estimates* the sensor; no teardown photograph, part marking or
datasheet citation supports it in either repository. Treated as **HYPOTHESIS
with no evidence behind it**, not as a premise. The measured result above is
inconsistent with its linear form, which is a reason to doubt the estimate
rather than to doubt the measurement.

## Consequence for the `.ti3`

On present evidence, writing 31 `SPEC_*` columns is **defensible** — the values
carry independent per-band information. It is not yet *established*, because
the corpus is a second unit and nonlinearity is unexcluded. Until
EXP-SPEC-001a/b run on our unit, any `.ti3` ChromIQ writes from a CR30 should
carry a provenance keyword recording that the spectral independence is
corroborated rather than verified. See `INTEGRATION.md`.


---

## EXP-MEAS-002 — the magnet gate, and what it did *not* settle

Ran 2026-08-28, gate engaged on the first attempt.
`captures/public/EXP-MEAS-002-magnet-gating.json`.

### The canned value is a real white-tile spectrum — VERIFIED

Flat at ~79 % reflectance from 420–700 nm with a rolloff to 70.4 % at 400 nm;
total range 10.3 points. For comparison, the plain paper measured in
`EXP-MEAS-001` ranges over 32.7 points. **This is the shape of a white ceramic
calibration tile**, so the device is displaying a *stored characterisation of
its own reference tile*, not a placeholder and not a live reading.

### Our decode reproduces the device's own firmware — VERIFIED, and it is a strong check

| | L\* | a\* | b\* |
|---|---|---|---|
| Device's own display | 91.64 | −0.78 | +1.36 |
| Our decode → CIE 1931 2°/**D65** | **91.661** | **−0.760** | **+1.305** |
| Our decode → CIE 1931 2°/D50 | 91.661 | −0.560 | +1.251 |

**ΔE₇₆ = 0.062 against D65.** This is an independent cross-validation of the
*entire* chain — chunk layout, byte order, float format, band mapping, percent
scale, and the colour maths — against the vendor firmware's own arithmetic. It
is much stronger evidence than the air/paper control, because it matches a
specific number the device computed itself.

### The measurement condition — settled by the device itself

**The display's top line reads `D65/10`** (operator, 2026-08-28). That is the
authoritative answer, and it is **not** what ChromIQ issue #159 implies: #159
records ColorQC2 pinning **M0 / D50 / 1931 2°**. So the *device's own display
condition* and the *vendor application's export condition* are **different
things**, and conflating them would put the wrong illuminant on every imported
reading.

Recomputing the same spectrum under all four combinations:

| | L\* | a\* | b\* | ΔE₇₆ vs display |
|---|---|---|---|---|
| **D65 / 10°** | **91.643** | −0.730 | +1.380 | **0.054** |
| D65 / 2° | 91.661 | −0.760 | +1.305 | 0.062 |
| D50 / 10° | 91.649 | −0.541 | +1.336 | 0.241 |
| D50 / 2° | 91.661 | −0.560 | +1.251 | 0.247 |

**What this evidence does and does not show.** It **confirms D65 over D50**
(0.054 vs 0.247, a factor of four). It does **not** discriminate 2° from 10°
— 0.054 against 0.062 is far too close on a near-neutral sample, which is the
worst possible case for separating observers. The observer is settled by the
**label on the screen**, not by this arithmetic; the arithmetic is merely
consistent with it, with L\* agreeing to 0.003.

`src/cr30/colour.py` now defaults to **CIE 1964 10° + D65** to match the device,
with `use_observer("2")` available. Both observers self-validate against
published white-point chromaticities before any Lab value is reported.

⚠ **`D65/10` implies the condition is a device SETTING** — something has to be
selecting it. See the note on parameter commands below.

### A candidate gate flag at offset 24 — HYPOTHESIS

| Frame | offset 24 |
|---|---|
| Gated button press (magnet engaged) | **`0x01`** |
| All 14 other `BB 01 09` headers, both runs | `0x00` |

The only difference between the two *button* frames across both sessions is the
magnet, so offset 24 is a plausible **"reading was taken in magnet mode"** flag —
exactly what a ChromIQ backend would need to reject such a reading.

**One observation. Not verified.** It needs replication before anything relies
on it.

### ⚠ What this run did NOT establish

**Whether a host-triggered measurement is gated. It is still open.**

The capped host-trigger returned data byte-identical to the preceding gated
button read — but its own header carried offset 24 = `0x00`, *not* the `0x01`
the button frame carried. Combined with the VERIFIED fact that measurements are
cached, the most economical explanation is that **the host trigger did not
produce a new measurement at all, and we re-read the button's data.**

That is the confound the experiment was meant to avoid and did not: the gated
button press *preceded* the host trigger, so it had already loaded the buffer
with the very value we were testing for.

`EXP-MEAS-003` separates the three possibilities by ensuring the buffer holds a
**distinctive patch** at the moment the magnet is engaged, with no button press
in between:

| Host-trigger result | Conclusion |
|---|---|
| the canned tile value | the USB path **is** gated |
| the previous patch | the trigger is **ignored** while gated (cache re-read) |
| a genuine white-tile reading, unlike both | USB **bypasses** the gate |

### Calibration integrity — VERIFIED

ΔE₇₆ between the same patch before and after the capped phase: **0.438**,
across a lift-and-replace. `EXP-MEAS-001` measured 0.056 % worst-band SD without
lifting, so this is ordinary repositioning error. **Nothing moved the stored
calibration**, which supports the conclusion in `CALIBRATION.md` that a magnet
cannot corrupt it.

### Either way, ChromIQ must defend against this

Whether the USB path returns a canned value or silently repeats the last one,
**the observable symptom is the same: consecutive patches returning identical
spectra.** A live backend must detect byte-identical consecutive readings and
refuse them, because both failure modes produce data that is plausible,
self-consistent, and completely wrong.


---

## ⚠ Parameter commands: the negative result was scoped to USB only

`[CR30-SKEPTIC]` concluded from ten vendor sniffer sessions that **no
sensor-parameter command exists**, and that ChromIQ issue #159's hope of a
faster reading via undocumented parameters is a dead end. That conclusion was
drawn entirely from **ColorQC2 over USB**.

Two observations reopen it:

1. **The display reads `D65/10`.** An illuminant and observer are being
   *selected*, so a setting exists in the device whether or not ColorQC2 ever
   changes it.
2. **The iOS app can change device settings over Bluetooth** (operator,
   2026-08-28, not yet exercised).

**Revised status: the negative result stands for the USB/ColorQC2 corpus and
does not generalise.** Parameter commands may exist and simply never be
exercised by the Windows application — which is exactly the case where a
different client on a different transport is the only way to see them.

This raises the value of the BLE investigation considerably. It is no longer
only "cable-free operation"; it is **the most promising route to the
configuration surface**, and it is reachable from the macOS host with `bleak`,
no driver required.

**Next**: `EXP-BLE-001` (does the device advertise, and with what GATT profile?)
before any attempt to change a setting. Changing settings from the app while
capturing is a later step and must not be done casually — an illuminant or
observer change would alter every subsequent reading, and the operator should
record the before state so it can be restored.


---

## EXP-MEAS-003 — the USB path IS gated · VERIFIED

Ran 2026-08-28, gate confirmed engaged by the operator.
`captures/public/EXP-MEAS-003-magnet-trigger.json`.

The buffer was deliberately loaded with a saturated blue patch, the magnet was
engaged **with no button press in between**, and only then was a host trigger
sent. The three hypotheses were fully separated:

| Reading | mean %R | L\* a\* b\* (D65/10°) |
|---|---|---|
| Buffered patch, before | 35.50 | 64.22 / −27.75 / −30.70 |
| **Host-triggered, magnet engaged** | **79.07** | **91.64 / −0.73 / +1.38** |
| Gated button press, after | 79.07 | 91.64 / −0.73 / +1.38 |

**ΔE₇₆ to the canned tile value: 0.083. ΔE₇₆ to the buffered patch: 50.1.**

**A host-triggered measurement with the magnet engaged returns the canned tile
value.** The trigger is not ignored and the cache is not being re-read — the
buffered patch was discarded and replaced with the stored constant. This
supersedes the ambiguity in `EXP-MEAS-002`.

### The strongest single result in this project so far

The operator attached the cap **reversed**, putting the **green** face under the
aperture, where `EXP-MEAS-002` had the **white tile** under it. The two gated
spectra are **bit-identical**:

```
EXP-MEAS-002  white tile under aperture : 70.3943 74.8234 77.4351 78.3985 ...
EXP-MEAS-003  GREEN       under aperture : 70.3943 74.8234 77.4351 78.3985 ...
max absolute difference across all 31 float32 bands : 0.0
```

Two different runs, two different optical targets, **zero difference to the last
bit**. Not "similar" — identical. A measurement cannot do this. **VERIFIED: the
gated reading is a stored constant with no dependence whatsoever on the optical
input.**

This was not the designed procedure — the script asked only for "the position
that triggers the effect". Reversing the cap turned the run into a controlled
optical-independence experiment for free, and it is stronger evidence than the
experiment as specified would have produced.

### ⚠ The gate is INVISIBLE to the host — and this is the important part

**The trigger reply's header carried offset 24 = `0x00`** — the same value as
every ungated measurement. The `0x01` seen in `EXP-MEAS-002` appears **only on
the unsolicited frame from a button press**.

So the candidate "magnet mode" flag is **useless for the case that matters**: a
host-triggered read is gated *without any header field announcing it*. The
transaction is indistinguishable from a normal one — correct framing, valid
checksums, a plausible near-neutral spectrum, no error, no status byte.

**HYPOTHESIS demoted to scoped fact**: offset 24 flags magnet mode on
button-originated frames only. It **cannot** be used to detect the condition on
the host path.

### What a ChromIQ backend must therefore do

Flag-based detection is not available. Detection has to be **behavioural**:

1. **Refuse byte-identical consecutive spectra.** The gated value is a stored
   constant, so every gated patch returns *exactly* the same 31 floats. Real
   consecutive measurements never do — `EXP-MEAS-001` measured 0.056 % worst-band
   SD even without lifting the instrument, so genuine repeats differ in the low
   bits. Bitwise equality is a reliable signature.
2. **Know the tile value.** The gated spectrum is flat at ~79 % with a 400 nm
   rolloff. A run whose readings all match that shape is gated, not measured.
3. **Fail loudly.** Per `ERRORS.md`, this must abort the chart read, not warn.
   The data is plausible, self-consistent and completely wrong — precisely the
   class of failure that silently produces a bad profile.

This is a **real, shipping-relevant hazard**: a user who leaves the magnetic cap
attached, or works near a magnet, gets a full chart of identical white readings
that no checksum, no framing check and no header field would catch.

### Calibration integrity — inconclusive in this run, and why

The before/after patch readings differ by ΔE ≈ 16.7, far beyond the 0.438 seen
in `EXP-MEAS-002`. **That is not a calibration shift.** A calibration change
scales every band by roughly the same factor; here the band-by-band ratio ranges
**1.564 to 2.541 (sd 0.382 on a mean of 1.96)** — a ~20 % spread. The spectral
*shape* changed, which means the instrument was on a different spot or partly
off the patch, not that the device's gain moved.

Recorded as **PROBABLE (repositioning), not verified.** `EXP-CAL-002`
(`tools/probe_calibration_check.py`) settles it in 30 seconds by re-measuring
plain white paper against the `EXP-MEAS-001` baseline: a near-constant ratio
would indicate a calibration change, a varying one a different surface.


---

## EXP-MEAS-005 — the ChromIQ spot workflow, working over Bluetooth

2026-08-28. 15 readings, **0 rejected**, every reply header at offset 0, all 15
spectra distinct. `captures/public/EXP-MEAS-005-spot-workflow.json`.

**The workflow ChromIQ issue #159 §3 describes now runs end to end:** place the
instrument, press *its own button*, the host picks the reading up over BLE. No
cable, no keyboard, no driver. Every button press produced a new, distinct
stored reading that we read back successfully.

### Positioning error — VERIFIED

Six lift-and-replace reads of one cyan patch:

| | |
|---|---|
| Mean ΔE₇₆ from the centroid | **0.215** |
| Worst single reading | **0.340** |
| Worst-band SD | **0.356 %R** |
| *(no-lift repeatability, `EXP-MEAS-001`)* | *0.056 %R* |

Lifting costs about **6× the band noise** of not lifting, and still lands inside
**ΔE 0.34**. For a hand-placed spot instrument that is good — positioning is not
a limiting factor for profiling accuracy.

⚠ **This does NOT give the minimum patch size, and must not be quoted as if it
did.** The operator replaced the instrument on a comfortably large patch each
time, so the aperture stayed well inside it. What is measured is *repeatability
under normal use*, not the *tolerance envelope*. The minimum patch size needs a
deliberate experiment placing the aperture near a patch edge until the reading
degrades. **Chart layout is still blocked on that**, not on this number.

### Rank analysis — too small a corpus to decide, and that is the finding

Singular values over the 15 spectra: 420.7, 285.7, 119.6, 53.5, 11.7, 8.6, 8.6,
6.4, 4.8, 2.5, … — a smooth decay with **no cliff** at 8 or 11 components.

**But this corpus cannot test the hypothesis.** Six of the fifteen readings are
the *same* cyan patch, so there are only ~10 genuinely distinct colours; a rank
of 11 is not even reachable. The result is *consistent with* `[CR30-SKEPTIC]`'s
disproof of the linear AS7341 reconstruction on 58 vendor spectra, and adds
nothing independent. `EXP-SPEC-001` needs **≥15 distinct, well-spread colours**
measured in one calibration state.

### `bb 14` — unresolved, and our probe was wrong

All three sub-commands (`0x00`, `0x08`, `0x09`) returned the identical
`bb 14 00 00 00 00 00 00 ff ce` on all 15 readings — nothing advances.

**That is not evidence `bb 14` lacks a counter.** We sent a zero payload; the
vendor sends `bb 14 08 a0 91 6a 01 00 ff 72`, with a 4-byte field in it. This is
the **echo behaviour** `[CR30-USB]` verified on USB: *the CR30 echoes commands it
does not implement.* A constant echo means our call was malformed, not that the
command is empty. **HYPOTHESIS still open.**

### The new-reading problem, restated with what we now know

A backend reads the *stored* measurement, so it must know when a new one has
arrived — and "the reading did not change" is also the magnet-gated signature.
No counter has been found.

**But it is solvable without one.** The gated value is a *specific known
constant* — the stored tile spectrum, flat at ~79 % with a 400 nm rolloff, and
bit-identical every time. So a backend can:

1. reject a reading bit-identical to the previous one, **and**
2. reject a reading matching the stored-tile signature,

which covers both failure modes. A counter would be cleaner; these two checks
are sufficient.
