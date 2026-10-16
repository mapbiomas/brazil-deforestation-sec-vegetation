# MapBiomas Brasil — Desmatamento e Vegetação Secundária

Código do mapeamento anual de **supressão de vegetação nativa** e **vegetação secundária** do
MapBiomas Brasil, derivado dos mapas de cobertura e uso da terra por regras temporais aplicadas
pixel a pixel.

| Coleção | Série | Implementação | Pasta |
|---|---|---|---|
| **Collection 11** | 1985–2025 (público a partir de 1987) | Python, Earth Engine API | [`collection11/`](collection11/) |
| Collection 9 | 1985–2023 | JavaScript, Code Editor | [`collection9/`](collection9/) |

Comece pela [Collection 11](collection11/README.md).

## Classes

| Código | Classe |
|---|---|
| 0 | Sem dado |
| 1 | Antrópico |
| 2 | Vegetação primária |
| 3 | Vegetação secundária |
| 4 | Supressão de vegetação primária |
| 5 | Recuperação para vegetação secundária |
| 6 | Supressão de vegetação secundária |
| 7 | Outras transições |

## Dado público

`projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_deforestation_secondary_vegetation_v5`
— uma banda `classification_{ano}` por ano, 1987–2025. Ver
[collection11/docs/products.md](collection11/docs/products.md).
