# TOOLS.md

## Host — macOS (primary, VERIFIED working)

| Tool | Version | Purpose | Notes |
|---|---|---|---|
| macOS | 15.7.9 (24G830) arm64 | host | |
| `AppleUSBCHCOM` | Apple, built in | CH34x serial driver | **no install needed** — see `PLATFORM_SUPPORT.md` |
| Python | 3.x (Homebrew) | | repo venv at `.venv/` |
| `pyserial` | 3.5 | USB serial transport | works |
| `bleak` | installed | BLE | not yet exercised |
| `system_profiler SPUSBDataType` | built in | USB enumeration | |
| `ioreg` | built in | driver/provider chain | how the DriverKit match was proven |
| `systemextensionsctl list` | built in | third-party sysext audit | proved none is used |
| `kmutil showloaded` | built in | kext audit | proved no CH34x kext |
| `system_profiler SPBluetoothDataType` | built in | BLE controller state | controller `BCM_4388`, GATT supported |

### Repo tools

| Tool | Experiment | Purpose |
|---|---|---|
| `tools/probe_identity.py` | EXP-MAC-USB-001 | Identity query across baud rates; records raw bytes verbatim |
| `tools/probe_checksum.py` | EXP-USB-002 | Varies only byte 59 to test checksum enforcement |
| `tools/redact.py` | — | Strips unit ids from captures, recomputes checksum, preserves offsets |

## Reference material on disk

| What | Path |
|---|---|
| ArgyllCMS 3.5.0 source | `~/Downloads/Argyll_V3.5.0_orig` |
| ArgyllCMS binaries | `/Applications/Argyll/bin` |
| Argyll vendored in ChromIQ | `~/develop/ChromIQ/native/instlib/` |
| ChromIQ (READ-ONLY) | `~/develop/ChromIQ` |
| Prior art, cloned | `/tmp/cr30-priorart/` — ⚠ `/private/tmp` is swept; re-clone rather than rely on it |

## Not yet available / not yet needed

- **USB packet capture.** Not needed so far: we are the client, so the transport
  log *is* the capture. It becomes necessary only to observe the vendor
  application, which lives on Windows.
- **Windows ARM VM.** Not characterised. Off the critical path for USB.
- **ColorQC2.** Installed on the Windows VM, state uncharacterised. Optional
  tooling only (`CLAUDE.md` §9).
- **Android HCI snoop.** Would need a phone and the vendor app; a human action.
  Only if macOS GATT enumeration proves insufficient.

---

## Added in session 2 by `[CR30-SKEPTIC]` — all hardware-free

| Tool | Purpose |
|---|---|
| `tools/mine_priorart_frames.py <dir>` | Extract CR30 frames from the itohio Eltima `.spm` dumps. Extraction is **structural** and never uses byte 59, so the corpus can test checksum hypotheses without circularity. Never rewrites byte 59; drops `AA 0A` identity frames rather than redacting them. `--all-windows` emits the false positives too, so a reviewer can measure the extraction's error rate. |
| `tools/decode_spectra.py <corpus>` | Decode measurements. Reads the spectral axis from the `BB 01 09` header and **rejects** a measurement whose chunks do not deliver what the header declares. |
| `tools/spectral_rank.py <spectra>` | EXP-SPEC-001 analysis: singular-value spectrum and per-component roughness of a measurement matrix. |

```bash
.venv/bin/python tools/mine_priorart_frames.py /tmp/cr30-priorart/color-science/reverse-engineer-c30/serial-sniffer
.venv/bin/python tools/decode_spectra.py captures/public/PRIORART-001-vendor-usb-frames.json
.venv/bin/python tools/spectral_rank.py captures/public/PRIORART-002-spectra.json
```

⚠ **`tools/redact.py` recomputes byte 59.** That makes a redacted frame a valid
*fixture* and useless as *evidence* for any checksum rule. Never cite a redacted
frame in support of the checksum. See `PROTOCOL.md` §0.

## Session 2 tools — `[CR30-USB]`

| Tool | Experiment | Hardware? |
|---|---|---|
| `probe_bb_class.py` | EXP-USB-003 stage 1 — does `0xBB` answer, and how? | yes |
| `probe_bb_checksum.py` | EXP-USB-003 stage 2 — checksum enforcement on `0xBB` | yes |
| `probe_request_fields.py` | EXP-USB-006 — what of a *request* does the device parse? | yes |
| `probe_timing.py` | EXP-USB-005 — latency, settle delay, gaps, reopen, idle, line coding, pipelining | yes |
| `probe_bb13_field.py` | EXP-USB-005b — what moves `BB 13`'s field; pipelining recovery | yes |
| `probe_write_granularity.py` | EXP-USB-005c — one-write rule; 12-min drift sampler | yes |
| `probe_argyll_scan.py` | EXP-USB-007 — ChromIQ's Argyll serial scan vs. the CR30 | yes |
| **`run_human_session.py`** | **EXP-CAL-001 + EXP-MEAS-001 — the one human session** | yes + human |

`run_human_session.py` sends only frames that are byte-identical to vendor
traffic; `tests/test_human_session_frames.py` fails the build if that stops
being true, or if any frame leaves `SAFETY_ENVELOPE.md`'s green list.
