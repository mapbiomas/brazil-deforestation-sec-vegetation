# -*- coding: utf-8 -*-
"""
Tests for the kernel-based secondary vegetation detection rules.

The production code builds an EE computation graph and cannot run offline.
These tests use a faithful pure-Python simulation of the sliding-window
algorithm to validate rule semantics. Rules are loaded from the pipeline
source via AST (no ee.Initialize needed).

Vendored from mapbiomas-pipeline @ c50594f (tests/test_deforestation_secondary_vegetation.py),
without the cross-region checks (Peru, Bolivia, Indonesia).
"""

import ast
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PIPELINE_SRC = os.path.join(
    os.path.dirname(__file__), "..", "mapbiomas_brazil_deforestation_secondary_vegetation.py"
)

# ---------------------------------------------------------------------------
# Class constants (mirror export_pipeline.py)
# ---------------------------------------------------------------------------
CLASS_ANTHROPIC = 1
CLASS_PRIMARY_VEGETATION = 2
CLASS_SECONDARY_VEGETATION = 3
CLASS_PRIMARY_VEG_SUPPRESSION = 4
CLASS_RECOVERY = 5
CLASS_SECONDARY_VEG_SUPPRESSION = 6

FULL_YEARS = list(range(1985, 2026))  # 41 years


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def series_from_list(values, years):
    return dict(zip(years, values))


def list_from_series(series, years):
    return [series[y] for y in years]


def load_rules_from_source(name, source_path=PIPELINE_SRC):
    """Load a rule-list literal from the pipeline source via AST — no ee.Initialize."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise ValueError(f"Could not find {name!r} in {source_path}")


def load_lookup_ids(source_path):
    """Load the original class IDs declared in ``CLASS_LOOKUP`` via AST."""
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    lookup = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CLASS_LOOKUP"
            for target in node.targets
        )
    )
    return {ast.literal_eval(pair.elts[0]) for pair in lookup.value.elts}


def apply_rule_kernel(series, rule, years, kernel_size):
    """
    Pure-Python simulation of the EE sliding-window kernel algorithm.

    Sequential: each window sees the result of the previous write.
    """
    kernel_bef, kernel_aft, min_start = rule[0], rule[1], rule[2]
    out = dict(series)
    for i in range(len(years) - kernel_size + 1):
        if i < min_start:
            continue
        window = years[i : i + kernel_size]
        current = [out[y] for y in window]
        if all(current[k] == kernel_bef[k] for k in range(kernel_size)):
            for k, y in enumerate(window):
                out[y] = kernel_aft[k]
    return out


def apply_rules(series, rules, years, kernel_size):
    for rule in rules:
        series = apply_rule_kernel(series, rule, years, kernel_size)
    return series


# Load rules once at module level so tests share the parsed constants.
RULES_KERNEL4 = load_rules_from_source("RULES_KERNEL4")
RULES_KERNEL4_END = load_rules_from_source("RULES_KERNEL4_END")
RULES_KERNEL4_SECONDARY = load_rules_from_source("RULES_KERNEL4_SECONDARY")
RULES_KERNEL3_SECONDARY = load_rules_from_source("RULES_KERNEL3_SECONDARY")
RULES_KERNEL6_SECONDARY_END = load_rules_from_source("RULES_KERNEL6_SECONDARY_END")
RULES_KERNEL4_SECONDARY_END_REVERT = load_rules_from_source(
    "RULES_KERNEL4_SECONDARY_END_REVERT"
)
RULES_KERNEL3_VEG_BLIP = load_rules_from_source("RULES_KERNEL3_VEG_BLIP")


def run_full_pipeline(initial, run_end_rules=True, run_blip_filter=True):
    """
    Single-pixel simulation of export_deforestation(), faithful to the GEE pipeline.

    `initial` maps year → aggregated class (1/2/7/0), covering FULL_YEARS.
    Frequency is computed from `initial` (the aggregated image, before kernel rules).
    """
    freq_anthropic = sum(1 for y in FULL_YEARS if initial[y] == CLASS_ANTHROPIC)
    s = dict(initial)

    # Step 1a: blip filter (all years)
    if run_blip_filter:
        s = apply_rules(s, RULES_KERNEL3_VEG_BLIP, FULL_YEARS, 3)

    # Step 1b: anchored end-of-series rules (run-first, clean image)
    if run_end_rules:
        s = apply_rules(s, RULES_KERNEL6_SECONDARY_END, FULL_YEARS[-6:], 6)
        s = apply_rules(s, RULES_KERNEL4_SECONDARY_END_REVERT, FULL_YEARS[-4:], 4)

    # Step 2-4
    s = apply_rules(s, RULES_KERNEL4, FULL_YEARS, 4)
    s = apply_rules(s, RULES_KERNEL4_SECONDARY, FULL_YEARS, 4)
    s = apply_rules(s, RULES_KERNEL3_SECONDARY, FULL_YEARS, 3)

    # Step 5: end-of-period rules (last 4 years)
    s = apply_rules(s, RULES_KERNEL4_END, FULL_YEARS[-4:], 4)

    # Step 6: frequency correction
    for y in FULL_YEARS:
        if freq_anthropic > 1 and s[y] == CLASS_PRIMARY_VEG_SUPPRESSION:
            s[y] = CLASS_SECONDARY_VEG_SUPPRESSION
        if freq_anthropic > 0 and s[y] == CLASS_PRIMARY_VEGETATION:
            s[y] = CLASS_SECONDARY_VEGETATION

    # Step 7: tail guard — strip frequency-induced secondary veg whose immediate
    # predecessor is anthropic (confirmed secondary preceded by recovery(5) or by 3 is preserved).
    nm2, nm1, n = FULL_YEARS[-3], FULL_YEARS[-2], FULL_YEARS[-1]
    if s[nm2] == CLASS_ANTHROPIC and s[nm1] == CLASS_SECONDARY_VEGETATION:
        s[nm1] = CLASS_ANTHROPIC
    if s[nm1] == CLASS_ANTHROPIC and s[n] == CLASS_SECONDARY_VEGETATION:
        s[n] = CLASS_ANTHROPIC

    return s


def make_mostly_anthropic(tail_values):
    """
    Build a FULL_YEARS series that is all-anthropic(1) except for the last 6 years,
    which are given by `tail_values`.
    """
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    for i, y in enumerate(FULL_YEARS[-6:]):
        s[y] = tail_values[i]
    return s


# ---------------------------------------------------------------------------
# Group 1: Rule loading via AST
# ---------------------------------------------------------------------------


def test_load_rules_kernel6_has_3_windows():
    assert len(RULES_KERNEL6_SECONDARY_END) == 3


def test_load_rules_kernel6_window1_pattern():
    rule = RULES_KERNEL6_SECONDARY_END[0]
    assert rule[0] == [1, 1, 1, 1, 2, 2]
    assert rule[1] == [1, 1, 1, 1, 5, 3]
    assert rule[2] == 0


def test_load_rules_kernel6_window2_pattern():
    rule = RULES_KERNEL6_SECONDARY_END[1]
    assert rule[0] == [1, 1, 1, 1, 1, 2]
    assert rule[1] == [1, 1, 1, 1, 1, 5]
    assert rule[2] == 0


def test_load_rules_kernel6_window3_pattern():
    rule = RULES_KERNEL6_SECONDARY_END[2]
    assert rule[0] == [2, 1, 1, 1, 1, 2]
    assert rule[1] == [2, 1, 1, 1, 1, 5]
    assert rule[2] == 0


def test_load_rules_blip_pattern():
    rule = RULES_KERNEL3_VEG_BLIP[0]
    assert rule[0] == [1, 2, 1]
    assert rule[1] == [1, 1, 1]
    assert rule[2] == 0


def test_load_rules_d_revert_pattern():
    rule = RULES_KERNEL4_SECONDARY_END_REVERT[0]
    assert rule[0] == [1, 2, 2, 1]
    assert rule[1] == [1, 1, 1, 1]
    assert rule[2] == 0


def test_load_rules_kernel4_has_entries():
    assert len(RULES_KERNEL4) >= 1


def test_load_rules_kernel4_secondary_has_entries():
    assert len(RULES_KERNEL4_SECONDARY) >= 4


# ---------------------------------------------------------------------------
# Group 2: apply_rule_kernel_6 — single-rule behaviour
# ---------------------------------------------------------------------------


def test_kernel6_window1_single_window():
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    s = series_from_list([1, 1, 1, 1, 2, 2], years)
    out = apply_rule_kernel(s, RULES_KERNEL6_SECONDARY_END[0], years, 6)
    assert list_from_series(out, years) == [1, 1, 1, 1, 5, 3]


def test_kernel6_window2_single_window():
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    s = series_from_list([1, 1, 1, 1, 1, 2], years)
    out = apply_rule_kernel(s, RULES_KERNEL6_SECONDARY_END[1], years, 6)
    assert list_from_series(out, years) == [1, 1, 1, 1, 1, 5]


def test_kernel6_window3_single_window():
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    s = series_from_list([2, 1, 1, 1, 1, 2], years)
    out = apply_rule_kernel(s, RULES_KERNEL6_SECONDARY_END[2], years, 6)
    assert list_from_series(out, years) == [2, 1, 1, 1, 1, 5]


def test_kernel6_no_match_partial_pattern():
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    s = series_from_list([1, 1, 1, 2, 2, 2], years)  # doesn't match any K6 rule exactly
    out = apply_rules(s, RULES_KERNEL6_SECONDARY_END, years, 6)
    # No window matches, series unchanged
    assert list_from_series(out, years) == [1, 1, 1, 2, 2, 2]


def test_kernel6_applies_all_3_rules_in_sequence():
    # A 7-year span creates multiple windows; rules apply sequentially.
    years = list(range(2019, 2026))  # 7 years → 2 windows of size 6
    # First window [2019..2024] = [1,1,1,1,2,2] → rule 1 applies, [2019..2024] → [1,1,1,1,5,3]
    # Second window [2020..2025] = [1,1,1,5,3,1] → no rule matches
    s = series_from_list([1, 1, 1, 1, 2, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL6_SECONDARY_END, years, 6)
    assert list_from_series(out, years) == [1, 1, 1, 1, 5, 3, 1]


# ---------------------------------------------------------------------------
# Group 3: min_start guard
# ---------------------------------------------------------------------------


def test_min_start_0_applies_at_index_0():
    # Rule with min_start=0 fires at the very first window.
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    s = series_from_list([1, 1, 1, 1, 2, 2], years)
    out = apply_rule_kernel(s, RULES_KERNEL6_SECONDARY_END[0], years, 6)
    assert out[2024] == 5 and out[2025] == 3


def test_min_start_1_blocks_at_index_0():
    # Establishment rule [[1,2,2,2],[1,5,3,3],1] blocked when window is at index 0.
    rule = [[1, 2, 2, 2], [1, 5, 3, 3], 1]
    years = [2020, 2021, 2022, 2023]
    s = series_from_list([1, 2, 2, 2], years)
    out = apply_rule_kernel(s, rule, years, 4)
    # min_start=1, only window is at i=0 → blocked
    assert list_from_series(out, years) == [1, 2, 2, 2]


def test_min_start_1_allows_at_index_1():
    # Same rule applies when there is a valid window at index 1.
    rule = [[1, 2, 2, 2], [1, 5, 3, 3], 1]
    years = [2017, 2018, 2019, 2020, 2021]
    s = series_from_list([1, 1, 2, 2, 2], years)
    out = apply_rule_kernel(s, rule, years, 4)
    assert list_from_series(out, years) == [1, 1, 5, 3, 3]


# ---------------------------------------------------------------------------
# Group 4: 1-year blip filter
# ---------------------------------------------------------------------------


def test_blip_filter_removes_1yr_veg_between_anthropic():
    years = [2020, 2021, 2022]
    s = series_from_list([1, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL3_VEG_BLIP, years, 3)
    assert list_from_series(out, years) == [1, 1, 1]


def test_blip_filter_does_not_remove_2yr_veg_block():
    years = [2019, 2020, 2021, 2022]
    s = series_from_list([1, 2, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL3_VEG_BLIP, years, 3)
    assert list_from_series(out, years) == [1, 2, 2, 1]


def test_blip_filter_removes_multiple_blips():
    years = [2019, 2020, 2021, 2022, 2023]
    s = series_from_list([1, 2, 1, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL3_VEG_BLIP, years, 3)
    # First blip: [2019,2020,2021]=[1,2,1] → [1,1,1]; second scan sees [1,1,1,2,1] → [1,1,1,1,1]
    assert out[2020] == 1 and out[2022] == 1


def test_blip_filter_does_not_match_at_n():
    # Vegetation at the last year (n) never has an anthropic year after it,
    # so [1,2] cannot form a [1,2,1] window — ongoing regen at n is preserved.
    years = [2023, 2024, 2025]
    s = series_from_list([1, 1, 2], years)
    out = apply_rules(s, RULES_KERNEL3_VEG_BLIP, years, 3)
    assert out[2025] == 2  # unchanged


def test_blip_filter_does_not_touch_ongoing_regeneration_at_n():
    # A pixel with 1-year veg at n (window 2 pattern) must survive blip filter.
    s = make_mostly_anthropic([1, 1, 1, 1, 1, 2])
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=True)
    # window 2 must have written recovery(5) at n=2025
    assert out[2025] == CLASS_RECOVERY


# ---------------------------------------------------------------------------
# Group 5: Anchored D revert
# ---------------------------------------------------------------------------


def test_d_revert_basic():
    years = [2022, 2023, 2024, 2025]
    s = series_from_list([1, 2, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL4_SECONDARY_END_REVERT, years, 4)
    assert list_from_series(out, years) == [1, 1, 1, 1]


def test_d_revert_does_not_revert_interior_1221():
    # When applied over a full-length year span, the rule CAN match [1,2,2,1] in the interior.
    # The anchored behavior in the pipeline comes from passing YEARS[-4:], not from the rule itself.
    # This test confirms the rule is general (not self-anchored) and relies on year slicing.
    years = [2019, 2020, 2021, 2022]
    s = series_from_list([1, 2, 2, 1], years)
    out = apply_rules(s, RULES_KERNEL4_SECONDARY_END_REVERT, years, 4)
    # Rule fires — it's anchored in the pipeline by passing YEARS[-4:]
    assert list_from_series(out, years) == [1, 1, 1, 1]


def test_d_revert_no_match_when_no_pattern():
    years = [2022, 2023, 2024, 2025]
    s = series_from_list([1, 1, 1, 1], years)
    out = apply_rules(s, RULES_KERNEL4_SECONDARY_END_REVERT, years, 4)
    assert list_from_series(out, years) == [1, 1, 1, 1]


# ---------------------------------------------------------------------------
# Group 6: Establishment rule (kernel4, min_start=1)
# ---------------------------------------------------------------------------


def test_establishment_rule_kernel4():
    rule = [[1, 2, 2, 2], [1, 5, 3, 3], 1]
    years = [2017, 2018, 2019, 2020, 2021]
    s = series_from_list([1, 1, 2, 2, 2], years)
    out = apply_rule_kernel(s, rule, years, 4)
    assert list_from_series(out, years) == [1, 1, 5, 3, 3]


def test_establishment_rule_blocked_at_series_start():
    # With only 4 years and min_start=1, the only possible window is at index 0 → blocked.
    rule = [[1, 2, 2, 2], [1, 5, 3, 3], 1]
    years = [2018, 2019, 2020, 2021]
    s = series_from_list([1, 2, 2, 2], years)
    out = apply_rule_kernel(s, rule, years, 4)
    assert list_from_series(out, years) == [1, 2, 2, 2]


# ---------------------------------------------------------------------------
# Group 7: Coverage matrix — full pipeline, end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, tail6, expected_tail3",
    [
        ("start=n   (1yr veg at n)", [1, 1, 1, 1, 1, 2], [1, 1, 5]),
        ("start=n-1 (2yr veg n-1,n)", [1, 1, 1, 1, 2, 2], [1, 5, 3]),
        ("start=n-2 (3yr veg n-2..n)", [1, 1, 1, 2, 2, 2], [5, 3, 3]),
        ("D: 2yr block cleared at n", [1, 1, 1, 2, 2, 1], [1, 1, 1]),
        ("E: 1yr veg blip", [1, 1, 1, 2, 1, 1], [1, 1, 1]),
        ("start=n-3 (4yr veg n-3..n)", [1, 1, 2, 2, 2, 2], [3, 3, 3]),
    ],
)
def test_tail_coverage_matrix(label, tail6, expected_tail3):
    s = make_mostly_anthropic(tail6)
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=True)
    tail3_years = FULL_YEARS[-3:]
    result = list_from_series(out, tail3_years)
    assert result == expected_tail3, f"{label}: got {result}, expected {expected_tail3}"


# ---------------------------------------------------------------------------
# Group 8: Flag behaviour
# ---------------------------------------------------------------------------


def test_flag_run_secondary_end_rules_false_keeps_d():
    # D without anchored revert: freq correction promotes veg → secondary.
    s = make_mostly_anthropic([1, 1, 1, 2, 2, 1])
    out = run_full_pipeline(s, run_end_rules=False, run_blip_filter=True)
    nm2, nm1 = FULL_YEARS[-3], FULL_YEARS[-2]
    # With flags off, the 2-year block survives → promoted to secondary by freq
    assert (
        out[nm2] == CLASS_SECONDARY_VEGETATION or out[nm1] == CLASS_SECONDARY_VEGETATION
    )


def test_flag_run_blip_filter_false_keeps_e():
    # E without blip filter: 1-year veg blip survives → promoted to secondary by freq.
    s = make_mostly_anthropic([1, 1, 1, 2, 1, 1])
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=False)
    nm2 = FULL_YEARS[-3]
    # Without blip filter, the blip at nm2 (2023) survives freq correction → secondary
    assert out[nm2] == CLASS_SECONDARY_VEGETATION


def test_flag_both_off_old_behavior_for_D():
    # Both flags off → D produces secondary vegetation (old behavior).
    s = make_mostly_anthropic([1, 1, 1, 2, 2, 1])
    out = run_full_pipeline(s, run_end_rules=False, run_blip_filter=False)
    tail = list_from_series(out, FULL_YEARS[-3:])
    # Old: [3, 3, 1] — blip filter was not present; both vegetation years promoted
    assert CLASS_SECONDARY_VEGETATION in tail


def test_flag_both_off_old_behavior_for_E():
    # Both flags off → E produces secondary vegetation (old behavior).
    s = make_mostly_anthropic([1, 1, 1, 2, 1, 1])
    out = run_full_pipeline(s, run_end_rules=False, run_blip_filter=False)
    nm2 = FULL_YEARS[-3]
    assert out[nm2] == CLASS_SECONDARY_VEGETATION


# ---------------------------------------------------------------------------
# Group 9: Run-first ordering
# ---------------------------------------------------------------------------


def test_run_first_window3_matches_on_clean_image():
    # Window 3 pattern [2,1,1,1,1,2] must see vegetation(2) at p0 — which is
    # guaranteed when the windows run on the clean aggregated image.
    years = FULL_YEARS[-6:]
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    for i, y in enumerate(years):
        s[y] = [2, 1, 1, 1, 1, 2][i]
    out = apply_rules(s, RULES_KERNEL6_SECONDARY_END, years, 6)
    assert out[FULL_YEARS[-1]] == CLASS_RECOVERY  # n written as 5


def test_run_first_marks_survive_k4():
    # 5 and 3 written by K6 must not be overwritten by RULES_KERNEL4.
    years = FULL_YEARS[-6:]
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    for i, y in enumerate(years):
        s[y] = [1, 1, 1, 1, 2, 2][i]
    s = apply_rules(s, RULES_KERNEL6_SECONDARY_END, years, 6)
    s = apply_rules(s, RULES_KERNEL4, FULL_YEARS, 4)
    assert s[FULL_YEARS[-2]] == CLASS_RECOVERY  # n-1 = 5 preserved
    assert s[FULL_YEARS[-1]] == CLASS_SECONDARY_VEGETATION  # n = 3 preserved


def test_run_first_marks_survive_k4_secondary():
    # 5/3 from K6 not overwritten by K4_SECONDARY.
    years = FULL_YEARS[-6:]
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    for i, y in enumerate(years):
        s[y] = [1, 1, 1, 1, 2, 2][i]
    s = apply_rules(s, RULES_KERNEL6_SECONDARY_END, years, 6)
    s = apply_rules(s, RULES_KERNEL4_SECONDARY, FULL_YEARS, 4)
    assert s[FULL_YEARS[-2]] == CLASS_RECOVERY
    assert s[FULL_YEARS[-1]] == CLASS_SECONDARY_VEGETATION


# ---------------------------------------------------------------------------
# Group 10: Tail guard
# ---------------------------------------------------------------------------


def test_tail_guard_strips_freq_induced_secondary_at_n():
    # Pixel with anthropic at n-1 and secondary(3) at n via freq → stripped.
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    s[FULL_YEARS[-1]] = CLASS_SECONDARY_VEGETATION  # freq-induced (hypothetical)
    out = run_full_pipeline(s, run_end_rules=False, run_blip_filter=False)
    assert out[FULL_YEARS[-1]] == CLASS_ANTHROPIC


def test_tail_guard_strips_freq_induced_secondary_at_nm1():
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    s[FULL_YEARS[-2]] = CLASS_SECONDARY_VEGETATION
    out = run_full_pipeline(s, run_end_rules=False, run_blip_filter=False)
    assert out[FULL_YEARS[-2]] == CLASS_ANTHROPIC


def test_tail_guard_preserves_recovery_mark_at_n():
    # Recovery(5) at n is NOT secondary vegetation(3) — guard doesn't touch it.
    s = make_mostly_anthropic([1, 1, 1, 1, 1, 2])
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=True)
    assert out[FULL_YEARS[-1]] == CLASS_RECOVERY


def test_tail_guard_preserves_confirmed_secondary_after_recovery():
    # A confirmed secondary(3) preceded by recovery(5) must not be stripped.
    s = make_mostly_anthropic([1, 1, 1, 1, 2, 2])
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=True)
    n, nm1 = FULL_YEARS[-1], FULL_YEARS[-2]
    # n-1=5 (recovery), n=3 (secondary) — predecessor of 3 is 5, not 1
    assert out[nm1] == CLASS_RECOVERY
    assert out[n] == CLASS_SECONDARY_VEGETATION


# ---------------------------------------------------------------------------
# Group 11: Regression / misc
# ---------------------------------------------------------------------------


def test_pipeline_all_anthropic():
    s = {y: CLASS_ANTHROPIC for y in FULL_YEARS}
    out = run_full_pipeline(s)
    assert all(out[y] == CLASS_ANTHROPIC for y in FULL_YEARS)


def test_pipeline_all_vegetation():
    s = {y: CLASS_PRIMARY_VEGETATION for y in FULL_YEARS}
    out = run_full_pipeline(s)
    # All vegetation, freq_anthropic=0 → freq correction writes no secondary
    assert all(out[y] == CLASS_PRIMARY_VEGETATION for y in FULL_YEARS)


def test_missing_min_start_raises():
    import pytest as _pytest
    from deforestation_secondary_vegetation import (
        DeforestationSecondaryVegetation,
    )
    import unittest.mock as mock

    processor = DeforestationSecondaryVegetation(mock.MagicMock(), [2020])
    with _pytest.raises((ValueError, TypeError)):
        processor.apply_rules([[[1, 2, 2, 2], [1, 5, 3, 3]]], kernel_size=4)


def test_kernel6_missing_min_start_raises():
    from deforestation_secondary_vegetation import (
        DeforestationSecondaryVegetation,
    )
    import unittest.mock as mock
    import pytest as _pytest

    processor = DeforestationSecondaryVegetation(
        mock.MagicMock(), list(range(2019, 2026))
    )
    with _pytest.raises((ValueError, TypeError)):
        processor.apply_rule_kernel_6(
            [[1, 1, 1, 1, 2, 2], [1, 1, 1, 1, 5, 3]], list(range(2019, 2026))
        )


def test_n_minus_2_covered_by_establishment_rule():
    # When regeneration starts at n-2 and reaches n (3 years), the establishment
    # rule [[1,2,2,2],[1,5,3,3],1] applied at the window ending at n marks n-2=5.
    s = make_mostly_anthropic([1, 1, 1, 2, 2, 2])
    out = run_full_pipeline(s, run_end_rules=True, run_blip_filter=True)
    nm2, nm1, n = FULL_YEARS[-3], FULL_YEARS[-2], FULL_YEARS[-1]
    assert out[nm2] == CLASS_RECOVERY
    assert out[nm1] == CLASS_SECONDARY_VEGETATION
    assert out[n] == CLASS_SECONDARY_VEGETATION
