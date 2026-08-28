# SESSION_HANDOFF.md

**For the next Claude Code session, on any machine.** Assume no conversation
history. This file plus `CLAUDE.md` and `STATUS.md` is the whole picture.

**Written:** 2026-08-28, end of session 2 · **Platform:** macOS 15.7.9 arm64

---

## What was established

**USB is finished.** Framing, checksum, identity, timing, the `0xBB` class, the
measurement transaction, the spectral decode, calibration, and a shipping-relevant
hazard. The decode is cross-validated against the device's own firmware to
ΔE 0.054 — not against our own arithmetic. See `STATUS.md` for the table.

The three results that matter most, none of them in the published prior art:

1. **Magnet + measurement = WHITE CALIBRATION** against whatever is under the
   aperture, and the host cannot see it happening. Verified the hard way: we
   corrupted the unit's calibration by triggering with a green surface presented,
   then restored it. The restore procedure — **seat the cap correctly, press the
   device button** — is the white-calibration procedure for this unit, which had
   no known procedure before.
2. **A gated read is bit-identical with white or green under the aperture**, all
   31 float32 values, difference 0.0. It is a stored constant, not a measurement.
3. **The gate is invisible on the host path** — offset 24 stays `0x00` on
   triggered reads. Detection must be behavioural.

**BLE is located and mapped but does not talk.** Advertises as its own USB
device-id, `ffe0` with `ffe1`/`ffe2` (write+notify) and `ffe3` (write), MTU 244,
one connection at a time, stops advertising when taken. Never answers.

## What remains unknown

- **BLE activation.** The vendor app's ~1 s handshake. Six variables eliminated;
  it cannot be guessed. `EXP-BLE-009` specifies the capture.
- **Which command wrote the calibration** in `EXP-MEAS-003` — the host trigger or
  the button press. 🔴 **Until separated, no host trigger with a magnet present.**
- **Spectral independence** — are the 31 bands real or reconstructed?
  `[CR30-SKEPTIC]` disproved the *linear* AS7341 hypothesis on 58 vendor spectra;
  `EXP-SPEC-001a/b` remain.
- Positioning error (lift between reads), which sets minimum patch size.

## Exact next experiments

**1. `EXP-BLE-009` — capture the activation handshake.** Needs PacketLogger
(*Additional Tools for Xcode*; **not installed on this Mac**) with an iPhone on
USB, or an Android HCI snoop log, or an nRF52840 dongle. Everything else about
BLE is known and `src/cr30/transport.py` already abstracts transports, so a BLE
transport is a small addition once activation is understood.

**2. `EXP-MEAS-004` — which command writes the calibration?** Needs deliberate
re-corruption with the now-verified restore in hand. Design it carefully; do not
run it casually. It is the difference between "a live backend returns bad data
near a magnet" and "a live backend destroys the user's calibration".

**3. `EXP-SPEC-001a/b`** — needs no hardware for (a); (b) needs a didymium filter.

## Required state

- **OS:** macOS. Windows is not on the critical path and was never needed.
- **USB:** `/dev/cu.usbserial-*` — re-check the node name, it changes on replug.
- **BLE:** device must be **advertising** (i.e. the phone app not connected) to
  be resolvable. Resolve it *before* anything else takes it.
- **ColorQC2 must NOT be running** — it holds the port.
- Acquire `.hardware-lock/LEASE` before opening the device.

## What must NOT be done

- Do not modify ChromIQ (`CLAUDE.md` §2). It was not touched in either session.
- **Do not send a host trigger with a magnet present** (see above).
- Do not send `BB 10` / `BB 11`. The calibration procedure is the cap + button.
- Do not recalibrate speculatively — see the standing instruction in
  `CALIBRATION.md`. Restoring a *proven* corruption is the exception.
- Do not commit `captures/raw/` or `LOCAL_DEVICE_IDS.md`.
- Do not verify redaction by grepping a hex capture for an ASCII string.

## Method lessons that cost real time this session

1. **A silence whose cause is unknown is not evidence.** Most BLE negatives ran
   against a sleeping radio and are *untested*, not disproven.
2. **A probe must be able to distinguish its own hypotheses.** `EXP-MEAS-002`
   let a gated button press precede the host trigger and handed itself the answer.
3. **Physical bounds beat clever statistics.** Paper reading 156 % was ignored by
   a ratio heuristic that assumed calibration shifts are spectrally neutral. They
   are not, when the reference is coloured.
4. **Do not let a redaction tool recompute the field under test** — it made two
   published frames circular evidence.
5. **The operator's imprecise report was right and my inference was wrong.**
   "It takes the reading as a calibration" was literally true.

## Reproducing

```bash
cd ~/develop/chromiq-cr30-research
python3 -m venv .venv && .venv/bin/pip install pyserial bleak pytest
.venv/bin/python -m pytest tests/ -q        # 406 pass, no hardware needed
```


---

## Session 3 addendum — `[CR30-SKEPTIC]`, 2026-08-28 (desk work, no lease taken)

**Read `STATUS.md`'s "Session 3" table first** — eight claims were overturned or
weakened and three defects are still open.

### The three things that must not be lost

1. **`TILE_SIGNATURE` is one unit's factory constant.** The magnet defence does
   not work on anybody else's CR30. `MEASUREMENT.md` Hole 1.
2. **The reflectance bounds accept a real corrupted reading** (105.47 %R) and are
   blind to the deflating half of the failure entirely. `MEASUREMENT.md` Hole 4.
   Deliberately NOT retuned — retuning a one-sided test does not fix it.
3. **A ChromIQ backend must never send `BB 01 00`.** "Don't trigger near a
   magnet" is a rule software cannot evaluate, because the host cannot see the
   magnet. The button-press workflow needs no trigger and is already proven.

### Next experiments, revised order

1. **`EXP-MEAS-004`** — which command writes the calibration. Still the dangerous
   one, still needed. **But first run the free half of it:** measure seating
   repeatability (calibrate twice without disturbing the cap, then twice
   re-seating between). That alone may settle the attribution from
   `EXP-MEAS-002`'s existing data. `CALIBRATION.md` §1.
2. **Replicate the offset-24 button flag on a second magnet position**, and on a
   second unit if one is ever available. Cheapest high-value experiment
   outstanding: it converts the only unit-independent magnet check from
   CORROBORATED to VERIFIED.
3. **`EXP-MEAS-006`** — what a fluorescing OBA paper really reads. Decides
   whether 110/130 are usable numbers. No hardware risk. `EXPERIMENTS.md`.
4. **`EXP-SPEC-001a`** — unchanged, and still the thing that could overturn the
   whole `.ti3` seam.

### Not done, and it should be

`EXPERIMENTS.md` has **no entry for twelve experiments that ran**, including both
magnet experiments and all of BLE. See the note appended there.
