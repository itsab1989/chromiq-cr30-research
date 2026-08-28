# SAFETY_ENVELOPE.md — the rules for probing an undocumented CR30

**Author:** `[CR30-SKEPTIC]` · **Version:** 1 · **2026-08-28**
**Status:** binding on `EXP-USB-004` and every future command-space probe.
**Supersedes** the placeholder note in `EXPERIMENTS.md`.

This is not generic caution. Every rule below is grounded in what is now
actually known about this device family, most of it from a corpus of the
**vendor application's own traffic** (`captures/public/PRIORART-001`,
260 frames, 10 sessions), which tells us exactly which commands the
manufacturer's software uses and which it never touches.

---

## 1. The evidence the envelope stands on

The vendor's software, across connect / calibrate / measure / button / job
sessions, uses **exactly sixteen** `(start, cmd, subcmd)` triples and no others:

| Triple | Seen in | Reading |
|---|---|---|
| `AA 0A 00`…`03` | Connect | device information (VERIFIED here, `EXP-MAC-USB-001`) |
| `BB 17 00` | Connect | handshake, empty both ways |
| `BB 28 00` | Connect | handshake, empty both ways |
| `BB 13 00` | Connect, job change | job record — two Unix timestamps + an ASCII label |
| `BB 10 00` | Calibrate only | black calibration (CORROBORATES itohio) |
| `BB 11 00` | Calibrate only | white calibration (CORROBORATES itohio) |
| `BB 01 00` | every measurement | trigger |
| `BB 01 09` | every measurement | measurement header — declares the spectral axis |
| `BB 01 10`/`11`/`12` | every measurement | spectral data chunks |
| `BB 01 13` | every measurement | fourth chunk, **not** spectral |
| `BB 21 01` | one long session, 1745 frames | streaming / live mode |

That is the whole observed vocabulary of `cmd`: **0x01, 0x0A, 0x10, 0x11,
0x13, 0x17, 0x21, 0x28**. Everything else in a 256-value `cmd` space is
unobserved — and unobserved on a Chinese instrument family whose firmware is
typically a single flat command switch is exactly where a bootloader entry,
a calibration-store write or a factory-reset lives.

Two further facts shape the policy:

- **The device does not validate request checksums** (`EXP-USB-002`). There is
  no accidental protection: a malformed frame that happens to name a dangerous
  command will be executed. Nothing between us and the firmware rejects
  nonsense on our behalf.
- **`BB 10 00` and `BB 11 00` — the calibration writes — are numerically
  adjacent to `BB 13 00` and `BB 17 00`, which are harmless.** The command
  space is *not* organised so that "low numbers are safe". A linear sweep
  walks straight through the calibration writes at step 16 and 17.

---

## 2. The envelope

### 2a. GREEN — probe freely, no further approval

**The sixteen triples above, and only with the payloads the vendor used.**
These are proven to be what the manufacturer's own software sends to this
device family. Replaying them cannot put the device in a state the vendor
software could not.

Two carve-outs even inside green:

- `BB 10 00` / `BB 11 00` **write calibration**. They are green only inside
  `EXP-CAL-001`, with the tiles present and a human watching, never in a
  survey. A survey that "just tries" them destroys the stored calibration.
- `BB 21 01` produced 1745 frames in one session. Treat it as a stream, not a
  query: send it only with a reader already running and a documented way to
  stop it (see §4).

### 2b. AMBER — one at a time, with the stop conditions of §4 armed

**`cmd` values that are unobserved but structurally adjacent to observed
ones, probed with `subcmd = 0x00` and an all-zero payload:**

```
cmd in {0x02..0x09, 0x0B..0x0F, 0x12, 0x14, 0x15, 0x16, 0x18, 0x19, 0x1A}
```

and, separately, **`subcmd` exploration of an already-green `cmd`**:

```
BB 01 ss   for ss in {0x01..0x08, 0x0A..0x0F, 0x14..0x1F}
AA 0A ss   for ss in {0x04..0x1F}
```

Rationale: the observed subcommands of `BB 01` are trigger (`00`), header
(`09`) and chunks (`10`–`13`). A device that answers `BB 01 0A` is far more
likely to be revealing another read of the *current measurement* than to be
writing anything. `AA 0A ss` is an information command by construction — all
four observed subcommands are pure reads.

**Amber requires, per probe:** device NOT on the calibration tile, identity
re-read before and after (§4b), one frame sent, one reply window, then stop
and record. Never a loop.

### 2c. RED — forbidden without a new, human-approved envelope

1. **`cmd >= 0x80`.** In a flat single-byte command switch the high half is
   where vendor/bootloader/service commands are conventionally parked, and we
   have zero observations there. No exceptions.
2. **Anything with a non-zero `param` byte (byte 3).** Every one of the 6252
   structural windows in the vendor corpus has `param == 0x00`. We do not know
   what the field means. A non-zero value may be "write" where zero is "read".
3. **Any payload that is not all-zero**, except the exact vendor payloads.
   A command byte alone is a question; a command byte with data is an
   instruction.
4. **`cmd` values 0x10, 0x11 with any subcmd other than 0x00**, and any
   neighbour of them (`0x0F`–`0x12`) — calibration territory.
5. **Any sweep**: no `for cmd in range(256)`, no nested loops, no unattended
   runs. `EXP-USB-004` is hereby redefined as **a sequence of individually
   logged single probes**, not a survey. If that is slow, it is slow.
6. **Repeating a command that produced an unexplained reply.** The second
   send is where a two-step "arm then commit" protocol commits.
7. **Anything at all while the device sits on the white tile or in the cap.**
   A calibration-write command is harmless-looking until it is pointed at a
   reference surface.

### 2d. What would justify widening it

- **A vendor capture containing the command.** The strongest evidence
  available and the reason §2a exists. More `.spm` sniffs, or a Windows
  session sniffing ColorQC2 through its settings screens, would move real
  commands from amber to green. **This is the highest-value next step and it
  needs no risky traffic at all.**
- **Firmware.** If an update image is ever obtainable, its command dispatch
  table settles the question outright.
- **A second, expendable unit.** Red becomes amber on a device nobody needs.
  Not on this one.
- Nothing else. Not "it looked harmless", not "the reply was empty", and not
  "the previous twenty were fine" — see §3.

---

## 3. How to recognise a state-changing reply BEFORE it is too late

This is the hard part, and it must be said honestly: **you cannot, in
general.** A firmware-write command can return the same empty
`BB xx 00 … FF cs` acknowledgement as a no-op. The envelope is therefore
built on *not sending* dangerous commands, not on detecting them afterwards.

What can be done is to detect that something changed, quickly:

**3a. Fingerprint before and after every amber probe.** All four identity
sub-commands, byte-for-byte. `AA 0A 00`–`03` returned identical frames across
five baud rates and two experiments, so they are a stable 240-byte
fingerprint. **Any change in any byte = stop, do not send another probe,
record both frames.** In particular a change in the `V11.3.` / `V10.0.0.0`
version strings or the `0.0.20231219` build date means firmware state moved.

**3b. Treat these replies as state-changing until proven otherwise:**

| Observation | Reading |
|---|---|
| A reply that does **not** echo the request's `start`/`cmd`/`subcmd` in bytes 0–2 | the device is not answering our question — it is reporting something |
| A reply longer or shorter than 60 bytes, or more than one reply | the device left the request/response pattern |
| Any unsolicited frame arriving with no request outstanding | prior art associates these with the button; from a probe it means a mode changed |
| A reply arriving later than ~1 s | a write or an erase, not a lookup |
| Silence where a reply was expected | possibly a reboot into a different mode; **do not retry** |
| `marker` (byte 58) != `0xFF` outside a `BB 01 09` header | in the vendor corpus 0x00 markers appear only there |

**3c. Latency is the cheapest tell.** Characterise normal reply latency
(`EXP-USB-005`) **before** running any amber probe, so an anomalously slow
reply is recognisable. A flash erase takes tens of milliseconds and is
visible. This ordering is a requirement, not a suggestion:
**EXP-USB-005 must precede EXP-USB-004.**

---

## 4. Stop conditions — abort the whole experiment, do not continue

Stop immediately, release the lease, and write up, on **any** of:

1. The identity fingerprint (§3a) changes in any byte.
2. The device stops answering `AA 0A 00 00`.
3. Any reply that does not echo bytes 0–2 of the request.
4. Any unsolicited frame.
5. A reply latency more than 5× the characterised norm.
6. More than 60 bytes returned for one request.
7. The device's own indicators change (LED, display, beep) without a human
   having touched it. **Amber probes must therefore be run with a human in
   the room**, which is a real constraint on scheduling, not a formality.
8. Anything at all the operator does not understand.

"Stop" means stop the experiment, not stop the probe and try the next one.

---

## 5. Procedure for `EXP-USB-004`, as re-scoped

1. `EXP-USB-005` first — reply-latency baseline, green commands only.
2. Acquire the lease. Device off the tile, cap off, in free air.
3. Identity fingerprint → record.
4. **One** amber probe: build the frame, log it, send it, read with a 2 s
   timeout, log every byte returned.
5. Identity fingerprint → record. Compare byte-for-byte. Any difference → §4.
6. Write the result into `EXPERIMENTS.md` — the frame, the reply, the two
   fingerprints. Then, and only then, probe the next value.
7. Never more than **one amber probe per lease**, and never unattended.

Yes, this is slow: ~40 amber probes is several sessions. The alternative is
a bricked instrument, and the corpus in §1 has already delivered most of what
the survey was going to find without sending a single byte.

---

## 6. A hazard that already exists, unprobed

`ChromIQ/core/argyll_runner.py:43` keeps `/dev/cu.usbserial-*` **in** Argyll's
serial scan on purpose, so serial SpectroScans still work. Argyll's
`fast_ser_dev_type()` (`spectro/inst.c:1446`) is then called during plain port
enumeration (`spectro/icoms_ux.c:167`) and writes foreign ASCII probes —
`;`, `D024\r\n`, `SV\r\n`, `P0\r` — to whatever is on that port, at 9600,
921600, 115200 and 38400 baud.

**So today, a CR30 plugged into a machine running ChromIQ is already being
sent unsolicited junk on every measurement start.** Nobody has checked what
it does with it. That is a real, shipped, unexamined exposure; it is also the
one piece of "dangerous" traffic whose exact bytes are already known. See
`EXP-USB-007` in `EXPERIMENTS.md` — it is amber, not red, and it is worth
running early because the answer changes an integration decision.
