"""Spectrum -> XYZ -> L*a*b*.

NOT device protocol. This is a small, self-validating colour utility used to
interpret what the CR30 returns, kept separate from `frame.py`/`session.py` so
the protocol layer stays free of colour science.

Observer is the **CIE 1931 2 degree** standard, deliberately: that is what the
vendor software pins (M0 / D50 / 1931 2 deg) and therefore what we must use to
compare against numbers the device itself displays. Argyll ships CIE *2012* 2
deg, which is a different observer and would introduce a difference of our own
making.

The observer and illuminant tables are hard-coded and are therefore CHECKED:
`validate_illuminants()` recomputes each white point's chromaticity from these
very tables and compares it against the published value. A mistyped coefficient
fails the check instead of quietly producing plausible-looking Lab values.
"""
from __future__ import annotations

WL = list(range(400, 701, 10))          # the CR30's 31 bands

# CIE standard illuminant relative SPDs, 400-700 nm at 10 nm.
D65 = [82.7549, 91.4860, 93.4318, 86.6823, 104.8650, 117.0080, 117.8120,
       114.8610, 115.9230, 108.8110, 109.3540, 107.8020, 104.7900, 107.6890,
       104.4050, 104.0460, 100.0000, 96.3342, 95.7880, 88.6856, 90.0062,
       89.5991, 87.6987, 83.2886, 83.6992, 80.0268, 80.2146, 82.2778, 78.2842,
       69.7213, 71.6091]
D50 = [49.3084, 56.5089, 60.0998, 57.8213, 74.8246, 87.2504, 90.6117, 91.3680,
       95.1082, 91.9526, 95.7237, 96.6137, 97.1292, 102.0980, 100.7550,
       102.3170, 100.0000, 97.7357, 98.9182, 93.5905, 97.1382, 99.9576,
       97.3918, 94.4276, 95.7787, 88.6489, 90.0062, 89.5991, 87.6987, 83.2886,
       83.6992]

# CIE 1931 2-degree observer at 10 nm, 400-700 (fallback if Argyll is absent).
_X = [0.01431, 0.04351, 0.13438, 0.28390, 0.34828, 0.33620, 0.29080, 0.19536,
      0.09564, 0.03201, 0.00490, 0.00930, 0.06327, 0.16550, 0.29040, 0.43345,
      0.59450, 0.76210, 0.91630, 1.02630, 1.06220, 1.00260, 0.85445, 0.64240,
      0.44790, 0.28350, 0.16490, 0.08740, 0.04677, 0.02270, 0.01136]
_Y = [0.00040, 0.00121, 0.00400, 0.01160, 0.02300, 0.03800, 0.06000, 0.09098,
      0.13902, 0.20802, 0.32300, 0.50300, 0.71000, 0.86200, 0.95400, 0.99495,
      0.99500, 0.95200, 0.87000, 0.75700, 0.63100, 0.50300, 0.38100, 0.26500,
      0.17500, 0.10700, 0.06100, 0.03200, 0.01700, 0.00821, 0.00410]
_Z = [0.06785, 0.20740, 0.64560, 1.38560, 1.74706, 1.77211, 1.66920, 1.28764,
      0.81295, 0.46518, 0.27200, 0.15820, 0.07825, 0.04216, 0.02030, 0.00875,
      0.00390, 0.00210, 0.00165, 0.00110, 0.00080, 0.00034, 0.00019, 0.00005,
      0.00002, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000]

XBAR, YBAR, ZBAR = _X, _Y, _Z
OBSERVER = "CIE 1931 2 degree standard observer"


def spectrum_to_xyz(refl, illum=D65):
    """refl: 31 values in PERCENT reflectance (as the CR30 returns them)."""
    if len(refl) != len(WL):
        raise ValueError(f"need {len(WL)} bands, got {len(refl)}")
    k = 100.0 / sum(s * y for s, y in zip(illum, YBAR))
    r = [v / 100.0 for v in refl]
    return tuple(k * sum(ri * s * c for ri, s, c in zip(r, illum, cmf))
                 for cmf in (XBAR, YBAR, ZBAR))


def white_point(illum=D65):
    k = 100.0 / sum(s * y for s, y in zip(illum, YBAR))
    return tuple(k * sum(s * c for s, c in zip(illum, cmf))
                 for cmf in (XBAR, YBAR, ZBAR))


def xyz_to_lab(xyz, illum=D65):
    wp = white_point(illum)
    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29
    fx, fy, fz = (f(c / w) for c, w in zip(xyz, wp))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def spectrum_to_lab(refl, illum=D65):
    return xyz_to_lab(spectrum_to_xyz(refl, illum), illum)


def validate_illuminants(tol=0.006):
    """Positive control on OUR OWN hard-coded numbers.

    Recomputes each illuminant's chromaticity and compares with the published
    value. A mistyped coefficient shows up here instead of quietly shifting
    every Lab number we report.
    """
    out = {}
    for name, sp, want in (("D65", D65, (0.31272, 0.32903)),
                           ("D50", D50, (0.34567, 0.35850))):
        X, Y, Z = white_point(sp)
        x, y = X / (X + Y + Z), Y / (X + Y + Z)
        err = max(abs(x - want[0]), abs(y - want[1]))
        out[name] = {"xy": (round(x, 5), round(y, 5)), "expected": want,
                     "max_error": round(err, 5), "ok": err < tol}
    return out


if __name__ == "__main__":
    print("observer:", OBSERVER)
    for k, v in validate_illuminants().items():
        print(f"  {k}: xy={v['xy']} expected={v['expected']} "
              f"err={v['max_error']} {'OK' if v['ok'] else '** FAIL **'}")
