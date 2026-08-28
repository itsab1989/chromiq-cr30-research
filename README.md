# chromiq-cr30-research

Reverse engineering the **CHNSpec CR30** spectrophotometer/colorimeter to a
verified, independently-challenged protocol specification and a clean reference
implementation — and, separately, designing how that would eventually reach
[ChromIQ](https://github.com/itsab1989/ChromIQ)'s chart-reading engine.

```
CR30 hardware -> USB / BLE transport -> verified protocol -> correct spectral data
              -> clean device adapter -> ChromIQ chart-reading engine
```

This repository is **independent of ChromIQ**. ChromIQ is a read-only analysis
and integration target here; nothing in this repo modifies it.

## Status in one line

Direct USB communication with the device is **established on macOS with no
driver install**, and the device self-identifies as `CR30`. See
[STATUS.md](STATUS.md).

## Headline findings so far

| # | Finding | Confidence |
|---|---|---|
| 1 | macOS drives the device natively via Apple's built-in `AppleUSBCHCOM` DriverKit extension — **no kext, no vendor driver** | VERIFIED |
| 2 | The device answers identically at 9600/19200/38400/57600/115200 baud — **baud rate is not a protocol parameter** | VERIFIED |
| 3 | The published checksum rule is **wrong**; the real rule is `sum(bytes 0..58) mod 256` | VERIFIED |
| 4 | The device **does not validate the request checksum at all** — which is why the wrong published rule went unnoticed | VERIFIED |
| 5 | ArgyllCMS 3.5.0 contains **no CR30 support whatsoever** | VERIFIED |

Confidence levels are defined in [CLAUDE.md](CLAUDE.md) and used consistently
throughout: VERIFIED / CORROBORATED / PROBABLE / HYPOTHESIS / DISPROVEN.

## Layout

| Path | Contents |
|---|---|
| `src/cr30/` | Reference implementation (transport-agnostic protocol + transports) |
| `tools/` | Investigative probes, one per experiment |
| `captures/public/` | Redacted capture fixtures, safe to publish |
| `captures/raw/` | **gitignored** — unredacted, contains the unit serial |
| `tests/` | Replay tests built from real captures |
| `docs/` | Long-form analysis |
| `scripts/` | Cross-platform session launchers |

## Documents

[STATUS.md](STATUS.md) · [SESSION_HANDOFF.md](SESSION_HANDOFF.md) ·
[RESEARCH_LOG.md](RESEARCH_LOG.md) · [PROTOCOL.md](PROTOCOL.md) ·
[TRANSPORT_USB.md](TRANSPORT_USB.md) · [TRANSPORT_BLE.md](TRANSPORT_BLE.md) ·
[MEASUREMENT.md](MEASUREMENT.md) · [CALIBRATION.md](CALIBRATION.md) ·
[ERRORS.md](ERRORS.md) · [PLATFORM_SUPPORT.md](PLATFORM_SUPPORT.md) ·
[INTEGRATION.md](INTEGRATION.md) · [EXPERIMENTS.md](EXPERIMENTS.md) ·
[TOOLS.md](TOOLS.md)

## Prior art

- itohi.com write-up — <https://itohi.com/colorimetry/reverse-engineering-cr30/>
- `itohio/color-science` (MIT) — <https://github.com/itohio/color-science>
- `beerjongen/CR30-ti3-Dispensary` (MIT) — <https://github.com/beerjongen/CR30-ti3-Dispensary>

Prior art is treated as **evidence, never as ground truth**. Finding #3 above is
a direct correction to it.

## Licence

MIT. Prior-art attribution is recorded in `docs/PROVENANCE.md`.
