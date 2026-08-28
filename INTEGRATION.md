# INTEGRATION.md — CR30 → ChromIQ

**Written 2026-08-28 by `[CR30-SKEPTIC]` from source inspection of
`/Users/Basti/develop/ChromIQ` at commit `f7ecc7f4`.** Documentation only.
Nothing here is implemented in ChromIQ, and nothing in this repository imports
it (`CLAUDE.md` §§2–3). Every claim carries a file and line number; where a
claim in ChromIQ issue #159 conflicts with the source, the source wins.

## The answer, in one paragraph

ChromIQ has **no device abstraction in Python** and **no transport
abstraction** — every measurement today comes from an Argyll process. But it
already has three things a CR30 needs: a **line-based JSON event protocol**
whose spot mode carries spectra through untouched, a **`.ti3` reader that
parses an arbitrary band count from the file's own header**, and **two working
precedents for a device Argyll cannot drive** (`scanin`, and `i1iSis` via
`EXTERNAL_INSTRUMENTS`). The smallest reliable interface is therefore **not a
live driver**: it is a `.ti3` file with spectral columns, produced by a
standalone CR30 package, consumed by machinery ChromIQ already has. §6 states
it, §7 attacks it.

---

## 1. How instruments are represented — there is no registry

Instrument identity is scattered across **fourteen** independent tables in four
layers, keyed four different ways (a printtarg flag code, a CGATS string, a
model-name substring, a USB VID/PID). The main ones:

| Location | Key | Contents |
|---|---|---|
| `workflow/layout_engine/instruments.py:26-34` | flag code | `TARGET_INSTRUMENT_NAME` → CGATS string, 6 entries |
| `workflow/layout_engine/instruments.py:36` | flag code | `DELEGATED = {"isis"}` |
| `data/patch_db.py:190` | flag code | `EXTERNAL_INSTRUMENTS = frozenset({"isis"})` |
| `ui/ti2_loader.py:35-39` | CGATS string | `KNOWN_INSTRUMENTS` — only **3** values |
| `core/usb_driver_installer.py:35-72` | (vid,pid) | `KNOWN_COLORIMETERS` — Windows WinUSB targets |
| `native/instlib/insttypes.c:306+` | CGATS string | Argyll's own `inst_enum()` |

**The tables disagree with each other.** `instruments.py:26` can write
`"X-Rite DTP41"` into a `.ti2`; `ui/ti2_loader.py:35` will then refuse to
measure it.

### Three hard gates reject an unknown instrument

- **Gate A**, Python, user-facing: `ui/tabs/tab_measure.py:4397-4457` (called
  at `:5175`). `if name is None or name in KNOWN_INSTRUMENTS: return False` —
  anything else raises a modal and blocks the run. **Absent is fine**; unknown
  is fatal.
- **Gate B**, C, hard exit: `native/chartread_helper/chromiq_chartread.c:3626-3632`
  — `inst_enum()` returns `instUnknown` → `error()` terminates. Absent keyword
  ⇒ silently `instI1Pro`.
- **Gate C**, layout: `workflow/layout_engine/instruments.py:357-359`.

**Consequence.** A `.ti2` whose `TARGET_INSTRUMENT` says `"CHNSpec CR30"` is
rejected before a single patch is read. **But all three gates pass a chart with
no `TARGET_INSTRUMENT` keyword at all** — which is the seam §6 uses.

⚠ **`MeasureParams.instrument` is not an instrument name.** It is Argyll's `-c`
comm-port *number*, from a spin box (`workflow/measure_manager.py:164`, `:890`;
`ui/tabs/tab_measure.py:11136`). ChromIQ never asks for a specific device; it
names a port index and accepts whatever answers. Issue #159's framing of
instrument selection does not match the code.

## 2. How measurements enter the system

**Normal path:** `chartread` or the fork `chromiq-chartread` reads the
instrument and writes the `.ti3` itself, in C —
`native/chartread_helper/chromiq_chartread.c:4157` (`save_ti3`), with per-patch
atomic autosave at `:465-496` (`cq_write_ti3_atomic`, temp + `rename`), called
from the spot loop at `:3120`. Destination `Run.measurement_ti3`,
`core/file_manager.py:798`.

**`.ti3` is *not* always produced by Argyll.** Python writes it in six places,
of which two matter here:

- `workflow/reference_convert.py:262-343` — `cxf_measurement_to_ti3()`. **The
  closest existing analogue to a CR30 path**: parses CxF3 reflectance spectra,
  integrates to XYZ in pure Python, writes a `.ti3`.
- `workflow/scanin_runner.py:498-536` — a **flatbed scanner**, a device
  Argyll's `inst` layer does not drive, nevertheless yields a `.ti3`.
  Precedent, and a strong one.

**`.ti3` parsers** are all hand-rolled Python, no CGATS library — chiefly
`workflow/ti3_analysis.py:116-192` (`parse_ti3` → `Ti3Data`) and
`workflow/profile_engine/ti3_data.py:261-266`.

## 3. What the chart-reading engine actually expects

Issue #159's claim is **confirmed**. `workflow/chartread_engine.py` is 136
lines of helper discovery plus a key→command map; the protocol lives in the C
source.

- **Emission:** `native/chartread_helper/chromiq_json.c:27-49`. One complete
  JSON object per line, preceded by `\n` so it starts at column 0, then
  `fflush`.
- **Decoding:** `workflow/chartread_engine.py:72-86` — a line must start with
  `{` and carry an `"event"` key; anything else is chartread prose for the log.
- **Commands in:** `chromiq_json.c:192-217`, a detached stdin thread. ⚠ The
  parser is **not** a JSON parser — `cq_json_get()` at `:99-121` does
  `strstr("\"key\"")` and reads the next quoted string. **String values only.**
  Comment at `:98`: *"our own GUI is the only writer on this pipe"*.
- **Transport:** plain pipes, `workflow/measure_manager.py:453` (`use_pty=False`).

**Read modes:** `chromiq_chartread.c:887` — `0 = spot, 1 = strip, 2 = xy,
3 = chart`. `rmode 0` is entered whenever `-p` is passed and the instrument
advertises `inst_mode_ref_spot` (`:1382-1384`) — **exactly a CR30's shape**.

**Spot mode already does what a CR30 needs.** `chromiq_chartread.c:2789` emits
`spot_ready`, `:2844` calls `read_sample`, and at `:3111-3113` it copies
`val.sp` into the sample **if `val.sp.spec_n > 0`** — then autosaves at
`:3120`. **Spectra are already carried through the spot path untouched.**

⚠ `MeasureParams`'s own docstring at `workflow/measure_manager.py:175-176` says
patch-by-patch *"always uses stock chartread (the engine covers strip reading
only)"*. The code at `:363-365` and the C spot loop say otherwise. The docstring
is stale; do not design from it.

### Two paths already supply a value from outside Argyll

**(a) `-x l` / `-x x`** — user-entered values. `chromiq_chartread.c:3489-3497`
(parse), `:3054-3101` (accept three numbers, `icmLab2XYZ`, set `rr=1`, emit
`patch_read`, autosave). At `:4097`, `if (!xtern && !cq_replay_active())` the
instrument path is skipped entirely — **no USB, no `inst` object at all.**

⚠ **This path is broken under `--json`.** It reads with `con_fgets()` at
`:2804`, straight from stdin, while `--json` unconditionally starts the
stdin-consuming command thread at `:3331`. They race for the same fd and
nothing gates the combination. It is also XYZ/Lab only — **no spectral input**.

**(b) The replay instrument**, `native/chartread_helper/chromiq_replay.c:449-520`
— a complete synthetic `inst` object with `read_strip`, `read_sample`,
`read_chart`, `read_xy`, `calibrate`, a stub `icoms` (`:111-124`) and
`p->dtype = instI1Pro` (`:512`). **This is the working proof that a non-Argyll
value source plugs into the engine's real read loop.**

## 4. Spectra are already represented — and the band count is not fixed

`workflow/ti3_analysis.py:174-184`, duplicated at
`workflow/profile_engine/ti3_data.py:261-271`:

```python
spec_i = [i for i, f in enumerate(fields) if f.startswith("SPEC_")]
if len(spec_i) >= 3 and "SPECTRAL_BANDS" in keywords:
    bands = int(keywords["SPECTRAL_BANDS"])
    lo = float(keywords["SPECTRAL_START_NM"]); hi = float(keywords["SPECTRAL_END_NM"])
    if len(spec_i) == bands:
        spectral = ...; wavelengths = np.linspace(lo, hi, bands)
```

**The grid is inferred from the file, not hard-coded.** A CR30's 31 bands at
400–700 nm parse **with no change to ChromIQ**, given `SPECTRAL_BANDS 31`,
`SPECTRAL_START_NM 400`, `SPECTRAL_END_NM 700` and columns `SPEC_400`…`SPEC_700`.
This is the single most important fact in this document.

ChromIQ owns its colorimetry: `workflow/profile_engine/spectral.py` —
`illuminant_spd()` (`:47`), `observer_cmf()` (`:62`), `spectra_to_xyz()`
(`:75`), and the M2 UV-cut `_uv_filter()` (`:39-44`). Observers `1931_2`,
`1964_10`; illuminants A, C, D50, D65, F5, F8, F10 and M2 variants.

⚠ **Two independent CIE datasets exist** — `workflow/cie_data.py:10-310` and
`workflow/profile_engine/spectral_data.py`. A CR30 path must pick one
deliberately.

⚠ **The CxF importer parses spectra and then discards them**
(`workflow/reference_convert.py:329-334` writes 8 fields, XYZ only), and
hard-codes 10 nm spacing at `:318`. **A CR30 importer must not repeat either.**

## 5. Calibration, errors, transport, dependencies

**Calibration** is a faithful port of Argyll's `inst_handle_calibrate()` with
the console touch points swapped for JSON — `chromiq_cal.c:57-138`, with **17
machine-readable conditions** at `:32-55`. Black/white/plate map onto
`man_ref_dark` / `man_ref_white` / `man_ref_whitek`. ⚠ **`cond` is emitted and
then discarded**: `ui/tabs/tab_measure.py:6978` stores it and never uses it;
the wording comes from instrument *family* (`ui/ti2_loader.py:125-160`), so 17
conditions collapse to three sentences. Convenient for a CR30 — the generic
branch already exists — but the machine-readable half is currently thrown away.

**Errors** have a rich signal set (`workflow/measure_manager.py:212-236`:
`no_instrument`, `device_busy`, `instrument_disconnected`, `coms_init_failed`,
`generic_instrument_error`, …) mapped from engine `error` events at `:1318-1371`.
⚠ **New user-facing text is gated by §M** — `workflow/measurement_messages.py`
+ `tests/test_message_catalogue.py` + `docs/design/unified_measurement_management.md`.
Mapping CR30 failures onto **existing** signals costs nothing and reuses
approved text; new wording needs human approval before it can appear in a tab.

**Transport is not abstracted.** Everything is `ArgyllRunner` → `QProcess`/PTY
→ an Argyll binary (`core/argyll_runner.py:351-433`, `:551-597`). No pyserial,
no pyusb, no hid anywhere in the repository.

**But serial is already a first-class concern**, and this is where a real
hazard lives — see §8.

**Dependencies.** `requirements.txt` is 13 lines and already carries a PEP 508
marker (`pyobjc-framework-Cocoa ; sys_platform == "darwin"`), CI-level
filtering (`.github/workflows/build-windows.yml:54` strips `pycups`) and
spec-level exclusion (`ChromIQWin.spec:135`). **`pyserial` would be the least
intrusive dependency in the file** — pure Python, no compiled extension, no
platform build step, no `collect_all` hook; one line in `hiddenimports` in each
of the three spec files.

⚠ **Do not add the CR30 to `KNOWN_COLORIMETERS`** (`core/usb_driver_installer.py:35-72`).
It installs WinUSB/libusb0, the **wrong driver class** for a serial bridge, and
the comment at `:26-29` warns this *breaks* a device that needs another driver.

## 6. The smallest reliable interface

> **A `.ti3` file with spectral columns, and a `.ti2` with no
> `TARGET_INSTRUMENT` keyword.**

That is the whole interface. Concretely:

**ChromIQ side — three changes, none of them a driver.**

1. `data/patch_db.py:190` — add `"cr30"` to `EXTERNAL_INSTRUMENTS`, and
   `workflow/layout_engine/instruments.py:36` — add it to `DELEGATED`. This is
   the `i1iSis` precedent exactly: ChromIQ lays out and prints the chart, omits
   the instrument keyword, and does not offer a Measure tab for it.
2. `workflow/reference_convert.py` — a sibling of `cxf_measurement_to_ti3()`
   that reads the CR30 package's output and **keeps the spectra**, emitting
   `SPECTRAL_BANDS` / `SPECTRAL_START_NM` / `SPECTRAL_END_NM` and `SPEC_*`
   columns. Everything downstream — `parse_ti3`, the profile engine,
   `spec2cie`, `colprof` — already handles them.
3. Nothing else. No new `instType`, no C, no `instlib` edit, no AGPL
   entanglement, no new UI window, no §M text.

**CR30 package side — the reference implementation exposes exactly this:**

```
identify()            -> model string, firmware/build strings, unit ids
calibrate_black()     -> outcome + the device's own status byte
calibrate_white()     -> outcome + the device's own status byte
measure()             -> Measurement | raises
```

with `Measurement` carrying **the axis the device declared** (`start_nm`,
`count`, `step_nm` — never assumed, `PROTOCOL.md` §7.2), the values, the
trigger source (software or button, from the header marker,
`PROTOCOL.md` §7.4), a timestamp, the device identity, and an explicit
success/failure state. No wire concepts cross the boundary: no frames, no
chunks, no checksum, no port name.

**And a provenance keyword in the `.ti3`.** Until EXP-SPEC-001a/b run on our
own unit, spectral independence is CORROBORATED, not VERIFIED
(`MEASUREMENT.md`). The `.ti3` should say so in a comment keyword rather than
present 31 bands as unqualified fact.

**Patch identity is the risk, and ChromIQ already knows it.**
`workflow/measurement_report.py:291-298` pairs by `SAMPLE_ID` and **falls back
to position** when it cannot; `verify_patch_identity()` at `:236-320` exists
because i1Profiler CxF objects carry no patch identity and
`reference_convert.py:335-336` numbers them 1..N by file order. **A handheld
spot reader has exactly the same defect.** The CR30 importer must therefore
either carry a patch id per reading or refuse the import — never pair by order
and hope. `workflow/measurement_state.py:38-67` already models the three
counts (`.ti2` sets, `.ti3` header claim, actual rows) and refuses to resume a
`MISMATCHED` file; that machinery is free and must be used.

## 7. Challenging my own recommendation

**"This is not integration, it is an import."** Correct, and it is the point.
The alternative — a live driver — costs, at minimum: a new `inst`
implementation in C99 inside `chromiq-chartread`, a new `instType` in
`native/instlib/insttypes.h:87`, a branch in `inst_enum()` and in `new_inst()`
(`native/instlib/inst.c:608-741`) — which breaks the stated invariant that
*"library sources are compiled byte-identical to upstream"*
(`native/chartread_helper/CMakeLists.txt:5-8`) and complicates every future
Argyll rebase, plus an AGPL obligation and a three-platform CI rebuild. **For a
protocol we cannot yet drive a single measurement with.** Nothing about the
import seam forecloses the live driver later; it is the same `Measurement`
object either way.

**"An import loses the guided reading experience."** True and it is the real
cost. The user gets no strip walk, no live preview, no resume, no pace
tracker. Whether that matters depends on chart size, and on a fact nobody has
measured: the CR30's real per-reading time. **`EXP-USB-005` should decide this,
not taste.** If a reading takes ~1 s and there is no averaging knob
(`PROTOCOL.md` §5), a 400-patch chart is ~7 minutes of manual placement whether
ChromIQ is watching or not.

**"Why not `-x l`, it already exists?"** Because it is XYZ/Lab only — it would
throw the spectra away, which is the entire value of this instrument — and
because it is broken under `--json` (§3a). Fixing it would be worthwhile
regardless, but it is not the CR30 seam.

**"Why not Seam B — a JSON `sample` command into a generalised replay
instrument?"** It is the right *second* step and I would recommend it once the
protocol is driven end to end. It needs one new C file plus one new command,
and `cq_json_get()` (`chromiq_json.c:99-121`) must be upgraded from
`strstr`-for-strings to a real parser before it can carry 31 floats. That is a
contained change; it is just not the first one.

**"The `EXTERNAL_INSTRUMENTS` route means no instrument keyword, so Gate B
silently defaults to `instI1Pro`."** Yes — `chromiq_chartread.c:3630`. That is
harmless for an import (no instrument is opened) but it is a latent trap if
anyone later measures such a chart with a real instrument. Worth a note in the
chart's sidecar rather than a code change.

**The one thing that would overturn all of this** is if EXP-SPEC-001a shows the
31 bands *are* a reconstruction. Then the honest `.ti3` has ~11 columns, or
none, and the whole seam changes shape. Nothing should be implemented in
ChromIQ before that runs.

## 8. A shipped hazard, found while doing this

`core/argyll_runner.py:43` — `_REAL_SERIAL_HINTS = ("usbserial", "usbmodem")` —
and `argyll_serial_exclusion_ports()` at `:104-125` **deliberately keep**
`/dev/cu.usbserial-*` in Argyll's serial scan, so a serial SpectroScan still
works. The comment at `:29-37` says so explicitly.

Argyll then calls `fast_ser_dev_type()` (`spectro/inst.c:1446`) during plain
port *enumeration* (`spectro/icoms_ux.c:167`, which flags any path containing
`usbserial` as `icomt_fastserial` at `:135-140`) and writes foreign ASCII
probes — `;`, `D024\r\n`, `SV\r\n`, `P0\r` — to whatever is on that port, at
9600, 921600, 115200 and 38400 baud.

**A CR30 plugged into a machine running ChromIQ is therefore already receiving
unsolicited junk on every measurement start, today.** Nobody has checked what
it does with it. Filed as `EXP-USB-008`.

The mitigation already exists and needs no new mechanism:
`merged_serial_exclusion()` (`core/argyll_runner.py:136-150`) builds
`ARGYLL_EXCLUDE_SERIAL_SCAN`, and Argyll matches it by exact port path
(`spectro/icoms.c:586`, `:640-658`). **Once a port is identified as a CR30 by
`AA 0A 00 00`, its path should be added to that exclusion** — which also
removes ~8 s of pointless probing from every measurement start.

## 9. What Argyll's serial transport does that we should copy — or reject

**Copy.**
- **One `command(in, out, bsize, timeout)` primitive, in two layers.**
  `dtp41.c::dtp41_fcommand` does raw I/O plus error extraction plus **an
  automatic error-clear command (`CE\r`) after a device error**; `dtp41_command`
  maps the device code to a generic one. Both layers earn their keep.
- **Per-command timeouts, passed by the caller** — 0.2 s, 0.5 s, 1.5 s, 2.5 s
  in the probe path. Never a single global timeout.
- **A two-part error code**: `inst_code` carries a generic category in the high
  bits and the instrument's own raw code in the low bits (`inst_imask`). A CR30
  error should carry both the category and the device's raw status byte.
- **Calibration as a negotiation, not a call.** `dtp41_calibrate()` returns an
  `inst_calc_cond` telling the caller what the *user* must physically do
  (`inst_calc_uop_ref_white`), and the caller loops. This is exactly the shape
  a CR30's black-then-white sequence needs, and it is the shape ChromIQ's
  engine already speaks (`chromiq_cal.c:32-55`).
- **Identify by asking the device and string-comparing the model** (`SV\r\n` →
  `"X-Rite DTP41"`, `inst.c:2018-2032`). Argyll never trusts a port's
  existence. Independent corroboration of `PLATFORM_SUPPORT.md`'s conclusion.
- **Drain before use** (the Klein branch, `inst.c:2040-2046`) and **a global
  give-up deadline with a user-abort callback checked each iteration**
  (`inst.c:1907`, `:1979-1986`).

**Reject, deliberately.**
- **The baud-rate search loop.** Argyll cycles rates for up to 20 s to find one
  that talks (`inst.c:1907-1917`). For a CR30 that is pure waste, and an
  independent argument for never exposing baud as a setting.
- **Probe-by-firing-a-foreign-command.** Argyll identifies unknown ports by
  writing another vendor's commands at them. That is precisely what
  `SAFETY_ENVELOPE.md` forbids — and §8 above is the same practice pointed at
  our device.
- **Ambiguous port lifetime.** `inst.c:2064` ships with
  `p->close_port(p); /* Or should we leave it open ?? */`. Our design must be
  explicit: one open, one close, one owner. macOS permits two processes to open
  `/dev/cu.*` concurrently and will happily interleave their bytes.
- **Prefix string-matching as integrity.** Fine for ASCII instruments,
  unacceptable for a binary framed protocol with a checksum.

## 10. Contradictions in ChromIQ issue #159, from source

| #159 says | Source says |
|---|---|
| macOS is not natively supported, needs a kernel extension, start on Windows | **DISPROVEN** — Apple's dext matches PID `0x7523` explicitly (`PLATFORM_SUPPORT.md`) |
| the engine boundary is a line-based JSON protocol over stdout/stdin | **CONFIRMED** — `chromiq_json.c:27-49`, `chartread_engine.py:72-86` |
| `rmode 0 = spot`, emits `spot_ready` | **CONFIRMED** — `chromiq_chartread.c:887`, `:2789`, `:600-608` |
| `TARGET_INSTRUMENT` rejects unknown names outright | **CONFIRMED, and there are three gates**, not one (§1) |
| `EXTERNAL_INSTRUMENTS` is precedent for a device Argyll cannot drive | **CONFIRMED**, and `scanin` is a second one |
| instrument selection identifies the device | **DISPROVEN** — `MeasureParams.instrument` is a comm-port number (§1) |
