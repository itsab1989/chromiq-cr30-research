#!/usr/bin/env python3
"""EXP-019 -- can the CR30 measure ACCURATELY while sliding, and can a human
swipe a real row well enough for strip reading?  (18_strip_design.md §6)

EXP-018 proved readings TRACK a moving surface (3.18/s, dE 0.27 median in
motion vs 0.0037 still). It did NOT prove a reading taken in motion equals the
settled reading of the same surface -- nothing with known ground truth was
under the aperture. That is this experiment.

## Safety

USB only. CAP OFF for the whole run, and it stays off. Only measure-trigger
and read-stored commands are ever sent -- never a calibration command
(`bb 10`/`bb 11` do not appear in this file). A host trigger with the cap ON
would silently rewrite the white calibration, which is why phase gates that
involve the instrument's own button also check the header's magnet flag.

## Method rules (learned the hard way this session)

* No timers on human actions: every phase starts on a REAL event -- keyboard
  Return or the instrument's own button -- and sliding phases END on a real
  event too (lifting the instrument off the paper, detected against the
  in-air signature measured in phase A). Sample caps exist only as backstops.
* Every phase has a control. Phase A is the negative control / end-detector
  training. Phase C (static stream) is the positive control: if phase D's
  "moving" samples are statistically indistinguishable from C, the probe
  declares the phase VOID -- movement was not detected -- never PASS.
* Results are written to captures/raw/EXP-019-strip-feasibility.json after
  EVERY phase, so a killed run loses nothing.
* Observations from the operator (did it beep?) are ASKED and STORED, never
  assumed (the EXP-BLE-015 lesson).

## Phases

  A  IN-AIR signature.       10 machine-paced readings, instrument in the air.
  B  SETTLED white baseline. 5 instrument-button presses on plain paper.
  C  STATIC stream, same spot. 20 machine-paced readings, not moving.
  D  SLIDE on plain paper.   Stream while sliding ~10 cm; end by lifting off.
  E  EDGE crossing.          Slide from white across the darkest patch; lift.
  F  REAL ROW rehearsal (optional):
     F1 pressed ground truth -- one button press per patch of one row;
     F2 swipe of the same row -- armed by a button press on the margin white.

Decision rules are FIXED in 18_strip_design.md §6 before any data existed.
Analysis of phase F: rerun with --analyse (no instrument needed).
"""
import argparse
import datetime
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "captures" / "raw" / "EXP-019-strip-feasibility.json"

AIR_DE = 5.0        # sample counts as "in the air" within this dE of phase A
AIR_RUN = 3         # consecutive air samples that end a sliding phase
CAP_D, CAP_E, CAP_F = 120, 90, 400   # backstop sample caps only


def de(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def lab_of(m):
    from cr30.colour import spectrum_to_lab
    return [round(x, 4) for x in spectrum_to_lab([v / 100.0 for v in m.values])]


def save(out):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"    [saved -> {OUT.name}]")


def stream(dev, cap, air_lab=None, live_note=""):
    """Machine-paced trigger+read until `cap` samples or AIR_RUN air samples."""
    labs, air_run = [], 0
    while len(labs) < cap:
        try:
            dev.trigger_unsafe()
            m = dev.read_measurement(enforce=False)
        except Exception as exc:                                # noqa: BLE001
            print(f"    (a cycle failed: {exc})")
            continue
        l = lab_of(m)
        labs.append(l)
        if len(labs) % 10 == 0:
            print(f"    …{len(labs)} readings{live_note}")
        if air_lab is not None:
            air_run = air_run + 1 if de(l, air_lab) < AIR_DE else 0
            if air_run >= AIR_RUN:
                print("    Lift-off detected — phase ends.")
                break
    return labs


def presses(dev, n, what):
    """n settled readings, each armed by the instrument's OWN button."""
    got = []
    while len(got) < n:
        print(f"    Press the instrument's button ({len(got)+1} of {n}) — {what}")
        try:
            m = dev.read_next_measurement(timeout=600.0)
        except Exception as exc:                                # noqa: BLE001
            print(f"    That press was refused ({exc}). Try again.")
            continue
        if m.gate_flag:
            print("    ⚠ The header says the MAGNET GATE was on — is the cap "
                  "off? Fix it and press again; that reading is discarded.")
            continue
        got.append(lab_of(m))
        print(f"      got L*a*b* {got[-1]}")
    return got


def med(labs):
    return [statistics.median(c) for c in zip(*labs)]


# ---------------------------------------------------------------- analysis --
def align(samples, patch_labs, tau=4.0):
    """Monotonic DP: states garbage0,P1,garbage1,P2,…,Pn,garbage_n.

    Cost in patch state = dE to that patch's (pressed) Lab; in garbage = tau.
    Returns per-patch sample index lists. Pure function — unit-testable."""
    n_states = 2 * len(patch_labs) + 1
    INF = float("inf")

    def cost(s, lab):
        return tau if s % 2 == 0 else de(lab, patch_labs[s // 2])

    prev = [INF] * n_states
    prev[0] = cost(0, samples[0])
    back = []
    for lab in samples[1:]:
        cur, bk = [INF] * n_states, [0] * n_states
        for s in range(n_states):
            best, arg = prev[s], s
            if s > 0 and prev[s - 1] < best:
                best, arg = prev[s - 1], s - 1
            # allow skipping an empty garbage state between two patches
            if s % 2 == 1 and s >= 2 and prev[s - 2] < best:
                best, arg = prev[s - 2], s - 2
            cur[s] = best + cost(s, lab)
            bk[s] = arg
        back.append(bk)
        prev = cur
    # end in the final garbage state (operator lifts off past the last patch)
    s = n_states - 1
    path = [s]
    for bk in reversed(back):
        s = bk[s]
        path.append(s)
    path.reverse()
    segs = {i: [] for i in range(len(patch_labs))}
    for idx, st in enumerate(path):
        if st % 2 == 1:
            segs[st // 2].append(idx)
    return segs, prev[n_states - 1]


def analyse(out):
    f = out.get("phases", {}).get("F")
    if not f or not f.get("swipe"):
        print("No phase F data to analyse."); return
    gt = f["pressed"]
    segs, total = align(f["swipe"], gt)
    print(f"\nPhase F alignment (tau=4.0, ground truth = the pressed row):")
    worst, missing, des = 0.0, 0, []
    for i, lab in enumerate(gt):
        idxs = segs[i]
        if not idxs:
            missing += 1
            print(f"  patch {i+1:2d}: NO SAMPLES ASSIGNED")
            continue
        v = med([f["swipe"][j] for j in idxs])
        d = de(v, lab)
        des.append(d); worst = max(worst, d)
        print(f"  patch {i+1:2d}: {len(idxs):2d} samples, dE to pressed = {d:.2f}")
    if des:
        print(f"  median dE {statistics.median(des):.2f}, worst {worst:.2f}, "
              f"patches with no samples: {missing}")
        verdict = ("GREEN (median<=1.0, worst<=3.0, none missing)"
                   if statistics.median(des) <= 1.0 and worst <= 3.0
                   and missing == 0 else "NOT green — see 18_strip_design.md §6")
        print(f"  Rule from 18_strip_design.md §6: {verdict}")
        out["analysis_F"] = {"median_de": round(statistics.median(des), 3),
                             "worst_de": round(worst, 3), "missing": missing,
                             "verdict": verdict}
        save(out)


# ------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyse", action="store_true",
                    help="re-analyse an existing capture; no instrument needed")
    a = ap.parse_args()

    if a.analyse:
        analyse(json.loads(OUT.read_text())); return

    print(__doc__)
    print("=" * 72)
    print("THE CAP MUST BE OFF and must stay off for the whole run.")
    if input("Type 'cap off' to continue: ").strip().lower() != "cap off":
        print("Aborted."); return

    from cr30.device import CR30
    print("\nOpening over USB …")
    dev = CR30.open_usb()
    print("Connected.")
    out = {"experiment": "EXP-019",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "phases": {}}

    # A ------------------------------------------------------------------
    print("\n--- PHASE A — the in-air signature (10 readings)")
    print("    Hold the instrument in the air, aperture pointing DOWN over")
    print("    nothing (no desk, no paper within 10 cm).")
    input("    Press Return when it is in position: ")
    labs = stream(dev, 10)
    air = med(labs)
    out["phases"]["A"] = {"labs": labs, "median": air}
    print(f"    in-air median L*a*b*: {air}")
    save(out)

    # B ------------------------------------------------------------------
    print("\n--- PHASE B — settled paper white (5 button presses)")
    print("    Put the chart's paper flat on the desk. Place the instrument")
    print("    on PLAIN PAPER (the margin, no printed patch) and hold still.")
    labs = presses(dev, 5, "settled, on plain paper, holding still")
    white = med(labs)
    spread = max(de(l, white) for l in labs)
    out["phases"]["B"] = {"labs": labs, "median": white,
                          "spread_de": round(spread, 4)}
    print(f"    settled white median {white}, spread dE {spread:.3f}")
    if de(white, air) < 2 * AIR_DE:
        print("    ⚠ Paper white and the in-air signature are close — the")
        print("    lift-off detector is unreliable in this run. Recorded.")
        out["phases"]["B"]["air_conflict"] = True
    save(out)

    # C ------------------------------------------------------------------
    print("\n--- PHASE C — static stream, same spot (20 readings, control)")
    print("    Leave the instrument EXACTLY where it is. Do not touch it.")
    input("    Press Return to start: ")
    labs = stream(dev, 20)
    cmed = med(labs)
    cbias = de(cmed, white)
    out["phases"]["C"] = {"labs": labs, "median": cmed,
                          "bias_vs_pressed_de": round(cbias, 4)}
    print(f"    stream-vs-pressed bias on the same spot: dE {cbias:.3f}")
    beep = input("    While it was streaming, did it beep on every reading? "
                 "(yes/no/not sure): ").strip()
    out["phases"]["C"]["operator_beep_observation"] = beep
    save(out)

    # D ------------------------------------------------------------------
    print("\n--- PHASE D — slide on plain paper (THE decisive accuracy test)")
    print("    Lay a ruler on the paper margin as a guide. You will slide the")
    print("    instrument along PLAIN PAPER about 10 cm, then LIFT it clearly")
    print("    off into the air — the lift is what ends the phase.")
    print("    Slide steadily, about one centimetre per second (slower than")
    print("    feels natural).")
    input("    Press Return, then start sliding straight away: ")
    labs = stream(dev, CAP_D, air_lab=air, live_note=" — keep sliding")
    # drop trailing air samples; judge the middle 60% of the on-paper part
    on_paper = [l for l in labs if de(l, air) >= AIR_DE]
    k = len(on_paper)
    mid = on_paper[k // 5: k - k // 5] if k >= 10 else on_paper
    d_meds = [de(l, white) for l in mid]
    d_med = statistics.median(d_meds) if d_meds else float("nan")
    d_max = max(d_meds) if d_meds else float("nan")
    moved = statistics.median(de(x, y) for x, y in zip(mid, mid[1:])) if len(mid) > 3 else 0.0
    out["phases"]["D"] = {"labs": labs, "on_paper": k,
                          "mid_de_vs_settled_median": round(d_med, 4),
                          "mid_de_vs_settled_max": round(d_max, 4),
                          "step_de_median": round(moved, 4)}
    print(f"    {k} on-paper samples; mid-slide dE vs settled white: "
          f"median {d_med:.3f}, max {d_max:.3f}")
    # positive control: was there movement at all? paper is uniform, so the
    # test is honest only if the operator confirms the slide happened.
    slid = input("    Did you actually slide the full ~10 cm? (yes/no): ").strip()
    out["phases"]["D"]["operator_confirms_slide"] = slid
    if slid.lower().startswith("y"):
        rule = ("PASS — motion reading is valid" if d_med <= 0.5 else
                "MARGINAL — widened tolerances + owner sign-off needed"
                if d_med <= 1.5 else
                "FAIL — a moving reading is not a settled reading; DON'T BUILD")
    else:
        rule = "VOID — the slide did not happen; repeat the phase"
    print(f"    Rule from 18_strip_design.md §6: {rule}")
    out["phases"]["D"]["verdict"] = rule
    save(out)

    # E ------------------------------------------------------------------
    print("\n--- PHASE E — edge crossing (how big is the moving window?)")
    print("    Find the DARKEST patch near the chart's edge. You will slide")
    print("    from the white margin, straight across that dark patch, out")
    print("    the other side, and then LIFT off. Same slow, steady pace.")
    input("    Press Return, then start sliding straight away: ")
    labs = stream(dev, CAP_E, air_lab=air, live_note=" — keep sliding")
    onp = [l for l in labs if de(l, air) >= AIR_DE]
    # count samples that are neither white-ish nor dark-ish = mixtures
    if onp:
        dark = min(onp, key=lambda l: l[0])          # darkest sample seen
        span = de(white, dark)
        mixtures = sum(1 for l in onp
                       if de(l, white) > 0.25 * span and de(l, dark) > 0.25 * span)
        out["phases"]["E"] = {"labs": labs, "on_paper": len(onp),
                              "white_dark_span_de": round(span, 3),
                              "mixture_samples": mixtures}
        print(f"    white↔dark span dE {span:.1f}; samples that are neither "
              f"(the moving window's smear): {mixtures}")
        if span < 20:
            print("    ⚠ span < 20 dE — the patch was not dark enough for this "
                  "to mean much. Recorded as weak.")
            out["phases"]["E"]["weak"] = True
        save(out)

    # F ------------------------------------------------------------------
    print("\n--- PHASE F — a real row, pressed then swiped (optional, ~4 min)")
    print("    This is the full rehearsal. Skip it if you are out of time —")
    print("    phases A–E already answer the accuracy question.")
    if input("    Do phase F? (yes/no): ").strip().lower().startswith("y"):
        npat = 0
        while npat < 2:
            try:
                npat = int(input("    How many patches are in the row you "
                                 "will use? "))
            except ValueError:
                pass
        print("    First the ground truth: press the button once on EACH")
        print("    patch of that row, in order, left to right, settled.")
        gt = presses(dev, npat, "next patch of the row, in order")
        out["phases"]["F"] = {"pressed": gt, "swipe": []}
        save(out)
        print("\n    Now the swipe of the SAME row, in the SAME direction.")
        print("    Place the instrument on the white margin BEFORE the first")
        print("    patch, against your ruler, and press the button once.")
        try:
            m0 = dev.read_next_measurement(timeout=600.0)
        except Exception as exc:                                # noqa: BLE001
            print(f"    Arming press failed ({exc}); phase F abandoned.")
            save(out); print("\nDone."); return
        if m0.gate_flag:
            print("    ⚠ magnet gate flagged — cap on? Phase F abandoned.")
            save(out); print("\nDone."); return
        print("    Streaming — slide NOW, slow and steady (two or three beeps")
        print("    per patch), across the whole row, then LIFT off past the")
        print("    last patch.")
        labs = [lab_of(m0)] + stream(dev, CAP_F, air_lab=air,
                                     live_note=" — keep sliding")
        out["phases"]["F"]["swipe"] = labs
        save(out)
        print("\n    Captured. The alignment verdict comes from:")
        print("        python3 tools/probe_strip_feasibility.py --analyse")

    print("\nAll phases done. Everything is in captures/raw/" + OUT.name)


if __name__ == "__main__":
    main()
