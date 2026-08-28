# PROVENANCE

This repository's own code is MIT.

## Prior art consulted

| Source | Licence | How it was used |
|---|---|---|
| [`itohio/color-science`](https://github.com/itohio/color-science) | MIT | Protocol claims read and **tested**. Its checksum rule was found incorrect against real hardware (`PROTOCOL.md` §2). No code copied; `src/cr30/frame.py` is an independent implementation of a different, verified rule. |
| [`beerjongen/CR30-ti3-Dispensary`](https://github.com/beerjongen/CR30-ti3-Dispensary) | MIT | `.ti3` writing approach and sample CSV, as evidence for value scale and measurement condition. No code copied. |
| [itohi.com write-up](https://itohi.com/colorimetry/reverse-engineering-cr30/) | article | Background and claims to test. |
| ArgyllCMS 3.5.0 | AGPL/GPL | Read only, as reference for serial-instrument transport patterns. **Contains no CR30 support.** Nothing copied. |

Prior art is evidence, never ground truth (`CLAUDE.md` §4).

⚠ **ColorQC2 is vendor software. Nothing of it is copied, redistributed or
depended upon** (`CLAUDE.md` §9).
