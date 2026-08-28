# SESSION_HANDOFF.md

**For the next Claude Code session, on any machine.** Assume no conversation
history. This file plus `CLAUDE.md` and `STATUS.md` is the whole picture.

**Written:** 2026-08-28, end of session 1 · **Platform used:** macOS 15.7.9 arm64

---

## What was just established

Direct USB communication with the CR30 works **on macOS, with nothing
installed**. The device answers, and identifies itself as `CR30`. The published
reverse-engineering checksum is wrong and has been corrected. See `STATUS.md`
for the full verified list.

The single most consequential result: **ChromIQ issue #159's platform strategy
was based on a false premise.** It says start on Windows because macOS needs a
kernel extension. macOS 15.7.9 ships Apple's own CH34x DriverKit driver and the
device just works.

## What remains unknown

Everything past identity: calibration, measurement, the spectrum, the `0xBB`
command class, parameters, errors, BLE, and whether the 31 spectral bands are
real measurements or a firmware reconstruction.

## Files changed

Repository created from nothing. All documents, `src/cr30/{frame,identity}.py`,
`tools/{probe_identity,probe_checksum,redact}.py`,
`tests/test_frame_replay.py`, `captures/public/*`.

## Latest protocol hypothesis

`PROTOCOL.md`. Verified: 60-byte frames, `sum(0..58) mod 256` checksum, identity
command and field offsets, baud irrelevance. Unverified: everything itohio
claims about `0xBB`, calibration, trigger and spectrum chunks — carried in §5 as
claims to be tested, not as facts.

## Exact next experiment

**`EXP-USB-003` first — it needs no human and no risk.** Determine whether the
checksum is enforced on the `0xBB` command class. `EXP-USB-002` proved only that
`AA 0A 00` ignores it; a side-effecting command may not. Use a harmless `0xBB`
command; do **not** sweep the command space until `[CR30-SKEPTIC]` has defined a
safety envelope (`EXPERIMENTS.md`, note on EXP-USB-004).

**Then `EXP-CAL-001` and `EXP-MEAS-001`, which need the human.** Design them so
that one session of human interaction answers as many questions as possible —
identity, calibration status before and after, black cal, white cal, a
measurement on a known patch, a repeat without lifting, and a button-triggered
reading, all in one scripted run with full transaction logging.

## Required state for that next experiment

- **OS:** macOS (Windows is not needed and is not on the critical path for USB)
- **Transport:** USB, `/dev/cu.usbserial-10` — re-check the node name, it is not stable
- **Hardware state:** CR30 plugged in via USB. For `EXP-CAL-001`, the black cap
  and the white tile must be to hand.
- **App/tool that must be running:** none. **ColorQC2 must NOT be running** — it
  would hold the port and serialise against us.
- **Lease:** acquire `.hardware-lock/LEASE` before opening the port.

## What must NOT be done

- Do not modify ChromIQ in any way (`CLAUDE.md` §2).
- Do not commit `captures/raw/` or `LOCAL_DEVICE_IDS.md` — they carry the unit's
  identifiers.
- Do not sweep undocumented command bytes without a safety envelope.
- Do not send firmware or calibration-storage writes.
- Do not treat any itohio claim in `PROTOCOL.md` §5 as fact.
- Do not verify redaction by grepping a hex capture for an ASCII string — it
  always "passes". Grep the hex-encoded form.

## Unresolved disagreements between agents

None yet — the agents were briefed at the end of session 1. Their opening
assessments are on the coordination issue.

## Relevant GitHub

- Coordination issue: **this repo, issue #1** — read new comments at session
  start. React only to `[CR30-USB]`, `[CR30-SKEPTIC]`, `itsab1989`,
  `soul-traveller`.
- Background: `itsab1989/ChromIQ#159` — read-only. **Several of its claims are
  now disproven**; do not take it as current.

## Commands to reproduce the current state

```bash
cd ~/develop/chromiq-cr30-research
python3 -m venv .venv && .venv/bin/pip install pyserial bleak pytest
.venv/bin/python -m pytest tests/ -q          # 57 pass, no hardware needed

ls /dev/cu.usbserial-*                        # find the node
.venv/bin/python tools/probe_identity.py /dev/cu.usbserial-10
.venv/bin/python tools/probe_checksum.py /dev/cu.usbserial-10
.venv/bin/python tools/redact.py captures/raw/*.json
```

Confirm the driver situation on any new macOS host:

```bash
ioreg -w0 -r -n CH554_CDC -l | grep -E "CFBundleIdentifier|IOClass"
# expect com.apple.DriverKit-AppleUSBCHCOM  -- Apple's own, nothing installed
```

## Recommended platform for the next session

**macOS.** USB works there with no driver, the human and the hardware are there,
and it is where ChromIQ's user runs. Windows becomes worth visiting only to
sniff ColorQC2 for the undecoded parameter commands, and BLE work starts on the
macOS host.
