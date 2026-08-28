# EXPERIMENTS.md

Format per `CLAUDE.md` §15. Never "I tried it and it worked".

---

## EXP-MAC-USB-001 — baseline USB identity probe · ✅ DONE

**Hypothesis.** The CR30 is reachable from macOS as a serial device without
installing a driver, and answers the published identity command `AA 0A ss 00`.
Corollary to test: the published baud rate matters.

**Setup.** macOS 15.7.9 (24G830) arm64 · CR30 on USB · `/dev/cu.usbserial-10` ·
pyserial 3.5 · `tools/probe_identity.py` · ColorQC2 not involved · device
uncalibrated, freshly plugged.

**Procedure.** For each of 115200/19200/9600/57600/38400 baud: open 8N1 no flow
control, settle 300 ms, drain 1.0 s passively, then send `AA 0A ss 00` for
ss = 0x00..0x03 and capture all bytes returned.

**Expected.** Either no response (driver missing) or a 60-byte reply at one
"correct" baud rate.

**Actual.** A 60-byte reply to **every** query at **every** baud rate, all
byte-for-byte identical across baud rates. Passive windows were empty. The
device reports the ASCII model string `CR30` at offset 39.

**Evidence.** `captures/public/EXP-MAC-USB-001-identity.json`

**Conclusions.**
1. macOS drives the device natively — **VERIFIED**, falsifies ChromIQ #159 §9b.
2. Baud rate is not a protocol parameter — **VERIFIED**.
3. Device self-identifies as `CR30` — **VERIFIED**.
4. Prior-art checksum rule fails on all four device frames; `sum(0..58) mod 256`
   holds on all four — **VERIFIED** (motivated EXP-USB-002).
5. Device is silent when idle — **VERIFIED** for a 1 s window; not a claim about
   longer idles.

**Next.** EXP-USB-002.

---

## EXP-USB-002 — does the device validate the request checksum? · ✅ DONE

**Hypothesis.** EXP-MAC-USB-001 sent every request with the prior-art (wrong)
checksum and still got replies. Either the device ignores request checksums, or
the prior-art rule is right for transmit and wrong for receive.

**Setup.** As above. Only byte 59 varies; the other 59 bytes are byte-identical
across all five cases. `tools/probe_checksum.py`.

**Procedure.** Send `AA 0A 00 00` five times with byte 59 = correct (`0xB3`),
prior-art (`0xB4`), `0x00`, `0xFF`, `0x42`. Record every reply.

**Expected.** If the device validates, the four wrong values yield no reply or
an error frame.

**Actual.** All five produced a normal 60-byte reply carrying a valid
`sum(0..58)` checksum.

**Evidence.** `captures/public/EXP-USB-002-checksum.json`

**Conclusion.** The device **does not validate request checksums** —
**VERIFIED**. This explains how the prior-art error survived undetected: on
transmit it has no consequence. The prior-art rule is **DISPROVEN** for received
frames, where it is off by exactly +1.

**Caveat, deliberately stated.** This is verified for **one command**
(`AA 0A 00`). A command with side effects — calibration, trigger — might be
validated where an identity query is not. Do not generalise to `0xBB` frames
until tested.

**Next.** EXP-USB-003 (checksum enforcement on a `0xBB` command), and the
measurement/calibration sequence.

---

## PRIORART-001 — mine the vendor sniffer dumps · ✅ DONE (no hardware)

**Author.** `[CR30-SKEPTIC]`, 2026-08-28.

**Hypothesis.** `itohio/color-science` ships ten Eltima Serial-Port-Monitor
captures of the VENDOR application driving a CR30
(`reverse-engineer-c30/serial-sniffer/*.spm`). Session 1 did not open them. If
frames can be recovered, they supply the `0xBB` traffic, the `0x00` markers and
the measurement data that our own four identity frames cannot.

**Setup.** No hardware, no lease. `tools/mine_priorart_frames.py`.

**Procedure.** Extract every 60-byte window **structurally** — `byte0 ∈
{0xAA,0xBB}`, `byte3 == 0x00`, `byte58 ∈ {0x00,0xFF}`, chaining — and **never
using byte 59**, so the corpus can test checksum hypotheses without
circularity. Drop `AA 0A` identity frames (they carry that unit's device ids);
never rewrite byte 59.

**Expected.** A few hundred frames, with a measurable false-positive rate.

**Actual.** 6252 structural windows → **2721 valid frames, 260 unique**, from
ten sessions. **3531 windows fail `sum(0..58)`** — the false-positive rate that
proves the extraction is not selecting on the rule it is used to test. Two
control rules (`sum[0:59]+0x37`, `sum[0:58]+0x91`) matched 0 and 1 windows
respectively out of 6305, so the extraction is clean.

**Evidence.** `captures/public/PRIORART-001-vendor-usb-frames.json`

**Conclusions.**
1. `sum(0..58) mod 256` is the **only** contiguous additive rule that survives
   the corpus plus the two un-redacted `0xAA` frames — **CORROBORATED**.
2. `0xBB` is a real start byte — **CORROBORATED** (260 frames).
3. The complete vendor command vocabulary is 8 `cmd` bytes — **CORROBORATED**.
   Basis of `SAFETY_ENVELOPE.md`.
4. Byte 58 is **not** a constant; `0x00` occurs on `BB 01 09` headers.
5. Payload extends to byte 57 — prior art's 4–55 is **DISPROVEN** (data at 56).
6. The prior art's "20 unexplained bytes" **do not exist** (`PROTOCOL.md` §7.3).
7. No sensor-parameter command appears anywhere, including in the capture named
   `param change.spm` — a **negative result**, see `PROTOCOL.md` §5.

**Caveat, deliberately stated.** A different unit, a different platform, a
different toolchain, decoded by us. **CORROBORATION, never VERIFIED.**
Everything above must be re-observed on our unit.

---

## EXP-SPEC-001 — are the 31 bands independent? · ✅ ANALYSIS DONE, CONFIRMATION PENDING

Full design and result in `MEASUREMENT.md`. Summary: on 58 unique spectra
decoded from `PRIORART-001`, there is **no singular-value cliff at any claimed
channel count** (largest gap anywhere 0.63 decades; σ₁₄/σ₀ = 5.1e-05, 400×
above float32 round-off), and the high-order basis vectors are alternating
band-to-band (roughness 6–15) where a ~20 nm FWHM filter basis cannot exceed
~0.1. **The linear form of the ~11-channel reconstruction hypothesis is
DISPROVEN**; nonlinear reconstruction is not excluded by the rank test.

`tools/spectral_rank.py`, pinned by `tests/test_spectral_independence.py`.

**Next:** EXP-SPEC-001a (noise-covariance rank) and EXP-SPEC-001b (didymium
filter), both specified in `MEASUREMENT.md`, both needing our own unit.

---

## ⚠ EXP-USB-003 / 005 / 005b / 006 — `[CR30-USB]`'s session-2 hardware work

**RECONSTRUCTED FROM THE CAPTURES BY `[CR30-SKEPTIC]`. `[CR30-USB]` MUST REVIEW
AND CORRECT.**

`[CR30-SKEPTIC]` rewrote `PROTOCOL.md`, `EXPERIMENTS.md` and `STATUS.md`
wholesale while `[CR30-USB]` was writing to the same uncommitted files, and
**overwrote their prose**. Their evidence is intact — the five capture JSONs,
six probe tools and three `src/cr30/` modules were separate files and survive
untouched — but the conclusions below are `[CR30-SKEPTIC]`'s reading of
`[CR30-USB]`'s data, not `[CR30-USB]`'s own words. Anything wrong here is the
reconstruction's fault, not the experiment's.

### EXP-USB-003 — is the checksum enforced on a `0xBB` command? · ✅ DONE

**Evidence.** `captures/public/EXP-USB-003-stage1-bb-class.json`,
`EXP-USB-003-stage2-bb-checksum.json`

**Stage 1.** `BB 28 00 pp` for pp = 00, 01, 02, 03, FF. Every one produced a
60-byte reply that is a **byte-for-byte echo of the request**.

**Stage 2.** `BB 28 00 00` and `BB 13 00 00` sent with correct, −1, +1, `0x00`,
`0xFF` and `0x42` checksums, interleaved with `AA 0A 00 00` re-baselines.

**Result.** All twelve produced normal replies. **The device does not validate
request checksums on the `0xBB` class either** — the caveat in `EXP-USB-002`
("do not generalise to `0xBB` until tested") is now discharged for two `0xBB`
commands. `PROTOCOL.md` §3.

**And a stronger finding than that.** With a wrong request checksum, the reply
to `BB 28` differs from the request **at byte 59 only** — the device echoed
bytes 0–58 and **recomputed byte 59 itself, correctly**. It did not pass our
bad checksum through. Combined with EXP-USB-006 below, this is what disposes of
the cached-reply hypothesis.

**Also established:**
- `BB 28 00` and `BB 17 00` are **pure echoes** — the reply equals the request
  in bytes 0–58, and a marker planted at bytes 53,54 (`A5 5A`) comes straight
  back. The device writes no response block. They are not queries, and
  `PROTOCOL.md` §5's "handshake" reading should be replaced by "echo/loopback".
- `BB 13 00` **is** a query: the device overwrites bytes 5–10 of the request.

### EXP-USB-005 — response-latency baseline · ✅ DONE

**Evidence.** `captures/public/EXP-USB-005-timing.json`

| | first byte | last byte |
|---|---|---|
| `AA 0A 00 00`, n=50 | median **0.735 ms**, max 0.932, σ 0.053 | median 0.767 ms, max 1.491 |
| `BB 13 Check`, n=50 | median **0.715 ms**, max 0.924, σ 0.049 | median 0.737 ms, max 0.967 |

50/50 replies for both. Settle delays of 0/5/25/50/100/300 ms all give 10/10 —
**no settling time is needed**. Inter-command delays of 0/1/5/20 ms all give
30/30 — **no inter-command gap is needed**.

**This is the baseline `SAFETY_ENVELOPE.md` §3c requires**, and it is a very
tight one: sub-millisecond, σ ≈ 0.05 ms. A reply slower than **~5 ms** is
already 80σ out and should be treated as a write. The 5× rule in
`SAFETY_ENVELOPE.md` §4 is generous; use **>5 ms, absolute**.

### EXP-USB-005b — `BB 13` field stability and write granularity · ✅ DONE

**Evidence.** `captures/public/EXP-USB-005b-bb13-field.json`

`BB 13 00` returns the same values (81, 1445, `51000000a505`) across 20
repeats, across 50 interleaved identity queries, **across a port close/reopen**,
and **across a 30 s idle**. So whatever `BB 13` reports is persistent device
state, not a per-session value.

**Two hard implementation constraints:**
- **One frame per write.** 1 frame in a single `write()` → 60 bytes back;
  **2 or 3 frames in one `write()` → 0 bytes back.** The device does not
  buffer, and a batched write is silently dropped.
- **No pipelining.** A pipelined request returned 0 bytes; the device recovered
  on the next single request.

### EXP-USB-006 — do request fields reach the device? · ✅ DONE

**Evidence.** `captures/public/EXP-USB-006-request-fields-AB.json`

**Battery A, `AA 0A 00 00`:** with the payload set to a ramp, the reply is
**not** the control reply — it carries `0x01` at byte 4 and `66 6d 74` at bytes
55–57, echoed from the request. With bytes 56,57 = `A5 5A`, the reply carries
`a5 5a` at bytes 56,57.

**Two consequences, both important:**

1. **The cached-reply hypothesis is DISPROVEN.** `[CR30-SKEPTIC]` objected that
   `EXP-USB-002` could not distinguish "ignores the checksum" from "validates,
   rejects, and replays the last reply". **A cached reply cannot echo bytes
   that were only just sent.** The device parses the request. `PROTOCOL.md` §3
   may be restored to VERIFIED on this evidence.
2. **The device does NOT write bytes 55–57 for the `AA 0A` class** — those
   offsets come back holding what the caller sent. The device-written span is
   5–54. But it is **command-class specific**: the vendor corpus shows the
   device writing byte 56 on `BB 01 09` measurement headers. Both results are
   needed; neither alone describes the frame. `PROTOCOL.md` §7.1.

**Battery A/B, marker:** request byte 58 = `0x00` or `0x5A` produced the normal
reply in both classes. **The device ignores the request's marker byte**, as it
ignores the request's checksum.

### The two agents' evidence is only decisive together

Neither corpus determines the checksum rule alone:

| Evidence | Contiguous additive rules that fit |
|---|---|
| `EXP-MAC-USB-001` (4 identity frames) | **15** |
| `[CR30-USB]`'s session-2 frames (11 unique, data at bytes 53–57, all marker `0xFF`) | **2** — `sum[0:59]+0x00` and `sum[0:58]+0xFF` |
| `PRIORART-001` alone (260 frames, all `0xBB`) | **2** — `sum[0:59]+0x00` and `sum[1:59]+0xBB` |
| **All of it together (269 unique frames)** | **1 — `sum(0..58) mod 256`** |

`[CR30-USB]`'s frames kill the payload-extent ambiguity (they carry data at
53–57); the prior-art frames kill the marker ambiguity (they carry marker
`0x00`); the `0xAA` frames kill the byte-0 ambiguity. Pinned by
`tests/test_checksum_rule_space.py`.

---

## Queued — not yet run

| ID | Question | Hardware? | Human? |
|---|---|---|---|
| **EXP-USB-005** | Response-latency baseline — **must run BEFORE EXP-USB-004** | yes | no |
| **EXP-USB-006** | Does the device really ignore request checksums, or is it replaying a cached reply? Vary the **sub-command**, not just byte 59; then truncate the request to 4 and 59 bytes | yes | no |
| **EXP-USB-007** | Is baud invariance the device or the macOS driver? Break the **framing**: 7 data bits, 2 stop bits, mark parity | yes | no |
| **EXP-USB-008** | What does a CR30 do when fed Argyll's serial-probe ASCII (`;`, `D024\r\n`, `SV\r\n`, `P0\r`) at 9600/921600/115200/38400? **This already happens on every ChromIQ measurement start** — `INTEGRATION.md` §8 | yes | no |
| EXP-USB-003 | Is the checksum enforced on a `0xBB` command? | yes | no |
| **EXP-USB-004** | Command-space probe — **re-scoped** to individually logged single probes | yes | **yes, in the room** |
| EXP-CAL-001 | Black then white calibration, status codes, failure modes | yes | **yes — tiles** |
| EXP-MEAS-001 | One software-triggered measurement, full transaction log | yes | **yes — placement** |
| EXP-MEAS-002 | Button-triggered measurement; does the header marker really go `0x00`? | yes | **yes — button** |
| EXP-SPEC-001a | Noise-covariance rank on ≥150 repeats without lifting | yes | **yes — clamp** |
| EXP-SPEC-001b | Didymium / holmium-oxide filter over the white tile | yes | **yes — buy a filter** |
| EXP-BLE-001 | Does the device advertise BLE, and with what GATT profile? | yes | maybe |
| EXP-PRIORART-002 | Sniff ColorQC2 through its settings screens on Windows. **The highest-value next step: it widens the safety envelope without sending a single risky byte** | yes | yes |

⚠ **EXP-USB-004 is governed by `SAFETY_ENVELOPE.md`, which is now published.**
It is re-scoped from "survey the command space" to "a sequence of individually
logged single probes, one per lease, attended". A sweep in any form is
forbidden. `EXP-USB-005` must run first, because a latency baseline is the only
cheap way to notice a write.

---

# Session 2 — `[CR30-USB]`, 2026-08-28, macOS 15.7.9 (24G830) arm64

Lease held by `[CR30-USB]` throughout. `/dev/cu.usbserial-10`. ColorQC2 not
running (`ps` verified). No firmware or calibration writes were sent.

---

## EXP-USB-003 — is the checksum enforced on the `0xBB` command class? · ✅ DONE

**Hypothesis.** `EXP-USB-002` proved only that `AA 0A 00` ignores the request
checksum. A side-effecting or state-bearing `0xBB` command might validate it.

**Choosing the least side-effecting `0xBB` command.** The only `0xBB` commands
with any provenance are the three that itohio/color-science's
`CR30Device.handshake()` issues on **every connect**: `BB 17 00 00`
("initialize"), `BB 13 00 00 + b"Check"` ("check"), and `BB 28 00 <idx>`
("query parameters"). A command the vendor's own software sends unconditionally
before doing anything cannot leave the device in a state the vendor software
could not. `BB 28` was chosen first because it is named as a *query* and takes
an index. `BB 10`/`BB 11` (calibration) were excluded: they write.

**Setup.** `tools/probe_bb_class.py`, then `tools/probe_bb_checksum.py`.
Every step bracketed by an `AA 0A 00 00` re-baseline.

**Procedure.**
1. Baseline `AA 0A 00 00`; abort if it fails.
2. `BB 28 00 xx` for xx = 00, 01, 02, 03, FF.
3. `BB 13`, `BB 17`, each with a re-baseline.
4. Vary **only byte 59** on `BB 28 00 00`: correct (`0xE2`), `0xE1`, `0xE3`,
   `0x00`, `0xFF`, `0x42`.
5. Vary **only byte 59** on `BB 13 00 00 + b"Check"`: correct (`0xAB`), `0xAA`,
   `0x00`, `0xFF`, `0x42`.

**Expected.** If the device validates, wrong checksums yield silence or an error.

**Actual.**
- Every `0xBB` command answered with a valid 60-byte frame. **First `0xBB`
  traffic this project has ever captured.**
- `BB 28` and `BB 17` came back as an **exact copy of the request**, with only
  byte 58 forced to `0xFF` and byte 59 recomputed. A request carrying `A5 5A`
  at frame offsets 53–54 got those same bytes back: **the device wrote nothing.**
- `BB 13` is **different**: it overwrote frame offsets **5–10** with
  `51 00 00 00 3C 04`. It is a real, implemented command.
- All six `BB 28` checksum values and all five `BB 13` checksum values produced
  a **byte-identical reply body** (bytes 0–57). The only byte that moved was 59,
  which the device recomputes.
- Opening and closing identity baselines were byte-identical.

**Evidence.** `captures/public/EXP-USB-003-stage1-bb-class.json`,
`captures/public/EXP-USB-003-stage2-bb-checksum.json`.

**Conclusions.**
1. **The device does not validate request checksums on the `0xBB` class
   either — VERIFIED**, and now on a command it demonstrably *acts on*
   (`BB 13`), not only on an information query. `EXP-USB-002`'s deliberate
   caveat is discharged.
2. **The CR30 echoes commands it does not implement — VERIFIED.** This is the
   most operationally important result of the session. *A 60-byte reply is not
   evidence that a command exists.* Any command-space survey that counts replies
   will invent a command set. `src/cr30/session.py::is_echo()` is the
   discriminator; `Session.transact_checked()` refuses to return an echo as a
   result.
3. itohio's `BB 17` "initialize device" and `BB 28` "query parameters" are
   **not implemented** on firmware `V11.3.` / `V10.0.0.0` / build `0.0.20231219`
   — **PROBABLE**, not VERIFIED: they might be valid only in a state we have not
   reached. `PRIORART-001` shows the vendor sends both and gets nothing back
   either, which corroborates it.
4. `BB 13` is a real command — **VERIFIED**. See EXP-USB-005b for what its
   reply field is, and is not.

**Confidence.** VERIFIED for 1, 2, 4. PROBABLE for 3.

**Next.** EXP-USB-006 (what the device parses), EXP-USB-005 (timing).

---

## EXP-USB-006 — how much of a *request* does the device parse? · ✅ DONE

**Hypothesis.** `PROTOCOL.md` §6 Q1 (is the payload 4–55 or 4–57?) and Q3 (is
byte 58 a constant marker or something else?) can both be attacked without
sending a new command, by varying request bytes and watching the reply.

**Setup.** `tools/probe_request_fields.py`. One byte-group changes per case;
all other 59 bytes byte-identical. The script asserts each mutation landed
before any conclusion is drawn.

**Procedure.** On `AA 0A 00 00` (device-info read, zero risk) and on
`BB 28 00 00` (framing byte only): control · payload 4–57 = a ramp ·
bytes 56,57 = `A5 5A` only · marker byte 58 = `0x00` · marker = `0x5A` ·
control again.

**Expected.** If bytes 56–57 are device payload they will be overwritten. If
byte 58 is a required constant, changing it will break the request.

**Actual.**
- **The reply is the request buffer mutated in place.** With a ramp in the
  payload, the reply came back with the ramp still present at frame offsets
  **4, 55, 56 and 57**, and device data at 5–54.
- The `A5 5A` probe is decisive on its own: that reply differed from the control
  reply at **exactly offsets 56, 57 and 59** — our two bytes, and the checksum.
- Request marker `0x00` and `0x5A` both produced a **normal reply whose marker
  was `0xFF`**, byte-identical to the control reply.

**Evidence.** `captures/public/EXP-USB-006-request-fields-AB.json`.

**Conclusions.**
1. **§6 Q1 is answered — VERIFIED.** For `AA 0A` the device writes exactly
   offsets **5–54** (50 bytes). Offsets 4, 55, 56, 57 in a reply are *the
   caller's own bytes*. Session 1 saw `0x00` at 56–57 in every frame and could
   not tell what they were; they were zero **because its requests were zero
   there**. Neither "payload = 4–55" nor "payload = 4–57" describes a response.
   **A reply's unwritten bytes cannot be read as device data** — the single most
   likely source of a false field discovery on this instrument.
2. **§6 Q3 is answered — VERIFIED.** Byte 58 is **device-set, not echoed**: the
   device forces `0xFF` whatever the request contained. The request's byte 58 is
   **not validated**.
3. Together with `[CR30-SKEPTIC]`'s corpus work (`PROTOCOL.md` §7.4), byte 58 is
   a **device-written flag**: `0xFF` on everything observed here, `0x00` on the
   `BB 01 09` measurement header in vendor traffic.

**Confidence.** VERIFIED, this unit, `AA 0A` and `BB 28` classes.

**Next.** Extend to a measurement chunk when EXP-MEAS-001 runs.

---

## EXP-USB-005 — timing and transport characterisation · ✅ DONE

**Hypothesis.** The 300 ms post-open settle delay, the inter-command delays and
the "baud does not matter" *mechanism* are all untested assumptions. Measure them.

**Setup.** `tools/probe_timing.py`, `tools/probe_bb13_field.py`,
`tools/probe_write_granularity.py`. Read-only commands only (`AA 0A`, `BB 13`).

**Actual.**

| Question | Measurement | Result |
|---|---|---|
| Response latency | 50 round trips × 2 commands | first byte **0.735 ms** median (min 0.603, max 0.932); **complete frame 0.767 ms** median, max 1.491. 100/100 replies |
| Settle delay after open | 6 delays × 10 opens | **0 ms → 10/10 valid.** Identical at 5/25/50/100/300 ms |
| Inter-command delay | 4 gaps × 30 commands | **0 ms → 30/30 valid.** No delay needed |
| Port close/reopen | 20 cycles | **20/20**, zero open errors |
| Unsolicited traffic | 90 s idle, then 12 min polled | **0 bytes**, always |
| Line coding | 8N1 / 7E1 / 8N2 / 7N1 / 8O1 | **all byte-identical** to 8N1 |
| Baud | 300 / 115200 / 1000000 | **all byte-identical** |
| Pipelining | 2 and 3 frames in one write | **0 bytes back.** Recovers on the next single-frame write, no reopen |
| Write granularity | 60 B split 30+30, 59+1, 1+59, 20+20+20 | **0 bytes back, 4/4.** One write of 60 B always replies |

**Evidence.** `captures/public/EXP-USB-005-timing.json`,
`EXP-USB-005b-bb13-field.json`, `EXP-USB-005c-write-granularity-and-drift.json`.

**Conclusions.**
1. **The 300 ms settle delay is superstition — VERIFIED.** Remove it.
2. **No inter-command delay is needed — VERIFIED.**
3. **A frame must be written in exactly ONE `write()` call — VERIFIED**, five
   ways. This is the most portability-critical rule found this session: any
   implementation that chunks, buffers or line-buffers its writes gets
   **silence**, not an error. Encoded in `src/cr30/transport.py`.
4. **Never write more than one frame per call — VERIFIED.**
5. **`PROTOCOL.md` §3's stated *mechanism* is now VERIFIED, by a far stronger
   argument than session 1 had.** Session 1 inferred "line coding never reaches
   a UART" from identical replies at five baud rates — an observation equally
   consistent with the bridge honouring `SET_LINE_CODING` at both ends. Two new
   measurements separate them: a 60-byte frame **completes in 0.77 ms**, where
   60 bytes across a 115200-baud line take **5.2 ms**; and at a nominal
   **300 baud** — where 60 bytes would take 2 seconds — the reply still arrived
   in **0.97 ms**. No UART is in the path. Framing is ignored too (7E1, 8N2,
   7N1, 8O1 identical).
6. The device is silent when idle over 90 s and over 12 minutes of polling —
   **VERIFIED**. Session 1's claim was scoped to 1 s.

**Confidence.** VERIFIED throughout, this unit, USB transport, macOS.

**Note on a broken probe, recorded deliberately.** The first two probes of this
session reported ~6.3 ms latency with suspicious consistency. That was the
*probe's* 5 ms `time.sleep()` polling granularity, not the device. The real
figure is 0.77 ms — **eight times faster**. Had it not been re-measured with a
0.5 ms poll, "the CR30 answers in ~6 ms" would have entered `TRANSPORT_USB.md`
as a fact. Any latency figure must state its polling resolution.

---

## EXP-USB-005b/c — what moves `BB 13`'s reply field? · ✅ DONE (partly NOT DETERMINED)

**Hypothesis.** `BB 13` writes `51 00 00 00 <u16 LE>` at frame offsets 5–10.
The u16 was seen at 1084, then 1445. Something moves it.

**Procedure.** 20 back-to-back reads · 50 intervening `AA 0A` commands · a port
close/reopen · a 30 s idle · a 90 s idle · then a sample every 30 s for 12 min.

**Actual.** Invariant under all of: 20 repeats, 50 intervening commands, a port
reopen, 30 s and 90 s idle. Over the 12-minute sampler it **stepped exactly
+361 twice**, once between t=275.9 s and t=306.5 s and once between t=642.9 s
and t=673.5 s — a step of 361 with an interval of 367 ± 30 s. Across the whole
session it was observed at 1084, 1445, 1806, 2167, 2528: **five values, four
steps, every one exactly +361.**

**Evidence.** `captures/public/EXP-USB-005b-bb13-field.json`,
`EXP-USB-005c-write-granularity-and-drift.json`.

**Conclusions.**
1. **Not a command counter, not a connection counter, not a fast clock —
   DISPROVEN** for all three.
2. **PROBABLE: it is a device clock in seconds, refreshed into the job record on
   a ~361 s cycle** — the step size and the update interval are equal within the
   sampling resolution.
3. **CORROBORATED by the vendor corpus** (`[CR30-SKEPTIC]`, `PRIORART-001`):
   `BB 13` is a **job record** — two `u32` LE **Unix timestamps** at frame
   offsets 5 and 9, and an ASCII label at offset 13. Vendor frames carry real
   October-2025 dates. **On this unit they read 81 and ~2500 — i.e. seconds
   since 1970. The clock has never been set.**
4. **itohio puts `b"Check"` at frame offset 4. The vendor puts it at offset 13.**
   The prior art has the label in the wrong field.
5. What byte 5 (`0x51` = 81, constant everywhere) means is **NOT DETERMINED**.

**Next.** Re-read `BB 13` before and after the human session — a measurement may
be what writes a job record. Built into `tools/run_human_session.py`.

---

## EXP-CAL-001 — calibration, and EXP-MEAS-001 — measurement · ⏸ READY, NEEDS THE HUMAN

Both are driven by **one script, one session**: `tools/run_human_session.py`.
Designed so a single period of human attention answers every hardware question
that is currently open. The human is asked only to move the instrument and press
Enter; every comparison, decode and judgement is made by the script
(`CLAUDE.md` §17).

**Safety.** Every `0xBB` frame the script sends is **byte-identical to a frame
the vendor application actually sent** (`PRIORART-001`), enforced by
`tests/test_human_session_frames.py`, which also asserts every triple is on
`SAFETY_ENVELOPE.md`'s green list and every `param` byte is zero (RED rule 2).
`BB 10`/`BB 11` **write calibration storage**; `SAFETY_ENVELOPE.md` §2a permits
them only here, with the tiles present and a human watching. Between every phase
the four identity sub-commands are re-read as a 240-byte fingerprint and **any
change aborts the run**.

**Preconditions.** CR30 on USB · ColorQC2 not running · black cap and white tile
to hand · a printed chart or colour patches · the lease held.

**Procedure (13 phases, ~15 minutes of human time).**

| # | Phase | Question it answers |
|---|---|---|
| 0 | identity fingerprint | baseline; repeated after every phase |
| 1 | `BB 13` job record, before | does a measurement write a job record? |
| 2 | measure a patch, **before any calibration** | is calibration a precondition, and what does an uncalibrated read return? |
| 3 | `BB 10 00 00` black calibration | command, reply, status byte, timing |
| 4 | `BB 11 00 00` white calibration | command, reply, status byte, timing |
| 5 | measure the **white tile** | **positive control** — a correct decode must read near-flat and near-maximum |
| 6 | measure the **black cap** | **negative control** — must read near-minimum |
| 7 | measure a colour patch **3× without lifting** | repeatability; per-band SD computed on the spot |
| 8 | re-fetch chunks **without re-triggering** | is a measurement cached? |
| 9 | press the instrument's own **button**, 15 s passive listen | is there unsolicited traffic, and does the header carry marker `0x00`? (tests `PROTOCOL.md` §7.4) |
| 10 | fetch chunks after the button press | is a button reading fetched the same way? |
| 11 | 4 further, varied patches | seed corpus for `EXP-SPEC-001` (are the 31 bands independent?) |
| 12 | `BB 13` job record, after · final fingerprint | did anything move? |

**Expected.** A `BB 01 09` header with `28 1f 0a` at offsets 4–6; three chunks
carrying 12 `float32` LE each from offset 6; the white tile reading near-flat
and high; the black cap reading near-zero.

**What a failure teaches.** If the white tile does **not** read flat and high,
the decode is wrong, not the instrument — that is exactly why the positive
control is in the script rather than trusting the first plausible float run.

**Actual / evidence / conclusion.** — pending the human.

---

## EXP-USB-007 — ChromIQ's Argyll serial scan vs. the CR30 · ✅ DONE

**Hypothesis (`EXP-USB-005c` predicted the answer before the test ran).** Every
Argyll probe string is 1–10 bytes; the CR30 answers nothing to any write that is
not exactly 60 bytes in one call. **The CR30 will ignore Argyll's probes entirely.**

**Setup.** `tools/probe_argyll_scan.py`. The eight probe strings taken verbatim
from ArgyllCMS 3.5.0 `spectro/inst.c::fast_ser_dev_type` — `;`, `D024\r\n`,
`X`, `#ZQS00\r`, `#0ZQS008E\r`, `#0ZQS018F\r`, `P0\r`, `*idn?\r` — at the four
baud rates Argyll actually tries: 9600, 921600, 115200, 38400. **32 probes.**
A 240-byte identity fingerprint before and after **every single probe**.

**Actual.** **32/32: zero bytes returned, fingerprint byte-identical every
time.** Final fingerprint identical to the opening baseline.

**Evidence.** `captures/public/EXP-USB-007-argyll-serial-scan.json`.

**Conclusion — VERIFIED.** A CR30 sharing a machine with ChromIQ is **not**
disturbed by Argyll's serial device scan. `ChromIQ/core/argyll_runner.py` keeping
`/dev/cu.usbserial-*` in the scan is **not a bug for this instrument**, and the
integration does **not** need `ARGYLL_EXCLUDE_SERIAL_SCAN` for the CR30's node.
The hazard `[CR30-SKEPTIC]` filed is real in principle and does not fire here,
for the reason `EXP-USB-005c` gives: the device's frame parser will not act on
anything that is not a whole 60-byte frame in a single write.

**Scope, honestly.** This proves the CR30 ignores the probes. It does **not**
prove the reverse direction: a scan that *opens* the port while a ChromIQ
measurement is in flight would still take the port away. That is a locking
question, not a protocol one, and belongs in `INTEGRATION.md`.
