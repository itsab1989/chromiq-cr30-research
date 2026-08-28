# INTEGRATION.md — CR30 → ChromIQ

**Status: scaffold. The architecture inspection is assigned and not yet done.**

This document is **design and documentation only**. Nothing here is implemented
in ChromIQ, and nothing in this repository imports ChromIQ (`CLAUDE.md` §3).

## The question this document must answer

> What is the smallest reliable interface between a CR30 reference
> implementation and ChromIQ's existing chart-reading engine?

It must be answered **from source inspection of ChromIQ**, not from assumption.

## Known starting points, from ChromIQ issue #159

To be verified against the actual source, not taken on trust:

| Claim in #159 | To confirm |
|---|---|
| `workflow/chartread_engine.py` — the engine boundary is a line-based JSON event/command protocol over stdout/stdin | If true this is the natural seam, and a CR30 backend need not be C inside Argyll |
| `native/chartread_helper/chromiq_chartread.c` — `rmode 0 = spot`, emits `spot_ready` | A spot instrument may already be modelled |
| `TARGET_INSTRUMENT` gate rejects unknown instrument names outright | Affects how a CR30 chart identifies itself |
| `EXTERNAL_INSTRUMENTS` (i1iSis via i1Profiler) | Precedent for a device Argyll cannot drive |
| `workflow/layout_engine/instruments.py` — ColorMunki branch fits a spot device | Chart geometry |

## What the reference implementation should expose

Conceptually — **the exact shape must follow from ChromIQ's actual needs, not be
imposed on them**:

```
connect() / identify() / calibrate_black() / calibrate_white() / measure() / disconnect()
```

A measurement should carry enough for ChromIQ to consume it **without knowing
the wire protocol**: wavelengths, values, the measurement condition, timing,
device identity, and an explicit success/failure state.

⚠ **Do not hard-code a data model here before the spectral question is settled.**
If the 31 bands turn out to be a reconstruction from ~11 physical channels
(`MEASUREMENT.md`), the honest data model must say so, because writing 31
`SPEC_*` columns into a `.ti3` asserts 31 independent measurements to `colprof`.

## Constraints already established

- **Device identification must be protocol-level, not USB-descriptor-level.**
  The USB descriptors describe a CH34x bridge shared with countless other
  devices, and there is no USB serial number. Only `AA 0A 00 00` returning
  `CR30` is sound (`PLATFORM_SUPPORT.md`).
- **Do not expose baud rate as a setting.** It is ignored by the device
  (`PROTOCOL.md` §3); offering it would be a meaningless control that invites
  false diagnoses.
- **No transmit-side error detection exists** (`ERRORS.md`). Reliability must
  come from receive-side validation, timeouts and retries.
- The patch-identity concern raised in #159 §3b applies: any import or live path
  must refuse a reading count that does not match the chart, rather than pairing
  by order and silently mislabelling everything downstream.

## Open

Sections still to be written: relevant ChromIQ architecture · identified
integration point · required measurement model · adapter boundary · transport
responsibilities · error mapping · calibration mapping · platform considerations ·
testing strategy · which ChromIQ subsystem owns which responsibility.
