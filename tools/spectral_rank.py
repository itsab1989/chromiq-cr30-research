#!/usr/bin/env python3
"""EXP-SPEC-001 analysis: are the 31 bands independent, or reconstructed?

    tools/spectral_rank.py captures/public/PRIORART-002-spectra.json

Two statistics, reported separately because they fail for different reasons.

**Rank.** If the 31 reported values were a LINEAR map of N physical sensor
channels, every spectrum would lie in an N-dimensional subspace and singular
values N+1.. would sit at float32 round-off -- a CLIFF. The number itself is
not the evidence; the cliff is. Sample diversity can only LOWER the observed
rank, never raise it, so a HIGH observed rank is strong evidence against a
low-channel reconstruction while a low one would be inconclusive. Only one
direction of this comparison is useful.

**Roughness.** Second-difference energy of each right singular vector, as a
fraction of its total energy. A basis built from ~20 nm FWHM interference
filters (an AS7341/AS7343) is band-limited and physically cannot exceed ~0.1.
Values of several units mean band-to-band alternating structure, i.e. per-band
independent variation. This statistic also bites a NONLINEAR reconstruction,
which the rank test alone cannot see.

Neither test can distinguish "independent" from "accurate". A band may vary
independently and still be wrong.
"""
import json, sys, pathlib
import numpy as np

FLOAT32_EPS = 1.1920929e-7


def analyse(X: np.ndarray) -> dict:
    A = X - X.mean(0)
    U, sv, Vt = np.linalg.svd(A, full_matrices=False)
    rel = sv / sv[0]
    d2 = np.diff(Vt, 2, axis=1)
    rough = (d2 ** 2).sum(1) / (Vt ** 2).sum(1)
    # largest drop between consecutive singular values, in decades
    with np.errstate(divide="ignore"):
        drops = np.log10(rel[:-1] / np.maximum(rel[1:], 1e-300))
    return {"n": int(X.shape[0]), "bands": int(X.shape[1]),
            "rel": rel, "rough": rough, "drops": drops,
            "rank_1e6": int((rel > 1e-6).sum()),
            "biggest_drop_decades": float(drops.max()),
            "biggest_drop_after": int(drops.argmax()) + 1}


def main(argv):
    d = json.loads(pathlib.Path(argv[1]).read_text())
    X = np.array([s["values"] for s in d["spectra"]], float)
    r = analyse(X)
    print(f"{r['n']} spectra x {r['bands']} bands   (provenance: {d.get('provenance','?')})")
    print(f"\n  #   sv/sv0     roughness")
    for i in range(r["bands"]):
        print(f" {i+1:3d}  {r['rel'][i]:.2e}   {r['rough'][i]:8.3f}")
    print(f"\nnumerical rank (sv/sv0 > 1e-6)      : {r['rank_1e6']} of {r['bands']}")
    print(f"largest gap between singular values : {r['biggest_drop_decades']:.2f} decades, "
          f"after component {r['biggest_drop_after']}")
    print(f"float32 relative epsilon            : {FLOAT32_EPS:.2e}")
    print("\nA linear reconstruction from N channels gives a cliff of >=5 decades")
    print("after component N. Roughness >1 cannot come from a ~20 nm FWHM basis.")


if __name__ == "__main__":
    main(sys.argv)
