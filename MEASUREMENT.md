# MEASUREMENT.md

**Status: not started.** No measurement has been taken by this project.

Everything below is prior-art claim, recorded for testing. None of it is
asserted. See `PROTOCOL.md` §5.

## The claimed sequence (itohio) — to be tested

```
trigger:  BB 01 00 00           -> header frame (subcmd 0x09?)
fetch:    BB 01 10 00           -> chunk 0  (payload[2:50] = 48 SPD bytes)
          BB 01 11 00           -> chunk 1  (48 bytes)
          BB 01 12 00           -> chunk 2  (48 bytes)
          BB 01 13 00           -> chunk 3  (final; their code extracts 0 bytes)
decode:   struct.unpack("<31f", accumulated[:124])   # 31 float32 LE
map:      400, 410, ... 700 nm
```

3 × 48 = 144 bytes accumulated, of which only the first 124 are used. **The
remaining 20 bytes are unexplained** and chunk `0x13` is fetched but discarded.
That asymmetry is a strong hint the chunking is misunderstood — a priority to
resolve, not to reproduce.

## Questions that must be answered by experiment

1. How many transactions does one measurement really take, and in what order?
2. Does the state machine match `idle → trigger → integrating → data → complete`,
   or something else? Do not assume this shape.
3. Does the device reject commands while busy? Can measurements overlap?
4. Is a measurement cached — does re-fetching chunks return the same data?
5. Does a button press produce unsolicited traffic, and is the resulting data
   fetched the same way as a software-triggered measurement?
6. Is calibration a precondition, and what does the device do without it?
7. What is the real end-to-end time, measured rather than quoted?

## The spectral question — the one that matters for colour science

**Are the 31 values 31 measurements, or a firmware reconstruction from a
smaller number of physical channels?** The prior-art write-up *estimates* an
AS7341/AS7343 sensor, which has ~11 channels.

This is not academic: writing 31 `SPEC_*` columns into a `.ti3` tells `colprof`
it has 31 independent measurements. If they are interpolated from 11, the
profile is built on a false premise about its own information content.

Ways to attack it without opening the device:
- Measure narrow-band or spiky sources and look for impossible smoothness.
- Look for fixed linear dependence between bands across many varied samples —
  a reconstruction from 11 channels cannot produce 31 linearly independent
  spectra. **Rank analysis of a large measurement matrix is decisive and needs
  no hardware knowledge**, only many diverse readings.
- Check whether adjacent bands ever cross in ways a smooth basis forbids.

This is `[CR30-SKEPTIC]` work and does not need the hardware lease once a
sufficient set of readings exists.
