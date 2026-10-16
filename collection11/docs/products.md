# Produtos — Collection 11

**MapBiomas Brasil · Desmatamento e Vegetação Secundária · série 1985–2025**

As regras temporais estão em [temporal-rules.md](temporal-rules.md). Este documento descreve o que
sai delas: a cadeia de produtos internos, o que foi publicado e como cada pixel é codificado.

---

## 1. Cadeia de processamento

Todos os produtos são gerados por
[`mapbiomas_brazil_deforestation_secondary_vegetation.py`](../mapbiomas_brazil_deforestation_secondary_vegetation.py),
exportados por bloco da CIM 1:1.000.000 (49 blocos, com buffer de 300 m), a 30 m, com pirâmide
`MODE`. Cada etapa grava uma `ImageCollection` em
`projects/mapbiomas-brazil/assets/LAND-COVER/COLLECTION-11/DEFORESTATION/` e é filtrada pela
propriedade `version` na etapa seguinte.

```
integração C11 (classification-ft, 0-4-14-c84-5)
  └─ RUN_DEF              deforestation-secondary-vegetation          regras temporais
      └─ RUN_DEF_FT       deforestation-secondary-vegetation-ft       filtro espacial (11 px, ano a ano)
          ├─ RUN_DEF_ANNUAL       …-annual                            transição*100 + cobertura(ano-1)
          │   └─ RUN_DEF_ACCUMULATED  …-accumulated                   primeiro evento por período
          ├─ RUN_DEF_FREQUENCY    deforestation-frequency             nº de anos com desmatamento
          └─ RUN_SV_AGE           secondary-vegetation-age            anos contínuos em veg. secundária
```

| Constante | Valor na C11 |
|---|---|
| `VERSION_INPUT_INTEGRATION` | `0-4-14-c84-5` |
| `VERSION_OUTPUT_*` (todos os produtos) | `0-4-14-c84-5-2` |
| `YEARS` | 1985–2025 (41 anos) |
| `GROUP_SIZE_FILTER` / `GROUP_SIZE_EXCEPTION_FILTER` | 11 / 11 pixels |
| `PERIODS_ALL_YEARS` | todos os pares `[início, fim]` com início em 1987–2025 — 780 períodos |

O export **pula** asset que já existe. Uma rodada nova exige subir `VERSION_OUTPUT_*`.

---

## 2. Legenda das transições

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

A agregação das classes de cobertura nesses códigos está em `CLASS_LOOKUP`, no topo do script, e
em [temporal-rules.md §1.1](temporal-rules.md#11-agregação-das-classes-originais).

---

## 3. Por que a série pública começa em 1987

As regras que escrevem as classes 3 e 5 têm `min_start=1`: precisam de um ano de histórico antes
da janela. 1985 e 1986 são, portanto, anos de **aquecimento** — o pipeline os processa, mas o
dado público começa em 1987. Ver [temporal-rules.md §4](temporal-rules.md#4-o-parâmetro-min_start).

---

## 4. Assets públicos

Pasta: `projects/mapbiomas-public/assets/brazil/lulc/collection11/`, leitura pública.
Conferido no Earth Engine em 15/10/2026.

| Asset | Bandas | Tipo | Conteúdo |
|---|---|---|---|
| `mapbiomas_brazil_collection11_deforestation_secondary_vegetation_v5` | 39 — `classification_1987` … `classification_2025` | `uint8` | Transições filtradas (códigos 0–7). **Produto oficial da C11** |
| `mapbiomas_brazil_collection11_deforestation_secondary_vegetation_by_coverage_v1` | 39 — `classification_1987` … `classification_2025` | `uint16` | `transição*100 + cobertura(ano-1)` |

- O `v5` é o produto `…-ft` (rodada `0-4-14-c84-5-2`) recortado para 1987–2025 e mosaicado.
  O `v4` saiu só até 2024 e foi despublicado em 18/08/2026.
- No `by_coverage`, os **dois dígitos da cobertura** usam a legenda pública da C11
  (`coverage_v3`), que publica a classe 13 como **77** — o asset grava
  `class_remap="13->77"` e `pixel_encoding="transition*100 + coverage(year-1)"`. Exemplo: `477` é
  supressão de vegetação primária (4) num pixel que no ano anterior era a classe 77.
- **Não publicados:** acumulado, frequência e idade da vegetação secundária da C11 existem só como
  assets internos (rodada `0-4-14-c84-5-2`).

Leitura no Code Editor:

```javascript
var asset = 'projects/mapbiomas-public/assets/brazil/lulc/collection11/' +
            'mapbiomas_brazil_collection11_deforestation_secondary_vegetation_v5';
var image = ee.Image(asset);

var palette = ['#ffffff', '#faf5d1', '#3f7849', '#5bcf20', '#ea1c1c', '#b4f792', '#fe9934', '#303149'];
Map.addLayer(image.select('classification_2025'), {min: 0, max: 7, palette: palette}, 'Def/Sec Veg 2025');
```

---

## 5. Codificação de cada produto

### 5.1 Transições (`…-secondary-vegetation`, `…-ft`, público `v5`)

Uma banda `classification_{ano}` por ano, códigos 0–7 da seção 2. O `-ft` difere do bruto apenas
pelo filtro espacial: manchas de desmatamento (4, 6) ou de vegetação secundária (3, 5) com até 11
pixels conectados no **mesmo ano** viram 7.

### 5.2 Anual cruzado com a cobertura (`…-annual`, público `by_coverage_v1`)

`classification_{ano} = transição(ano) * 100 + cobertura(ano - 1)`. A cobertura é a do ano
**anterior**, que é o que diz *o que* foi suprimido ou de onde a vegetação secundária partiu. O
interno começa em 1986 (o primeiro ano com cobertura anterior) e usa os códigos de cobertura
internos (13); o público, em 1987 e com o remap `13 → 77`.

### 5.3 Acumulado (`…-accumulated`, interno)

Para cada um dos 780 períodos, duas bandas:

- `deforestation_accumulated_{início}_{fim}` — o valor anual (5.2) do **primeiro** desmatamento no
  período; supressão de vegetação primária (4xx) tem precedência sobre a de secundária (6xx);
- `secondary_vegetation_accumulated_{início}_{fim}` — o valor anual da primeira ocorrência de
  vegetação secundária (3xx) no período; na falta, a recuperação (5xx) do último ano.

1.560 bandas, com máscara onde não há evento.

### 5.4 Frequência (`deforestation-frequency`, interno)

`deforestation_frequency_{início}_{fim}`: quantos anos do período o pixel teve classe 4 ou 6.
780 bandas, `uint8`, com máscara onde a frequência é zero.

### 5.5 Idade da vegetação secundária (`secondary-vegetation-age`, interno)

`secondary_vegetation_age_{ano}` — anos consecutivos em classe 3 ou 5 até aquele ano, zerando
quando o pixel sai dessas classes: `idade(t) = (idade(t-1) + sv(t)) * sv(t)`. 41 bandas, `uint8`.
Note o prefixo das bandas: **não** é `classification_`.
