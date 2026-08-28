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
