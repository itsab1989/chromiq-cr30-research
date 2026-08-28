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

## Timing — observed, not yet characterised

Identity replies arrive well within the 1.2 s drain window used by
`tools/probe_identity.py`. Response latency has not been measured precisely;
that belongs to a dedicated timing experiment. No inter-command delay was
needed between the four identity queries.

## Open questions

1. Is a settling delay needed after opening the port? The probe uses 300 ms
   without testing whether it is necessary.
2. Does the device emit anything unsolicited while idle? `EXP-MAC-USB-001`
   captured a 1.0 s passive window at each baud and saw **nothing**. This is
   consistent with the prior-art claim that button presses produce unsolicited
   traffic only when a button is actually pressed — untested here.
3. Reconnect and sleep/wake behaviour: untested.
