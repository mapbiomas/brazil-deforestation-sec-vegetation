# Collection 11 — Desmatamento e Vegetação Secundária

Pipeline da Collection 11 do MapBiomas Brasil (série 1985–2025), em Python, sobre a API do Google
Earth Engine. Substitui os scripts JavaScript da [Collection 9](../collection9/).

| Arquivo | O que é |
|---|---|
| [`mapbiomas_brazil_deforestation_secondary_vegetation.py`](mapbiomas_brazil_deforestation_secondary_vegetation.py) | Pipeline: configuração, regras, filtro espacial e export de todos os produtos |
| [`deforestation_secondary_vegetation.py`](deforestation_secondary_vegetation.py) | Classe que aplica as regras de janela temporal (kernels de 3, 4 e 6 anos) |
| [`tests/test_rules.py`](tests/test_rules.py) | Testes offline da semântica das regras |
| [`docs/temporal-rules.md`](docs/temporal-rules.md) | As regras, a ordem em que rodam e o comportamento no fim da série |
| [`docs/products.md`](docs/products.md) | Produtos gerados, codificação dos pixels e assets públicos |

## O método em uma página

1. **Agregação.** As classes de cobertura da integração C11 viram três estados: antrópico (1),
   vegetação (2) e outras (7). A tabela está em `CLASS_LOOKUP`.
2. **Regras temporais.** Janelas deslizantes de 3, 4 e 6 anos reescrevem a série de cada pixel:
   a supressão de vegetação primária (4) exige confirmação de dois anos antrópicos; a vegetação
   secundária (3) exige três anos de vegetação depois de uso antrópico, e o ano de recuperação é
   marcado com 5; a supressão de vegetação secundária é 6.
3. **Correção por frequência.** Vegetação num pixel que já foi antrópico é secundária, não
   primária.
4. **Fim da série.** Os últimos anos não têm anos seguintes para confirmar nada. Janelas ancoradas
   de 6 anos detectam regeneração em curso, e uma guarda de cauda remove vegetação secundária
   não confirmada.
5. **Filtro espacial.** Manchas de até 11 pixels (~1 ha), ano a ano, viram "outras transições" (7).
6. **Produtos derivados.** Anual cruzado com a cobertura, acumulado por período, frequência de
   desmatamento e idade da vegetação secundária.

O que mudou em relação à Collection 9: `min_start` obrigatório em toda regra (evita vegetação
secundária espúria em 1985–1986), janelas ancoradas de fim de série, filtro de blip de um ano,
reversão ancorada de bloco de dois anos e filtro espacial ano a ano. O histórico está em
[temporal-rules.md §11](docs/temporal-rules.md#11-histórico-de-problemas-resolvidos).

## Dado publicado

| Asset (`projects/mapbiomas-public/assets/brazil/lulc/collection11/`) | Período |
|---|---|
| `mapbiomas_brazil_collection11_deforestation_secondary_vegetation_v5` | 1987–2025 |
| `mapbiomas_brazil_collection11_deforestation_secondary_vegetation_by_coverage_v1` | 1987–2025 |

Detalhes, codificação e exemplo de uso em [docs/products.md](docs/products.md).

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt

# testes das regras: offline, sem credencial
python -m pytest tests -v

# pipeline: exige acesso de escrita ao projeto mapbiomas-brazil
earthengine authenticate
EE_PROJECT=mapbiomas-brazil python mapbiomas_brazil_deforestation_secondary_vegetation.py
```

Todas as flags `RUN_*` vêm desligadas: a rodada da C11 (`0-4-14-c84-5-2`) já está materializada,
e o export pula asset existente. Para uma rodada nova, suba os `VERSION_OUTPUT_*` e ligue as etapas
na ordem descrita em [docs/products.md](docs/products.md#1-cadeia-de-processamento).

## Origem

Código copiado do repositório interno de pipelines do MapBiomas (`mapbiomas-pipeline`, commit
`c50594f`, 15/10/2026). As regras e o processamento são os mesmos; mudaram só os imports, o projeto
do Earth Engine (variável `EE_PROJECT`) e a grade do Brasil, que passou a estar no próprio script.
