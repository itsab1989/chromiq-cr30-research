"""Write a raw capture WITHOUT ever destroying an earlier one.

CLAUDE.md 13: "Never modify a raw capture." Every probe wrote to a fixed
filename, so re-running one silently overwrote the previous run. That is how the
corrupted-calibration spectrum from EXP-CAL-002 was lost -- the single most
valuable negative fixture we had, gone because the restore run reused the name.

Use `save_capture()` in every probe from now on.
"""
from __future__ import annotations

import json
import pathlib


def save_capture(root: pathlib.Path, name: str, payload: dict) -> pathlib.Path:
    """Write captures/raw/<name>.json, rolling any existing file aside.

    An existing file becomes <name>.001.json, .002.json, ... so the newest run
    always has the plain name and NOTHING is ever overwritten.
    """
    out = root / "captures" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{name}.json"
    if p.exists():
        n = 1
        while (out / f"{name}.{n:03d}.json").exists():
            n += 1
        p.rename(out / f"{name}.{n:03d}.json")
    p.write_text(json.dumps(payload, indent=2))
    return p
