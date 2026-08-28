# TRANSPORT_BLE.md

**Status: the device is FOUND and its GATT tree is mapped. It does not answer
— yet.** `EXP-BLE-001` / `-002` / `-003`, 2026-08-28, macOS host.

## The device advertises, and its own USB identity is the name — VERIFIED

```
advertised name : CM454M0223       <- byte-for-byte the string AA 0A 01 returns over USB
services (adv)  : ffe0, fee7
negotiated MTU  : 244              <- a 60-byte frame fits in ONE write; no fragmentation needed
```

**The advertised name is the device-id string we read over USB.** That is how it
was identified, and it is the cleanest possible link between the two transports.

⚠ **My name heuristic failed and would have produced a false negative.** It
flagged `65" Crystal UHD` (the substring "cr") and did **not** flag the real
device. Discovery came from recognising the USB identity string, not from the
search. Recorded because a wider hint list would not have helped — the fix is to
match on the device's own reported id, which only the USB work made available.

`fee7` is a Tencent/WeChat IoT service UUID, consistent with the manufacturer's
advertised **WeChat mini program** support. Only `ffe0` appeared in the connected
GATT tree.

## Single connection, and it stops advertising when taken — VERIFIED

Attempting to resolve the device by name while the vendor app was connected
failed three times in a row: **the CR30 stops advertising once a central
connects.** It is a single-connection peripheral.

Two consequences:

1. **Connection state is observable without asking the operator.** If the device
   is advertising, nothing holds it; if it is not, something does. That is a
   free state signal for any future probe.
2. Our earlier Mac connections genuinely held the device — it was free at the
   time — so "connected but silent" was a real connection, not a phantom.

⚠ **This broke `EXP-BLE-008` as first written**, which resolved the device
*after* asking the operator to connect the app: an impossible order that could
only ever fail. Three wasted runs. The device must be resolved **before** the
app takes it and the handle reused afterwards.

## GATT — VERIFIED

| Characteristic | Properties |
|---|---|
| `ffe1` | write · **notify** · write-without-response |
| `ffe2` | write · **notify** · write-without-response |
| `ffe3` | write · write-without-response |

**No characteristic has `read`.** This is a write/notify transport — commands
out by write, responses back by notification — the conventional BLE-UART shape
(`ffe0`/`ffe1` is the classic HM-10 style profile). Three characteristics rather
than one is unusual and unexplained.

## It does not respond — DISPROVEN that BLE is simply "the same, over BLE"

The identity command `AA 0A 00 00` — read-only, no side effects, sent hundreds
of times over USB — was written to **every** characteristic in **both** write
modes, with notifications subscribed on `ffe1` and `ffe2`:

| Channel | write-without-response | write-with-response |
|---|---|---|
| `ffe1` | 0 bytes | 0 bytes |
| `ffe2` | 0 bytes | rejected (ATT error 14) |
| `ffe3` | 0 bytes | 0 bytes |

A 4-second passive listen returned nothing either. **Every write was accepted;
nothing ever came back.**

So the claim in ChromIQ issue #159 that BLE "probably" carries the same 60-byte
packets is **not supported** on present evidence. It is not yet *disproven*
either — see below. This is exactly why the standing rule is that it must be
proved, not assumed.

## ✅ SOLVED — BLE works, and it is a DIFFERENT protocol from USB

`EXP-BLE-009` (vendor capture) → `EXP-BLE-010` (our own client, working).
2026-08-28.

A PacketLogger trace of the vendor iOS app was parsed down to the ATT layer
(`tools/parse_pklg.py`). It answered the question in one pass, and every earlier
hypothesis was wrong.

### Why nothing we sent ever worked

**The host must write a single `0x01` byte to poll.** That is the entire missing
ingredient. The device answers a poll, not a command-and-wait. We had been
writing 60-byte USB frames and waiting — so it never spoke, and that had nothing
to do with channel, chunk size, sleep or activation.

### The BLE protocol — VERIFIED against our own working client

| | USB | **BLE** |
|---|---|---|
| Frame size | **60 bytes** | **10 bytes** |
| Transport | one `write()` of exactly 60 | ATT write to `ffe1` |
| Flow control | request → reply | **write `0x01` to poll**; replies arrive as notifications |
| Spectral axis in header | `28 1f 0a` = 40(×10), 31, 10 | `01 90 0a 1f` = **400 (BE uint16)**, 10, 31 |
| Bulk reply | 4 chunk fetches, 50 bytes each | one 200-byte notification |
| Checksum | `sum(0..58) mod 256` | **`sum(0..8) mod 256`** — the same rule, generalised |

**The checksum rule generalises across transports and frame sizes**: sum every
byte except the last, marker included. That is a genuine unification, and it is
further confirmation that the USB rule (not the published one) is correct.

**⚠ ChromIQ issue #159 assumed "the framing on top is probably the same 60-byte
packets". It is not.** BLE is a different frame size, a different flow-control
model, and a different axis encoding.

### Reply layout — VERIFIED (`bb 02 10`, read stored measurement)

```
offset   0   8 bytes   header  bb 02 10 00 | 01 90 (=400nm BE) | 0a (10nm) | 1f (31)
offset   8   124 bytes 31 x float32 LE  -- the spectrum, percent reflectance
offset 132   52 bytes  13 x float32 zero -- reserved/unused
offset 184   12 bytes  3 x float32 LE   -- L*, a*, b*  FROM THE DEVICE
offset 196   4 bytes   0x7FFF0000 (NaN) -- terminator
             = 200 bytes total
```

### Two cross-validations, both exact

1. **The BLE spectrum equals the USB spectrum to float32 precision** — maximum
   difference **4.7 × 10⁻⁷** across all 31 bands, measured on the same stored
   reading. Two independent transports, identical data. The decode is right.
2. **The device transmits its own L\*a\*b\***: `91.6424 / −0.7779 / +1.3622`,
   matching the display exactly. Our computation from the spectrum gives
   ΔE **0.051** under **D65/10°**, against 0.239 for D50/10° and 0.062 for
   D65/2°. Our colour maths is now validated against the firmware's own
   arithmetic rather than assumed — and D65 over D50 is confirmed a second time,
   independently.

### Commands seen in the vendor session

| Frame | Meaning |
|---|---|
| `01` (1 byte) | **poll** — the device sends its next pending data |
| `bb 02 10 00 00 00 00 00 ff cc` | read the stored measurement → the 200-byte reply above |
| `bb 14 08 a0 91 6a 01 00 ff 72` | unknown; carries a 4-byte field that looks like a timestamp |
| `bb 14 09 a0 91 6a 01 00 ff 73` | unknown; same field, sub `0x09` |
| `bb 01 00 00 01 90 0a 1f ff 75` | *(device → host)* hello / axis announcement |

The `bb 14` family is **not yet understood** and is the obvious next target —
it is the only command class the vendor app used that we cannot explain.

### Practical consequence for ChromIQ

**A CR30 can be read from macOS over Bluetooth with no driver, no kernel
extension and no cable**, using `bleak`, which is cross-platform. That was the
strategic hope in issue #159 §1b, and it is now demonstrated rather than assumed
— though for a different reason than #159 gave, since USB needs no driver on
macOS either.

⚠ The device stops advertising while a central holds it, so the phone app and
ChromIQ cannot both be connected.


---

# 🔴 ADVERSARIAL REVIEW — `[CR30-SKEPTIC]`, 2026-08-28

Everything above rests on **one ~30-second vendor PacketLogger trace**
(`EXP-BLE-009`) plus our own client's replies. That is a small base, and this
section says exactly which claims it can carry. All of it is pinned in
`tests/test_ble_claims_under_attack.py`.

## Scale, first

The **entire BLE frame corpus is five distinct 10-byte frames.** USB needed 260
before its checksum rule was uniquely determined, and four frames left fifteen
candidates. Every claim below should be read against that number.

## SURVIVES — the poll byte, and the spectrum offset

- **`0x01` polls.** VERIFIED by our own working client, then exercised over 15
  readings in `EXP-MEAS-005`. This is the strongest BLE result and it is not in
  doubt.
- **Spectrum at offset 8, 31 × float32 LE.** Two vendor replies plus our own,
  cross-validating against the USB decode to 4.7 × 10⁻⁷. CORROBORATED.
- **`bb 14` echoes app-supplied data.** UPGRADED, see `MEASUREMENT.md`: the
  vendor's non-zero payload and our zero payload undergo the *same*
  transformation, which is the mutation landing. `bb 14` reports nothing.

## WEAKENED — "the same checksum rule generalised" is 1 of 4, not 1

Enumerating contiguous additive rules `sum[i:j] + c` over the whole five-frame
corpus leaves **four** survivors, not one:

```
sum[0:8] + 0xff      <- arithmetically itohio's 0xBB branch
sum[0:9] + 0x00      <- the rule this document and src/cr30/ble.py assert
sum[1:8] + 0xba
sum[1:9] + 0xbb
```

The confounds are the same two that trapped session 1 on USB: **byte 0 is `0xbb`
in every frame** and **byte 8 is `0xff` in every frame**, so start-of-range and
marker-inclusion both trade against the constant. On USB the tie was broken only
by the `BB 01 09` headers carrying marker `0x00`; **no BLE frame with a marker
other than `0xFF` has ever been seen**, so the discriminating case does not
exist here.

Calling this *"a genuine unification"* and *"further confirmation that the USB
rule is correct"* assumes the answer. **Downgrade to PROBABLE by analogy.**
Practically the risk is latent — nothing verifies a received BLE frame's
checksum at all today — but if it is ever added and the device does emit a
marker-`0x00` frame, three of these four rules reject it.

## DISPROVEN — the "0x7FFF0000 terminator"

| | bytes 196..200 |
|---|---|
| our unit (`EXP-BLE-010`) | `00 00 ff 7f` — float32 LE NaN |
| **vendor unit, both replies** (`EXP-BLE-009`) | **`00 00 00 00`** |

It is not a constant and it is not a terminator. An implementation that
validated a reply with it would reject every reply from the vendor's unit.
`src/cr30/ble.py` does not use it — the *document* was wrong, not the code.

## 🔴 NEW HAZARD — a truncated reply, zero-filled, that passes every check

The vendor's 410-byte notification stream is **not** "one 200-byte
notification". It is:

```
110 bytes  a TRUNCATED bb 02 10 reply: bands 0-24 intact,
             band 25 half-written (2 bytes), then nothing
 90 bytes  zero fill
200 bytes  a complete reply -- same spectrum, L*a*b* = 91.6424 / -0.7779 / +1.3622
 10 bytes  the bb 14 echo
```

*Reconstruction caveat, because it matters:* this is a concatenation of two
PacketLogger records (241 + 169 bytes). A **lost** record would also explain
zeros — but it would misalign everything after it, and the second reply parses
byte-perfectly at offset 200 while the arithmetic closes exactly at
110 + 90 + 200 + 10 = 410. Alignment is the control, and it holds.

**What the shipped code does with those bytes** (`tests/test_ble_claims_under_attack.py`):

- `device.py:105` does `raw.find(MEASUREMENT_HDR)` and takes the **first** hit —
  which is the truncated reply.
- `device.py:109` requires only 196 bytes after it. 200 are available. Passes.
- There is **no checksum over the 200-byte reply, no length equality, no
  terminator check**. `_drain()` is a 0.4 s timing heuristic, not a guarantee —
  and its own docstring records that its absence "silently produced fifteen
  garbage readings".
- `Measurement.check_usable()` then **accepts** the result: five bands of
  exactly `0.0 %R` are finite and inside `[-1, 130]`, and a device `L* = 0.0`
  satisfies `0.0 <= L* <= 100.0`.

So a BLE backend can return a measurement whose last five bands are zero and
whose Lab is pure black, for a sample that is in fact a 91.6 L\* white — with no
error. This is precisely the pattern `CLAUDE.md` §14 forbids.

**Requested actions for `[CR30-USB]`, in order of value:**

1. Reject a reply whose device L\*a\*b\* is exactly `(0, 0, 0)`. Free, and it
   catches this case outright.
2. Reject trailing exact zeros in the spectrum. A real reflectance band is never
   exactly `0.0` — the air control read 0.002 %, not 0.
3. Scan for the header from the **end** of the buffer, or require exactly one
   occurrence, rather than taking `find()`'s first hit.
4. Require the reply length to be exactly 200 for a 31-band axis, not `>= 196`.

## Also open, and not currently acknowledged

- **`LAB_AT = 184` and `MIN_REPLY = 196` are hard-coded for 31 bands** while the
  spectrum is unpacked using the device-declared `axis.bands`. If the device
  ever declares a different count the two overlap silently. Derive both from the
  axis, or assert the axis.
- **Only one command has ever produced a bulk reply.** The offsets are `bb 02
  10`'s. Nothing is known about the layout of any other command's reply, and
  `device.py` would unpack floats out of whatever it found.
- **The vendor session is ~30 s and starts at connection.** It contains no
  calibration, no trigger, no `bb 13`. "The commands seen in the vendor session"
  is not the BLE command set.
- **No BLE host trigger is known**, which is fortunate — see `CALIBRATION.md` §2.
