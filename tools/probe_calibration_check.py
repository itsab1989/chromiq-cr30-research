#!/usr/bin/env python3
"""EXP-CAL-002 -- 30-second check that the stored calibration has not moved.

Re-measures plain white paper and compares against the EXP-MEAS-001 baseline.
A calibration shift moves every band by roughly the same FACTOR; a different
spot changes the SHAPE. The ratio's spread separates the two.

Sends only the trigger and four chunk fetches. Never sends BB 10 or BB 11.
"""
import sys, json, pathlib, datetime, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "src"))
import run_human_session as hs
from cr30.colour import spectrum_to_lab, D65

BASE = json.loads((ROOT / "captures" / "raw" /
                   "EXP-CAL-001-EXP-MEAS-001-human-session.json").read_text())
REF = [p for p in BASE["phases"] if "WHITE PAPER" in p["phase"]][0]["spectrum"]


def main():
    hs.LOG.clear()
    hs.LOG.update({"experiment": "EXP-CAL-002",
                   "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "port": hs.PORT, "phases": [], "aborted": None})
    print("EXP-CAL-002 -- has the stored calibration moved?")
    print(f"baseline (EXP-MEAS-001 white paper): mean {statistics.fmean(REF):.2f}%\n")
    import serial
    with serial.Serial(hs.PORT, 115200, timeout=0.05, bytesize=8, parity="N",
                       stopbits=1, rtscts=False, dsrdtr=False) as ser:
        ser.reset_input_buffer()
        hs.ask("Cap OFF. Place the CR30 on PLAIN WHITE PAPER -- the same kind you\n"
               "         used in the first session (an unprinted margin is fine).")
        now = hs.measure(ser, "white paper, calibration check").get("spectrum")
    if not now:
        sys.exit("no spectrum returned")
    ratio = [n / r for n, r in zip(now, REF) if r > 1e-6]
    mean, sd = statistics.fmean(ratio), statistics.pstdev(ratio)
    de = sum((a - b) ** 2 for a, b in
             zip(spectrum_to_lab(now, D65), spectrum_to_lab(REF, D65))) ** 0.5
    hs.LOG["analysis"] = {"mean_now": round(statistics.fmean(now), 3),
                          "mean_baseline": round(statistics.fmean(REF), 3),
                          "ratio_mean": round(mean, 4), "ratio_sd": round(sd, 4),
                          "delta_e76": round(de, 3)}
    print(f"\n  now {statistics.fmean(now):.2f}%   baseline {statistics.fmean(REF):.2f}%")
    print(f"  band ratio: mean {mean:.3f}  sd {sd:.3f}")
    print(f"  dE76 vs baseline: {de:.2f}")
    if abs(mean - 1) < 0.05 and de < 3:
        v = "CALIBRATION UNCHANGED -- readings agree with the baseline."
    elif sd < 0.05:
        v = ("UNIFORM SHIFT of %.1f%% -- a nearly constant ratio across all bands "
             "is what a CALIBRATION CHANGE looks like. Report this." % ((mean - 1) * 100))
    else:
        v = ("SHAPE DIFFERS (ratio sd %.3f) -- that is a different spot or a "
             "different paper, NOT a calibration shift." % sd)
    hs.LOG["verdict"] = v
    print("\n  VERDICT: " + v)
    q = ROOT / "captures" / "raw" / "EXP-CAL-002-calibration-check.json"
    q.write_text(json.dumps(hs.LOG, indent=2)); print(f"\nwrote {q}")


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\ninterrupted")
