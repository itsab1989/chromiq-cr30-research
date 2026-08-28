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
| ArgyllCMS 3.5.0 source | `/Users/Basti/Downloads/Argyll_V3.5.0_orig` |
| ArgyllCMS binaries | `/Applications/Argyll/bin` |
| Argyll vendored in ChromIQ | `/Users/Basti/develop/ChromIQ/native/instlib/` |
| ChromIQ (READ-ONLY) | `/Users/Basti/develop/ChromIQ` |
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
