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

## Queued — not yet run

| ID | Question | Needs hardware? | Needs human? |
|---|---|---|---|
| EXP-USB-003 | Is the checksum enforced on `0xBB` (side-effecting) commands? | yes | no |
| EXP-USB-004 | Command-space survey: which `cmd`/`subcmd` values answer at all? | yes | no |
| EXP-USB-005 | Response latency and timing characterisation | yes | no |
| EXP-CAL-001 | Black then white calibration sequence and status codes | yes | **yes** — tiles |
| EXP-MEAS-001 | One software-triggered measurement, full transaction log | yes | **yes** — placement |
| EXP-MEAS-002 | Button-triggered measurement; unsolicited traffic | yes | **yes** — button |
| EXP-MEAS-003 | Chunk-structure resolution: what are the unexplained 20 bytes? | yes | no |
| EXP-SPEC-001 | Rank analysis: are 31 bands independent or reconstructed? | no (needs a corpus) | yes — many samples |
| EXP-BLE-001 | Does the device advertise BLE, and with what GATT profile? | yes | maybe — enable BT |
| EXP-PARAM-001 | Parameter/configuration command discovery | yes | no |
| EXP-ARGYLL-001 | Argyll serial-instrument transport patterns worth reusing | no | no |

⚠ **EXP-USB-004 requires a safety policy before it runs.** Sweeping the command
space on an undocumented device risks hitting a firmware-write or
calibration-write command. `CLAUDE.md` §11 forbids blind destructive traffic.
`[CR30-SKEPTIC]` must define the allowed sweep envelope before `[CR30-USB]`
executes it.
