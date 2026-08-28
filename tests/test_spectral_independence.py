"""EXP-SPEC-001: is a 31-band CR30 reading 31 measurements or a reconstruction?

Pins the falsification in MEASUREMENT.md so a later corpus cannot quietly
reverse it. These tests need no hardware.
"""
import json
import pathlib
import sys

import pytest

np = pytest.importorskip("numpy")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from spectral_rank import analyse  # noqa: E402

SPECTRA = json.loads(
    (ROOT / "captures" / "public" / "PRIORART-002-spectra.json").read_text())
X = np.array([s["values"] for s in SPECTRA["spectra"]], float)
R = analyse(X)

# AS7341 has 8 visible + clear + NIR + flicker; AS7343 adds five more.
CLAIMED_CHANNELS = (8, 11, 13, 14)


def test_corpus_is_big_enough_to_ask_the_question():
    assert X.shape[0] > X.shape[1], (
        "rank can never exceed min(samples, bands); with fewer spectra than "
        "bands the test is vacuous and would 'find' a deficiency that is ours")
    assert X.shape[1] == 31


def test_no_singular_value_cliff_at_any_claimed_channel_count():
    """A LINEAR map from N channels puts sv[N:] at float32 round-off."""
    # A linear reconstruction leaves sv[N:] at the float32 round-off of the
    # reported values, ~1.2e-7 relative. 100x that is a generous margin and
    # still three orders below the smallest value observed here.
    floor = 100 * 1.1920929e-7
    for n in CLAIMED_CHANNELS:
        assert R["rel"][n] > floor, (
            f"sv[{n}]/sv[0] = {R['rel'][n]:.2e} is within {floor:.1e} of "
            f"float32 round-off -- consistent with a linear reconstruction "
            f"from {n} channels")
    assert R["biggest_drop_decades"] < 2.0, (
        "a reconstruction shows a multi-decade gap somewhere; the largest gap "
        f"here is {R['biggest_drop_decades']:.2f} decades")


def test_high_order_components_are_far_above_float32_quantisation():
    """Otherwise the 'independence' counted here is just round-off noise.

    Values are ~1e2, so a float32 ulp is ~1e-5 absolute. Component 20's
    absolute singular value must clear that by a wide margin.
    """
    ulp = np.abs(X).max() * 1.1920929e-7
    sv20_abs = R["rel"][20] * np.linalg.svd(X - X.mean(0), compute_uv=False)[0]
    assert sv20_abs > 100 * ulp, f"sv[20]={sv20_abs:.2e} vs ulp={ulp:.2e}"


def test_leading_components_are_smooth_and_tail_components_are_not():
    """The signature that separates a filter basis from per-band variation.

    A ~20 nm FWHM interference-filter basis is band-limited: it cannot produce
    alternating band-to-band structure. This also bites a NONLINEAR
    reconstruction, which the rank test alone cannot see.
    """
    assert R["rough"][0] < 0.1, "the first component must look like a spectrum"
    assert R["rough"][2] < 0.2
    assert R["rough"][14] > 1.0, (
        "no smooth basis of ~11 filters can generate this component")


def test_reconstruction_from_eleven_channels_is_disproven_in_its_linear_form():
    assert R["rank_1e6"] > 14, (
        f"numerical rank {R['rank_1e6']} -- at or below the AS7343 channel "
        "count would leave the reconstruction hypothesis alive")


def test_the_disproof_is_scoped_and_not_a_claim_about_accuracy():
    """Documentation test: what this corpus is, and is not, evidence for."""
    assert "CORROBORATION only" in SPECTRA["confidence"]
    assert SPECTRA["provenance"].startswith("decoded from")
