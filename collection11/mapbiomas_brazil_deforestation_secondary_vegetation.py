# -*- coding: utf-8 -*-
"""
This script is designed to export various datasets related to land cover changes,
deforestation, and secondary vegetation in Brazil.

Includes:
- Exporting deforestation and secondary vegetation transitions
- Exporting filtered deforestation and secondary vegetation transitions
- Exporting annual deforestation and secondary vegetation maps
- Exporting accumulated deforestation and secondary vegetation maps
- Exporting deforestation frequency maps
- Exporting secondary vegetation age maps
- Exporting transitions between land cover classes

Execution of each export can be toggled using Boolean flags in the configuration section.

The script uses grid-based export (1:1,000,000 CIM blocks) and includes automated task monitoring.
All export parameters (versioning, region, years, asset paths, class codes, export scale, etc.)
are defined in a centralized configuration block at the top of the script.

Vendored from mapbiomas-pipeline @ c50594f (1_brazil/mapbiomas_brazil_export_pipeline.py).
Changes from the source: local imports, Earth Engine project from EE_PROJECT, the Brazil
grid/bbox embedded below instead of utils/region_utils.py, and all RUN_* flags off.
Rules and processing are unchanged.

Usage:
    EE_PROJECT=mapbiomas-brazil python mapbiomas_brazil_deforestation_secondary_vegetation.py
"""

import ee
import time
import sys
import os
import textwrap
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from deforestation_secondary_vegetation import DeforestationSecondaryVegetation

# ================================
# AUTHENTICATION AND INITIALIZATION
# ================================
EE_PROJECT = os.environ.get('EE_PROJECT', 'mapbiomas-brazil')

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    print("Authenticating Earth Engine...")
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

# ==============================
# GENERAL SCRIPT CONFIGURATION
# ==============================

# Region and collection
REGION_NAME = 'brazil'
REGION_ISO3 = 'BRA'
COLLECTION_ID = 11

TERRITORY_CATEGORY_ID = '1'
TERRITORY_FEATURE_ID  = '1'
TERRITORY_VERSION     = '2'
TERRITORY_IMAGE_ID    = f'{TERRITORY_CATEGORY_ID}_{TERRITORY_FEATURE_ID}_{TERRITORY_VERSION}'

# Asset paths
# These paths are constructed based on the region and collection ID.
# The DEFORESTATION folder needs to be created manually in the MapBiomas cloud project.
# The image collection is created automatically by the script, except for the integration asset.
ASSET_COLLECTION      = f'projects/mapbiomas-{REGION_NAME}/assets/LAND-COVER/COLLECTION-{str(COLLECTION_ID).replace(".", "_")}'
ASSET_INTEGRATION     = f'{ASSET_COLLECTION}/INTEGRATION/classification-ft'
ASSET_TRANSITIONS     = f'{ASSET_COLLECTION}/INTEGRATION/transitions'
ASSET_DEF_SEC_VEG     = f'{ASSET_COLLECTION}/DEFORESTATION/deforestation-secondary-vegetation'
ASSET_DEF_SEC_VEG_FT  = f'{ASSET_COLLECTION}/DEFORESTATION/deforestation-secondary-vegetation-ft'
ASSET_DEF_SEC_VEG_ANN = f'{ASSET_COLLECTION}/DEFORESTATION/deforestation-secondary-vegetation-annual'
ASSET_DEF_SEC_VEG_ACC = f'{ASSET_COLLECTION}/DEFORESTATION/deforestation-secondary-vegetation-accumulated'
ASSET_DEF_FREQ        = f'{ASSET_COLLECTION}/DEFORESTATION/deforestation-frequency'
ASSET_SEC_VEG_AGE     = f'{ASSET_COLLECTION}/DEFORESTATION/secondary-vegetation-age'
ASSET_GRID            = 'projects/mapbiomas-workspace/AUXILIAR/cim-world-1-250000'

# Bands
BAND_PREFIX            = 'classification_'
FREQ_BAND_PATTERN      = 'deforestation_frequency_{start}_{end}'
ACCUM_BAND_PATTERN_DEF = 'deforestation_accumulated_{start}_{end}'
ACCUM_BAND_PATTERN_SV  = 'secondary_vegetation_accumulated_{start}_{end}'
AGE_BAND_PATTERN       = 'secondary_vegetation_age_{year}'

# Export parameters
EXPORT_SCALE = 30
EXPORT_MAX_PIXELS = 1e13
EXPORT_PYRAMIDING_POLICY = 'MODE'

# Periods for land use and cover transitions
TRANSITION_PERIODS = [
    (1985, 1986), (1986, 1987), (1987, 1988), (1988, 1989), (1989, 1990),
    (1990, 1991), (1991, 1992), (1992, 1993), (1993, 1994), (1994, 1995),
    (1995, 1996), (1996, 1997), (1997, 1998), (1998, 1999), (1999, 2000),
    (2000, 2001), (2001, 2002), (2002, 2003), (2003, 2004), (2004, 2005),
    (2005, 2006), (2006, 2007), (2007, 2008), (2008, 2009), (2009, 2010),
    (2010, 2011), (2011, 2012), (2012, 2013), (2013, 2014), (2014, 2015),
    (2015, 2016), (2016, 2017), (2017, 2018), (2018, 2019), (2019, 2020),
    (2020, 2021), (2021, 2022), (2022, 2023), (2023, 2024), (1985, 2024),
    (1985, 1990), (1990, 1995), (1995, 2000), (2000, 2005), (2005, 2010),
    (2010, 2015), (2015, 2020), (2020, 2024), (1985, 2000), (2000, 2024),
    (1990, 2000), (2000, 2010), (2010, 2020), (1985, 1994), (1995, 2004),
    (2005, 2014), (1985, 1995), (1995, 2005), (2005, 2015), (2015, 2024),
]

# CIM 1:1,000,000 blocks that intersect Brazil (49). Each name is matched with stringContains
# against ASSET_GRID (1:250,000 sheets), so one export covers a whole block.
GRID_NAMES = [
    "NA-19", "NA-20", "NA-21", "NA-22", "NB-20", "NB-21", "NB-22", "SA-19",
    "SA-20", "SA-21", "SA-22", "SA-23", "SA-24", "SB-18", "SB-19", "SB-20",
    "SB-21", "SB-22", "SB-23", "SB-24", "SB-25", "SC-18", "SC-19", "SC-20",
    "SC-21", "SC-22", "SC-23", "SC-24", "SC-25", "SD-20", "SD-21", "SD-22",
    "SD-23", "SD-24", "SE-20", "SE-21", "SE-22", "SE-23", "SE-24", "SF-21",
    "SI-22", "SF-23", "SF-24", "SG-21", "SG-22", "SG-23", "SH-21", "SH-22",
    "SF-22",
]

# BBox of the region (used only by export_transitions)
REGION_BBOX = ee.Geometry.BBox(-74.0206, -34.0036, -32.3925, 5.4057)

# ================================
# DEFORESTATION & SECONDARY VEGETATION RULES
# ================================

# Deforestation and Secondary Vegetation class codes
CLASS_NO_DATA                   = 0
CLASS_ANTHROPIC                 = 1
CLASS_PRIMARY_VEGETATION        = 2
CLASS_SECONDARY_VEGETATION      = 3
CLASS_PRIMARY_VEG_SUPPRESSION   = 4
CLASS_RECOVERY_TO_SECONDARY     = 5
CLASS_SECONDARY_VEG_SUPPRESSION = 6
CLASS_OTHER_TRANSITIONS         = 7

# Year range between 1985 and 2025 for annual calculations of deforestation and secondary vegetation sub-products
YEARS = list(range(1985, 2026))

# Pairs [start, end] of years for accumulated and frequency calculations: every start in
# YEARS[2:] (1987..2025) with every end up to the last year — 780 periods. 1985 and 1986 are
# warm-up years for the rules with min_start=1 and are left out, as in the public v5.
PERIODS_ALL_YEARS = [[i, j] for i in YEARS[2:] for j in range(i, YEARS[-1] + 1)]

# Last year to consider in post-processing logic
LAST_YEAR = YEARS[-1]

# Last 4 years for end-of-period deforestation logic (e.g. 2021–2024, when last year is 2024)
YEARS_END = YEARS[-4:]

# Lookup table for class aggregation
# Format: [original_class_id, aggregated_class_id]
CLASS_LOOKUP = [
    [0, CLASS_NO_DATA],                     # 6. Not Observed
    [1, CLASS_PRIMARY_VEGETATION],          # 1. Forest formation
    [3, CLASS_PRIMARY_VEGETATION],          # 1.1. Forest
    [4, CLASS_PRIMARY_VEGETATION],          # 1.2. Dry forest
    [5, CLASS_PRIMARY_VEGETATION],          # 1.3. Mangrove
    [6, CLASS_PRIMARY_VEGETATION],          # 1.4. Floodable Forest
    [7, CLASS_PRIMARY_VEGETATION],          # 1.5. Floodable Savanna
    [9, CLASS_ANTHROPIC],                   # 3.3. Forest Plantation
    [10, CLASS_PRIMARY_VEGETATION],         # 2. Non Forest Natural Formation
    [11, CLASS_PRIMARY_VEGETATION],         # 2.1. Swamp or Flooded Grassland
    [12, CLASS_PRIMARY_VEGETATION],         # 2.2. Grassland / Herbaceous Formation
    [13, CLASS_PRIMARY_VEGETATION],         # 2.6. Other non-forest formation
    [14, CLASS_ANTHROPIC],                  # 3. Farming
    [15, CLASS_ANTHROPIC],                  # 3.1. Pasture
    [18, CLASS_ANTHROPIC],                  # 3.2. Agriculture
    [19, CLASS_ANTHROPIC],                  # 3.2.1. Temporary Crop
    [20, CLASS_ANTHROPIC],                  # 3.2.1.2. Sugar cane
    [21, CLASS_ANTHROPIC],                  # 3.4. Mosaic of agriculture and pasture
    [22, CLASS_ANTHROPIC],                  # 4. Non vegetated area
    [23, CLASS_OTHER_TRANSITIONS],          # 4.1. Beach
    [24, CLASS_ANTHROPIC],                  # 4.2. Urban Area
    [25, CLASS_ANTHROPIC],                  # 4.7. Other non vegetated area
    [26, CLASS_OTHER_TRANSITIONS],          # 5. Water
    [27, CLASS_NO_DATA],                    # 6. Not Observed
    [29, CLASS_OTHER_TRANSITIONS],          # 2.3. Rocky Outcrop
    [30, CLASS_ANTHROPIC],                  # 4.3. Mining
    [31, CLASS_ANTHROPIC],                  # 5.2. Aquaculture
    [32, CLASS_OTHER_TRANSITIONS],          # 4.4. Coastal salt flats
    [33, CLASS_OTHER_TRANSITIONS],          # 5.1. River, Lake or Ocean
    [34, CLASS_OTHER_TRANSITIONS],          # 5.3. Glaciares
    [35, CLASS_ANTHROPIC],                  # 3.2.1. Palm Oil
    [36, CLASS_ANTHROPIC],                  # 3.2.2. Perennial Crop
    [39, CLASS_ANTHROPIC],                  # 3.2.1.1. Soybean
    [40, CLASS_ANTHROPIC],                  # 3.2.2. Rice
    [41, CLASS_ANTHROPIC],                  # 3.2.1.5. Other Temporary Crops
    [46, CLASS_ANTHROPIC],                  # 3.2.2.1. Coffee
    [47, CLASS_ANTHROPIC],                  # 3.2.2.2. Citrus
    [48, CLASS_ANTHROPIC],                  # 3.2.2.4. Other Perennial Crops
    [49, CLASS_PRIMARY_VEGETATION],         # 1.5. Wooded Sandbank Vegetation
    [50, CLASS_PRIMARY_VEGETATION],         # 2.4. Herbaceous Sandbank Vegetation
    [61, CLASS_OTHER_TRANSITIONS],          # 4.5. Salt flat
    [62, CLASS_ANTHROPIC],                  # 3.2.1.4. Cotton
    [66, CLASS_PRIMARY_VEGETATION],         # 2.4. Scrubland
    [68, CLASS_OTHER_TRANSITIONS],          # 4.6. Other natural non vegetated area
    [69, CLASS_OTHER_TRANSITIONS],          # 5.3. Coral Reef
    [70, CLASS_PRIMARY_VEGETATION],         # 2.5. Fog oasis
    [72, CLASS_ANTHROPIC],                  # 3.2.3. Other crops
    [75, CLASS_ANTHROPIC],                  # 4.8. Photovoltaic power plant
    [84, CLASS_PRIMARY_VEGETATION],         # 1.6. Salt marsh
    [91, CLASS_ANTHROPIC],                  # 4.9. Wind power plant
]


# Split lookup into input/output
LOOKUP_IN = [pair[0] for pair in CLASS_LOOKUP]
LOOKUP_OUT = [pair[1] for pair in CLASS_LOOKUP]

# Rules for detecting 4-year deforestation (suppression of primary vegetation)
RULES_KERNEL4 = [
    [[2, 2, 1, 1], [2, 2, 4, 1], 0],  # Primary vegetation suppression
]

# End-of-period deforestation rules (also 4-year) applied to last 3 years (unconfirmed transitions)
RULES_KERNEL4_END = [
    [[2, 2, 2, 1], [2, 2, 2, 4], 0],  # Unconfirmed primary deforestation
    [[3, 3, 3, 1], [3, 3, 3, 6], 0],  # Unconfirmed secondary deforestation
]

# Rules for secondary vegetation establishment (4-year patterns)
RULES_KERNEL4_SECONDARY = [
    [[1, 2, 2, 2], [1, 5, 3, 3], 1], # Establishment of secondary vegetation | writes 5 at t2: needs history before 1985
    [[5, 3, 3, 2], [5, 3, 3, 3], 0], # Recovery to secondary vegetation | t2 is already 3, no risk
    [[3, 2, 2, 2], [3, 3, 3, 3], 1], # Secondary vegetation persistence | writes 3 at t2: same reason as rule 1
    [[3, 2, 2, 4], [3, 3, 3, 4], 1], # Suppression of secondary vegetation | writes 3 at t2: same reason
    [[3, 3, 2, 4], [3, 3, 3, 6], 0], # Suppression of secondary vegetation with recovery | t2 is already 3, no risk
    [[3, 3, 2, 2], [3, 3, 3, 3], 0], # Suppression of secondary vegetation with persistence | t2 is already 3, no risk
    [[3, 3, 3, 2], [3, 3, 3, 3], 0], # Suppression of secondary vegetation with persistence | t2 is already 3, no risk
    [[1, 2, 2, 4], [1, 1, 1, 1], 0], # Suppression of primary vegetation with recovery | writes neither 3 nor 5, no risk
]

# Rules for deforestation in secondary vegetation (3-year patterns)
RULES_KERNEL3_SECONDARY = [
    [[3, 4, 1], [3, 6, 1], 0], # Suppression of secondary vegetation
]

# Last 6 years of the series — anchored window [n-5 .. n] (e.g. 2020..2025)
YEARS_SECONDARY_END = YEARS[-6:]

# Anchored end-of-series rules for secondary vegetation (6-year kernel).
# Applied ONLY over YEARS_SECONDARY_END, so there is a single window (index 0).
# These flexibilize establishment/recovery detection at the tail of the series,
# which the 4-year rules cannot confirm (they need 3 consecutive vegetation years).
# min_start=0 is safe here: the window starts at n-5 (2020), which has full history
# before it — there is no risk of writing class 3/5 at the start of the series.
# NOTE (window 3): p0 (n-5) stays vegetation(2) in the rule, but the global
# frequency correction later converts leftover 2->3 for pixels with prior anthropic
# (which the window guarantees), so the effective tail becomes [3,1,1,1,1,5].
# This is semantically consistent (n-5 was secondary vegetation) and accepted.
RULES_KERNEL6_SECONDARY_END = [
    # window 1: 4 anthropic + 2 vegetation → recovery(5) at n-1, secondary(3) at n
    [[1, 1, 1, 1, 2, 2], [1, 1, 1, 1, 5, 3], 0],
    # window 2: 5 anthropic + 1 vegetation → recovery(5) at n
    [[1, 1, 1, 1, 1, 2], [1, 1, 1, 1, 1, 5], 0],
    # window 3: vegetation + 4 anthropic + vegetation → recovery(5) at n
    [[2, 1, 1, 1, 1, 2], [2, 1, 1, 1, 1, 5], 0],
]

# Turns the anchored end-of-series detection (6-year windows) on or off, so the user
# can choose whether to apply these rules. The tail guard (Step 7 in
# export_deforestation) runs regardless of this flag.
RUN_SECONDARY_END_RULES = True

# Anchored end-of-series revert (last 4 years, [n-3..n]). In the interior of the
# series a 2-year vegetation block followed by anthropic is reverted to anthropic in
# two steps: RULES_KERNEL4 marks the suppression ([2,2,1,1]->[2,2,4,1]) and then
# RULES_KERNEL4_SECONDARY reverts ([1,2,2,4]->[1,1,1,1]). At the series end the
# suppression cannot be marked (there is no year after n to complete [2,2,1,1]), so
# the block would survive and be promoted to secondary(3) by the frequency correction.
# This rule reproduces the interior result directly for the tail. Anchored (not global)
# on purpose: a global [1,2,2,1] would also revert interior [1,2,2,1,2] blocks.
YEARS_SECONDARY_END_REVERT = YEARS[-4:]
RULES_KERNEL4_SECONDARY_END_REVERT = [
    [[1, 2, 2, 1], [1, 1, 1, 1], 0],  # anthropic, veg, veg, anthropic → all anthropic
]

# General 1-year vegetation blip filter (all years). A single vegetation year between
# two anthropic years cannot be confirmed as secondary vegetation (which needs 3 years)
# and is treated as noise → reverted to anthropic. Without this, the frequency
# correction promotes such blips to secondary(3) everywhere in the series. min_start=0
# (writes only class 1, never 3/5). Cannot match at year n (needs an anthropic year
# after the vegetation), so it never touches an ongoing regeneration at the tail.
RUN_VEG_BLIP_FILTER = True
RULES_KERNEL3_VEG_BLIP = [
    [[1, 2, 1], [1, 1, 1], 0],  # anthropic, veg (1 year), anthropic → anthropic
]

# ================================
# FILTER CONFIGURATION FOR DEFORESTATION AND SECONDARY VEGETATION
# ================================

# Threshold (in pixels) for spatial filtering of deforestation and secondary vegetation patches
GROUP_SIZE_FILTER = 11               # applied to all years by default
GROUP_SIZE_EXCEPTION_FILTER = 11     # applied only to exception years (usually the last year)

# Years to apply the relaxed threshold (e.g., the most recent years)
YEARS_EXCEPTION = [YEARS[-1]]       # List of years to treat as exceptions (default: last year only)

# ================================
# VERSIONING
# ================================

VERSION_INPUT_INTEGRATION = '0-4-14-c84-5'

VERSION_OUTPUT_TRANSITIONS     = f'{VERSION_INPUT_INTEGRATION}-1' # for export_transitions()
VERSION_OUTPUT_DEF_SEC_VEG     = f'{VERSION_INPUT_INTEGRATION}-2' # for export_deforestation_secondary_vegetation()
VERSION_OUTPUT_DEF_SEC_VEG_FT  = f'{VERSION_INPUT_INTEGRATION}-2' # for export_deforestation_secondary_vegetation_ft()
VERSION_OUTPUT_DEF_SEC_VEG_ANN = f'{VERSION_INPUT_INTEGRATION}-2' # for export_deforestation_secondary_vegetation_annual()
VERSION_OUTPUT_DEF_SEC_VEG_ACC = f'{VERSION_INPUT_INTEGRATION}-2' # for export_deforestation_secondary_vegetation_accumulated()
VERSION_OUTPUT_DEF_FREQ        = f'{VERSION_INPUT_INTEGRATION}-2' # for export_deforestation_frequency()
VERSION_OUTPUT_SEC_VEG_AGE     = f'{VERSION_INPUT_INTEGRATION}-2' # for export_secondary_vegetation_age()

# ================================
# EXECUTION CONTROL
# ================================

# All off: the Collection 11 round (0-4-14-c84-5-2) is already materialized. To run a new
# round, bump VERSION_OUTPUT_* and turn on the steps in order — RUN_DEF → RUN_DEF_FT →
# RUN_DEF_ANNUAL → RUN_DEF_ACCUMULATED; RUN_DEF_FREQUENCY and RUN_SV_AGE read the filtered
# product. Existing assets are skipped, never overwritten.
RUN_DEF             = False
RUN_DEF_FT          = False
RUN_DEF_ANNUAL      = False
RUN_DEF_ACCUMULATED = False
RUN_DEF_FREQUENCY   = False
RUN_SV_AGE          = False
RUN_TRANSITIONS     = False  # LULC transitions (not part of this product)

# ================================
# TASK MONITORING
# ================================

def wait_until_tasks_finish(export_tasks=[], polling_interval=60):
    """
    Waits until all export tasks created by this script have finished.

    Continues monitoring even if some tasks fail. Displays status and duration at the end.
    Output is formatted with consistent alignment.
    Skips processing if no tasks were submitted.
    """
    if not export_tasks:
        print("⚠️  No export tasks to monitor.")
        return

    start_time = time.time()
    print(f"\n⏳ Waiting for {len(export_tasks)} task(s) to finish...")

    completed = set()
    failed_tasks = []

    # Calculate max width for formatting
    max_len = max(len(task.status().get('description', '')) for task in export_tasks)
    label_pad = max(40, max_len + 4)

    while True:
        all_done = True

        for task in export_tasks:
            status = task.status()
            description = status.get('description', '[No Description]')
            state = status['state']

            if description in completed:
                continue

            if state in ['READY', 'RUNNING']:
                all_done = False
                print(f"🚀 {description.ljust(label_pad)} | {time.strftime('%Y-%m-%dT%H:%M:%S')} | Status: {state}")
            elif state == 'FAILED':
                error_message = status.get('error_message', 'No error message provided.')
                failed_tasks.append((description, error_message))
                completed.add(description)
                print(f"❌ {description.ljust(label_pad)} | {time.strftime('%Y-%m-%dT%H:%M:%S')} | Status: {state} | Error: {error_message} ")
            elif state == 'COMPLETED':
                completed.add(description)
                print(f"✅ {description.ljust(label_pad)} | {time.strftime('%Y-%m-%dT%H:%M:%S')} | Status: {state}")
            elif state == 'CANCELLED':
                completed.add(description)
                print(f"⚠️ {description.ljust(label_pad)} | {time.strftime('%Y-%m-%dT%H:%M:%S')} | Status: {state}")

        if all_done and len(completed) == len(export_tasks):
            total_time = time.time() - start_time
            formatted_time = str(timedelta(seconds=int(total_time)))
            print(f"\n✅ All tasks finished. Total time: {formatted_time}")
            if failed_tasks:
                print(f"\n❌ {len(failed_tasks)} task(s) failed:\n")
                for description, error in failed_tasks:
                    print(f"❌ {description}\n→ {error}\n")
            break

        time.sleep(polling_interval)


# ==============================
# TEMPLATE MARKDOWN FUNCTIONS
# ==============================

def get_markdown_transitions():
    '''
    Generates a markdown-formatted description for the transitions product.
    '''
    return textwrap.dedent(f"""
                           
    ### Land Use and Cover Transitions – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}
    
    **Description:**
    
    This product represents **pairwise land use and cover transitions** derived from the integration maps of two different years, as provided by MapBiomas.
    
    **Technical details:**
    - **Input integration version:** `{VERSION_INPUT_INTEGRATION}`
    - **Output version:** `{VERSION_OUTPUT_TRANSITIONS}`
    - **List of transitions:** {len(TRANSITION_PERIODS)} pairwise year intervals between 1985 and 2024
    
    **Methodology:**
    1. For each `[start, end]` period, the band from year `start` is multiplied by 100 and added to the band from year `end`.
    2. The resulting values encode the transition: e.g., `311` means class 3 in year `start`, class 11 in year `end`.
    3. Each transition is stored as a single-band image.
    
    **Example transition code:**
    - `311`: Class 3 → Class 11
    - `502`: Class 5 → Class 2
    
    **Exports:**
    - One image per transition pair, exported to `{ASSET_TRANSITIONS}`.
    - Export region: Bounding box for `{REGION_NAME.upper()}` with 300 m buffer.
    
    **Visualization script example:** 
    ```javascript
    var asset = '{ASSET_TRANSITIONS}/mapbiomas_{REGION_NAME}_2000_2005_{VERSION_OUTPUT_TRANSITIONS}'; 
    
    var transition = ee.Image(asset); 
    
    var vis = {{
        min: 0,
        max: 100 * 34 + 34,  // max class id range
        palette: ["#ffffff", "#a6cee3", "#1f78b4", "#b2df8a", "#33a02c"],
        format: 'png'
    }};
    
    Map.addLayer(transition, vis, 'Transitions 2000–2005');
    Map.centerObject(transition);
    ```
    """)


def get_markdown_deforestation():
    """
    Generates a markdown-formatted description for the deforestation and secondary vegetation transitions product.
    """
    return textwrap.dedent(f"""
    ### Deforestation and Secondary Vegetation Transitions – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**

    This product identifies land cover transitions related to **deforestation** and **secondary vegetation** using temporal pattern recognition rules. The classification is derived from MapBiomas integrated maps and follows a logic of historical validation using 3- and 4-year kernels.

    **Technical details:**
    - **Input asset:** `{ASSET_INTEGRATION}`
    - **Input version:** `{VERSION_INPUT_INTEGRATION}`
    - **Output version:** `{VERSION_OUTPUT_DEF_SEC_VEG}`
    - **Analyzed years:** `{YEARS[0]} to {YEARS[-1]}`

    **Class codes (after rule application):**
    - `1`: Anthropogenic
    - `2`: Primary Vegetation
    - `3`: Secondary Vegetation
    - `4`: Suppression of Primary Vegetation (deforestation)
    - `5`: Recovery to Secondary Vegetation
    - `6`: Suppression of Secondary Vegetation
    - `7`: Other transitions

    **Rule types applied:**
    - **4-year kernels** (`RULES_KERNEL4`): Detect consistent transitions such as suppression of primary vegetation.
    - **4-year kernels for secondary vegetation** (`RULES_KERNEL4_SECONDARY`): Identify regeneration and persistence.
    - **3-year kernels for secondary loss** (`RULES_KERNEL3_SECONDARY`): Detect suppression of regenerating areas.
    - **End-of-period 4-year rules** (`RULES_KERNEL4_END`): Confirm unverified suppression events in the last 4 years.

    **Post-processing adjustments:**
    - Reclassification of pixels based on anthropogenic frequency:
        - `4 → 6` if frequency > 1
        - `2 → 3` if frequency > 0
    - Adjustment of secondary vegetation in the last three years:
        - Reverts class `3` to `1` if preceded by class `1`
        - Avoids false positives for regeneration or deforestation in recent years

    **Export structure:**
    - Exported as one image per 1:250,000 grid tile (`CIM grid`) with 300 m buffer.
    - Exported to: `{ASSET_DEF_SEC_VEG}`
    - Exported grid cells: {', '.join([f'`{g}`' for g in GRID_NAMES])}

    **Visualization example:**
    ```javascript
    var asset = '{ASSET_DEF_SEC_VEG}';
    var version = '{VERSION_OUTPUT_DEF_SEC_VEG}';

    var image = ee.ImageCollection(asset)
        .filter(ee.Filter.eq('version', version))
        .mosaic();

    var band = image.select('classification_{YEARS[-1]}');

    var vis = {{
        min: 0,
        max: 7,
        palette: [
            '#ffffff', // 0: No data
            '#faf5d1', // 1: Anthropogenic
            '#3f7849', // 2: Primary Vegetation
            '#5bcf20', // 3: Secondary Vegetation
            '#ea1c1c', // 4: Suppression of Primary Vegetation
            '#b4f792', // 5: Recovery to Secondary Vegetation
            '#fe9934', // 6: Suppression of Secondary Vegetation
            '#303149'  // 7: Other transitions
        ],
        format: 'png'
    }};

    Map.addLayer(band, vis, 'Deforestation - {YEARS[-1]}');
    Map.centerObject(band);
    ```
    """)


def get_markdown_deforestation_filtered():
    """
    Generates a markdown-formatted description for the filtered deforestation and secondary vegetation product.
    """
    return textwrap.dedent(f"""
    ### Filtered Deforestation and Secondary Vegetation – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**

    This product applies **spatial filtering** to the base transition map of deforestation and secondary vegetation, removing small patches considered noise. It ensures more reliable spatial consistency by keeping only connected clusters of pixels above a given threshold.

    **Technical details:**
    - **Input asset:** `{ASSET_DEF_SEC_VEG}`
    - **Output asset:** `{ASSET_DEF_SEC_VEG_FT}`
    - **Input version:** `{VERSION_OUTPUT_DEF_SEC_VEG}`
    - **Output version:** `{VERSION_OUTPUT_DEF_SEC_VEG_FT}`
    - **Analyzed year range:** `{YEARS[0]} to {YEARS[-1]}`
    - **Connected pixel threshold:** `{GROUP_SIZE_FILTER}` pixels
    - **Exception year(s):** {", ".join([str(y) for y in YEARS_EXCEPTION])}
    - **Exception threshold:** `{GROUP_SIZE_EXCEPTION_FILTER}` pixels

    **Methodology:**
    1. Class `4` (suppression of primary vegetation) and `6` (suppression of secondary vegetation) are masked and filtered by `connectedPixelCount()`.
    2. If the connected area is smaller than `{GROUP_SIZE_FILTER}` pixels, the pixel is reassigned to class `7` (other transitions).
    3. Classes `3` and `5` (secondary vegetation and recovery) undergo the same filtering.
    4. For the exception years (`{", ".join([str(y) for y in YEARS_EXCEPTION])}`), the threshold is relaxed to `{GROUP_SIZE_EXCEPTION_FILTER}` pixels.
    5. The final image is assembled by replacing filtered years with their adjusted versions and preserving other bands.

    **Export structure:**
    - One image per 1:250,000 CIM grid tile with a 300 m buffer
    - Exported to: `{ASSET_DEF_SEC_VEG_FT}`

    **Visualization script example:**
    ```javascript
    var asset = '{ASSET_DEF_SEC_VEG_FT}';
    var version = '{VERSION_OUTPUT_DEF_SEC_VEG_FT}';

    var image = ee.ImageCollection(asset)
        .filter(ee.Filter.eq("version", version))
        .mosaic();

    var vis = {{
        min: 0,
        max: 7,
        palette: [
            '#ffffff', // 0: No data
            '#faf5d1', // 1: Anthropogenic
            '#3f7849', // 2: Primary Vegetation
            '#5bcf20', // 3: Secondary Vegetation
            '#ea1c1c', // 4: Suppression of Primary Vegetation
            '#b4f792', // 5: Recovery to Secondary Vegetation
            '#fe9934', // 6: Suppression of Secondary Vegetation
            '#303149'  // 7: Other transitions / filtered noise
        ],
        format: 'png'
    }};

    Map.addLayer(image.select('classification_{YEARS[-1]}'), vis, 'Filtered Deforestation {YEARS[-1]}');
    Map.centerObject(image);
    ```
    """)


def get_markdown_deforestation_annual():
    '''
    Generates a markdown-formatted description for the annual deforestation and secondary vegetation product.
    '''
    return textwrap.dedent(f"""
                           
    ### Annual Deforestation and Secondary Vegetation – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**
    
    This product represents the **annual classification of land cover transitions** for each pixel, identifying events of deforestation and establishment of secondary vegetation, based on MapBiomas annual data.

    **Technical details:**
    - **Input version:** `{VERSION_OUTPUT_DEF_SEC_VEG_FT}` (deforestation and secondary vegetation transitions)
    - **Output version:** `{VERSION_OUTPUT_DEF_SEC_VEG_ANN}`
    - **Analyzed year range:** `{YEARS[0]} to {YEARS[-1]}`

    **Transition codes used:**
    - `{CLASS_PRIMARY_VEG_SUPPRESSION}`: Suppression of primary vegetation (deforestation)
    - `{CLASS_SECONDARY_VEG_SUPPRESSION}`: Suppression of secondary vegetation (deforestation)
    - `{CLASS_SECONDARY_VEGETATION}`: Secondary vegetation
    - `{CLASS_RECOVERY_TO_SECONDARY}`: Recovery to secondary vegetation

    **Methodology:**
    1. The base transition image is combined with the integration image using the formula: `(transition * 100) + integration`.
    2. Each year’s band represents a classification code indicating the transition type.
    3. The result is a multiband image (one band per year), encoding annual transitions.

    **Example of generated band:**
    - `classification_{YEARS[-1]}`: Encoded classification of transition for the year {YEARS[-1]}.

    **Exports:**
    - Exported in 1:250,000 CIM grid tiles with 300 m buffer.
    - Exported grid cells:
    {', '.join([f'`{g}`' for g in GRID_NAMES])}

    **Visualization example script:** 
    ```javascript
    // Example script to visualize one of the annual classification bands
    var asset = "{ASSET_DEF_SEC_VEG_ANN}";
    var version = "{VERSION_OUTPUT_DEF_SEC_VEG_ANN}";

    // Load the image from the asset
    var image = ee.ImageCollection(asset)
                  .filter(ee.Filter.eq("version", version))
                  .mosaic();

    var band = image.select("classification_{YEARS[-1]}")
                     .divide(100)
                     .byte();

    // Visualization parameters
    var vis = {{
        min: 0,
        max: 7,
        palette: [
            "#ffffff", // 0: No data
            "#faf5d1", // 1: Anthropogenic
            "#3f7849", // 2: Primary Vegetation
            "#5bcf20", // 3: Secondary Vegetation
            "#ea1c1c", // 4: Primary Vegetation Suppression
            "#b4f792", // 5: Recovery to Secondary Vegetation
            "#fe9934", // 6: Secondary Vegetation Suppression
            "#303149"  // 7: Other transitions
        ],
        format: "png"
    }};

    Map.addLayer(band, vis, "Annual Classification {YEARS[-1]}");
    Map.centerObject(band);
    ```
    """)


def get_markdown_deforestation_accumulated():
    '''
    Generates a markdown-formatted description for the accumulated deforestation and secondary vegetation product.
    '''
    return textwrap.dedent(f"""
                           
    ### Accumulated Deforestation and Secondary Vegetation – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**

    This product represents the **accumulated deforestation and secondary vegetation** over multiple periods between `{YEARS[0]}` and `{YEARS[-1]}`, derived from annual land cover transition classifications from **MapBiomas {REGION_NAME.upper()} Collection {COLLECTION_ID}**.

    **Technical details:**
    - **Input version:** `{VERSION_OUTPUT_DEF_SEC_VEG_ANN}`
    - **Output version:** `{VERSION_OUTPUT_DEF_SEC_VEG_ACC}`
    - **Analyzed year range:** `{YEARS[0]} to {YEARS[-1]}`

    **Classes considered:**
    - `{CLASS_PRIMARY_VEG_SUPPRESSION}`: Suppression of primary vegetation (deforestation)
    - `{CLASS_SECONDARY_VEG_SUPPRESSION}`: Suppression of secondary vegetation (deforestation)
    - `{CLASS_SECONDARY_VEGETATION}`: Secondary vegetation
    - `{CLASS_RECOVERY_TO_SECONDARY}`: Recovery to secondary vegetation

    **Methodology:**
    1. Annual classification images are filtered by version and rescaled.
    2. All `[start, end]` year intervals are constructed between the defined year range.
    3. For each interval, classification bands are selected for each year.
    4. Pixels with class `{CLASS_PRIMARY_VEG_SUPPRESSION}` or `{CLASS_SECONDARY_VEG_SUPPRESSION}` are combined to compute accumulated deforestation.
    5. Pixels with class `{CLASS_SECONDARY_VEGETATION}` are summed across the period, and pixels with class `{CLASS_RECOVERY_TO_SECONDARY}` are included only in the final year.
    6. The result is a multi-band image, with each band representing one accumulated metric per period.

    **Example of generated bands:**
    - `{ACCUM_BAND_PATTERN_DEF.format(start=2001, end=2024)}`: Accumulated deforestation from 2001 to 2024.
    - `{ACCUM_BAND_PATTERN_SV.format(start=2001, end=2024)}`: Accumulated secondary vegetation (including recovery) from 2001 to 2024.

    **Exports:**
    - Exported in 1:250,000 grid tiles (CIM grid) with a 300 m buffer for edge smoothing.
    - Exported grid cells:
    {', '.join([f'`{g}`' for g in GRID_NAMES])}

    **Visualization example script:**
    ```javascript
    // Example script to visualize one of the accumulated bands
    var asset = "{ASSET_DEF_SEC_VEG_ACC}";
    var version = "{VERSION_OUTPUT_DEF_SEC_VEG_ACC}";

    // Load the image from the asset
    var image = ee.ImageCollection(asset)
                  .filter(ee.Filter.eq("version", version))
                  .mosaic();

    // Select the accumulated deforestation band for 2001–2024
    var band = image.select("deforestation_accumulated_2001_2024")
                     .divide(100)
                     .byte();

    // Visualization parameters
    var vis = {{
        min: 0,
        max: 7,
        palette: [
            "#ffffff", // 0: No data
            "#faf5d1", // 1: Anthropogenic
            "#3f7849", // 2: Primary Vegetation
            "#5bcf20", // 3: Secondary Vegetation
            "#ea1c1c", // 4: Primary Vegetation Suppression
            "#b4f792", // 5: Recovery to Secondary Vegetation
            "#fe9934", // 6: Secondary Vegetation Suppression
            "#303149"  // 7: Other transitions
        ],
        format: "png"
    }};

    Map.addLayer(band, vis, "Accumulated Deforestation 2001–2024");
    Map.centerObject(band);
    ```
    """)


def get_markdown_deforestation_frequency():
    '''
    Generates a markdown-formatted description for the deforestation frequency product.
    '''
    return textwrap.dedent(f"""
                           
    ### Deforestation Frequency – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**
    
    This product represents the **accumulated frequency of deforestation** per pixel, based on the **suppression of primary vegetation (code {CLASS_PRIMARY_VEG_SUPPRESSION})** and **secondary vegetation (code {CLASS_SECONDARY_VEG_SUPPRESSION})**, derived from **MapBiomas {REGION_NAME.upper()}**.

    **Versions:**
    - Input version: `{VERSION_OUTPUT_DEF_SEC_VEG_FT}`
    - Output version: `{VERSION_OUTPUT_DEF_FREQ}`

    **Analyzed years:**
    - From `{YEARS[0]}` to `{YEARS[-1]}`

    **Deforestation codes considered:**
    - `{CLASS_PRIMARY_VEG_SUPPRESSION}`: Suppression of primary vegetation
    - `{CLASS_SECONDARY_VEG_SUPPRESSION}`: Suppression of secondary vegetation

    **Methodology:**
    1. A binary mask is applied to pixels equal to `{CLASS_PRIMARY_VEG_SUPPRESSION}` or `{CLASS_SECONDARY_VEG_SUPPRESSION}`.
    2. For each period `[start, end]`, the frequency is calculated using `.reduce(ee.Reducer.sum())`.
    3. The result is a multiband image, with one band per period.

    **Example band:** 
    - `deforestation_frequency_2000_2020`: Represents the total deforestation events per pixel from 2000 to 2020.

    **Exported by grid cell (1:250,000):**
    
    {', '.join([f'`{g}`' for g in GRID_NAMES])}

    **Visualization example script:**
    ```javascript
    // Define the asset path for the deforestation frequency product
    var asset = "{ASSET_DEF_FREQ}";

    // Define the version of the product to load
    var version = "{VERSION_OUTPUT_DEF_FREQ}";

    // Load the image collection and filter by the desired version
    var deforestationFreq = ee.ImageCollection(asset)
        .filter(ee.Filter.eq("version", version));

    // Select the specific band for the 2000–2020 period
    var band = deforestationFreq.select("deforestation_frequency_2000_2020");

    // Set visualization parameters for the frequency map
    var visParams = {{
        min: 0,
        max: 5,  // Adjust this value based on the actual max frequency
        palette: ["white", "yellow", "orange", "red"],
        format: 'png'
    }};

    // Display the selected band on the map
    Map.addLayer(band, visParams, "Deforestation Frequency 2000–2020");

    // Optional: Center the map view over the region
    Map.centerObject(band);
    ```
    """)


def get_markdown_secondary_vegetation_age():
    '''
    Generates a markdown-formatted description for the secondary vegetation age product.
    '''
    return textwrap.dedent(f"""
    ### Secondary Vegetation Age – MapBiomas {REGION_NAME.upper()} – Collection {COLLECTION_ID}

    **Description:**

    This product represents the **annual age of secondary vegetation per pixel**, based on the transition of land cover to secondary vegetation over time, using data from **MapBiomas {REGION_NAME.upper()} Collection {COLLECTION_ID}**.

    **Technical details:**
    - **Input version:** `{VERSION_OUTPUT_DEF_SEC_VEG_FT}`
    - **Output version:** `{VERSION_OUTPUT_SEC_VEG_AGE}`
    - **Analyzed year range:** `{YEARS[0]} to {YEARS[-1]}`

    **Transition codes used:**
    - `{CLASS_SECONDARY_VEGETATION}`: Secondary vegetation
    - `{CLASS_RECOVERY_TO_SECONDARY}`: Recovery to secondary vegetation (only in the last year of interval)

    **Methodology:**
    1. The transition image (class `{CLASS_SECONDARY_VEGETATION}` or `{CLASS_RECOVERY_TO_SECONDARY}`) is filtered by version.
    2. A binary mask is applied to pixels matching those classes.
    3. For each year, the age is incremented if the pixel remains classified as secondary vegetation.
    4. The output is a multiband image, one band per year, storing the age of secondary vegetation.

    **Example of generated band:**
    - `{AGE_BAND_PATTERN.format(year=2023)}`: Number of years a pixel has been classified as secondary vegetation up to 2023.

    **Export details:**
    - Image exported in 1:250,000 grid cells (CIM grid), with 300 m buffer to smooth tile edges.
    - Exported grid cells: {', '.join([f'`{g}`' for g in GRID_NAMES])}

    **Example visualization script:**
    ```javascript
    // Asset path for the secondary vegetation age product
    var assetCollection = "{ASSET_SEC_VEG_AGE}";
    var version = "{VERSION_OUTPUT_SEC_VEG_AGE}";

    // Load the ImageCollection and filter by version
    var svAgeCollection = ee.ImageCollection(assetCollection)
        .filter(ee.Filter.eq("version", version));

    // Get the image (only one expected per version)
    var svAgeImage = svAgeCollection.mosaic().selfMask();

    // Define the year to visualize
    var year = 2023;
    var bandName = "secondary_vegetation_age_" + year;

    // Visualization parameters
    var visParams = {{
        min: 1,
        max: 15,
        palette: [
            "#e7f8eb", "#cff2d8", "#b7ecc5", "#a0e6b2", "#88e09f", "#70da8b",
            "#59d478", "#41ce65", "#29c852", "#12c23f", "#10ae38", "#0e9b32",
            "#0c872c", "#0a7425", "#09611f"
        ],
        format: 'png'
    }};

    // Add the layer to the map
    Map.addLayer(svAgeImage.select(bandName), visParams, "SV Age " + year);

    Map.centerObject(svAgeCollection);
    ```
    """)


# ==============================
# UTILITY FUNCTIONS
# ==============================

def asset_exists(asset_id):
    """"
    Checks if an asset exists in the Earth Engine.
    Parameters:
    - asset_id: str, the full asset ID to check
    Returns:
    - bool: True if the asset exists, False otherwise
    """
    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def ensure_asset_exists(path, asset_type='ImageCollection'):
    """
    Ensure a given Earth Engine asset exists. If not, it will be created.

    Parameters:
    - path (str): Full path to the Earth Engine asset, e.g., 'projects/my-project/assets/my-imagecollection'.
    - asset_type (str): Either 'Folder' or 'ImageCollection'. Defaults to 'ImageCollection'.

    Raises:
    - ee.EEException if asset creation fails for other reasons.
    """
    try:
        ee.data.getAsset(path)
        print(f"✅ Asset already exists: {path}")
    except ee.EEException as e:
        print(f"📁 Asset does not exist: {path}")
        print(f"🛠️ Creating asset of type '{asset_type}'...")
        try:
            ee.data.createAsset({'type': asset_type}, path)
            print(f"✅ Created {asset_type}: {path}")
        except ee.EEException as create_err:
            print(f"❌ Failed to create asset: {path}")
            raise create_err

# ==============================
# EXPORT FUNCTIONS
# ==============================
def get_pyramiding_policy_mode(image):
    """
    Generates a pyramiding policy dictionary with 'MODE' for all bands in the image.

    Parameters:
        image (ee.Image): Image whose band names will be used.

    Returns:
        dict: Dictionary {band_name: 'MODE'} for all bands.
    """
    band_names = image.bandNames().getInfo()
    return {band: EXPORT_PYRAMIDING_POLICY for band in band_names}


def export_by_grid(image, asset_output, task_description_prefix, version, description):
    """
    Exports an image for each grid. Skips export if the asset already exists.
    
    Parameters:
    - image: ee.Image to export
    - asset_output: str, base asset path for exports
    - task_description_prefix: str, prefix for export task description
    - version: str, version string to attach to metadata
    - description: str, markdown description to attach to image metadata

    Returns:
    - List of started ee.batch.Export.image.toAsset tasks
    """
    grids = ee.FeatureCollection(ASSET_GRID)
    task_list = []

    for grid_name in GRID_NAMES:
        asset_id = f"{asset_output}/{grid_name}-{version}"
        task_description = f"{task_description_prefix}-{grid_name}-{version}"

        # Check if asset already exists
        if asset_exists(asset_id):
            print(f"⚠️  Skipping {task_description} (already exists).")
            continue

        grid = grids.filter(ee.Filter.stringContains('name', grid_name))
        task = ee.batch.Export.image.toAsset(
            image=image.set({
                'version': version,
                'description': description,
                'territory': REGION_NAME,
            }),
            description=task_description,
            assetId=asset_id,
            region=grid.geometry().buffer(300).bounds(),
            scale=EXPORT_SCALE,
            maxPixels=EXPORT_MAX_PIXELS,
            
            pyramidingPolicy=get_pyramiding_policy_mode(image)
        )

        print(f"▶️  Exporting {task_description}")
        task.start()
        task_list.append(task)

    return task_list


def export_transitions():
    """
    Loads and exports transition images between year pairs. Returns a list of tasks.
    """
    integration = ee.ImageCollection(ASSET_INTEGRATION)\
        .filter(ee.Filter.eq("version", VERSION_INPUT_INTEGRATION))\
        .min()

    task_list = []

    for start, end in TRANSITION_PERIODS:
        asset_id = f"{ASSET_TRANSITIONS}/mapbiomas_{REGION_NAME}_{start}_{end}_{VERSION_OUTPUT_TRANSITIONS}"
        task_description = f"mapbiomas_{REGION_NAME}_{start}_{end}_{VERSION_OUTPUT_TRANSITIONS}"

        # Check if asset already exists
        if asset_exists(asset_id):
            print(f"⚠️  Skipping {task_description} (already exists).")
            continue

        img0 = integration.select(f'{BAND_PREFIX}{start}')
        img1 = integration.select(f'{BAND_PREFIX}{end}')
        transitions = img0.multiply(100).add(img1).toInt16().rename('transitions')

        transitions = transitions.set({
            'year0': start,
            'year1': end,
            'version': VERSION_OUTPUT_TRANSITIONS,
            'theme': 'integration',
            'territory': REGION_NAME,
            'type': 'transitions',
            'description': get_markdown_transitions()
        })

        task = ee.batch.Export.image.toAsset(
            image=transitions,
            description=task_description,
            assetId=asset_id,
            region=REGION_BBOX,
            scale=EXPORT_SCALE,
            maxPixels=EXPORT_MAX_PIXELS,
            pyramidingPolicy=get_pyramiding_policy_mode(transitions)
        )

        print(f"▶️ Exporting {task_description}")
        task.start()
        task_list.append(task)

    return task_list


def export_deforestation():
    """
    Apply deforestation and secondary vegetation rules to a classification image.

    Returns:
    - ee.Image with all rules applied
    """

    # Load the integration image
    integration = ee.ImageCollection(ASSET_INTEGRATION)\
        .filter(ee.Filter.eq("version", VERSION_INPUT_INTEGRATION))\
        .select([f"{BAND_PREFIX}{year}" for year in YEARS])\
        .min()
    
    # Step 1: Aggregate class IDs according to input-output mapping
    aggregated = DeforestationSecondaryVegetation.aggregate_classes(integration, LOOKUP_IN, LOOKUP_OUT)

    processor = DeforestationSecondaryVegetation(aggregated, YEARS)

    # Step 1a: Remove 1-year vegetation blips (noise) across ALL years, on the clean
    # aggregated image. A single vegetation year between two anthropic years cannot be
    # confirmed as secondary vegetation (needs 3 years) and is reverted to anthropic —
    # consistently in the interior and the tail. Runs FIRST so the cleaned data flows
    # into the anchored windows (a real regeneration is still detected after the blip
    # is removed). Optional via RUN_VEG_BLIP_FILTER.
    if RUN_VEG_BLIP_FILTER:
        processor.apply_rules(RULES_KERNEL3_VEG_BLIP, kernel_size=3)

    # Step 1b: Anchored end-of-series rules (6-year window over the last 6 years).
    # Run FIRST, on the clean aggregated image ({0,1,2,7}), so the window patterns
    # match raw anthropic(1)/vegetation(2) and are NOT affected by classes {3,4,5,6}
    # written by the rules below (which would otherwise turn window-3 input [2,...]
    # into [3/4/5/6,...] and prevent it from matching). The 5/3 written here survive
    # all downstream rules (they match no downstream kernel_bef) and the frequency
    # correction (which only touches classes 2 and 4). Optional via RUN_SECONDARY_END_RULES.
    if RUN_SECONDARY_END_RULES:
        processor.apply_rules(RULES_KERNEL6_SECONDARY_END, kernel_size=6,
                              years_override=YEARS_SECONDARY_END)
        # Revert an unconfirmed 2-year vegetation block followed by anthropic at n
        # (interior mirrors this via the suppression(4) mechanism; the tail cannot).
        processor.apply_rules(RULES_KERNEL4_SECONDARY_END_REVERT, kernel_size=4,
                              years_override=YEARS_SECONDARY_END_REVERT)

    # Step 2: Apply 4-year deforestation rules
    processor.apply_rules(RULES_KERNEL4, kernel_size=4)

    # Step 3: Apply secondary vegetation rules (also 4-year)
    processor.apply_rules(RULES_KERNEL4_SECONDARY, kernel_size=4)

    # Step 4: Apply 3-year deforestation-in-secondary rules
    processor.apply_rules(RULES_KERNEL3_SECONDARY, kernel_size=3)

    # Step 5: Apply end-of-period rules for last four years
    processor.apply_rules(RULES_KERNEL4_END, kernel_size=4, years_override=YEARS_END)
    
    # Get processed image
    deforestation_transitions = ee.Image(processor.get_image())

    # Step 6: Apply frequency-based corrections
    freq_anthropic = DeforestationSecondaryVegetation.get_class_frequency(aggregated, class_id=1)

    deforestation_transitions = deforestation_transitions.where(
        freq_anthropic.gt(1).And(deforestation_transitions.eq(CLASS_PRIMARY_VEG_SUPPRESSION)), CLASS_SECONDARY_VEG_SUPPRESSION
    )
    deforestation_transitions = deforestation_transitions.where(
        freq_anthropic.gt(0).And(deforestation_transitions.eq(CLASS_PRIMARY_VEGETATION)), CLASS_SECONDARY_VEGETATION
    )

    # Step 7: Tail guard for unconfirmed secondary vegetation (last two years).
    # Runs independently of RUN_SECONDARY_END_RULES. Replaces the previous manual
    # last-3-years post-processing: when enabled, the anchored 6-year rules (Step 1b)
    # define the tail deterministically. Here we only strip secondary vegetation(3)
    # whose IMMEDIATE predecessor is anthropic(1) — i.e. frequency-induced, unconfirmed
    # regeneration. Sequences written by the anchored rules (window 1: n-1=5 then n=3;
    # janelas 2/3: n=5) and confirmed establishments (3 preceded by 3) are preserved,
    # since their predecessor is not anthropic.
    y1, y2, y3 = YEARS[-3], YEARS[-2], YEARS[-1]

    b1 = f'{BAND_PREFIX}{y1}'
    b2 = f'{BAND_PREFIX}{y2}'
    b3 = f'{BAND_PREFIX}{y3}'

    t1 = deforestation_transitions.select(b1)
    t2 = deforestation_transitions.select(b2)
    t3 = deforestation_transitions.select(b3)

    # n-1: strip unconfirmed secondary vegetation (predecessor n-2 is anthropic)
    t2 = t2.where(t1.eq(CLASS_ANTHROPIC).And(t2.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)

    # n: strip unconfirmed secondary vegetation (immediate predecessor n-1 is anthropic;
    # uses the updated t2 so the strip cascades over consecutive unconfirmed years)
    t3 = t3.where(t2.eq(CLASS_ANTHROPIC).And(t3.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)

    deforestation_transitions = deforestation_transitions.addBands(t2.rename(b2), overwrite=True)
    deforestation_transitions = deforestation_transitions.addBands(t3.rename(b3), overwrite=True)

    return export_by_grid(
        image=deforestation_transitions,
        asset_output=ASSET_DEF_SEC_VEG,
        task_description_prefix='deforestation-secondary-vegetation',
        version=VERSION_OUTPUT_DEF_SEC_VEG,
        description=get_markdown_deforestation()
    )


def export_deforestation_filtered():
    """
    Applies spatial filters to deforestation and secondary vegetation transitions to remove small patches.

    - Filters areas smaller than defined thresholds using connected pixel count.
    - Specific exceptions are applied for recent years.
    - Transitions are reclassified to class 7 (Other transitions) when filtered.
    - Returns a list of export tasks per 1:250,000 grid cell.
    """
    # Load the deforestation transitions image
    transitions = ee.ImageCollection(ASSET_DEF_SEC_VEG) \
        .filter(ee.Filter.eq("version", VERSION_OUTPUT_DEF_SEC_VEG)) \
        .min()

    # Generate deforestation mask (classes 4 and 6)
    df_mask = ee.ImageCollection([
        transitions.select(f"{BAND_PREFIX}{year}")
            .remap([CLASS_PRIMARY_VEG_SUPPRESSION, CLASS_SECONDARY_VEG_SUPPRESSION], [1, 1], 0)
            .rename("deforestation_mask")
        for year in YEARS
    ]).reduce(ee.Reducer.anyNonZero())

    # Generate secondary vegetation mask (classes 3 and 5)
    sv_mask = ee.ImageCollection([
        transitions.select(f"{BAND_PREFIX}{year}")
            .remap([CLASS_SECONDARY_VEGETATION, CLASS_RECOVERY_TO_SECONDARY], [1, 1], 0)
            .rename("secondary_vegetation_mask")
        for year in YEARS
    ]).reduce(ee.Reducer.max())

    # Exceptions: recent years that use a larger filter threshold
    df_mask_exception = ee.ImageCollection([
        transitions.select(f"{BAND_PREFIX}{year}")
            .remap([CLASS_PRIMARY_VEG_SUPPRESSION, CLASS_SECONDARY_VEG_SUPPRESSION], [1, 1], 0)
            .rename("deforestation_mask_exception")
        for year in YEARS_EXCEPTION
    ]).reduce(ee.Reducer.anyNonZero())

    # Connected pixel analysis
    df_connected = df_mask.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)
    sv_connected = sv_mask.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)
    df_connected_exception = df_mask_exception.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)

    # Apply filters using configuration constants
    filtered = transitions

    # Deforestation filters
    filtered = filtered.where(
        df_connected.lte(GROUP_SIZE_FILTER)
                    .And(filtered.eq(CLASS_PRIMARY_VEG_SUPPRESSION)), 
        CLASS_OTHER_TRANSITIONS)

    # Deforestation in secondary vegetation filters
    filtered = filtered.where(
        df_connected.lte(GROUP_SIZE_FILTER)
                    .And(filtered.eq(CLASS_SECONDARY_VEG_SUPPRESSION)), 
        CLASS_OTHER_TRANSITIONS)
    
    # Secondary vegetation filters
    filtered = filtered.where(
        sv_connected.lte(GROUP_SIZE_FILTER)
                    .And(filtered.eq(CLASS_SECONDARY_VEGETATION)), 
        CLASS_OTHER_TRANSITIONS)
    
    # Recovery to secondary vegetation filters
    filtered = filtered.where(
        sv_connected.lte(GROUP_SIZE_FILTER)
                    .And(filtered.eq(CLASS_RECOVERY_TO_SECONDARY)), 
        CLASS_OTHER_TRANSITIONS)

    # Apply exception filters for specified years
    for year in YEARS_EXCEPTION:
        band = f"{BAND_PREFIX}{year}"
        filtered_last = filtered.select(band)
        
        filtered_last = filtered_last.where(
            df_connected_exception.lte(GROUP_SIZE_EXCEPTION_FILTER)
                                  .And(filtered_last.eq(CLASS_PRIMARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered_last = filtered_last.where(
            df_connected_exception.lte(GROUP_SIZE_EXCEPTION_FILTER)
                                  .And(filtered_last.eq(CLASS_SECONDARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered = filtered.addBands(filtered_last.rename(band), overwrite=True)

    filtered = filtered.set({
        'group_size_filter': GROUP_SIZE_FILTER,
        'group_size_exception_filter': GROUP_SIZE_EXCEPTION_FILTER,
        'years_exception': YEARS_EXCEPTION
    })

    return export_by_grid(
        image=filtered,
        asset_output=ASSET_DEF_SEC_VEG_FT,
        task_description_prefix='deforestation-secondary-vegetation-ft',
        version=VERSION_OUTPUT_DEF_SEC_VEG_FT,
        description=get_markdown_deforestation_filtered()
    )


def export_deforestation_filtered_no_accumulation():

    # Load the deforestation transitions image
    transitions = ee.ImageCollection(ASSET_DEF_SEC_VEG) \
        .filter(ee.Filter.eq("version", VERSION_OUTPUT_DEF_SEC_VEG)) \
        .min()
    
    filtered = []
    for year in YEARS:
        band = f"{BAND_PREFIX}{year}"
        
        df_mask = (transitions.select(band)
                           .remap([CLASS_PRIMARY_VEG_SUPPRESSION, CLASS_SECONDARY_VEG_SUPPRESSION], [1, 1], 0))
        
        sv_mask = (transitions.select(band)
                           .remap([CLASS_SECONDARY_VEGETATION, CLASS_RECOVERY_TO_SECONDARY], [1, 1], 0))

        df_connected = df_mask.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)
        sv_connected = sv_mask.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)

        filtered_band = transitions.select(band)
        
        filtered_band = filtered_band.where(
            df_connected.lte(GROUP_SIZE_FILTER)
                        .And(filtered_band.eq(CLASS_PRIMARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered_band = filtered_band.where(
            df_connected.lte(GROUP_SIZE_FILTER)
                        .And(filtered_band.eq(CLASS_SECONDARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered_band = filtered_band.where(
            sv_connected.lte(GROUP_SIZE_FILTER)
                        .And(filtered_band.eq(CLASS_SECONDARY_VEGETATION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered_band = filtered_band.where(
            sv_connected.lte(GROUP_SIZE_FILTER)
                        .And(filtered_band.eq(CLASS_RECOVERY_TO_SECONDARY)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered.append(filtered_band.rename(band))


    filtered = ee.Image.cat(filtered)

    # Apply exception filters for specified years
    for year in YEARS_EXCEPTION:
        band = f"{BAND_PREFIX}{year}"
        filtered_last = filtered.select(band)
        
        df_mask = (transitions.select(band)
                    .remap([CLASS_PRIMARY_VEG_SUPPRESSION, CLASS_SECONDARY_VEG_SUPPRESSION], [1, 1], 0))
        
        df_connected_exception = df_mask.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)

        filtered_last = filtered_last.where(
            df_connected_exception.lte(GROUP_SIZE_EXCEPTION_FILTER)
                                  .And(filtered_last.eq(CLASS_PRIMARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered_last = filtered_last.where(
            df_connected_exception.lte(GROUP_SIZE_EXCEPTION_FILTER)
                                  .And(filtered_last.eq(CLASS_SECONDARY_VEG_SUPPRESSION)), 
            CLASS_OTHER_TRANSITIONS)
        
        filtered = filtered.addBands(filtered_last.rename(band), overwrite=True)

    filtered = filtered.set({
        'group_size_filter': GROUP_SIZE_FILTER,
        'group_size_exception_filter': GROUP_SIZE_EXCEPTION_FILTER,
        'years_exception': YEARS_EXCEPTION
    })

    return export_by_grid(
        image=filtered,
        asset_output=ASSET_DEF_SEC_VEG_FT,
        task_description_prefix='deforestation-secondary-vegetation-ft',
        version=VERSION_OUTPUT_DEF_SEC_VEG_FT,
        description=get_markdown_deforestation_filtered()
    )


def export_deforestation_annual():
    '''
    Exports an annual map with transition codes (deforestation, regeneration),
    combining the transition image with the corresponding years of integration.

    The integration uses the year prior to the start of the deforestation series
    up to the penultimate year (e.g., 1999 to 2023, if YEARS = 2000–2024).
    '''
    # Generates a list of transition bands from second year to the last year
    transitions_years = YEARS[1:]
    transitions_bands = [f'{BAND_PREFIX}{year}' for year in transitions_years]

    transitions = ee.ImageCollection(ASSET_DEF_SEC_VEG_FT) \
        .filter(ee.Filter.eq("version", VERSION_OUTPUT_DEF_SEC_VEG_FT)) \
        .select(transitions_bands) \
        .min()
    
    # Generates a list of integration bands from the first year to the penultimate year
    integration_years = YEARS[:-1]
    integration_bands = [f'{BAND_PREFIX}{year}' for year in integration_years]

    # Selects the bands by name, avoiding fragile numerical slicing
    integration = ee.ImageCollection(ASSET_INTEGRATION)\
        .filter(ee.Filter.eq("version", VERSION_INPUT_INTEGRATION))\
        .select(integration_bands)\
        .min()
    
    # Final image composition: transition * 100 + integration
    composite = transitions.multiply(100).add(integration)

    return export_by_grid(
        image=composite,
        asset_output=ASSET_DEF_SEC_VEG_ANN,
        task_description_prefix='deforestation-annual',
        version=VERSION_OUTPUT_DEF_SEC_VEG_ANN,
        description=get_markdown_deforestation_annual()
    )


def export_deforestation_accumulated():
    """
    Exports accumulated deforestation (classes 4 and 6) and accumulated secondary vegetation (classes 3 and 5)
    for all defined year periods using firstNonNull logic.
    """
    image = (
        ee.ImageCollection(ASSET_DEF_SEC_VEG_ANN)
        .filter(ee.Filter.eq('version', VERSION_OUTPUT_DEF_SEC_VEG_ANN))
        .min()
    )

    # Transitions encoded as XXX, where XXX // 100 = class (e.g., 400, 600, 300, 500)
    transitions = image.divide(100).byte()

    # Boolean masks for each class type
    deforestation_pv_mask = transitions.eq(CLASS_PRIMARY_VEG_SUPPRESSION)
    deforestation_sv_mask = transitions.eq(CLASS_SECONDARY_VEG_SUPPRESSION)
    secondary_veg_mask = transitions.eq(CLASS_SECONDARY_VEGETATION)
    secondary_veg_recovery_mask = transitions.eq(CLASS_RECOVERY_TO_SECONDARY)

    # List of periods (e.g. [(1985, 1990), (1991, 2000), ...])
    periods = ee.List(PERIODS_ALL_YEARS)

    def process_period(p, image_acc):
        p = ee.List(p)
        start = ee.Number(p.get(0))
        end = ee.Number(p.get(1))
        years = ee.List.sequence(start, end)
        bands = years.map(lambda y: ee.String(BAND_PREFIX).cat(ee.Number(y).format('%.0f')))
        last_band = ee.String(BAND_PREFIX).cat(end.format('%.0f'))

        # Deforestation: firstNonNull (PV first, fallback SV)
        deforestation_pv = (
            image.updateMask(deforestation_pv_mask)
                 .select(bands)
                 .reduce(ee.Reducer.firstNonNull())
        )

        deforestation_sv = (
            image.updateMask(deforestation_sv_mask)
                 .select(bands)
                 .reduce(ee.Reducer.firstNonNull())
        )

        deforestation_acc = (
            deforestation_pv.unmask(deforestation_sv)
                            .rename(ee.String(ACCUM_BAND_PATTERN_DEF)
                                       .replace('{start}', start.format('%.0f'))
                                       .replace('{end}', end.format('%.0f')))
        )

        # Secondary vegetation: firstNonNull + recovery year
        secondary_veg = (
            image.updateMask(secondary_veg_mask)
                 .select(bands)
                 .reduce(ee.Reducer.firstNonNull())
        )

        secondary_veg_recovery = (
            image.updateMask(secondary_veg_recovery_mask)
                 .select([last_band])
        )

        secondary_veg_acc = (
            secondary_veg.unmask(secondary_veg_recovery)
                         .rename(ee.String(ACCUM_BAND_PATTERN_SV)
                                     .replace('{start}', start.format('%.0f'))
                                     .replace('{end}', end.format('%.0f')))
        )

        return ee.Image(image_acc).addBands(deforestation_acc).addBands(secondary_veg_acc)

    # Apply the function to every period
    accum_images = periods.iterate(process_period, ee.Image().select())

    # Concatenate all generated bands
    result = ee.Image(accum_images).selfMask()

    return export_by_grid(
        image=result,
        asset_output=ASSET_DEF_SEC_VEG_ACC,
        task_description_prefix='deforestation-accumulated',
        version=VERSION_OUTPUT_DEF_SEC_VEG_ACC,
        description=get_markdown_deforestation_accumulated()
    )


def export_deforestation_frequency():
    """
    Exports accumulated deforestation frequency by summing binary occurrence
    of deforestation (classes 4 and 6) across all defined year ranges.

    Returns:
        list: A list of Earth Engine export tasks, one per grid.
    """
    image = (
        ee.ImageCollection(ASSET_DEF_SEC_VEG_FT)
        .filter(ee.Filter.eq('version', VERSION_OUTPUT_DEF_SEC_VEG_FT))
        .min()
    )

    mask = image.eq(CLASS_PRIMARY_VEG_SUPPRESSION).Or(
        image.eq(CLASS_SECONDARY_VEG_SUPPRESSION)
    )

    # Convert the list of periods to ee.List for iterate
    periods = ee.List(PERIODS_ALL_YEARS)

    def compute_frequency(period, image_freq):
        # Extract start and end from the year pair
        period = ee.List(period)
        start = ee.Number(period.get(0))
        end = ee.Number(period.get(1))

        # List of bands for the period
        bands = ee.List.sequence(start, end).map(lambda y: ee.String(BAND_PREFIX).cat(ee.Number(y).format('%.0f')))
        
        # Sum the selected bands and rename the band with the expected pattern
        freq = mask.select(bands).reduce(ee.Reducer.sum()).rename(
            ee.String(FREQ_BAND_PATTERN).replace('{start}', start.format('%.0f')).replace('{end}', end.format('%.0f'))
        )

        return ee.Image(image_freq).addBands(freq)

    # Compute the frequency for each period
    freq_list = periods.iterate(compute_frequency, ee.Image().select())

    # Concatenate the bands into one image and apply selfMask. The sum of masks comes out
    # int64; the maximum is the number of years in the period (39), so it fits in uint8.
    result = ee.Image(freq_list).selfMask().toUint8()

    return export_by_grid(
        image=result,
        asset_output=ASSET_DEF_FREQ,
        task_description_prefix='deforestation-frequency',
        version=VERSION_OUTPUT_DEF_FREQ,
        description=get_markdown_deforestation_frequency(),
    )


def export_secondary_vegetation_age():
    """
    Exports the annual age of secondary vegetation per pixel (accumulation of class 3 and 5).
    
    The age increases each year a pixel remains in class 3 or 5 (secondary vegetation or recovery).
    Resets to zero when pixel exits these classes.
    """
    # Load the transitions image and build a binary mask for classes 3 and 5
    transitions = (
        ee.ImageCollection(ASSET_DEF_SEC_VEG_FT)
        .filter(ee.Filter.eq("version", VERSION_OUTPUT_DEF_SEC_VEG_FT))
        .min()
    )

    sv = transitions.eq(CLASS_SECONDARY_VEGETATION).Or(
        transitions.eq(CLASS_RECOVERY_TO_SECONDARY)
    )

    # Accumulate the age with a client-side loop: YEARS is a Python list known when the
    # graph is built, so there is no reason for a server-side iterate/ee.Algorithms.If
    # (the previous version broke at index 0, because ee.List.get(-1) wraps around and
    # returned the last year, selecting a band that does not exist in the empty image).
    age_bands = []
    previous_age = None

    for year in YEARS:
        sv_year = sv.select([f'{BAND_PREFIX}{year}']).unmask()

        if previous_age is None:
            age = sv_year
        else:
            # age(t) = (age(t-1) + sv(t)) * sv(t)
            # resets to zero when the pixel stops being secondary vegetation
            age = previous_age.add(sv_year).multiply(sv_year)

        age_bands.append(age.rename(AGE_BAND_PATTERN.format(year=year)))
        previous_age = age

    # Maximum age = len(YEARS) years, fits in uint8
    age_image = ee.Image.cat(age_bands).toUint8()

    return export_by_grid(
        image=age_image,
        asset_output=ASSET_SEC_VEG_AGE,
        task_description_prefix='secondary-vegetation-age',
        version=VERSION_OUTPUT_SEC_VEG_AGE,
        description=get_markdown_secondary_vegetation_age()
    )


# ==============================
# MODULAR EXECUTION
# ==============================
def run_pipeline():
    """
    PIPELINE EXECUTION
    - Ensure all required assets exist.
    - Executes all export tasks managing dependencies between them.

    The exports are organized into dependent and independent groups:

    DEPENDENT TASKS:
    - Deforestation Transitions (RUN_DEF):
        Processes the integration classification image using temporal rules to detect deforestation
        and secondary vegetation dynamics. Outputs multi-band images with transitions per year.
        This step is required before exporting annual deforestation.

    - Filtered Deforestation Transitions (RUN_DEF_FT):
        Applies spatial filters to the deforestation transitions to remove small patches and noise.
        Outputs a filtered version of the transitions, which is required before exporting annual deforestation.

    - Annual Deforestation (RUN_DEF_ANNUAL):
        Waits for the deforestation transition exports to finish. Combines the transition image
        with the integration map to create encoded annual deforestation maps. Each year's band
        represents a deforestation or regeneration transition combined to the integration map.

    - Accumulated Deforestation (RUN_DEF_ACCUMULATED):
        Waits for the annual deforestation exports to finish. Computes accumulated maps of
        deforestation and secondary vegetation for multiple periods.

    INDEPENDENT TASKS:
    - Transitions from integration (RUN_TRANSITIONS)
    - Deforestation Frequency (RUN_DEF_FREQUENCY)
    - Secondary Vegetation Age (RUN_SV_AGE)

    All exports are performed per 1:250,000 grid cell with buffer and versioning.
    """

    # Starts the export process
    print("🚀 Starting exports...")
    tasks_independent = []
    tasks_def_transition = []
    tasks_def_transition_ft = []
    tasks_def_annual = []

    # Step 1 — Process and export deforestation transitions (required before filtered and annual)
    if RUN_DEF:
        print("\n📦 Exporting TRANSITIONS OF DEFORESTATION AND SECONDARY VEGETATION")
        ensure_asset_exists(ASSET_DEF_SEC_VEG)
        tasks_def_transition = export_deforestation()

        print("\n📦 Waiting for transition exports before running FILTERED...")
        wait_until_tasks_finish(tasks_def_transition, polling_interval=60)

    # Step 2 — Process and export filtered deforestation transitions (required before annual)
    if RUN_DEF_FT:
        print("\n📦 Exporting FILTERED TRANSITIONS OF DEFORESTATION AND SECONDARY VEGETATION")
        ensure_asset_exists(ASSET_DEF_SEC_VEG_FT)
        # tasks_def_transition_ft = export_deforestation_filtered()
        tasks_def_transition_ft = export_deforestation_filtered_no_accumulation()
        
        print("\n📦 Waiting for transition exports before running ANNUAL...")
        wait_until_tasks_finish(tasks_def_transition_ft, polling_interval=60)

    # Step 3 — Export annual classification (only after deforestation transitions finish)
    if RUN_DEF_ANNUAL:
        print("\n📦 Exporting ANNUAL DEFORESTATION AND SECONDARY VEGETATION")
        ensure_asset_exists(ASSET_DEF_SEC_VEG_ANN)
        tasks_def_annual = export_deforestation_annual()

    # Step 4 — Start independent exports in parallel
    if RUN_DEF_FREQUENCY:
        print("\n📦 Exporting DEFORESTATION FREQUENCY")
        ensure_asset_exists(ASSET_DEF_FREQ)
        tasks_independent += export_deforestation_frequency()

    if RUN_SV_AGE:
        print("\n📦 Exporting SECONDARY VEGETATION AGE")
        ensure_asset_exists(ASSET_SEC_VEG_AGE)
        tasks_independent += export_secondary_vegetation_age()

    if RUN_TRANSITIONS:
        print("\n📦 Exporting LULC TRANSITIONS")
        ensure_asset_exists(ASSET_TRANSITIONS)
        tasks_independent += export_transitions()

    # Step 5 — Monitor parallel groups
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_annual = executor.submit(wait_until_tasks_finish, export_tasks=tasks_def_annual, polling_interval=60)
        future_independent = executor.submit(wait_until_tasks_finish, export_tasks=tasks_independent, polling_interval=60)

        # Step 6 — Export accumulated only after annual is done
        future_annual.result()
        if RUN_DEF_ACCUMULATED:
            print("\n📦 Exporting ACCUMULATED DEFORESTATION AND SECONDARY VEGETATION")
            ensure_asset_exists(ASSET_DEF_SEC_VEG_ACC)
            tasks_accumulated = export_deforestation_accumulated()
            wait_until_tasks_finish(export_tasks=tasks_accumulated, polling_interval=60)

        future_independent.result()

    print("\n✅ All export routines completed.")


if __name__ == "__main__":
    run_pipeline()

