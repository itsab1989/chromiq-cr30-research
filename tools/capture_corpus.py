#!/usr/bin/env python3
"""EXP-SPEC-001a -- capture a large, varied colour corpus, fast.

WHY. The open colour-science question is whether the CR30's 31 bands are 31
measurements or a firmware reconstruction from ~11 physical sensor channels.
It decides whether writing 31 SPEC_* columns into a .ti3 honestly tells colprof
it has 31 independent measurements. Answering it needs MANY well-spread colours
measured in ONE calibration state -- EXP-MEAS-005's corpus had only ~10 distinct
surfaces because six readings were the same patch.

NO ENTER PRESSES. The device stores its last reading; this polls over BLE and
records automatically whenever the reading CHANGES. Place, press the button,
move on. A running count is printed.

Every reading is bounds-checked before it is accepted (src/cr30/measurement.py),
so a gated or truncated reply is rejected out loud rather than silently joining
the corpus.
"""
import sys, json, pathlib, datetime, time, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from cr30.device import CR30
from cr30.measurement import MeasurementError
from capture_io import save_capture

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 40
ADDRESS = sys.argv[2] if len(sys.argv) > 2 else None


def main():
    print(__doc__)
    print(f"Target: {TARGET} distinct patches. Ctrl-C to stop early "
          "(everything captured so far is saved).\n")
    print("  Cap OFF, no magnets near the instrument.")
    print("  For each patch: place it, press the CR30's own button, move on.\n")
    log = {"experiment": "EXP-SPEC-001a", "transport": "ble",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "note": "one calibration state; readings auto-detected on change",
           "readings": [], "rejected": []}
    seen: set[tuple] = set()
    dev = CR30.open_ble(address=ADDRESS)
    try:
        last = None
        idle = 0
        while len(log["readings"]) < TARGET:
            try:
                # enforce=False here: a repeat simply means "no new reading yet",
                # which is normal while waiting. Real validation happens below.
                m = dev.read_measurement(enforce=False)
            except MeasurementError as e:
                log["rejected"].append({"reason": str(e)})
                print(f"\n  !! rejected: {str(e)[:70]}")
                time.sleep(0.6); continue
            key = tuple(m.values)
            if key in seen:
                idle += 1
                print(f"\r  waiting for a new patch... "
                      f"{len(log['readings'])}/{TARGET} captured", end="", flush=True)
                time.sleep(0.5); continue
            try:
                m.check_usable(last)          # full gate on anything NEW
            except MeasurementError as e:
                log["rejected"].append({"reason": str(e),
                                        "values": m.values[:5]})
                print(f"\n  !! rejected: {str(e)[:70]}")
                seen.add(key); time.sleep(0.5); continue
            seen.add(key); last = m
            log["readings"].append(m.as_dict())
            save_capture(ROOT, "EXP-SPEC-001a-corpus", log) if False else None
            (ROOT / "captures" / "raw").mkdir(parents=True, exist_ok=True)
            (ROOT / "captures" / "raw" / "EXP-SPEC-001a-corpus.partial.json"
             ).write_text(json.dumps(log, indent=2))
            L = m.lab or [0, 0, 0]
            print(f"\r  [{len(log['readings']):3d}/{TARGET}] mean {m.mean:6.2f}%  "
                  f"L*{L[0]:6.2f} a*{L[1]:+7.2f} b*{L[2]:+7.2f}          ")
            idle = 0
    except KeyboardInterrupt:
        print("\n  stopped by operator")
    finally:
        try: dev.close()
        except Exception: pass
    p = save_capture(ROOT, "EXP-SPEC-001a-corpus", log)
    tmp = ROOT / "captures" / "raw" / "EXP-SPEC-001a-corpus.partial.json"
    if tmp.exists(): tmp.unlink()
    n = len(log["readings"])
    print(f"\n  {n} distinct patches captured, {len(log['rejected'])} rejected")
    if n:
        means = [statistics.fmean(r["values"]) for r in log["readings"]]
        print(f"  lightness spread: {min(means):.1f}% .. {max(means):.1f}% mean R")
    print(f"  wrote {p}")
    if n < 15:
        print("  ⚠ fewer than 15 distinct colours -- not enough for a rank test.")


if __name__ == "__main__":
    main()
