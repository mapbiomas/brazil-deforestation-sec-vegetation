# MapBiomas Brazil — Deforestation and Secondary Vegetation

Code for MapBiomas Brazil's annual mapping of **native vegetation suppression** and **secondary
vegetation**, derived from the land use and land cover maps by temporal rules applied pixel by
pixel.

| Collection | Series | Implementation | Folder |
|---|---|---|---|
| **Collection 11** | 1985–2025 (public from 1987) | Python, Earth Engine API | [`collection11/`](collection11/) |
| Collection 9 | 1985–2023 | JavaScript, Code Editor | [`collection9/`](collection9/) |

Start with [Collection 11](collection11/README.md).

## Classes

| Code | Class |
|---|---|
| 0 | No data |
| 1 | Anthropic |
| 2 | Primary vegetation |
| 3 | Secondary vegetation |
| 4 | Primary vegetation suppression |
| 5 | Recovery to secondary vegetation |
| 6 | Secondary vegetation suppression |
| 7 | Other transitions |

## Public data

`projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_deforestation_secondary_vegetation_v5`
— one `classification_{year}` band per year, 1987–2025. See
[collection11/docs/products.md](collection11/docs/products.md).
