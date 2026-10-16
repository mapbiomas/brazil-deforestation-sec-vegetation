# Deforestation & Secondary Vegetation — Temporal Rules

**MapBiomas Brazil · Collection 11 · 1985–2025 series (41 years)**

This document describes the temporal rules applied to detect deforestation and secondary
vegetation dynamics. The rules are implemented in
[`deforestation_secondary_vegetation.py`](../deforestation_secondary_vegetation.py)
and invoked by `export_deforestation()` in
[`mapbiomas_brazil_deforestation_secondary_vegetation.py`](../mapbiomas_brazil_deforestation_secondary_vegetation.py).

The input is the Collection 11 integration image (`INTEGRATION/classification-ft`, filtered by the
version in `VERSION_INPUT_INTEGRATION`), with one `classification_{year}` band per year. The output
has the same bands, filled with the 8 simplified codes from section 1.

> **Revision 2** (2026-08-11). Revision 1 described Collection 10.1, a series up to 2024 and four
> rule groups — see [§11](#11-history-of-resolved-problems) for what changed and why.

---

## Table of contents

- [1. Class legend](#1-class-legend)
- [2. Rule format](#2-rule-format)
- [3. Kernel sizes and anchored windows](#3-kernel-sizes-and-anchored-windows)
- [4. The `min_start` parameter](#4-the-min_start-parameter)
- [5. Processing order](#5-processing-order)
- [6. Rule groups](#6-rule-groups)
- [7. Post-processing](#7-post-processing)
- [8. End-of-series behavior](#8-end-of-series-behavior)
- [9. Validation and tests](#9-validation-and-tests)
- [10. What comes after the temporal rules](#10-what-comes-after-the-temporal-rules)
- [11. History of resolved problems](#11-history-of-resolved-problems)
- [12. Quick reference](#12-quick-reference--all-rules-in-execution-order)

---

## 1. Class legend

Simplified codes used internally by the deforestation pipeline, after aggregation from the original
MapBiomas classification via `aggregate_classes()`.

| ID | Name | Color | Description |
|----|------|-----|-----------|
| 0 | No Data | `#FFFFFF` | Unobserved or masked pixels |
| 1 | Anthropic | `#FAF5D1` | Any anthropic use (pasture, agriculture, urban, mining…) |
| 2 | Primary Veg. | `#C7E4CB` | Native vegetation with no prior anthropic history |
| 3 | Secondary Veg. | `#5BCF20` | Regeneration over a previously anthropic area |
| 4 | Primary Suppression | `#EA1C1C` | Confirmed primary vegetation suppression event |
| 5 | Recovery to Secondary | `#B4F792` | First year of regeneration after anthropic use |
| 6 | Secondary Suppression | `#FE9934` | Suppression event over secondary vegetation |
| 7 | Other Transitions | `#303149` | Water, rocky outcrop, beach, filtered noise |

### 1.1 Aggregation of the original classes

The mapping lives in `CLASS_LOOKUP` in the pipeline and is applied band by band by
`aggregate_classes()`, which uses `remap(..., default=0)` — **any class missing from the lookup
becomes No Data (0)**.

| Aggregated class | Original MapBiomas IDs |
|---|---|
| **1 — Anthropic** | 9 (forest plantation), 14 (farming), 15 (pasture), 18/19/20/39/40/41/62 (temporary crop), 36/35/46/47/48 (perennial crop), 72, 21 (mosaic of uses), 22 (non-vegetated area), 24 (urban), 25 (other non-vegetated areas), 30 (mining), 31 (aquaculture), 75 (photovoltaic power plant), 91 (wind power plant) |
| **2 — Primary Veg.** | 1, 3 (forest formation), 4 (savanna formation), 5 (mangrove), 6 (floodable forest), 7 (floodable savanna), 10, 11 (wetland), 12 (grassland), 13 (herbaceous-shrub mosaic), 49 (wooded sandbank vegetation), 50 (herbaceous sandbank vegetation), 66, 70, 84 (salt marsh) |
| **7 — Other Transitions** | 23 (beach/dune), 26 (water), 29 (rocky outcrop), 32 (hypersaline tidal flat), 33 (river/lake/ocean), 34, 61, 68, 69 |
| **0 — No Data** | 0, 27 (not observed) |

⚠️ **Classes 75 (photovoltaic) and 91 (wind) entered in Collection 11** and were added to the
lookup as anthropic. Every new legend class must be added to `CLASS_LOOKUP` explicitly: without
that, the `remap`'s `default=0` turns it into No Data and the pixel disappears from the
deforestation series without any warning.

> **The lookup consumes the internal data, not the public data.** In C11 the public product remaps
> 13 → 77 (`PUBLIC_COVERAGE_REMAP`), but the internal assets — which feed these rules — keep the 13.
> A pipeline rebuilt from the **public** data would need to map 77 explicitly. The lookup also
> carries IDs that do not exist in Brazil's legend (34, 61, 66, 68, 69, 70, 72), inherited from the
> lookup shared with other regions; they are harmless.

---

## 2. Rule format

Each rule is a Python list with three elements:

```python
[kernel_bef, kernel_aft, min_start]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `kernel_bef` | `list[int]` | yes | Sequence of classes that must match the input (before state) |
| `kernel_aft` | `list[int]` | yes | Sequence of classes to write when it matches (after state) |
| `min_start` | `int` | **yes** | Minimum index in the year list from which the rule can be applied |

> **Enforcement:** `min_start` is required. `apply_rule_kernel_3`, `_4` and `_6` raise `ValueError`
> if the third element is missing, preventing a silent error in an unreviewed rule.

```python
[[1, 2, 2, 2], [1, 5, 3, 3], 1]
#  ↑ before     ↑ after       ↑ min_start=1 → the first valid window starts in 1986
```

For a 4-year kernel, the position indices map to years as follows:

```
index:   i=0   i=1   i=2   i=3
         t1    t2    t3    t4
         1985  1986  1987  1988   ← window starting at index 0
         1986  1987  1988  1989   ← window starting at index 1 (min_start=1)
```

---

## 3. Kernel sizes and anchored windows

`apply_rules(rules, kernel_size, years_override=None)` accepts `kernel_size` **3, 4 or 6**,
dispatching to `apply_rule_kernel_3/4/6`. Any other value raises `ValueError`. Each method is a
moving window over `ee.List.sequence(0, len(years) - kernel_size)`.

| Mode | How it is called | No. of windows | Used by |
|---|---|---|---|
| **Sliding** | without `years_override` (uses `YEARS`) | `len(YEARS) - k + 1` | blip, KERNEL4, KERNEL4_SECONDARY, KERNEL3_SECONDARY |
| **Anchored** | `years_override` with exactly `k` elements | 1 (index 0) | KERNEL6_SECONDARY_END, KERNEL4_SECONDARY_END_REVERT |
| **Restricted** | `years_override` with more than `k` elements | `len(override) - k + 1` | KERNEL4_END (4 years over 4 → 1 window) |

⚠️ **`min_start` is an index into the list actually used**, not into `YEARS`. With
`years_override=YEARS[-6:]`, `min_start=0` means "from 2020 onward" — not "from 1985 onward". That
is why the anchored rules of Step 1b can safely use `min_start=0` even though they write classes 3
and 5.

### 3.1 Sequential application — why order matters

Each rule runs as an `iterate` over the windows, and each window sees the result written by the
previous window. Likewise, each group operates on the image already modified by the previous group.

- One rule can **enable** another: `RULES_KERNEL3_SECONDARY` depends on class 3 in `t1`, which only
  exists if `RULES_KERNEL4_SECONDARY` has already written it.
- One rule can **disable** another: that is exactly why Steps 1a/1b run before everything else
  (see [§5](#5-processing-order)).

### Period constants

| Constant | Value | Used in |
|---|---|---|
| `YEARS` | 1985–2025 (41 years) | all sliding rules |
| `YEARS_END` | `YEARS[-4:]` → 2022–2025 | `RULES_KERNEL4_END` (Step 5) |
| `YEARS_SECONDARY_END` | `YEARS[-6:]` → 2020–2025 | `RULES_KERNEL6_SECONDARY_END` (Step 1b) |
| `YEARS_SECONDARY_END_REVERT` | `YEARS[-4:]` → 2022–2025 | `RULES_KERNEL4_SECONDARY_END_REVERT` (Step 1b) |
| `LAST_YEAR` | `YEARS[-1]` → 2025 | spatial filter and post-processing |

In the rest of this document, **n** denotes the last year of the series (2025), **n-1** the
second-to-last, and so on. The rules are written in terms of `n` because the tail shifts with each
collection — nothing in the code depends on the year 2025 literally.

---

## 4. The `min_start` parameter

### Problem

Some rules assign class `3` (secondary vegetation) or `5` (recovery) at position `t2`. When the
sliding window starts at index `i=0`, `t2` corresponds to **1986** — the second year of the series.
This is incorrect, because there is no historical context before 1985 to confirm that there was a
prior anthropic or secondary state.

### Decision criterion

| Condition | `min_start` | Rationale |
|---|---|---|
| `kernel_aft[1]` assigns class `3` or `5` (new assignment) | `1` | `t1` must represent a confirmed prior state; 1985 has no history |
| `kernel_aft[1]` is already class `3` (no new assignment) | `0` | `t2` already had class `3` in the input; no risk of a false assignment |
| `kernel_aft` assigns neither class `3` nor `5` anywhere | `0` | no secondary vegetation class is written |
| Rules with `years_override` at the tail | `0` | the window never reaches 1985/1986 — `years_override` already restricts the scope |

> `min_start=0` is always declared **explicitly**. It is not an omission: it is the documented
> confirmation that the rule was evaluated and deemed safe from the first year of the series.

### Implementation

The three methods apply `min_start` in the same way: they raise `ValueError` if the third element
is missing and add `.And(i.gte(min_start))` to the pixel mask.

```python
def apply_rule_kernel_6(self, rule, years):
    if len(rule) < 3:
        raise ValueError(
            f"Rule is missing min_start (3rd element): {rule}. "
            "Set min_start=0 explicitly if the rule is safe from the first year of the series."
        )
    kernel_bef, kernel_aft = rule[0], rule[1]
    min_start = ee.Number(rule[2])

    def apply_kernel_6(i, image):
        ...
        mask = (
            t1.eq(kernel_bef[0])
            .And(t2.eq(kernel_bef[1]))
            ...
            .And(t6.eq(kernel_bef[5]))
            .And(i.gte(min_start))   # blocks windows before the minimum index
        )
```

The `.And(i.gte(min_start))` condition is a scalar EE expression broadcast to all pixels, with no
relevant computational cost.

---

## 5. Processing order

The rules are applied **sequentially** in `export_deforestation()`.

```python
# Step 1  — aggregates the original MapBiomas codes into the simplified codes (0–7)
aggregated = DeforestationSecondaryVegetation.aggregate_classes(integration, LOOKUP_IN, LOOKUP_OUT)
processor  = DeforestationSecondaryVegetation(aggregated, YEARS)

# Step 1a — removes 1-year vegetation blips (whole series)              [RUN_VEG_BLIP_FILTER]
processor.apply_rules(RULES_KERNEL3_VEG_BLIP, kernel_size=3)

# Step 1b — anchored end-of-series rules (6- and 4-year windows)        [RUN_SECONDARY_END_RULES]
processor.apply_rules(RULES_KERNEL6_SECONDARY_END, kernel_size=6, years_override=YEARS_SECONDARY_END)
processor.apply_rules(RULES_KERNEL4_SECONDARY_END_REVERT, kernel_size=4,
                      years_override=YEARS_SECONDARY_END_REVERT)

# Step 2  — confirmed primary vegetation suppression
processor.apply_rules(RULES_KERNEL4, kernel_size=4)

# Step 3  — secondary vegetation dynamics (establishment, persistence, suppression)
processor.apply_rules(RULES_KERNEL4_SECONDARY, kernel_size=4)

# Step 4  — suppression within secondary vegetation
processor.apply_rules(RULES_KERNEL3_SECONDARY, kernel_size=3)

# Step 5  — unconfirmed transitions at the end of the series
processor.apply_rules(RULES_KERNEL4_END, kernel_size=4, years_override=YEARS_END)

# Step 6  — anthropic frequency correction
# Step 7  — tail guard (unconfirmed secondary vegetation in the last 2 years)
```

⚠️ **Steps 1a and 1b run first, and this is essential.** They need to see the clean aggregated map
(`{0,1,2,7}`), with raw anthropic(1) and vegetation(2). If they ran after Steps 2–4, the windows'
`p0` would already have been rewritten to `{3,4,5,6}` — for example `[4,1,1,1,1,2]` or
`[6,1,1,1,1,2]` — and window 3, which literally matches `[2,1,1,1,1,2]`, would no longer match. The
`5`/`3` marks written in Steps 1a/1b survive all subsequent rules (they match no downstream
`kernel_bef`) and the frequency correction, which only touches classes 2 and 4.

---

## 6. Rule groups

Presented **in execution order**. In all tables, `2 2 1 1` reads as the sequence of classes from
`t1` to `tk`; the "after" column shows what is written when the pattern matches.

### 6.1 `RULES_KERNEL3_VEG_BLIP` — 1-year blip filter (Step 1a)

**Kernel:** 3 years · **Years:** whole series · **Flag:** `RUN_VEG_BLIP_FILTER` (default `True`)

A single year of vegetation between two anthropic years cannot be confirmed as secondary
vegetation — establishment requires 3 years — and is treated as noise, reverted to anthropic.
Without this filter, the frequency correction (Step 6) would promote these blips to secondary(3)
throughout the series.

```python
RULES_KERNEL3_VEG_BLIP = [
    [[1, 2, 1], [1, 1, 1], 0],  # anthropic, veg (1 year), anthropic → anthropic
]
```

| Rule | before | → | after | min_start |
|---|---|---|---|---|
| 1-year vegetation blip | `1 2 1` | → | `1` **`1`** `1` | 0 |

- `min_start=0` is safe: the rule only writes class 1, never 3 or 5.
- **Does not match at `n`**: it requires an anthropic year after the vegetation, which does not
  exist in the last year. By construction, it never touches an ongoing regeneration at the end of
  the series.
- Runs first so that clean data feeds the anchored windows — a real regeneration is still detected
  after the blip is removed.

### 6.2 `RULES_KERNEL6_SECONDARY_END` — anchored end-of-series windows (Step 1b)

**Kernel:** 6 years · **Years:** `YEARS_SECONDARY_END` (`YEARS[-6:]`, single window) ·
**Flag:** `RUN_SECONDARY_END_RULES` (default `True`)

The 4-year rules require 3 consecutive years of vegetation to confirm establishment, so they
**do not cover the last 2 years** of the series: a regeneration starting at `n` or `n-1` does not
have enough years ahead to be confirmed. These three windows, anchored on the interval
`[n-5 .. n]`, solve this case by using the **prior** history (4 to 5 anthropic years) as evidence
in place of the future confirmation that does not exist.

```python
RULES_KERNEL6_SECONDARY_END = [
    [[1, 1, 1, 1, 2, 2], [1, 1, 1, 1, 5, 3], 0],  # window 1: 4 anthropic + 2 veg → 5,3
    [[1, 1, 1, 1, 1, 2], [1, 1, 1, 1, 1, 5], 0],  # window 2: 5 anthropic + 1 veg → 5
    [[2, 1, 1, 1, 1, 2], [2, 1, 1, 1, 1, 5], 0],  # window 3: veg + 4 anthropic + veg → 5
]
```

| Window | before (n-5 … n) | → | after (n-5 … n) | min_start |
|---|---|---|---|---|
| 1 — 4 anthropic + 2 years of vegetation | `1 1 1 1 2 2` | → | `1 1 1 1` **`5 3`** | 0 |
| 2 — 5 anthropic + 1 year of vegetation | `1 1 1 1 1 2` | → | `1 1 1 1 1` **`5`** | 0 |
| 3 — vegetation + 4 anthropic + vegetation | `2 1 1 1 1 2` | → | `2 1 1 1 1` **`5`** | 0 |

> **`min_start=0` is safe here.** With `years_override=YEARS[-6:]` there is only the window at
> index 0, which starts at `n-5` (2020) — with the whole series of history before it. There is no
> risk of writing 3 or 5 at the beginning of the series.

> **Window 3 — accepted side effect.** The `p0` (n-5) remains vegetation(2) in the rule, but the
> frequency correction of Step 6 converts 2 → 3 for pixels with anthropic history (which the window
> itself guarantees), so the effective tail becomes `[3,1,1,1,1,5]`. This is semantically
> consistent — year n-5 really was secondary vegetation — and is accepted.

### 6.3 `RULES_KERNEL4_SECONDARY_END_REVERT` — anchored reversal of a 2-year block (Step 1b)

**Kernel:** 4 years · **Years:** `YEARS_SECONDARY_END_REVERT` (`YEARS[-4:]`) ·
**Flag:** gated by `RUN_SECONDARY_END_RULES`

In the **interior** of the series, a 2-year block of vegetation followed by anthropic is already
reverted in two steps: `RULES_KERNEL4` marks the suppression (`[2,2,1,1]→[2,2,4,1]`) and
`RULES_KERNEL4_SECONDARY` reverts everything (`[1,2,2,4]→[1,1,1,1]`). At the **tail**, the
suppression cannot be marked — there is no year after `n` to complete the pattern — and the block
would survive, being promoted to secondary(3) by the frequency correction. This rule directly
reproduces the interior result.

```python
RULES_KERNEL4_SECONDARY_END_REVERT = [
    [[1, 2, 2, 1], [1, 1, 1, 1], 0],  # anthropic, veg, veg, anthropic → all anthropic
]
```

| Rule | before | → | after | min_start |
|---|---|---|---|---|
| 2-year block cut before `n` | `1 2 2 1` | → | `1` **`1 1`** `1` | 0 |

⚠️ **It is anchored on purpose.** A global version of `[1,2,2,1]` would also revert legitimate
blocks in the interior of the series, such as `[1,2,2,1,2]`. Locked by
`test_d_revert_does_not_revert_interior_1221`.

### 6.4 `RULES_KERNEL4` — primary vegetation suppression (Step 2)

**Kernel:** 4 years · **Years:** full series (1985–2025) · no rule writes 3 or 5

```python
RULES_KERNEL4 = [
    [[2, 2, 1, 1], [2, 2, 4, 1], 0],  # Primary vegetation suppression
]
```

| Rule | before | → | after | min_start |
|---|---|---|---|---|
| Primary vegetation suppression | `2 2 1 1` | → | `2 2` **`4`** `1` | 0 |

**Reading:** if the pixel was primary vegetation (2) for two consecutive years and became
anthropic (1) for two years, the third year is marked as suppression (4). Confirmation requires two
years of anthropic use to avoid false positives from single-year noise.

### 6.5 `RULES_KERNEL4_SECONDARY` — secondary vegetation dynamics (Step 3)

**Kernel:** 4 years · **Years:** full series · **3 rules require `min_start=1`**

```python
RULES_KERNEL4_SECONDARY = [
    [[1, 2, 2, 2], [1, 5, 3, 3], 1],  # Secondary vegetation establishment
    [[5, 3, 3, 2], [5, 3, 3, 3], 0],  # Recovery → secondary: persistence
    [[3, 2, 2, 2], [3, 3, 3, 3], 1],  # Secondary vegetation persistence
    [[3, 2, 2, 4], [3, 3, 3, 4], 1],  # Secondary with suppression at the end
    [[3, 3, 2, 4], [3, 3, 3, 6], 0],  # Suppression with recovery
    [[3, 3, 2, 2], [3, 3, 3, 3], 0],  # Persistence with interrupted primary
    [[3, 3, 3, 2], [3, 3, 3, 3], 0],  # Persistence: 3 confirmed years
    [[1, 2, 2, 4], [1, 1, 1, 1], 0],  # Primary suppression with recovery
]
```

| Rule | before | → | after | min_start | Note |
|---|---|---|---|---|---|
| Secondary vegetation establishment | `1 2 2 2` | → | `1` **`5 3 3`** | **1** | ⚠️ t2 receives class 5 |
| Recovery → secondary: persistence | `5 3 3 2` | → | `5 3 3` **`3`** | 0 | t2 is already class 3 |
| Secondary vegetation persistence | `3 2 2 2` | → | `3` **`3 3 3`** | **1** | ⚠️ t2 receives class 3 |
| Secondary with suppression at the end | `3 2 2 4` | → | `3` **`3 3`** `4` | **1** | ⚠️ t2 receives class 3 |
| Suppression with recovery | `3 3 2 4` | → | `3 3` **`3 6`** | 0 | t2 is already class 3 |
| Persistence with interrupted primary | `3 3 2 2` | → | `3 3` **`3 3`** | 0 | t2 is already class 3 |
| Persistence: 3 confirmed years | `3 3 3 2` | → | `3 3 3` **`3`** | 0 | t2 is already class 3 |
| Primary suppression with recovery | `1 2 2 4` | → | **`1 1 1 1`** | 0 | writes neither 3 nor 5 |

**Reading the ⚠️ rules:**

- `[[1,2,2,2],[1,5,3,3],1]` — detects `anthropic → vegetation → vegetation → vegetation` and
  interprets the vegetation as regeneration. It requires `t1` to be a confirmed anthropic state,
  which 1985 cannot provide. `min_start=1` ensures the first window is `[1986,1987,1988,1989]`.
  **This is the rule that covers a regeneration starting at `n-2`** (see
  [§8](#8-end-of-series-behavior)).
- `[[3,2,2,2],[3,3,3,3],1]` — consolidates the whole sequence as secondary. For `t1=1985` to be
  class 3, a previous rule would have had to write it, which is impossible in the first year.
- `[[3,2,2,4],[3,3,3,4],1]` — same rationale, with a suppression event at `t4`.

### 6.6 `RULES_KERNEL3_SECONDARY` — suppression within secondary vegetation (Step 4)

**Kernel:** 3 years · **Years:** full series · no rule writes 3 or 5 at `t2`

```python
RULES_KERNEL3_SECONDARY = [
    [[3, 4, 1], [3, 6, 1], 0],  # Suppression of secondary vegetation
]
```

| Rule | before | → | after | min_start |
|---|---|---|---|---|
| Secondary vegetation suppression | `3 4 1` | → | `3` **`6`** `1` | 0 |

**Reading:** if the pixel was secondary vegetation (3), underwent an event marked as primary
suppression (4) and returned to anthropic (1), the event is reclassified as secondary suppression
(6). This group depends on class 3 in `t1`, written by Step 3 — with the `min_start` in force
there, the dependency chain is safe.

### 6.7 `RULES_KERNEL4_END` — unconfirmed transitions at the end of the series (Step 5)

**Kernel:** 4 years · **Years:** `YEARS_END` (`YEARS[-4:]`, one window) · writes only 4 or 6 at `t4`

```python
RULES_KERNEL4_END = [
    [[2, 2, 2, 1], [2, 2, 2, 4], 0],  # Unconfirmed primary deforestation
    [[3, 3, 3, 1], [3, 3, 3, 6], 0],  # Unconfirmed secondary deforestation
]
```

| Rule | before | → | after | min_start |
|---|---|---|---|---|
| Unconfirmed primary deforestation | `2 2 2 1` | → | `2 2 2` **`4`** | 0 |
| Unconfirmed secondary deforestation | `3 3 3 1` | → | `3 3 3` **`6`** | 0 |

**Reading:** in a confirmed deforestation rule (`RULES_KERNEL4`), the transition requires two years
of anthropic use to avoid noise. At the end of the series, the second confirmation year does not
exist yet. These rules mark the last year as suppression (4 or 6) based on a single anthropic
year, accepting the lower confidence.

---

## 7. Post-processing

### 7.1 Reclassification by anthropic frequency (Step 6)

Computes the per-pixel anthropic frequency across all years with `get_class_frequency()`, over the
**aggregated** image (before the kernel rules).

| Condition | Action | Rationale |
|---|---|---|
| `freq_anthropic > 1` **and** pixel = class `4` | → class `6` | If the pixel has been anthropic more than once, a primary suppression is likely a secondary one |
| `freq_anthropic > 0` **and** pixel = class `2` | → class `3` | If the pixel has any anthropic history, the current primary vegetation is likely regeneration |

```python
freq_anthropic = DeforestationSecondaryVegetation.get_class_frequency(aggregated, class_id=1)

deforestation_transitions = deforestation_transitions.where(
    freq_anthropic.gt(1).And(deforestation_transitions.eq(CLASS_PRIMARY_VEG_SUPPRESSION)),
    CLASS_SECONDARY_VEG_SUPPRESSION
)
deforestation_transitions = deforestation_transitions.where(
    freq_anthropic.gt(0).And(deforestation_transitions.eq(CLASS_PRIMARY_VEGETATION)),
    CLASS_SECONDARY_VEGETATION
)
```

> The correction **only touches classes 2 and 4**. That is why the 3 and 5 marks written by the
> anchored windows of Step 1b pass through this step intact.

### 7.2 Tail guard (Step 7) — replaces the last-3-years adjustment

The manual post-processing block for the last 3 years (four conditional adjustments) was
**removed**. With the anchored windows of Step 1b defining the tail deterministically, only one
guard remained: remove secondary vegetation(3) whose **immediate predecessor** is anthropic(1) —
that is, the unconfirmed regeneration induced by the frequency correction.

```python
y1, y2, y3 = YEARS[-3], YEARS[-2], YEARS[-1]

# n-1: removes unconfirmed secondary (the predecessor n-2 is anthropic)
t2 = t2.where(t1.eq(CLASS_ANTHROPIC).And(t2.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)

# n: same — uses the already updated t2, so the removal cascades through consecutive years
t3 = t3.where(t2.eq(CLASS_ANTHROPIC).And(t3.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)
```

- **Runs independently** of `RUN_SECONDARY_END_RULES`.
- Preserves the outputs of the anchored windows (window 1: `n-1`=5 and then `n`=3 — the
  predecessor of the 3 is 5, not 1) and confirmed establishments (3 preceded by 3).
- Removes only the frequency-induced `3`s, which are noise.

| Old adjustment (removed) | How the case is handled today |
|---|---|
| `t1`=anthropic and `t2`=secondary → reverts `t2` | kept, as the 1st condition of the tail guard |
| `t1`=anthropic and `t3`=secondary → reverts `t3` | covered by the cascading of the 2nd condition |
| `t2`=anthropic and `t3`=secondary → reverts `t3` | kept, as the 2nd condition of the tail guard |
| `t2`=secondary and `t3`=anthropic → reverts `t3` to secondary | **discarded** — it rewrote the last year blindly; the tail is now defined by the anchored windows |

---

## 8. End-of-series behavior

For a regeneration that starts near the end of the series, what comes out on the map? The matrix
below was verified by simulating the full pipeline over the 1985–2025 series and is locked by tests
(`test_tail_coverage_matrix`).

| Input (last 6 years) | Situation | Output (n-2, n-1, n) | Mechanism |
|---|---|---|---|
| `1 1 1 1 1 2` | regeneration starts at `n` (1 ongoing year) | `1 1 5` | window 2 or 3 (6 years) |
| `1 1 1 1 2 2` | starts at `n-1` (2 ongoing years) | `1 5 3` | window 1 (6 years) |
| `1 1 1 2 2 2` | starts at `n-2` and reaches `n` (3 years) | `5 3 3` | **establishment rule (4 years)** |
| `1 1 2 2 2 2` | starts at `n-3` (4 years) | `3 3 3` | establishment rule (4 years) |
| `1 1 1 2 2 1` | 2-year block cut before `n` | `1 1 1` | **anchored reversal** ([§6.3](#63-rules_kernel4_secondary_end_revert--anchored-reversal-of-a-2-year-block-step-1b)) |
| `1 1 1 2 1 1` | 1-year blip | `1 1 1` | **blip filter** ([§6.1](#61-rules_kernel3_veg_blip--1-year-blip-filter-step-1a)) |

The 6-year windows are needed **only** for **ongoing** regenerations starting at `n` or `n-1`. A
regeneration that starts at `n-2` and reaches `n` already has 3 years of vegetation and is
confirmed by the 4-year establishment rule — `n-2` was **not** left out.

Short regenerations that **end before `n`** are treated as noise, mirroring the behavior in the
interior of the series: 2 years cut by the anchored reversal, 1 year by the blip filter.

### 8.1 Execution flags

| Flag | Default | What it controls | Effect when `False` |
|---|---|---|---|
| `RUN_VEG_BLIP_FILTER` | `True` | Step 1a — 1-year blip filter over the whole series | blips survive and are promoted to secondary(3) by the frequency correction |
| `RUN_SECONDARY_END_RULES` | `True` | Step 1b — 6-year windows **and** anchored reversal | the tail reverts to the previous behavior: 2-year blocks become secondary; ongoing regeneration at `n`/`n-1` is not detected |

The tail guard (Step 7) is **not** controlled by a flag — it always runs. The two flags exist to
allow reproducing the previous behavior in comparisons; locked by the `test_flag_*` tests.

---

## 9. Validation and tests

The actual code is an Earth Engine graph and does not run offline.
[`tests/test_rules.py`](../tests/test_rules.py) validates the **semantics of the rules** with a
faithful Python simulator of the kernel algorithm — including sequential application, in which
each window sees the result of the previous one.

```bash
# from collection11/
python -m pytest tests -v
```

**50 tests, all passing** (verified on 2026-10-16). They run offline, without Earth Engine
credentials.

| Group | What it covers |
|---|---|
| 1. Loading rules via AST | Literal patterns of each group |
| 2. `apply_rule_kernel_6` | Single window, partial non-match, 3 windows in sequence |
| 3. `min_start` | Index 0 applies with 0; blocks with 1; allows at index 1 |
| 4. Blip filter | Removes 1 year; preserves 2-year block; multiple blips; does not match at `n` |
| 5. Anchored reversal | Reverts at the tail; does **not** revert `[1,2,2,1]` in the interior |
| 6. Establishment rule | Matches in the interior; blocked at the start of the series |
| 7. Tail coverage matrix | Full end-to-end pipeline for the 6 scenarios in [§8](#8-end-of-series-behavior) |
| 8. Flags | Old behavior reproduced with the flags turned off |
| 9. Run-first ordering | The 5/3 marks from Step 1b survive KERNEL4 and KERNEL4_SECONDARY |
| 10. Tail guard | Removes frequency-induced 3; preserves recovery(5) and confirmed 3 |
| 11. Regression | All-anthropic / all-vegetation series; missing `min_start` raises an error |
| 12. Frequency correction | The anthropic frequency is cumulative up to each year: vegetation before the first anthropic year stays primary; 4 → 6 only after 2+ anthropic years |

> The rules are loaded **from the source code via AST** (`load_rules_from_source`), without
> importing the pipeline — which avoids `ee.Initialize()` in the tests and ensures that the
> document and the tests describe the same constants that run in production.

---

## 10. What comes after the temporal rules

The image produced by `export_deforestation()` is the first link. The products below derive from it
and live in `LAND-COVER/COLLECTION-11/DEFORESTATION/`.

| Product | Asset | Flag | Depends on |
|---|---|---|---|
| Deforestation transitions | `deforestation-secondary-vegetation` | `RUN_DEF` | integration |
| Filtered transitions (spatial filter) | `…-ft` | `RUN_DEF_FT` | transitions |
| Annual deforestation | `…-annual` | `RUN_DEF_ANNUAL` | filtered transitions |
| Accumulated deforestation | `…-accumulated` | `RUN_DEF_ACCUMULATED` | annual |
| Deforestation frequency | `deforestation-frequency` | `RUN_DEF_FREQUENCY` | filtered transitions |
| Secondary vegetation age | `secondary-vegetation-age` | `RUN_SV_AGE` | filtered transitions |

**Spatial filter:** `export_deforestation_filtered_no_accumulation()` removes, **year by year**,
patches of up to `GROUP_SIZE_FILTER` (11 pixels, ~1 ha) by connected-pixel count (8-neighborhood),
reclassifying them to class 7 (Other Transitions). Deforestation (4, 6) and secondary vegetation
(3, 5) are filtered with separate masks. `YEARS_EXCEPTION` (by default, only the last year) allows a
separate threshold for the most recent years — in C11, also 11.

> This is the function called by `run_pipeline()` since Collection 10 and the one that produced
> C11. The script keeps `export_deforestation_filtered()`, the previous variant, which counts
> connected pixels over the **accumulated** mask of the whole series (a small patch in one year
> survives if it touches deforestation from another year); it is not used.

**Secondary vegetation age:** accumulates, per pixel, the consecutive years in class 3 or 5,
resetting to zero when the pixel leaves those classes — `age(t) = (age(t-1) + sv(t)) * sv(t)`.
Bands are named `secondary_vegetation_age_{year}`, **not** `classification_{year}`, unlike the
other assets of the pipeline.

**Reuse in other regions:** Peru (C4), Bolivia (C4), Uruguay, Argentina (C3) and Indonesia (C5)
use **the same seven temporal rule lists**. What differs is the `CLASS_LOOKUP`, specific to each
region's legend, and the spatial filter.

---

## 11. History of resolved problems

### 11.1 Secondary vegetation in the first years of the series

**Symptom.** Classes `3` and `5` appeared improperly in the second year of the series (1986) — and,
in some cases, also in 1985 — on the deforestation map.

**Root cause.** The `RULES_KERNEL4_SECONDARY` rules that assign 3 or 5 at position `t2` were
applied starting at index `i=0`, corresponding to `[1985,1986,1987,1988]`. In that window,
`t2`=1986 received 5 or 3 without any history before 1985 to validate the transition.

```python
[[1, 2, 2, 2], [1, 5, 3, 3], ...]  →  t2 (1986) received class 5
[[3, 2, 2, 2], [3, 3, 3, 3], ...]  →  t2 (1986) received class 3
[[3, 2, 2, 4], [3, 3, 3, 4], ...]  →  t2 (1986) received class 3
```

**Fix.** Introduction of `min_start`, with value `1` in the three affected rules: the earliest
window becomes `[1986,1987,1988,1989]`, with `t2`=1987. The parameter was added explicitly with
value `0` to all other rules, and its absence now raises `ValueError`.

### 11.2 Regeneration not detected in the last 2 years

**Symptom.** **Ongoing** regenerations — which start at `n` or `n-1` and do not yet have 3 years of
vegetation — did not appear on the map, because the 4-year rules require confirmation over 3
consecutive years. At the same time, short noise (1 or 2 years of vegetation) at the tail **was**
promoted to secondary vegetation by the frequency correction: the real signal was missing and the
noise remained.

**Root cause.** The end of the series lacks the future years that the rest of the series uses as
confirmation. The previous treatment was a manual block of four conditional adjustments over the
last 3 years, which did not distinguish ongoing regeneration from noise and even rewrote the last
year blindly.

**Fix.**

1. **Blip filter** ([§6.1](#61-rules_kernel3_veg_blip--1-year-blip-filter-step-1a)) — removes an
   isolated single year of vegetation throughout the series, before everything else.
2. **Anchored 6-year windows**
   ([§6.2](#62-rules_kernel6_secondary_end--anchored-end-of-series-windows-step-1b)) — detect
   ongoing regeneration at `n` and `n-1` using the prior history as evidence.
3. **Anchored reversal of a 2-year block**
   ([§6.3](#63-rules_kernel4_secondary_end_revert--anchored-reversal-of-a-2-year-block-step-1b)) —
   reproduces at the tail what the interior already did via suppression(4).
4. **Tail guard** ([§7.2](#72-tail-guard-step-7--replaces-the-last-3-years-adjustment)) —
   replaces the manual block with a single rule, based on the immediate predecessor.

The result is the coverage matrix in [§8](#8-end-of-series-behavior), locked by tests. The
execution order — Steps 1a and 1b before everything else — is part of the fix, not an
implementation detail.

---

## 12. Quick reference — all rules, in execution order

| # | Group | k | Years | before → after | min_start |
|---|---|---|---|---|---|
| 1a | `RULES_KERNEL3_VEG_BLIP` | 3 | all | `1 2 1` → `1 1 1` | 0 |
| 1b | `RULES_KERNEL6_SECONDARY_END` | 6 | `YEARS[-6:]` | `1 1 1 1 2 2` → `1 1 1 1 5 3` | 0 |
| | | | | `1 1 1 1 1 2` → `1 1 1 1 1 5` | 0 |
| | | | | `2 1 1 1 1 2` → `2 1 1 1 1 5` | 0 |
| 1b | `RULES_KERNEL4_SECONDARY_END_REVERT` | 4 | `YEARS[-4:]` | `1 2 2 1` → `1 1 1 1` | 0 |
| 2 | `RULES_KERNEL4` | 4 | all | `2 2 1 1` → `2 2 4 1` | 0 |
| 3 | `RULES_KERNEL4_SECONDARY` | 4 | all | `1 2 2 2` → `1 5 3 3` | **1** |
| | | | | `5 3 3 2` → `5 3 3 3` | 0 |
| | | | | `3 2 2 2` → `3 3 3 3` | **1** |
| | | | | `3 2 2 4` → `3 3 3 4` | **1** |
| | | | | `3 3 2 4` → `3 3 3 6` | 0 |
| | | | | `3 3 2 2` → `3 3 3 3` | 0 |
| | | | | `3 3 3 2` → `3 3 3 3` | 0 |
| | | | | `1 2 2 4` → `1 1 1 1` | 0 |
| 4 | `RULES_KERNEL3_SECONDARY` | 3 | all | `3 4 1` → `3 6 1` | 0 |
| 5 | `RULES_KERNEL4_END` | 4 | `YEARS[-4:]` | `2 2 2 1` → `2 2 2 4` | 0 |
| | | | | `3 3 3 1` → `3 3 3 6` | 0 |
| 6 | frequency correction | — | all | `freq>1 ∧ 4 → 6` · `freq>0 ∧ 2 → 3` | — |
| 7 | tail guard | — | `YEARS[-3:]` | `1` before `3` → `3` becomes `1` (cascades) | — |
