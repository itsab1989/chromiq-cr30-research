# SESSION_HANDOFF.md

**For the next Claude Code session, on any machine.** Assume no conversation
history. This file plus `CLAUDE.md` and `STATUS.md` is the whole picture.

**Written:** 2026-08-28, end of session 2 (`[CR30-SKEPTIC]` audit) ·
**Platform:** macOS 15.7.9 arm64 · **No hardware was used in session 2.**

---

## What changed in session 2

An adversarial re-derivation of all nine session-1 findings, plus a corpus
session 1 never opened.

**Seven of session 1's conclusions survive. Four were filed at a confidence the
cited evidence did not buy, and are now re-worded.** The full scorecard is in
`STATUS.md`; the objections are on issue #1 and must not be quietly dropped.

**The single most consequential result:** ten Eltima sniffer dumps in
`itohio/color-science` (`reverse-engineer-c30/serial-sniffer/*.spm`, MIT) yield
**260 unique frames of the VENDOR application driving a second CR30** — the
`0xBB` traffic, the `0x00` markers and 60 measurements that our own four
identity frames could never supply. That corpus:

- settles the checksum rule (exactly one contiguous additive rule survives it);
- gives the **complete vendor command vocabulary**, which is what
  `SAFETY_ENVELOPE.md` is built on;
- disproves three prior-art structural claims;
- **disproves the linear form of the "31 bands are reconstructed" hypothesis.**

It is CORROBORATION, never VERIFIED — a different unit, platform and toolchain,
decoded by us. Everything in it must be re-observed on our unit.

## What remains unknown

Calibration and measurement **on our unit** · error and timeout behaviour ·
reconnect and sleep/wake · what `BB 21 01` is (1745 frames in one vendor
session) · whether any sensor-parameter command exists at all · BLE anything ·
whether the bands survive a *nonlinear* reconstruction test · accuracy.

## Files changed in session 2

New: `SAFETY_ENVELOPE.md` · `tools/mine_priorart_frames.py` ·
`tools/decode_spectra.py` · `tools/spectral_rank.py` ·
`captures/public/PRIORART-001-vendor-usb-frames.json` ·
`captures/public/PRIORART-002-spectra.json` ·
`tests/test_checksum_rule_space.py` · `tests/test_spectral_independence.py`

Rewritten: `PROTOCOL.md` · `MEASUREMENT.md` (now carries EXP-SPEC-001) ·
`INTEGRATION.md` (was a scaffold; now written from ChromIQ source with file and
line citations) · `STATUS.md` · `SESSION_HANDOFF.md`

Amended: `EXPERIMENTS.md` · `ERRORS.md` · `CALIBRATION.md` ·
`PLATFORM_SUPPORT.md` · `TOOLS.md` · `RESEARCH_LOG.md`

**`src/cr30/` was NOT changed.** `[CR30-USB]` owns the implementation; four
defects are filed in `ERRORS.md` and on issue #1 for them to fix.

## Exact next experiments, in order

1. **`EXP-USB-005` — response-latency baseline.** Green commands only, no
   human. **This is a precondition of `SAFETY_ENVELOPE.md`**: an anomalously
   slow reply is the cheapest way to notice a flash write, and it is only
   recognisable against a baseline. `EXP-USB-004` must not run before it.
2. **`EXP-USB-006` — is Finding 7 real?** Send `AA 0A 01 00` (sub-command
   **1**) with a wrong checksum immediately after a good `AA 0A 00 00`. If the
   reply follows the new sub-command the device really parsed the frame; if it
   repeats the old reply, "does not validate" is disproven and a cached reply
   is the explanation. Then truncate the request to 4 and 59 bytes to see
   whether byte 59 is read at all. Two minutes, no human.
3. **`EXP-USB-007` — is Finding 3 the device or the driver?** Break the
   framing, not the rate: 7 data bits, or 2 stop bits, or mark parity. A real
   UART truncates `0xAA` to `0x2A` at 7 bits and cannot answer. One probe.
4. **`EXP-USB-008` — Argyll's ASCII probes.** Replay `;`, `D024\r\n`,
   `SV\r\n`, `P0\r` at 9600/921600/115200/38400. **This already happens on
   every ChromIQ measurement start** (`INTEGRATION.md` §8) — it is a shipped,
   unexamined exposure, and the bytes are known and bounded.
5. **`EXP-CAL-001` + `EXP-MEAS-001` + `EXP-MEAS-002`, one human session.**
   Design them to answer as much as possible at once: identity, cal status
   before and after, black cal, white cal, a measurement on a known patch, a
   repeat without lifting, and a button-triggered reading — checking whether the
   header's byte 58 really goes `0x00` on the button (`PROTOCOL.md` §7.4).
6. **`EXP-SPEC-001a`** — but first establish, with five readings, that repeats
   of the same patch *differ at all*. In the vendor corpus they were
   byte-identical, and if ours are too the noise-rank test cannot run.

**Highest value for lowest risk, and it needs no CR30 traffic at all:**
sniff ColorQC2 on Windows through its **settings** screens. That is the only
cheap way to widen `SAFETY_ENVELOPE.md`, and it would settle whether a
sensor-parameter command exists.

## Required state

- **OS:** macOS. Windows only for vendor sniffing.
- **Transport:** USB, `/dev/cu.usbserial-*` — **re-check the node name.**
- **ColorQC2 must NOT be running** — it holds the port.
- **Lease:** acquire `.hardware-lock/LEASE` before opening the port.
- For `EXP-CAL-001`: the black cap and white tile to hand.

## What must NOT be done

- Do not modify ChromIQ in any way (`CLAUDE.md` §2).
- Do not commit `captures/raw/` or `LOCAL_DEVICE_IDS.md`.
- **Do not sweep the command space.** `EXP-USB-004` is re-scoped to
  individually logged single probes, one per lease, attended, under
  `SAFETY_ENVELOPE.md`. A `for cmd in range(256)` loop is forbidden.
- **Never send `BB 10 00` or `BB 11 00` outside `EXP-CAL-001`** — they write
  calibration, and they sit between harmless neighbours.
- Do not send anything with a non-zero `param` byte, a non-zero payload, or
  `cmd >= 0x80`.
- **Never cite a redacted frame as evidence for the checksum** —
  `tools/redact.py` recomputes byte 59.
- Do not verify redaction by grepping a hex capture for an ASCII string.

## ⚠ Damage done in session 2, and what is still at risk

**`[CR30-SKEPTIC]` overwrote `[CR30-USB]`'s uncommitted prose** in
`PROTOCOL.md`, `EXPERIMENTS.md` and `STATUS.md` by rewriting those files
wholesale while the other agent was editing them. HEAD was still session 1, so
nothing was recoverable from git.

Their **evidence survives** — five capture JSONs, six probe tools,
`src/cr30/{discovery,session,transport}.py`, `tests/test_transport_replay.py`
and their edits to `src/cr30/{frame,__init__}.py`. Their four experiments have
been **reconstructed from those captures** into `EXPERIMENTS.md` under a
heading that says so and asks them to correct it.

**Those files were still uncommitted at the end of session 2.** They were not
staged deliberately — `[CR30-USB]` was actively writing, and committing a
half-written file would have compounded the error. **If they are still
uncommitted, commit them before doing anything else.**

Lesson, for both agents: **re-read a shared document immediately before writing
it, and never rewrite one wholesale while another agent holds the repo.**
Append, or edit in place.

## Unresolved disagreements between agents

- `[CR30-SKEPTIC]` filed five objections on issue #1 (comment 1). **Objection 3
  (cached reply) is withdrawn** — `[CR30-USB]`'s `EXP-USB-006` disproved the
  rival hypothesis and Finding 7 is restored to VERIFIED. Objection 4 (baud) is
  open and `EXP-USB-007` settles it. The rest are wording corrections already
  applied.
- **`[CR30-SKEPTIC]` disproved a `[CR30-USB]` claim**: `src/cr30/frame.py` says
  the device forces byte 58 to `0xFF` on every frame it emits. It does not —
  `BB 01 09` measurement headers carry `0x00` (20 occurrences, 7 distinct, in
  the vendor corpus). The docstring needs amending; `PROTOCOL.md` §7.1a and
  `tests/test_checksum_rule_space.py` record it.
- **Four open defects in `src/cr30/`** filed in `ERRORS.md`.

**Do not close any of these by editing a document — close them with a
capture.**

## Relevant GitHub

- Coordination issue: **this repo, issue #1.** React only to `[CR30-USB]`,
  `[CR30-SKEPTIC]`, `itsab1989`, `soul-traveller`.
- Background: `itsab1989/ChromIQ#159` — read-only. **Four of its claims are now
  disproven** (`INTEGRATION.md` §10). Do not take it as current.

## Reproducing the current state

```bash
cd ~/develop/chromiq-cr30-research
python3 -m venv .venv && .venv/bin/pip install pyserial bleak pytest numpy
.venv/bin/python -m pytest tests/ -q          # 331 pass, no hardware

# re-clone the prior art if /private/tmp has been swept (it is, nightly)
mkdir -p /tmp/cr30-priorart && cd /tmp/cr30-priorart
git clone https://github.com/itohio/color-science.git
git clone https://github.com/beerjongen/CR30-ti3-Dispensary.git
cd ~/develop/chromiq-cr30-research
.venv/bin/python tools/mine_priorart_frames.py \
  /tmp/cr30-priorart/color-science/reverse-engineer-c30/serial-sniffer
.venv/bin/python tools/decode_spectra.py captures/public/PRIORART-001-vendor-usb-frames.json
.venv/bin/python tools/spectral_rank.py captures/public/PRIORART-002-spectra.json
```

Confirm the driver situation on any macOS host — note this is a **two-PID
allow-list**, not general CH34x support:

```bash
plutil -p /System/Library/DriverExtensions/com.apple.DriverKit-AppleUSBCHCOM.dext/Info.plist \
  | grep -E 'idVendor|idProduct'
# expect 6790/29987 (0x1A86/0x7523) and 6790/21972 (0x1A86/0x55D4)
```

## Recommended platform for the next session

**macOS** for everything on the critical path. **Windows** has one job and it is
now the highest-value job available: sniff ColorQC2's settings screens, because
that is what widens the safety envelope without risking the device.
