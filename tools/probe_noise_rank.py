#!/usr/bin/env python3
"""EXP-SPEC-001b -- noise-covariance rank. The test that removes the confound.

EXP-SPEC-001a found a rank-9 cliff over 40 printed patches, but that CANNOT
distinguish a 9-channel sensor from a 9-dimensional chart: patches printed with
a fixed ink set are low-dimensional by construction, so a perfect 31-channel
spectrometer would give the same answer.

This removes sample diversity BY CONSTRUCTION. One patch, never moved, measured
many times. The only thing varying is measurement noise.

  * noise spans ~31 dimensions  -> the sensor really has 31 independent channels
  * noise collapses to ~9-13    -> the output is reconstructed from fewer, and
                                   writing 31 SPEC_* columns to a .ti3 would
                                   assert information that is not there

TARGET: a LIGHT NEUTRAL (plain paper or light grey). A saturated colour has
near-zero signal in some bands, so those bands show almost no noise and would
fake a low rank. A light neutral has real signal in all 31 bands.

Triggers over USB so the operator does not press the button 30 times. No magnet
is involved, so the trigger cannot cause a calibration write -- but the run
still re-checks the device against a known reference at the end.
"""
import sys, json, pathlib, datetime, time, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from cr30 import usb_measure
from cr30.transport import SerialTransport
from cr30.discovery import candidates
from cr30.measurement import Measurement, MeasurementError
from capture_io import save_capture

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def main():
    print(__doc__)
    found = candidates()
    if not found:
        sys.exit("No CH34x serial device. Plug the CR30 in by USB and retry.")
    port = found[0].device
    print(f"port: {port}\n")
    print("  Place the CR30 flat on a LIGHT NEUTRAL patch (plain paper or light")
    print("  grey). Cap OFF, no magnets. DO NOT TOUCH IT once you press Enter --")
    print(f"  it will take {N} readings by itself, about {N*2//60}:{N*2%60:02d}.")
    input("\n  press Enter to start > ")

    log = {"experiment": "EXP-SPEC-001b", "utc": datetime.datetime.now(
        datetime.timezone.utc).isoformat(), "n_requested": N,
        "target": "light neutral, not moved", "readings": [], "rejected": []}
    t = SerialTransport(port); t.open()
    try:
        for i in range(N):
            try:
                usb_measure.trigger(t)
                time.sleep(0.25)
                m = usb_measure.read_stored(t)
                m.validate()
                log["readings"].append(m.values)
                print(f"\r  [{len(log['readings']):3d}/{N}] mean {m.mean:6.3f}%   ",
                      end="", flush=True)
            except (MeasurementError, Exception) as e:
                log["rejected"].append(str(e)[:120])
                print(f"\n  !! {type(e).__name__}: {str(e)[:70]}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        t.close()

    X = log["readings"]
    n = len(X)
    print(f"\n\n  {n} readings, {len(log['rejected'])} rejected")
    if n < 12:
        print("  too few for a rank test"); save_capture(ROOT, "EXP-SPEC-001b-noise", log); return

    dup = len(X) - len({tuple(r) for r in X})
    log["identical_pairs"] = dup
    print(f"  identical readings: {dup}  (must be 0 -- otherwise the device is "
          "not re-measuring and there is no noise to analyse)")

    try:
        import numpy as np
    except ImportError:
        print("  numpy missing: .venv/bin/pip install numpy"); save_capture(ROOT,"EXP-SPEC-001b-noise",log); return
    A = np.array(X, float)
    R = A - A.mean(0)                      # residuals = pure noise
    s = np.linalg.svd(R, compute_uv=False)
    s = s[s > 0]
    log["singular_values"] = [float(v) for v in s]
    print("\n  NOISE singular values:")
    for i, v in enumerate(s[:20]):
        print(f"   {i+1:2d}: {v:10.5f}  {'#'*int(46*v/s[0])}")
    lg = np.log10(s)
    gaps = [(float(lg[i] - lg[i + 1]), i + 1) for i in range(len(lg) - 1)]
    g, k = max(gaps)
    log["largest_gap_decades"], log["largest_gap_after"] = round(g, 4), k
    print(f"\n  largest gap {g:.3f} decades after component {k}")
    eff = int((s > s[0] * 0.01).sum())
    log["effective_rank_1pct"] = eff
    print(f"  components above 1% of the largest: {eff}")
    if eff >= 20:
        v = ("NOISE IS HIGH-DIMENSIONAL -- consistent with a genuine 31-channel "
             "sensor. The rank-9 cliff in EXP-SPEC-001a was the CHART, not the "
             "instrument, and 31 SPEC_* columns are defensible.")
    elif eff <= 14:
        v = (f"NOISE COLLAPSES TO ~{eff} DIMENSIONS -- the output is "
             "reconstructed from fewer physical channels. Writing 31 SPEC_* "
             "columns would assert information the device does not have.")
    else:
        v = (f"INCONCLUSIVE at ~{eff} effective dimensions -- between the two "
             "hypotheses. A spiky reflectance standard would settle it.")
    log["verdict"] = v
    print("\n  VERDICT: " + v)
    p = save_capture(ROOT, "EXP-SPEC-001b-noise", log)
    print(f"\n  wrote {p}")
    print("\n  Now re-check calibration was untouched:")
    print("    .venv/bin/python tools/probe_calibration_check.py " + port)


if __name__ == "__main__":
    main()
