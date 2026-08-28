# TRANSPORT_USB.md

## Identification — VERIFIED

| Field | Value |
|---|---|
| Vendor ID | `0x1A86` (WCH — Nanjing Qinheng) |
| Product ID | `0x7523` (CH34x-class serial bridge) |
| Product string | `CH554_CDC` |
| Manufacturer string | *(none — `iManufacturer` = 0)* |
| Serial number | *(none — `iSerialNumber` = 0)* |
| `bDeviceClass` | `0xFF` vendor-specific |
| `bDeviceProtocol` | `0x02` |
| `bcdDevice` | `0x0263` (2.63) |
| Configurations | 1 |
| Speed | Full speed, 12 Mb/s |
| Current required | 96 mA |

The name `CH554_CDC` indicates a **WCH CH554 microcontroller running serial
bridge firmware**, presenting the classic CH340 PID. It is *not* a standard
USB-CDC-ACM device (`bDeviceClass` is `0xFF`, not `0x02`).

⚠ **`iSerialNumber` is 0** — the device exposes no USB serial number. Two CR30s
on one machine cannot be told apart by USB descriptor alone; they must be
distinguished by the protocol-level device id (`AA 0A 00`).

## Serial configuration — VERIFIED

| Parameter | Value | Evidence |
|---|---|---|
| Baud | **any** | `EXP-MAC-USB-001`: identical replies at 9600/19200/38400/57600/115200 |
| Data bits | 8 | works |
| Parity | None | works |
| Stop bits | 1 | works |
| Flow control | none (`rtscts=False`, `dsrdtr=False`) | works |

Untested: whether non-8N1 framing also works. Given that line coding never
reaches a UART, **HYPOTHESIS**: it is equally ignored. Low value to test.

## Timing — MEASURED, `EXP-USB-005` (2026-08-28, `[CR30-USB]`)

All figures from this unit over USB on macOS 15.7.9, 0.5 ms polling resolution.

| | median | min | max | n |
|---|---|---|---|---|
| First byte of the reply | **0.735 ms** | 0.603 | 0.932 | 50 |
| Complete 60-byte reply | **0.767 ms** | 0.706 | 1.491 | 50 |
| Same for `BB 13` | 0.737 ms | 0.695 | 0.967 | 50 |

100/100 transactions replied. A 1 s timeout is four orders of magnitude of
headroom for identity and status commands. **Calibration and measurement are
not characterised** — they must carry their own, longer timeouts.

⚠ **Quote a latency only with its polling resolution.** The first probes of
session 2 reported ~6.3 ms; that was a 5 ms `sleep()` in the probe, not the
device. The device is **eight times faster** than the first measurement said.

## Transport rules — VERIFIED

| Rule | Evidence |
|---|---|
| **A frame must be one `write()` call.** 30+30, 59+1, 1+59, 20+20+20 → **no reply at all**, 4/4 | `EXP-USB-005c` |
| **One frame per write, never two.** 120 B and 180 B → no reply; recovers on the next single-frame write with no reopen | `EXP-USB-005b` |
| **No settle delay after open.** 10/10 valid at 0 ms, identical to 300 ms | `EXP-USB-005` |
| **No inter-command delay.** 30/30 valid at a 0 ms gap | `EXP-USB-005` |
| **Close/reopen is clean.** 20/20 cycles, 0 open errors | `EXP-USB-005` |
| **Silent when idle.** 0 unsolicited bytes over 90 s, and over 12 min of polling | `EXP-USB-005/-005c` |
| **Line coding is ignored.** 8N1 / 7E1 / 8N2 / 7N1 / 8O1 byte-identical; 300 / 115200 / 1000000 baud byte-identical | `EXP-USB-005` |
| **Argyll's serial device-scan probes are inert.** 32 probes, 0 bytes back, identity fingerprint unchanged 32/32 | `EXP-USB-007` |

The one-write rule is the trap. A buffered or chunked writer gets **silence**,
not an error, and looks like a dead device or a wrong baud rate. It is enforced
in `src/cr30/transport.py`, which refuses to send anything that is not exactly
60 bytes.

## No UART is in the path — VERIFIED

A 60-byte frame at 115200 baud needs **5.2 ms** on the wire; the reply completes
in **0.77 ms**. At a nominal 300 baud, 60 bytes would need **2 seconds**; the
reply still arrived in **0.97 ms**. The CH554 bridge accepts and discards the
line coding. This upgrades `PROTOCOL.md` §3 from a plausible story to a measured
fact — see §7.1c there.

## Open questions

1. ~~Is a settling delay needed after opening the port?~~ **Answered: no.**
2. ~~Does the device emit anything unsolicited while idle?~~ **Answered: no**,
   over 90 s and over 12 minutes. Whether a *button press* produces unsolicited
   traffic is still untested and is phase 9 of `tools/run_human_session.py`.
3. Sleep/wake and unplug/replug: still untested. Close/reopen is clean.
4. Whether the one-write rule also holds on Windows and Linux, where the USB
   stack may coalesce or split writes differently. **This is the portability
   risk that matters**, and it needs no CR30 expertise to test — only the device
   on another host.

## The USB serial link can go silent while the instrument is perfectly alive

**VERIFIED 2026-08-28.** After roughly ninety minutes idle, the CR30 stopped
answering on USB entirely — not an error, not a truncated frame, **zero bytes**
to the identity query `AA 0A 00 00`, which is the lightest thing the protocol
has. The serial node was still present and nothing else held the port. The same
command had worked all afternoon.

⚠ **First recorded here as the instrument sleeping. That was WRONG**, and the
correction is the interesting part. At the moment USB was silent:

* the device was **advertising over BLE** (RSSI −54), so its radio was up and no
  central held it;
* a **BLE read succeeded immediately**, returning a plausible spectrum and the
  device's own Lab;
* its **display showed `U`**, i.e. the instrument believed the USB link was up.

So the instrument was awake and working. **Only the USB serial link was dead**,
and only on the host side. A replug restores it.

The lesson is the one this project keeps relearning: a silence explains nothing
by itself. "Asleep" fitted the evidence available and was still false, and the
thing that disproved it was reading the device over the *other* transport.

### Why this matters more than it looks

**A sleeping instrument and an unplugged one look identical to the host**:
`/dev/cu.usbserial-*` exists in both cases, because the node belongs to the
CH34x bridge rather than to the CR30's firmware. Any "is the instrument there?"
check that trusts the node's existence is wrong.

Consequences for an implementation:

1. **Presence must be established by asking the device**, never by finding the
   port. `AA 0A 00 00` returning the model string `CR30` is the only sound test
   — the same conclusion `PLATFORM_SUPPORT.md` reaches for a different reason
   (the descriptors describe the shared bridge, and there is no USB serial
   number).
2. **A read that times out mid-chart does not tell you why.** Observed causes so
   far: a stale serial link with the instrument fully alive (this note). The
   host cannot distinguish that from sleep, from a pulled cable, or from a
   powered-off device — the port node survives all of them. So the message must
   offer the cheap checks in order (is the display on? unplug and replug the
   cable?) rather than assert a cause it cannot know.
3. **When USB is silent, TRY BLE before blaming the instrument.** It is the one
   check that separates "the device is gone" from "this link is gone", and it
   costs seconds.
4. **Do not retry silently for long.** Ten seconds of nothing per patch, times a
   chart, is a miserable way to discover the instrument dozed off.

### The instrument's display shows transport state — and `U` is not a health light

Observed live (operator, 2026-08-28): the display carries a **`U`** while a USB
cable is attached and a **`B`** while a Bluetooth session is open. The `B`
appeared the moment this project connected over BLE and vanished the moment it
disconnected, so `B` tracks an *active connection*, not merely a powered radio.

⚠ **`U` was showing throughout the silent-USB incident above.** So `U` means "a
cable is plugged in", not "the USB link is working" — the instrument's own
display cannot tell the user their serial link has wedged any more than the host
can. Do not treat it, or the presence of the port node, as evidence of a healthy
link. Only a reply to `AA 0A 00 00` is that.

**Not established:** what wedges the serial link (idle time, the number of
open/close cycles, or a specific command), whether BLE is affected by the same
condition (it was not here), and whether anything short of a replug clears it.
