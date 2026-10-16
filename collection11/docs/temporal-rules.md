# Desmatamento & Vegetação Secundária — Regras Temporais

**MapBiomas Brasil · Collection 11 · série 1985–2025 (41 anos)**

Este documento descreve as regras temporais aplicadas para detectar desmatamento e dinâmica de
vegetação secundária. As regras são implementadas em
[`deforestation_secondary_vegetation.py`](../deforestation_secondary_vegetation.py)
e invocadas por `export_deforestation()` em
[`mapbiomas_brazil_deforestation_secondary_vegetation.py`](../mapbiomas_brazil_deforestation_secondary_vegetation.py).

A entrada é a imagem de integração da Collection 11 (`INTEGRATION/classification-ft`, filtrada pela
versão em `VERSION_INPUT_INTEGRATION`), com uma banda `classification_{ano}` por ano. A saída tem as
mesmas bandas, preenchidas com os 8 códigos simplificados da seção 1.

> **Revisão 2** (11/08/2026). A revisão 1 descrevia a Collection 10.1, série até 2024 e quatro grupos
> de regras — ver [§11](#11-histórico-de-problemas-resolvidos) para o que mudou e por quê.

---

## Índice

- [1. Legenda de classes](#1-legenda-de-classes)
- [2. Formato das regras](#2-formato-das-regras)
- [3. Tamanhos de kernel e janelas ancoradas](#3-tamanhos-de-kernel-e-janelas-ancoradas)
- [4. O parâmetro `min_start`](#4-o-parâmetro-min_start)
- [5. Ordem de processamento](#5-ordem-de-processamento)
- [6. Grupos de regras](#6-grupos-de-regras)
- [7. Pós-processamento](#7-pós-processamento)
- [8. Comportamento no fim da série](#8-comportamento-no-fim-da-série)
- [9. Validação e testes](#9-validação-e-testes)
- [10. O que vem depois das regras temporais](#10-o-que-vem-depois-das-regras-temporais)
- [11. Histórico de problemas resolvidos](#11-histórico-de-problemas-resolvidos)
- [12. Referência rápida](#12-referência-rápida--todas-as-regras-em-ordem-de-execução)

---

## 1. Legenda de classes

Códigos simplificados usados internamente pelo pipeline de desmatamento, depois da agregação a
partir da classificação original do MapBiomas via `aggregate_classes()`.

| ID | Nome | Cor | Descrição |
|----|------|-----|-----------|
| 0 | No Data | `#FFFFFF` | Pixels não observados ou mascarados |
| 1 | Anthropic | `#FAF5D1` | Qualquer uso antrópico (pastagem, agricultura, urbano, mineração…) |
| 2 | Primary Veg. | `#C7E4CB` | Vegetação nativa sem histórico antrópico anterior |
| 3 | Secondary Veg. | `#5BCF20` | Regeneração sobre área anteriormente antrópica |
| 4 | Primary Suppression | `#EA1C1C` | Evento confirmado de supressão de vegetação primária |
| 5 | Recovery to Secondary | `#B4F792` | Primeiro ano de regeneração após uso antrópico |
| 6 | Secondary Suppression | `#FE9934` | Evento de supressão sobre vegetação secundária |
| 7 | Other Transitions | `#303149` | Água, afloramento rochoso, praia, ruído filtrado |

### 1.1 Agregação das classes originais

O mapeamento vive em `CLASS_LOOKUP` no pipeline e é aplicado banda a banda por
`aggregate_classes()`, que usa `remap(..., default=0)` — **qualquer classe ausente do lookup vira
No Data (0)**.

| Classe agregada | IDs originais do MapBiomas |
|---|---|
| **1 — Anthropic** | 9 (silvicultura), 14 (agropecuária), 15 (pastagem), 18/19/20/39/40/41/62 (lavoura temporária), 36/35/46/47/48 (lavoura perene), 72, 21 (mosaico de usos), 22 (área não vegetada), 24 (urbano), 25 (outras áreas não vegetadas), 30 (mineração), 31 (aquicultura), 75 (usina fotovoltaica), 91 (usina eólica) |
| **2 — Primary Veg.** | 1, 3 (formação florestal), 4 (formação savânica), 5 (mangue), 6 (floresta alagável), 7 (savana alagável), 10, 11 (área úmida), 12 (campo), 13 (mosaico herbáceo-arbustivo), 49 (restinga arbórea), 50 (restinga herbácea), 66, 70, 84 (marisma) |
| **7 — Other Transitions** | 23 (praia/duna), 26 (água), 29 (afloramento rochoso), 32 (planície hipersalina), 33 (rio/lago/oceano), 34, 61, 68, 69 |
| **0 — No Data** | 0, 27 (não observado) |

⚠️ **As classes 75 (fotovoltaica) e 91 (eólica) entraram na Collection 11** e foram adicionadas ao
lookup como antrópico. Toda classe nova da legenda precisa entrar em `CLASS_LOOKUP` explicitamente:
sem isso, o `default=0` do `remap` a transforma em No Data e o pixel some da série de desmatamento
sem nenhum aviso.

> **O lookup consome o dado interno, não o público.** Na C11 o produto público remapeia 13 → 77
> (`PUBLIC_COVERAGE_REMAP`), mas os assets internos — que alimentam estas regras — mantêm o 13. Um
> pipeline reconstruído a partir do dado **público** precisaria mapear o 77 explicitamente. O lookup
> também carrega IDs que não existem na legenda do Brasil (34, 61, 66, 68, 69, 70, 72), herdados do
> lookup compartilhado com outras regiões; são inofensivos.

---

## 2. Formato das regras

Cada regra é uma lista Python com três elementos:

```python
[kernel_bef, kernel_aft, min_start]
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `kernel_bef` | `list[int]` | sim | Sequência de classes que deve casar com a entrada (estado antes) |
| `kernel_aft` | `list[int]` | sim | Sequência de classes a escrever quando casa (estado depois) |
| `min_start` | `int` | **sim** | Índice mínimo da lista de anos a partir do qual a regra pode ser aplicada |

> **Enforcement:** `min_start` é obrigatório. `apply_rule_kernel_3`, `_4` e `_6` levantam `ValueError`
> se o terceiro elemento estiver ausente, evitando erro silencioso em regra não revisada.

```python
[[1, 2, 2, 2], [1, 5, 3, 3], 1]
#  ↑ antes      ↑ depois      ↑ min_start=1 → a primeira janela válida começa em 1986
```

Para um kernel de 4 anos, os índices de posição mapeiam para anos assim:

```
índice:  i=0   i=1   i=2   i=3
         t1    t2    t3    t4
         1985  1986  1987  1988   ← janela começando no índice 0
         1986  1987  1988  1989   ← janela começando no índice 1 (min_start=1)
```

---

## 3. Tamanhos de kernel e janelas ancoradas

`apply_rules(rules, kernel_size, years_override=None)` aceita `kernel_size` **3, 4 ou 6**,
despachando para `apply_rule_kernel_3/4/6`. Qualquer outro valor levanta `ValueError`. Cada método é
uma janela móvel sobre `ee.List.sequence(0, len(years) - kernel_size)`.

| Modo | Como é chamado | Nº de janelas | Usado por |
|---|---|---|---|
| **Deslizante** | sem `years_override` (usa `YEARS`) | `len(YEARS) - k + 1` | blip, KERNEL4, KERNEL4_SECONDARY, KERNEL3_SECONDARY |
| **Ancorada** | `years_override` com exatamente `k` elementos | 1 (índice 0) | KERNEL6_SECONDARY_END, KERNEL4_SECONDARY_END_REVERT |
| **Restrita** | `years_override` com mais de `k` elementos | `len(override) - k + 1` | KERNEL4_END (4 anos sobre 4 → 1 janela) |

⚠️ **`min_start` é um índice na lista efetivamente usada**, não em `YEARS`. Com
`years_override=YEARS[-6:]`, `min_start=0` significa "a partir de 2020" — não "a partir de 1985". É
por isso que as regras ancoradas do Step 1b podem usar `min_start=0` com segurança mesmo escrevendo
classes 3 e 5.

### 3.1 Aplicação sequencial — por que a ordem importa

Cada regra roda como um `iterate` sobre as janelas, e cada janela enxerga o resultado escrito pela
janela anterior. Da mesma forma, cada grupo opera sobre a imagem já modificada pelo grupo anterior.

- Uma regra pode **habilitar** outra: `RULES_KERNEL3_SECONDARY` depende da classe 3 em `t1`, que só
  existe se `RULES_KERNEL4_SECONDARY` já a tiver escrito.
- Uma regra pode **inviabilizar** outra: é exatamente o motivo de os Steps 1a/1b rodarem antes de
  tudo (ver [§5](#5-ordem-de-processamento)).

### Constantes de período

| Constante | Valor | Usada em |
|---|---|---|
| `YEARS` | 1985–2025 (41 anos) | todas as regras deslizantes |
| `YEARS_END` | `YEARS[-4:]` → 2022–2025 | `RULES_KERNEL4_END` (Step 5) |
| `YEARS_SECONDARY_END` | `YEARS[-6:]` → 2020–2025 | `RULES_KERNEL6_SECONDARY_END` (Step 1b) |
| `YEARS_SECONDARY_END_REVERT` | `YEARS[-4:]` → 2022–2025 | `RULES_KERNEL4_SECONDARY_END_REVERT` (Step 1b) |
| `LAST_YEAR` | `YEARS[-1]` → 2025 | filtro espacial e pós-processamento |

No restante do documento, **n** designa o último ano da série (2025), **n-1** o penúltimo, e assim
por diante. As regras são escritas em função de `n` porque a cauda se desloca a cada coleção — nada
no código depende do ano 2025 literalmente.

---

## 4. O parâmetro `min_start`

### Problema

Algumas regras atribuem classe `3` (vegetação secundária) ou `5` (recuperação) na posição `t2`.
Quando a janela deslizante começa no índice `i=0`, `t2` corresponde a **1986** — o segundo ano da
série. Isso é incorreto, porque não existe contexto histórico antes de 1985 para confirmar que houve
um estado antrópico ou secundário anterior.

### Critério de decisão

| Condição | `min_start` | Justificativa |
|---|---|---|
| `kernel_aft[1]` atribui classe `3` ou `5` (atribuição nova) | `1` | `t1` precisa representar um estado anterior confirmado; 1985 não tem histórico |
| `kernel_aft[1]` já é classe `3` (sem atribuição nova) | `0` | `t2` já vinha com classe `3` da entrada; sem risco de atribuição falsa |
| `kernel_aft` não atribui classe `3` nem `5` em lugar nenhum | `0` | nenhuma classe de vegetação secundária é escrita |
| Regras com `years_override` na cauda | `0` | a janela nunca alcança 1985/1986 — o `years_override` já restringe o escopo |

> `min_start=0` é sempre declarado **explicitamente**. Não é omissão: é a confirmação documentada de
> que a regra foi avaliada e considerada segura desde o primeiro ano da série.

### Implementação

Os três métodos aplicam `min_start` da mesma forma: levantam `ValueError` se o terceiro elemento
estiver ausente e somam `.And(i.gte(min_start))` à máscara de pixels.

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
            .And(i.gte(min_start))   # bloqueia janelas antes do índice mínimo
        )
```

A condição `.And(i.gte(min_start))` é uma expressão escalar do EE difundida para todos os pixels,
sem custo computacional relevante.

---

## 5. Ordem de processamento

As regras são aplicadas **sequencialmente** em `export_deforestation()`.

```python
# Step 1  — agrega os códigos originais do MapBiomas para os códigos simplificados (0–7)
aggregated = DeforestationSecondaryVegetation.aggregate_classes(integration, LOOKUP_IN, LOOKUP_OUT)
processor  = DeforestationSecondaryVegetation(aggregated, YEARS)

# Step 1a — remove blips de 1 ano de vegetação (toda a série)          [RUN_VEG_BLIP_FILTER]
processor.apply_rules(RULES_KERNEL3_VEG_BLIP, kernel_size=3)

# Step 1b — regras ancoradas de fim de série (janelas de 6 e 4 anos)   [RUN_SECONDARY_END_RULES]
processor.apply_rules(RULES_KERNEL6_SECONDARY_END, kernel_size=6, years_override=YEARS_SECONDARY_END)
processor.apply_rules(RULES_KERNEL4_SECONDARY_END_REVERT, kernel_size=4,
                      years_override=YEARS_SECONDARY_END_REVERT)

# Step 2  — supressão confirmada de vegetação primária
processor.apply_rules(RULES_KERNEL4, kernel_size=4)

# Step 3  — dinâmica de vegetação secundária (estabelecimento, persistência, supressão)
processor.apply_rules(RULES_KERNEL4_SECONDARY, kernel_size=4)

# Step 4  — supressão dentro de vegetação secundária
processor.apply_rules(RULES_KERNEL3_SECONDARY, kernel_size=3)

# Step 5  — transições não confirmadas no fim da série
processor.apply_rules(RULES_KERNEL4_END, kernel_size=4, years_override=YEARS_END)

# Step 6  — correção por frequência de antrópico
# Step 7  — guarda de cauda (vegetação secundária não confirmada nos 2 últimos anos)
```

⚠️ **Steps 1a e 1b rodam primeiro, e isso é essencial.** Eles precisam ver o mapa agregado limpo
(`{0,1,2,7}`), com antrópico(1) e vegetação(2) crus. Se rodassem depois dos Steps 2–4, o `p0` das
janelas já teria sido reescrito para `{3,4,5,6}` — por exemplo `[4,1,1,1,1,2]` ou `[6,1,1,1,1,2]` — e
a janela 3, que casa literalmente `[2,1,1,1,1,2]`, deixaria de casar. As marcas `5`/`3` escritas nos
Steps 1a/1b sobrevivem a todas as regras seguintes (não casam nenhum `kernel_bef` downstream) e à
correção de frequência, que só toca as classes 2 e 4.

---

## 6. Grupos de regras

Apresentados **na ordem de execução**. Em todas as tabelas, `2 2 1 1` lê-se como a sequência de
classes de `t1` a `tk`; a coluna "depois" traz o que é escrito quando o padrão casa.

### 6.1 `RULES_KERNEL3_VEG_BLIP` — filtro de blip de 1 ano (Step 1a)

**Kernel:** 3 anos · **Anos:** toda a série · **Flag:** `RUN_VEG_BLIP_FILTER` (default `True`)

Um único ano de vegetação entre dois anos antrópicos não pode ser confirmado como vegetação
secundária — o estabelecimento exige 3 anos — e é tratado como ruído, revertido para antrópico. Sem
esse filtro, a correção por frequência (Step 6) promoveria esses blips a secundária(3) em toda a
série.

```python
RULES_KERNEL3_VEG_BLIP = [
    [[1, 2, 1], [1, 1, 1], 0],  # antrópico, veg (1 ano), antrópico → antrópico
]
```

| Regra | antes | → | depois | min_start |
|---|---|---|---|---|
| Blip de 1 ano de vegetação | `1 2 1` | → | `1` **`1`** `1` | 0 |

- `min_start=0` é seguro: a regra só escreve classe 1, nunca 3 ou 5.
- **Não casa em `n`**: exige um ano antrópico depois da vegetação, que não existe no último ano. Por
  construção, nunca toca uma regeneração em curso na ponta da série.
- Roda primeiro para que o dado limpo alimente as janelas ancoradas — uma regeneração real continua
  sendo detectada depois de o blip ser removido.

### 6.2 `RULES_KERNEL6_SECONDARY_END` — janelas ancoradas de fim de série (Step 1b)

**Kernel:** 6 anos · **Anos:** `YEARS_SECONDARY_END` (`YEARS[-6:]`, janela única) ·
**Flag:** `RUN_SECONDARY_END_RULES` (default `True`)

As regras de 4 anos exigem 3 anos seguidos de vegetação para confirmar o estabelecimento, então
**não contemplam os 2 últimos anos** da série: uma regeneração que começa em `n` ou `n-1` não tem
anos suficientes à frente para ser confirmada. Estas três janelas, ancoradas no intervalo
`[n-5 .. n]`, resolvem esse caso usando o histórico **anterior** (4 a 5 anos antrópicos) como
evidência no lugar da confirmação futura que não existe.

```python
RULES_KERNEL6_SECONDARY_END = [
    [[1, 1, 1, 1, 2, 2], [1, 1, 1, 1, 5, 3], 0],  # janela 1: 4 antrópico + 2 veg → 5,3
    [[1, 1, 1, 1, 1, 2], [1, 1, 1, 1, 1, 5], 0],  # janela 2: 5 antrópico + 1 veg → 5
    [[2, 1, 1, 1, 1, 2], [2, 1, 1, 1, 1, 5], 0],  # janela 3: veg + 4 antrópico + veg → 5
]
```

| Janela | antes (n-5 … n) | → | depois (n-5 … n) | min_start |
|---|---|---|---|---|
| 1 — 4 antrópicos + 2 anos de vegetação | `1 1 1 1 2 2` | → | `1 1 1 1` **`5 3`** | 0 |
| 2 — 5 antrópicos + 1 ano de vegetação | `1 1 1 1 1 2` | → | `1 1 1 1 1` **`5`** | 0 |
| 3 — vegetação + 4 antrópicos + vegetação | `2 1 1 1 1 2` | → | `2 1 1 1 1` **`5`** | 0 |

> **`min_start=0` é seguro aqui.** Com `years_override=YEARS[-6:]` existe apenas a janela de índice 0,
> que começa em `n-5` (2020) — com a série inteira de histórico antes dela. Não há risco de escrever
> 3 ou 5 no início da série.

> **Janela 3 — efeito colateral aceito.** O `p0` (n-5) permanece vegetação(2) na regra, mas a
> correção de frequência do Step 6 converte 2 → 3 para pixels com histórico antrópico (que a própria
> janela garante), de modo que a cauda efetiva vira `[3,1,1,1,1,5]`. É semanticamente consistente — o
> ano n-5 era mesmo vegetação secundária — e está aceito.

### 6.3 `RULES_KERNEL4_SECONDARY_END_REVERT` — reversão ancorada de bloco de 2 anos (Step 1b)

**Kernel:** 4 anos · **Anos:** `YEARS_SECONDARY_END_REVERT` (`YEARS[-4:]`) ·
**Flag:** gated por `RUN_SECONDARY_END_RULES`

No **interior** da série, um bloco de 2 anos de vegetação seguido de antrópico já é revertido em duas
etapas: `RULES_KERNEL4` marca a supressão (`[2,2,1,1]→[2,2,4,1]`) e `RULES_KERNEL4_SECONDARY` reverte
tudo (`[1,2,2,4]→[1,1,1,1]`). Na **cauda**, a supressão não pode ser marcada — não existe ano depois
de `n` para completar o padrão — e o bloco sobreviveria, sendo promovido a secundária(3) pela
correção de frequência. Esta regra reproduz diretamente o resultado do interior.

```python
RULES_KERNEL4_SECONDARY_END_REVERT = [
    [[1, 2, 2, 1], [1, 1, 1, 1], 0],  # antrópico, veg, veg, antrópico → tudo antrópico
]
```

| Regra | antes | → | depois | min_start |
|---|---|---|---|---|
| Bloco de 2 anos cortado antes de `n` | `1 2 2 1` | → | `1` **`1 1`** `1` | 0 |

⚠️ **É ancorada de propósito.** Uma versão global de `[1,2,2,1]` reverteria também blocos legítimos
no interior da série, como `[1,2,2,1,2]`. Travado por `test_d_revert_does_not_revert_interior_1221`.

### 6.4 `RULES_KERNEL4` — supressão de vegetação primária (Step 2)

**Kernel:** 4 anos · **Anos:** série completa (1985–2025) · nenhuma regra escreve 3 ou 5

```python
RULES_KERNEL4 = [
    [[2, 2, 1, 1], [2, 2, 4, 1], 0],  # Primary vegetation suppression
]
```

| Regra | antes | → | depois | min_start |
|---|---|---|---|---|
| Supressão de vegetação primária | `2 2 1 1` | → | `2 2` **`4`** `1` | 0 |

**Leitura:** se o pixel era vegetação primária (2) em dois anos consecutivos e passou a antrópico (1)
por dois anos, o terceiro ano é marcado como supressão (4). A confirmação exige dois anos de uso
antrópico para evitar falsos positivos por ruído de um único ano.

### 6.5 `RULES_KERNEL4_SECONDARY` — dinâmica de vegetação secundária (Step 3)

**Kernel:** 4 anos · **Anos:** série completa · **3 regras exigem `min_start=1`**

```python
RULES_KERNEL4_SECONDARY = [
    [[1, 2, 2, 2], [1, 5, 3, 3], 1],  # Estabelecimento de vegetação secundária
    [[5, 3, 3, 2], [5, 3, 3, 3], 0],  # Recuperação → secundária: persistência
    [[3, 2, 2, 2], [3, 3, 3, 3], 1],  # Persistência de vegetação secundária
    [[3, 2, 2, 4], [3, 3, 3, 4], 1],  # Secundária com supressão no fim
    [[3, 3, 2, 4], [3, 3, 3, 6], 0],  # Supressão com recuperação
    [[3, 3, 2, 2], [3, 3, 3, 3], 0],  # Persistência com primária interrompida
    [[3, 3, 3, 2], [3, 3, 3, 3], 0],  # Persistência: 3 anos confirmados
    [[1, 2, 2, 4], [1, 1, 1, 1], 0],  # Supressão de primária com recuperação
]
```

| Regra | antes | → | depois | min_start | Observação |
|---|---|---|---|---|---|
| Estabelecimento de vegetação secundária | `1 2 2 2` | → | `1` **`5 3 3`** | **1** | ⚠️ t2 recebe classe 5 |
| Recuperação → secundária: persistência | `5 3 3 2` | → | `5 3 3` **`3`** | 0 | t2 já é classe 3 |
| Persistência de vegetação secundária | `3 2 2 2` | → | `3` **`3 3 3`** | **1** | ⚠️ t2 recebe classe 3 |
| Secundária com supressão no fim | `3 2 2 4` | → | `3` **`3 3`** `4` | **1** | ⚠️ t2 recebe classe 3 |
| Supressão com recuperação | `3 3 2 4` | → | `3 3` **`3 6`** | 0 | t2 já é classe 3 |
| Persistência com primária interrompida | `3 3 2 2` | → | `3 3` **`3 3`** | 0 | t2 já é classe 3 |
| Persistência: 3 anos confirmados | `3 3 3 2` | → | `3 3 3` **`3`** | 0 | t2 já é classe 3 |
| Supressão de primária com recuperação | `1 2 2 4` | → | **`1 1 1 1`** | 0 | não escreve 3 nem 5 |

**Leitura das regras ⚠️:**

- `[[1,2,2,2],[1,5,3,3],1]` — detecta `antrópico → vegetação → vegetação → vegetação` e interpreta a
  vegetação como regeneração. Exige que `t1` seja um estado antrópico confirmado, o que 1985 não pode
  oferecer. `min_start=1` garante que a primeira janela seja `[1986,1987,1988,1989]`. **É esta regra
  que cobre uma regeneração iniciada em `n-2`** (ver [§8](#8-comportamento-no-fim-da-série)).
- `[[3,2,2,2],[3,3,3,3],1]` — consolida como secundária toda a sequência. Para `t1=1985` ser classe 3,
  uma regra anterior teria de tê-la escrito, o que é impossível no primeiro ano.
- `[[3,2,2,4],[3,3,3,4],1]` — mesma justificativa, com evento de supressão em `t4`.

### 6.6 `RULES_KERNEL3_SECONDARY` — supressão dentro de vegetação secundária (Step 4)

**Kernel:** 3 anos · **Anos:** série completa · nenhuma regra escreve 3 ou 5 em `t2`

```python
RULES_KERNEL3_SECONDARY = [
    [[3, 4, 1], [3, 6, 1], 0],  # Suppression of secondary vegetation
]
```

| Regra | antes | → | depois | min_start |
|---|---|---|---|---|
| Supressão de vegetação secundária | `3 4 1` | → | `3` **`6`** `1` | 0 |

**Leitura:** se o pixel era vegetação secundária (3), sofreu um evento marcado como supressão de
primária (4) e voltou a antrópico (1), o evento é reclassificado como supressão de secundária (6).
Este grupo depende da classe 3 em `t1`, escrita pelo Step 3 — com o `min_start` em vigor lá, a cadeia
de dependência é segura.

### 6.7 `RULES_KERNEL4_END` — transições não confirmadas no fim da série (Step 5)

**Kernel:** 4 anos · **Anos:** `YEARS_END` (`YEARS[-4:]`, uma janela) · escreve apenas 4 ou 6 em `t4`

```python
RULES_KERNEL4_END = [
    [[2, 2, 2, 1], [2, 2, 2, 4], 0],  # Unconfirmed primary deforestation
    [[3, 3, 3, 1], [3, 3, 3, 6], 0],  # Unconfirmed secondary deforestation
]
```

| Regra | antes | → | depois | min_start |
|---|---|---|---|---|
| Desmatamento de primária não confirmado | `2 2 2 1` | → | `2 2 2` **`4`** | 0 |
| Desmatamento de secundária não confirmado | `3 3 3 1` | → | `3 3 3` **`6`** | 0 |

**Leitura:** numa regra de desmatamento confirmado (`RULES_KERNEL4`), a transição exige dois anos de
uso antrópico para evitar ruído. No fim da série, o segundo ano de confirmação ainda não existe.
Estas regras marcam o último ano como supressão (4 ou 6) com base em um único ano antrópico,
aceitando a confiança menor.

---

## 7. Pós-processamento

### 7.1 Reclassificação por frequência de antrópico (Step 6)

Calcula a frequência de antrópico por pixel ao longo de todos os anos com `get_class_frequency()`,
sobre a imagem **agregada** (antes das regras de kernel).

| Condição | Ação | Justificativa |
|---|---|---|
| `freq_anthropic > 1` **e** pixel = classe `4` | → classe `6` | Se o pixel já foi antrópico mais de uma vez, uma supressão de primária é provavelmente de secundária |
| `freq_anthropic > 0` **e** pixel = classe `2` | → classe `3` | Se o pixel tem qualquer histórico antrópico, a vegetação primária atual é provavelmente regeneração |

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

> A correção **só toca as classes 2 e 4**. É por isso que as marcas 3 e 5 escritas pelas janelas
> ancoradas do Step 1b atravessam essa etapa intactas.

### 7.2 Guarda de cauda (Step 7) — substitui o ajuste dos últimos 3 anos

O bloco manual de pós-processamento dos últimos 3 anos (quatro ajustes condicionais) foi
**removido**. Com as janelas ancoradas do Step 1b definindo a cauda de forma determinística, restou
apenas uma guarda: remover vegetação secundária(3) cujo **predecessor imediato** seja antrópico(1) —
ou seja, a regeneração não confirmada induzida pela correção de frequência.

```python
y1, y2, y3 = YEARS[-3], YEARS[-2], YEARS[-1]

# n-1: remove secundária não confirmada (o predecessor n-2 é antrópico)
t2 = t2.where(t1.eq(CLASS_ANTHROPIC).And(t2.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)

# n: idem — usa o t2 já atualizado, então a remoção cascateia por anos consecutivos
t3 = t3.where(t2.eq(CLASS_ANTHROPIC).And(t3.eq(CLASS_SECONDARY_VEGETATION)), CLASS_ANTHROPIC)
```

- **Roda independentemente** de `RUN_SECONDARY_END_RULES`.
- Preserva as saídas das janelas ancoradas (janela 1: `n-1`=5 e depois `n`=3 — o predecessor do 3 é
  5, não 1) e os estabelecimentos confirmados (3 precedido de 3).
- Remove apenas os `3` induzidos por frequência, que são ruído.

| Ajuste antigo (removido) | Como o caso é tratado hoje |
|---|---|
| `t1`=antrópico e `t2`=secundária → reverte `t2` | mantido, como a 1ª condição da guarda de cauda |
| `t1`=antrópico e `t3`=secundária → reverte `t3` | coberto pelo cascateamento da 2ª condição |
| `t2`=antrópico e `t3`=secundária → reverte `t3` | mantido, como a 2ª condição da guarda de cauda |
| `t2`=secundária e `t3`=antrópico → reverte `t3` para secundária | **descartado** — reescrevia o último ano cegamente; a cauda agora é definida pelas janelas ancoradas |

---

## 8. Comportamento no fim da série

Para uma regeneração que começa perto do fim da série, o que sai no mapa? A matriz abaixo foi
verificada por simulação do pipeline completo sobre a série 1985–2025 e está travada por testes
(`test_tail_coverage_matrix`).

| Entrada (últimos 6 anos) | Situação | Saída (n-2, n-1, n) | Mecanismo |
|---|---|---|---|
| `1 1 1 1 1 2` | regeneração começa em `n` (1 ano em curso) | `1 1 5` | janela 2 ou 3 (6 anos) |
| `1 1 1 1 2 2` | começa em `n-1` (2 anos em curso) | `1 5 3` | janela 1 (6 anos) |
| `1 1 1 2 2 2` | começa em `n-2` e alcança `n` (3 anos) | `5 3 3` | **regra de estabelecimento (4 anos)** |
| `1 1 2 2 2 2` | começa em `n-3` (4 anos) | `3 3 3` | regra de estabelecimento (4 anos) |
| `1 1 1 2 2 1` | bloco de 2 anos cortado antes de `n` | `1 1 1` | **reversão ancorada** ([§6.3](#63-rules_kernel4_secondary_end_revert--reversão-ancorada-de-bloco-de-2-anos-step-1b)) |
| `1 1 1 2 1 1` | blip de 1 ano | `1 1 1` | **filtro de blip** ([§6.1](#61-rules_kernel3_veg_blip--filtro-de-blip-de-1-ano-step-1a)) |

As janelas de 6 anos são necessárias **apenas** para regenerações **em curso** que começam em `n` ou
`n-1`. Uma regeneração que começa em `n-2` e chega a `n` já tem 3 anos de vegetação e é confirmada
pela regra de estabelecimento de 4 anos — `n-2` **não** ficou esquecido.

Regenerações curtas que **terminam antes de `n`** são tratadas como ruído, espelhando o
comportamento do interior da série: 2 anos cortados pela reversão ancorada, 1 ano pelo filtro de blip.

### 8.1 Flags de execução

| Flag | Default | O que controla | Efeito quando `False` |
|---|---|---|---|
| `RUN_VEG_BLIP_FILTER` | `True` | Step 1a — filtro de blip de 1 ano em toda a série | blips sobrevivem e são promovidos a secundária(3) pela correção de frequência |
| `RUN_SECONDARY_END_RULES` | `True` | Step 1b — janelas de 6 anos **e** reversão ancorada | a cauda volta ao comportamento anterior: blocos de 2 anos viram secundária; regeneração em curso em `n`/`n-1` não é detectada |

A guarda de cauda (Step 7) **não** é controlada por flag — roda sempre. As duas flags existem para
permitir reproduzir o comportamento anterior em comparações; travadas pelos testes `test_flag_*`.

---

## 9. Validação e testes

O código real é um grafo do Earth Engine e não roda offline.
[`tests/test_rules.py`](../tests/test_rules.py) valida a **semântica das regras** com um simulador
Python fiel do algoritmo de kernel — inclusive a aplicação sequencial, em que cada janela vê o
resultado da anterior.

```bash
# a partir de collection11/
python -m pytest tests -v
```

**48 testes, todos passando** (verificado em 15/10/2026). Rodam offline, sem credencial do Earth Engine.

| Grupo | O que cobre |
|---|---|
| 1. Carga das regras via AST | Padrões literais de cada grupo |
| 2. `apply_rule_kernel_6` | Janela única, não-casamento parcial, 3 janelas em sequência |
| 3. `min_start` | Índice 0 aplica com 0; bloqueia com 1; libera no índice 1 |
| 4. Filtro de blip | Remove 1 ano; preserva bloco de 2 anos; múltiplos blips; não casa em `n` |
| 5. Reversão ancorada | Reverte na cauda; **não** reverte `[1,2,2,1]` no interior |
| 6. Regra de estabelecimento | Casa no interior; bloqueada no início da série |
| 7. Matriz de cobertura da cauda | Pipeline completo end-to-end para os 6 cenários da [§8](#8-comportamento-no-fim-da-série) |
| 8. Flags | Comportamento antigo reproduzido com as flags desligadas |
| 9. Ordenação run-first | As marcas 5/3 do Step 1b sobrevivem a KERNEL4 e KERNEL4_SECONDARY |
| 10. Guarda de cauda | Remove 3 induzido por frequência; preserva recuperação(5) e 3 confirmado |
| 11. Regressão | Série toda antrópica / toda vegetação; `min_start` ausente levanta erro |

> As regras são carregadas **do código-fonte via AST** (`load_rules_from_source`), sem importar o
> pipeline — o que evita `ee.Initialize()` nos testes e garante que documento e testes descrevam as
> mesmas constantes que rodam em produção.

---

## 10. O que vem depois das regras temporais

A imagem produzida por `export_deforestation()` é o primeiro elo. Os produtos abaixo derivam dela e
ficam em `LAND-COVER/COLLECTION-11/DEFORESTATION/`.

| Produto | Asset | Flag | Depende de |
|---|---|---|---|
| Transições de desmatamento | `deforestation-secondary-vegetation` | `RUN_DEF` | integração |
| Transições filtradas (filtro espacial) | `…-ft` | `RUN_DEF_FT` | transições |
| Desmatamento anual | `…-annual` | `RUN_DEF_ANNUAL` | transições filtradas |
| Desmatamento acumulado | `…-accumulated` | `RUN_DEF_ACCUMULATED` | anual |
| Frequência de desmatamento | `deforestation-frequency` | `RUN_DEF_FREQUENCY` | transições filtradas |
| Idade da vegetação secundária | `secondary-vegetation-age` | `RUN_SV_AGE` | transições filtradas |

**Filtro espacial:** `export_deforestation_filtered_no_accumulation()` remove, **ano a ano**,
manchas de até `GROUP_SIZE_FILTER` (11 pixels, ~1 ha) por contagem de pixels conectados (8-vizinhança),
reclassificando-as para a classe 7 (Other Transitions). Desmatamento (4, 6) e vegetação secundária
(3, 5) são filtrados com máscaras separadas. `YEARS_EXCEPTION` (por padrão, só o último ano) permite
um limiar próprio para os anos mais recentes — na C11, também 11.

> É a função chamada por `run_pipeline()` desde a Collection 10 e a que gerou a C11. O script
> mantém `export_deforestation_filtered()`, a variante anterior, que conta os pixels conectados
> sobre a máscara **acumulada** da série inteira (uma mancha pequena num ano sobrevive se encostar
> em desmatamento de outro ano); ela não é usada.

**Idade da vegetação secundária:** acumula, por pixel, os anos consecutivos em classe 3 ou 5, zerando
quando o pixel deixa essas classes — `age(t) = (age(t-1) + sv(t)) * sv(t)`. Bandas nomeadas
`secondary_vegetation_age_{ano}`, **não** `classification_{ano}`, ao contrário dos outros assets do
pipeline.

**Reuso em outras regiões:** Peru (C4), Bolívia (C4), Uruguai, Argentina (C3) e Indonésia (C5)
usam **as mesmas sete listas de regras temporais**. O que difere é o `CLASS_LOOKUP`, específico da
legenda de cada região, e o filtro espacial.

---

## 11. Histórico de problemas resolvidos

### 11.1 Vegetação secundária nos primeiros anos da série

**Sintoma.** As classes `3` e `5` apareciam indevidamente no segundo ano da série (1986) — e, em
alguns casos, também em 1985 — no mapa de desmatamento.

**Causa raiz.** As regras de `RULES_KERNEL4_SECONDARY` que atribuem 3 ou 5 na posição `t2` eram
aplicadas a partir do índice `i=0`, correspondente a `[1985,1986,1987,1988]`. Nessa janela, `t2`=1986
recebia 5 ou 3 sem que houvesse histórico antes de 1985 para validar a transição.

```python
[[1, 2, 2, 2], [1, 5, 3, 3], ...]  →  t2 (1986) recebia classe 5
[[3, 2, 2, 2], [3, 3, 3, 3], ...]  →  t2 (1986) recebia classe 3
[[3, 2, 2, 4], [3, 3, 3, 4], ...]  →  t2 (1986) recebia classe 3
```

**Correção.** Introdução do `min_start`, com valor `1` nas três regras afetadas: a janela mais antiga
passa a ser `[1986,1987,1988,1989]`, com `t2`=1987. O parâmetro foi adicionado explicitamente com
valor `0` em todas as demais regras, e sua ausência passou a levantar `ValueError`.

### 11.2 Regeneração não detectada nos 2 últimos anos

**Sintoma.** Regenerações **em curso** — que começam em `n` ou `n-1` e ainda não têm 3 anos de
vegetação — não apareciam no mapa, porque as regras de 4 anos exigem confirmação por 3 anos
consecutivos. Ao mesmo tempo, ruídos curtos (1 ou 2 anos de vegetação) na cauda **eram** promovidos a
vegetação secundária pela correção de frequência: falta o sinal real e sobra o ruído.

**Causa raiz.** O fim da série não tem os anos futuros que o restante da série usa como confirmação.
O tratamento anterior era um bloco manual de quatro ajustes condicionais sobre os últimos 3 anos, que
não distinguia regeneração em curso de ruído e chegava a reescrever o último ano cegamente.

**Correção.**

1. **Filtro de blip** ([§6.1](#61-rules_kernel3_veg_blip--filtro-de-blip-de-1-ano-step-1a)) — remove
   1 ano isolado de vegetação em toda a série, antes de tudo.
2. **Janelas ancoradas de 6 anos**
   ([§6.2](#62-rules_kernel6_secondary_end--janelas-ancoradas-de-fim-de-série-step-1b)) — detectam
   regeneração em curso em `n` e `n-1` usando o histórico anterior como evidência.
3. **Reversão ancorada de bloco de 2 anos**
   ([§6.3](#63-rules_kernel4_secondary_end_revert--reversão-ancorada-de-bloco-de-2-anos-step-1b)) —
   reproduz na cauda o que o interior já fazia via supressão(4).
4. **Guarda de cauda** ([§7.2](#72-guarda-de-cauda-step-7--substitui-o-ajuste-dos-últimos-3-anos)) —
   substitui o bloco manual por uma única regra, baseada no predecessor imediato.

O resultado é a matriz de cobertura da [§8](#8-comportamento-no-fim-da-série), travada por testes. A
ordem de execução — Steps 1a e 1b antes de tudo — é parte da correção, não um detalhe de
implementação.

---

## 12. Referência rápida — todas as regras, em ordem de execução

| # | Grupo | k | Anos | antes → depois | min_start |
|---|---|---|---|---|---|
| 1a | `RULES_KERNEL3_VEG_BLIP` | 3 | todos | `1 2 1` → `1 1 1` | 0 |
| 1b | `RULES_KERNEL6_SECONDARY_END` | 6 | `YEARS[-6:]` | `1 1 1 1 2 2` → `1 1 1 1 5 3` | 0 |
| | | | | `1 1 1 1 1 2` → `1 1 1 1 1 5` | 0 |
| | | | | `2 1 1 1 1 2` → `2 1 1 1 1 5` | 0 |
| 1b | `RULES_KERNEL4_SECONDARY_END_REVERT` | 4 | `YEARS[-4:]` | `1 2 2 1` → `1 1 1 1` | 0 |
| 2 | `RULES_KERNEL4` | 4 | todos | `2 2 1 1` → `2 2 4 1` | 0 |
| 3 | `RULES_KERNEL4_SECONDARY` | 4 | todos | `1 2 2 2` → `1 5 3 3` | **1** |
| | | | | `5 3 3 2` → `5 3 3 3` | 0 |
| | | | | `3 2 2 2` → `3 3 3 3` | **1** |
| | | | | `3 2 2 4` → `3 3 3 4` | **1** |
| | | | | `3 3 2 4` → `3 3 3 6` | 0 |
| | | | | `3 3 2 2` → `3 3 3 3` | 0 |
| | | | | `3 3 3 2` → `3 3 3 3` | 0 |
| | | | | `1 2 2 4` → `1 1 1 1` | 0 |
| 4 | `RULES_KERNEL3_SECONDARY` | 3 | todos | `3 4 1` → `3 6 1` | 0 |
| 5 | `RULES_KERNEL4_END` | 4 | `YEARS[-4:]` | `2 2 2 1` → `2 2 2 4` | 0 |
| | | | | `3 3 3 1` → `3 3 3 6` | 0 |
| 6 | correção por frequência | — | todos | `freq>1 ∧ 4 → 6` · `freq>0 ∧ 2 → 3` | — |
| 7 | guarda de cauda | — | `YEARS[-3:]` | `1` antes de `3` → `3` vira `1` (cascateia) | — |
