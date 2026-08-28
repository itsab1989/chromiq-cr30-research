# PROTOCOL.md — CR30 wire protocol

Confidence levels per `CLAUDE.md` §4. Every VERIFIED line names its capture.

**Revised 2026-08-28 by `[CR30-SKEPTIC]`.** Session 1 filed several findings at
a confidence its evidence did not buy; the corrections are marked ⚠ in place.
The corrections do not change the conclusions — they change what is *proved*.

## 0. The evidence base

| Capture | What it is | Class |
|---|---|---|
| `captures/public/EXP-MAC-USB-001-identity.json` | this unit, macOS, 4 distinct device frames | VERIFIED-class, but see ⚠ below |
| `captures/public/EXP-USB-002-checksum.json` | this unit, one command, five checksums | VERIFIED-class |
| `captures/public/PRIORART-001-vendor-usb-frames.json` | **260 unique frames** from the vendor application driving a *second* CR30 on Windows | CORROBORATION only |
| `captures/public/PRIORART-002-spectra.json` | 58 unique spectra decoded from the above | CORROBORATION only |

⚠ **Two of the four published identity frames carry a checksum computed by
`tools/redact.py`, not by the device.** The redactor rewrites byte 59 after
replacing the device-id strings. Those two frames are self-consistent by
construction and are **not evidence for any checksum rule**. The device's own
bytes are in `captures/raw/` (gitignored) and do satisfy the rule. Pinned by
`tests/test_checksum_rule_space.py`.

`tools/mine_priorart_frames.py` extracts the prior-art corpus **structurally**
(start byte, `param == 0x00`, marker, chaining) and never looks at byte 59, so
the corpus can test checksum hypotheses without circularity. Of 6252 structural
windows, 3531 fail `sum(0..58)` — a false-positive rate that proves the
extraction is not selecting on the rule it is used to test.

## 1. Frame format

**VERIFIED** — every frame observed, in both directions, on two units, on two
platforms, is exactly **60 bytes**.

| Byte | Field | Observed |
|---|---|---|
| 0 | Start | `0xAA` identity class · `0xBB` command class (**now CORROBORATED**, 260 vendor frames) |
| 1 | Command | see §5 |
| 2 | Sub-command | see §5 |
| 3 | Parameter | `0x00` in **all 6252** windows across both units. Never seen non-zero. |
| 4–57 | Payload | 54 bytes. See §7.1 — the prior art's 4–55 reading is now **DISPROVEN**. |
| 58 | Marker | `0xFF`, **except on a `BB 01 09` measurement header**, where `0x00` also occurs — see §6 |
| 59 | Checksum | §2 |

## 2. Checksum

**The rule:**

```
checksum = sum(frame[0..58]) mod 256        # 59 bytes, marker INCLUDED
```

**Confidence: CORROBORATED, and now uniquely determined.** Not on session 1's
evidence — on the vendor corpus.

⚠ **What session 1's four frames actually proved.** They excluded whole
families: XOR over any range, negated/two's-complement sums, Fletcher-8,
Fletcher-16-low, position-weighted sums, and CRC-8 over 11 polynomials × 256
initial values × both bit orders × 5 ranges with `xorout` solved — **0 of
14 080 CRC parameterisations fit**. So "an unweighted additive byte sum" was
earned. But **fifteen** contiguous additive rules fit those four frames
exactly:

```
sum[0:55]+0xff  sum[0:56]+0xff  sum[0:57]+0xff  sum[0:58]+0xff  sum[0:59]+0x00
sum[1:55]+0xa9  …                                              sum[1:59]+0xaa
sum[2:55]+0xb3  …                                              sum[2:59]+0xb4
```

plus 2^12 = 4096 further indistinguishable variants per rule, because bytes
3, 4, 38, 43–48 and **55, 56, 57** are zero in all four. The confounds are
structural: bytes 0/1/3 are constant (start of range trades against the
constant), byte 58 is constant `0xFF` (marker inclusion trades against the
constant), 55–57 are zero (payload extent invisible).

**What settles it.** Against 260 vendor frames spanning both start classes,
**both marker values**, eight command bytes and frames with data at bytes 54
and 56, exactly **one** contiguous rule survives — `sum[0:59] + 0x00`. The
frames with marker `0x00` are the discriminating case, and they choose our
rule over `sum[0:58]+0xff` outright.

**Prior art, precisely.** itohio
(`cr30reader/protocol/packets.py::calculate_checksum`) computes `sum(0..57)`
and subtracts 1 when the start byte is `0xBB`. Its **`0xAA` branch is
DISPROVEN**. Its **`0xBB` branch is not "a coincidental patch in the wrong
place"** — `sum(0..57) − 1` is `sum[0:58]+0xff`, one of the fifteen rules our
own four frames could not distinguish from the correct one. It is wrong only
on frames where the marker is `0x00`, which is exactly where their own
documentation says `0xBB` markers can be `0x00`.

**VERIFIED, and it is why the bug survived** (`EXP-USB-002`): the CR30 does not
validate the checksum of a request — see §3, which now qualifies that.

**The checksum matters in the receive direction.** Device replies are
consistently checksummed on both units, so it is the only integrity check on
inbound spectral data. Per `CLAUDE.md` §14, a mismatch must fail loudly.

## 3. Request-checksum validation — ⚠ downgraded to PROBABLE

`EXP-USB-002` sent `AA 0A 00 00` five times varying only byte 59 and got five
identical replies. **That data cannot exclude its strongest rival:** the device
may have validated, rejected, and replayed a cached reply. Every case used the
same sub-command, so a cache and an ignore produce a byte-identical transcript.
A second rival: the device may never read byte 59 at all, if it acts on a
prefix or frames by inter-byte gap.

**⚠ Both rivals are now DISPROVEN — restore to VERIFIED.** `[CR30-USB]`'s
`EXP-USB-006` sent `AA 0A 00 00` with the payload set to a ramp and the reply
came back **carrying request bytes echoed into offsets 4 and 55–57**; a request
with `A5 5A` at 56–57 was answered with `A5 5A` still there. **A cached reply
cannot echo bytes that were only just sent**, so the device parses the request.
And `EXP-USB-003` extended the result to two `0xBB` commands, with the device
**recomputing byte 59 itself** rather than passing our bad checksum through.

The device also **ignores the request's marker byte** — byte 58 set to `0x00`
or `0x5A` produced the normal reply in both classes (`EXP-USB-006`).

Implementation consequence unchanged: no transmit-side error detection exists
(`ERRORS.md`).

## 4. Baud rate — ⚠ downgraded to PROBABLE

**Observed (VERIFIED):** byte-identical replies at 9600, 19200, 38400, 57600
and 115200 (`EXP-MAC-USB-001`).

**Inferred (PROBABLE):** that the *device* discards line coding. The
observation is equally explained by Apple's `AppleUSBCHCOM` never emitting the
CH34x divisor vendor request. Session 1 tested one host driver on one OS and
wrote a conclusion about the device.

**Decided by `EXP-USB-007`**: break the *framing*, not the rate — 7 data bits,
or 2 stop bits, or mark parity. A real UART behind the bridge truncates `0xAA`
to `0x2A` at 7 bits and cannot answer; a firmware CDC endpoint with no UART
answers identically.

**The implementation consequence is unchanged and safe either way:** never
expose, negotiate or "detect" a baud rate, and never diagnose a fault as a
wrong baud rate.

## 5. Command vocabulary

**CORROBORATED** from `PRIORART-001` — the complete set the vendor application
uses across connect, calibrate, measure, button and job sessions. Eight `cmd`
bytes: `0x01, 0x0A, 0x10, 0x11, 0x13, 0x17, 0x21, 0x28`.

| Triple | Context | Reading | Confidence |
|---|---|---|---|
| `AA 0A 00`–`03` | connect | device information | **VERIFIED** here (§6) |
| `BB 17 00` | connect | **pure echo** — reply equals request in bytes 0–58 (`EXP-USB-003`) | VERIFIED |
| `BB 28 00` | connect | **pure echo** — a marker planted at bytes 53,54 comes straight back (`EXP-USB-003`) | VERIFIED |
| `BB 13 00` | connect, job change | **job record**: two little-endian Unix timestamps at payload 1..8, ASCII label at payload 9 | CORROBORATED |
| `BB 10 00` | calibration only | **black calibration** | CORROBORATED |
| `BB 11 00` | calibration only | **white calibration** | CORROBORATED |
| `BB 01 00` | measurement | trigger | CORROBORATED |
| `BB 01 09` | measurement | header — declares the spectral axis (§7) | CORROBORATED |
| `BB 01 10/11/12` | measurement | spectral chunks (§7) | CORROBORATED |
| `BB 01 13` | measurement | fourth chunk, **not spectral** (§7) | CORROBORATED |
| `BB 21 01` | one long session, **1745 frames** | streaming / live mode | HYPOTHESIS |

Calibration replies carry `0x01` at **payload index 2 (frame offset 6)** for
both black and white, on all four occurrences. itohio calls this "payload byte
1"; the offset is 2. Reading it as success is HYPOTHESIS — no failed
calibration has been captured, so `0x01` has never been contrasted with
anything.

⚠ **`BB 13 00` is not a sensor-parameter command.** `STATUS.md` and
`PROTOCOL.md` §6.4 previously called parameter/configuration commands the
"highest-value unknown" because "integration time and averaging would live
there" and they are "the only things that could change the ~1 s/reading
verdict". The vendor capture *named* `param change.spm` contains **only**
`BB 13 00` frames, and their payload is two Unix timestamps (decoding to
2025-10-11, matching the capture dates) plus the ASCII label `Check`. **No
sensor-parameter command appears anywhere in ten vendor sessions.** On present
evidence there is no known knob for integration time or averaging. That is a
negative result, and it should be treated as one rather than left as an open
promise.

## 6. Device information — `0xAA 0x0A ss 0x00`

**VERIFIED** (`EXP-MAC-USB-001`), on **one unit**. Offsets are absolute.

| Sub | Field | Offset | Length | Observed on this unit |
|---|---|---|---|---|
| `0x00` | Device id | 9 | ≥10 | (redacted) |
| `0x00` | **Model** | 39 | ≥4 | **`CR30`** |
| `0x00` | Unknown | 5–8 | 4 | `56 00 19 03` |
| `0x01` | Second id | 19 | ≥10 | (redacted) |
| `0x01` | Version | 49 | 8 | `V11.3.` |
| `0x02` | Build date | 5 | 12 | `0.0.20231219` |
| `0x02` | Version | 29 | 9 | `V10.0.0.0` |
| `0x03` | Unknown | 19 | 1 | `0x02` |

⚠ **The lengths are lower bounds, not field widths.** They are the lengths of
*this unit's* values. `src/cr30/identity.py` hard-codes them as exact, which
silently truncates a longer value on another unit and makes `is_cr30()` return
True for any model whose name merely *starts* with `CR30`. Fields should be
read to the NUL terminator inside a bounded region.

The reply echoes the request's start, command and sub-command in bytes 0–2,
which gives free request/response correlation. `parse_identity()` does not
currently check it.

## 7. Measurement frames

### 7.1 Payload extent — resolved, and it is command-class specific

Two independent results, which only make sense together.

**`[CR30-USB]`, `EXP-USB-006`, our unit.** A reply is the request buffer
**mutated in place**. For the `AA 0A` class the device overwrites offsets
**5–54**, forces byte 58, recomputes byte 59, and **leaves offsets 4, 55, 56
and 57 holding whatever the caller sent** — proved by planting `A5 5A` at 56–57
and getting it back. So session 1 saw `0x00` at 56–57 because the *requests*
were zero there, not because the field ends at 55.

**`[CR30-SKEPTIC]`, `PRIORART-001`, a second unit.** Exactly **20** frames (7 distinct) in
the vendor corpus carry non-zero data at byte 56, and they are **all** `BB 01 09`
measurement headers — device-emitted, payload non-empty, and the checksum
covers byte 56. Bytes 55 and 57 are zero in all 6252 windows.

**Together:** `[CR30-USB]`'s HYPOTHESIS that "the 5–54 span is command-class
specific and a measurement chunk may differ" is **CORROBORATED**. The frame's
payload field is **4–57 inclusive, 54 bytes**; the *device-written* span is
5–54 for `AA 0A` and reaches byte 56 for `BB 01 09`. itohio's "payload = 4–55"
is DISPROVEN as a description of the frame. A decoder must not assume either
span — read what the frame declares (§7.2).

### 7.1a ⚠ Disagreement between the agents — resolved against `[CR30-USB]`

`src/cr30/frame.py` currently states, as VERIFIED from `EXP-USB-006`:

> *the device forces byte 58 to `0xFF` on every frame it emits, whatever the
> request contained. So on this firmware the two rules cannot be told apart on
> `0xBB` traffic, and their `0xBB` branch is correct.*

**DISPROVEN.** The device emits marker `0x00` on `BB 01 09` measurement
headers — **20 occurrences, 7 distinct frames** across two vendor sessions
(`captures/public/PRIORART-001-vendor-usb-frames.json`), payload non-empty,
checksum valid under `sum(0..58)`.

The claim is true for `AA 0A`, `BB 13`, `BB 17` and `BB 28` — every class
`EXP-USB-006` exercised — and false for the one class it could not reach,
which is the one that carries the measurement. Consequently itohio's `0xBB`
branch is **not** correct on this firmware: it is off by one on exactly the
measurement header frames, the frames a real implementation must parse. That
is also why those 20 frames are what makes `sum(0..58)` the unique surviving
rule (§2).

**Requested action for `[CR30-USB]`:** amend the `checksum()` docstring. The
finding that motivated it — that the device rewrites byte 58 and byte 59 on the
reply — stands and is valuable; only "on every frame it emits" is too strong.

### 7.1b Transport rules — VERIFIED, `[CR30-USB]`, `EXP-USB-005/-005b/-005c/-007`

| Rule | Evidence |
|---|---|
| **One frame per `write()`.** A 60-byte frame split 30+30, 59+1, 1+59 or 20+20+20 is answered with **silence** | 4/4, `EXP-USB-005c` |
| **Never more than one frame per write.** 120 B and 180 B → no reply. Recovers on the next single-frame write, no reopen | `EXP-USB-005b` |
| **No settle delay after opening the port.** The session-1 probe's 300 ms was untested superstition | 10/10 valid at 0 ms; identical at 5/25/50/100/300 ms |
| **No inter-command delay** | 30/30 valid at a 0 ms gap |
| Round trip **0.767 ms** median (min 0.706, max 1.491) over 100 transactions | `EXP-USB-005` |
| Port close/reopen: **20/20** clean, zero open errors | `EXP-USB-005` |
| Silent when idle over **90 s**, and over 12 min of polling | `EXP-USB-005/-005c` |
| **The request checksum is not validated on the `0xBB` class either** — including on `BB 13`, which the device demonstrably acts on | `EXP-USB-003` |
| **The device echoes commands it does not implement.** A 60-byte reply is **not** evidence a command exists | `EXP-USB-003` |
| **Argyll's serial-scan probe strings are inert.** 8 strings × 4 baud rates = 32 probes: 0 bytes back, identity fingerprint unchanged 32/32 | `EXP-USB-007` |

⚠ The one-write rule is the most portability-critical result of session 2. An
implementation that chunks, buffers or line-buffers its writes gets **silence**,
not an error, and will look like a dead device.

**On measuring latency at all.** The first two probes of session 2 reported
~6.3 ms with suspicious consistency. That was the *probe's* 5 ms `sleep()`
granularity, not the device. The real figure is **eight times faster**. Any
latency number in this repository must state its polling resolution.

### 7.1c Line coding — §3's *mechanism* is now VERIFIED, not inferred

Session 1 concluded "line coding never reaches a UART" from identical replies at
five baud rates. That observation is equally consistent with the bridge honouring
`SET_LINE_CODING` at both ends, so it did not prove the mechanism — only the
behaviour. Two measurements do (`EXP-USB-005`):

- a 60-byte frame **completes in 0.77 ms**, where 60 bytes across a 115200-baud
  line take **5.2 ms**;
- at a nominal **300 baud** — where 60 bytes would take **2 seconds** — the reply
  still arrived in **0.97 ms**.

Framing is ignored too: **8N1, 7E1, 8N2, 7N1 and 8O1 are byte-identical**, as
are 300, 115200 and 1000000 baud. The conclusion session 1 reached is right; it
now rests on evidence that could have falsified it.

### 7.2 The header frame declares the spectral axis

Every `BB 01 09` header in all ten vendor sessions carries the same
`frame[4:7] = 28 1f 0a` = **40, 31, 10**.

Independently, the vendor application's own exported record for the same
traffic (`param change-and-measure.colors`, base64 JSON) contains:

```json
"spectral_info": { "wave_start": 400, "wave_number": 31, "wave_interval": 10 }
```

**CORROBORATED reading:** byte 4 = start wavelength ÷ 10, byte 5 = band count,
byte 6 = step in nm. It is *consistent with* — not proof of — a self-describing
axis, because all 70 headers observed are identical.

**Implementation consequence, sound either way:** do not hard-code 400–700/10.
Read the header, and **fail loudly if it is not `28 1f 0a`** rather than
assuming.

### 7.3 Chunk layout — the "unexplained 20 bytes" do not exist

Floats are little-endian `float32`, **twelve per chunk**, starting at frame
offset 6:

```
chunk 0x10 -> values  0..11      (12)
chunk 0x11 -> values 12..23      (12)
chunk 0x12 -> values 24..30      ( 7, remaining slots zero-padded)
                                 -- 31 values total
chunk 0x13 -> NOT spectral. Carries a copy of values 0..4 at frame offset 34.
```

itohio concatenates 0x10–0x12 and slices 124 bytes, which arrives at the same
31 numbers by accident. Their "144 accumulated, 124 used, **20 unexplained**"
is chunk `0x12`'s zero padding, and the chunk `0x13` they fetch and discard is
a different field. `MEASUREMENT.md`'s statement that "that asymmetry is a
strong hint the chunking is misunderstood" is **resolved**: the chunking was
understood, the accounting was not.

`tools/decode_spectra.py` implements this and **rejects** a measurement whose
chunks do not deliver what the header declares.

### 7.4 The marker byte is not a constant

Marker `0x00` occurs **only** on `BB 01 09` headers, never on any other frame,
in either unit's traffic. Where the capture names the trigger:

| Capture | marker `0x00` | marker `0xFF` |
|---|---|---|
| `button presses and disconnected presses` | **5** | 0 |
| `Test Sample …`, `Test Target …`, `Calibrate …`, `param change-and-measure` | 0 | **25** |
| `experiments - long` (unlabelled, mixed) | 15 | 18 |

**VERIFIED on the REQUEST side (`EXP-USB-006`, our unit):** byte 58 is
**device-set, never echoed, and never validated**. Requests sent with byte 58 =
`0x00` and `0x5A` were answered normally, with the reply's byte 58 = `0xFF` both
times and the reply otherwise byte-identical to the control. Whatever byte 58
means, it means it in the **reply** direction only, and a request may carry
anything there.

**HYPOTHESIS, well corroborated:** byte 58 on a measurement header flags a
**button-triggered / unsolicited** reading. Every capture with an unambiguous
label agrees; the one mixed capture is unlabelled and neither confirms nor
refutes it. This answers `PROTOCOL.md` §6.3 as it previously stood: "marker" is
a flag field, not a constant, and an implementation must not assert `0xFF`.

## 8. Still open

1. `56 00 19 03` at offset 5 of sub `0x00` — HYPOTHESIS: `0x56` = 'V'.
2. Two version strings (`V11.3.`, `V10.0.0.0`) — firmware vs algorithm?
3. Sub `0x03` returning `0x02` — status or capability byte.
4. `BB 21 01` — 1745 frames in one session; the first carries `00 01 00 …`.
   Streaming or live preview. Unresolved and **green only as a stream**
   (`SAFETY_ENVELOPE.md` §2a).
5. `BB 17 00` / `BB 28 00` — empty both ways. Handshake, keep-alive or mode?
6. Whether calibration status `0x01` contrasts with anything.
7. What the copy of values 0..4 in chunk `0x13` is for.
8. **Whether any sensor-parameter command exists at all.** See §5.
