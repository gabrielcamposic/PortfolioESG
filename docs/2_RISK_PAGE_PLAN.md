# 2_risk.html — Risk KPIs Page Plan

**Criado:** 2026-03-14  
**Status:** ✅ Implementado (2026-03-14)  
**Referência:** docs/METRICS_REFERENCE.md, docs/D_PUBLISH_METRICS_PLAN.md

---

## Objetivo

Criar `html/sections/2_risk.html` — uma página standalone de KPIs de risco com três métricas: **Tracking Error**, **Information Ratio** e **HHI** (Herfindahl-Hirschman Index). Todas as métricas devem respeitar janelas temporais (All, YTD, 3M, 6M, 12M, 24M) e manter o princípio render-only do frontend.

---

## Diagnóstico: Disponibilidade dos Dados

### Tracking Error & Information Ratio

**Status: ⚠️ Parcialmente pronto — valor global disponível, janelas temporais ausentes.**

Ambos estão computados em `D_Publish.py → _compute_real_metrics()` a partir da série `portfolio_real_daily.csv` e expostos em `dashboard_latest.json → real.relative`:

```json
"relative": {
  "beta": 0.84,
  "tracking_error": 0.1773,
  "information_ratio": 1.39,
  "correlation": 0.67
}
```

**Problema:** Esses são valores **globais** (período inteiro: 2025-10-17 → 2026-03-13). Não existem versões por janela temporal. Para exibir TE e IR por janela (YTD, 3M, 6M), é necessário computá-los no backend por janela — o frontend não deve fazer cálculos estatísticos (std, cov).

**Fórmulas:**
- `tracking_error = std(r_port − r_bench, ddof=1) × √252`
- `information_ratio = alpha_annual / tracking_error`
  - onde `alpha_annual = ((1 + port_total)^(252/n) − 1) − ((1 + bench_total)^(252/n) − 1)`

### HHI (Herfindahl-Hirschman Index)

**Status: ❌ Dados incorretos + janelas temporais ausentes.**

**Problema 1 — Fonte errada:** O HHI atual em `dashboard_latest.json → real.structure.hhi` (valor: 0.5244) vem de `DIAGNOSTICS_HISTORY_CSV` (gerado por A4_Analysis.py), que calcula concentração do **portfólio modelo** (5 ativos GA), não do portfólio **real** (9 posições no ledger).

**Problema 2 — Sem janelas temporais:** O HHI é um snapshot único (última run). Não existe HHI calculado para diferentes janelas (e.g., "como estava a concentração 3 meses atrás?").

**Dados disponíveis para corrigir:** `portfolio_history.csv` contém linhas por posição por dia com colunas `date, symbol, qty, price, value, market_value`. O peso de cada posição num dado dia é `w_i = value_i / market_value`, e `HHI = Σ(w_i²)`. Exemplo do último dia (2026-03-13, 9 posições):

| Symbol | Value | Weight | Weight² |
|---|---|---|---|
| PETR3.SA | 1086.36 | 0.3669 | 0.1346 |
| SAPR11.SA | 592.05 | 0.1999 | 0.0400 |
| MDNE3.SA | 356.40 | 0.1203 | 0.0145 |
| PLPL3.SA | 272.65 | 0.0921 | 0.0085 |
| AURA33.SA | 266.20 | 0.0899 | 0.0081 |
| VALE3.SA | 156.60 | 0.0529 | 0.0028 |
| CMIG3.SA | 124.00 | 0.0419 | 0.0018 |
| TEND3.SA | 58.06 | 0.0196 | 0.0004 |
| VULC3.SA | 49.23 | 0.0166 | 0.0003 |
| **Total** | **2961.55** | **1.0000** | **HHI = 0.2108** |

O HHI real (0.2108) é significativamente diferente do modelo (0.5244). Isso confirma a necessidade de correção.

**Fórmula:**
- `HHI = Σ(w_i²)` onde `w_i = value_i / Σ(value)` para posições ativas naquela data
- Para janela temporal: usar o HHI do **último dia** contido na janela (snapshot point-in-time, não média)

---

## Mudanças Necessárias

### Mudança 1 — Corrigir `real.structure` para usar portfólio real

**Arquivo:** `engines/D_Publish.py`  
**Onde:** `_build_real_section()` (linhas 990–999)

Substituir o bloco atual que lê de `DIAGNOSTICS_HISTORY_CSV` (modelo):

```python
# ANTES: Structure from latest diagnostics (HHI, concentration) — MODELO
structure = {}
diag = latest_csv_rows(DIAGNOSTICS_HISTORY_CSV)
if not diag.empty:
    row = diag.iloc[0]
    structure = {
        "hhi": safe_float(row.get("hhi")),
        "top3": safe_float(row.get("top3_concentration")),
        "top5": safe_float(row.get("top5_concentration")),
        "n_assets": int(safe_float(row.get("n_assets"), 0)),
    }
```

Pela computação direta a partir de `ledger_positions.json` (portfólio real):

```python
# DEPOIS: Structure from ledger_positions.json — REAL
positions = ledger_data.get("positions", [])
weights = []
for pos in positions:
    qty = safe_float(pos.get("net_qty"), 0.0)
    price = safe_float(pos.get("current_price"), 0.0)
    mv = qty * price
    if mv > 0:
        weights.append(mv / total_ledger_market)

weights_sorted = sorted(weights, reverse=True)
structure = {
    "hhi": round(sum(w**2 for w in weights), 4),
    "top3": round(sum(weights_sorted[:3]), 4) if len(weights_sorted) >= 3 else round(sum(weights_sorted), 4),
    "top5": round(sum(weights_sorted[:5]), 4) if len(weights_sorted) >= 5 else round(sum(weights_sorted), 4),
    "n_assets": len(weights),
}
```

### Mudança 2 — Adicionar `risk_windows` a `dashboard_latest.json`

**Arquivo:** `engines/D_Publish.py`  
**Onde:** Nova função helper `_compute_risk_windows(daily_df, hist_df)`  
**Chamada por:** `main()`, resultado passado para `_build_real_section()`.

**Inputs:**
- `daily_df`: DataFrame de `portfolio_real_daily.csv` (já carregado em `_build_real_daily_series()`)
- `hist_df`: DataFrame de `portfolio_history.csv` (já carregado em `_build_real_daily_series()` — precisa ser exposto)

**Nova estrutura JSON** em `dashboard_latest.json → real.risk_windows`:

```json
"risk_windows": {
  "All": {
    "tracking_error": 0.1773,
    "information_ratio": 1.39,
    "hhi": 0.2108,
    "n_assets": 9,
    "trading_days": 68
  },
  "YTD": {
    "tracking_error": 0.1801,
    "information_ratio": 1.42,
    "hhi": 0.2108,
    "n_assets": 9,
    "trading_days": 45
  },
  "3M": { "..." },
  "6M": { "..." },
  "12M": { "..." },
  "24M": { "..." }
}
```

**Algoritmo para TE e IR por janela:**

```
Para cada janela (All, YTD, 3M, 6M, 12M, 24M):
  1. Filtrar daily_df pelo período da janela
     - All: sem filtro
     - YTD: date >= 1 jan do ano corrente
     - 3M/6M/12M/24M: date >= last_date - N meses
  2. port_rets = coluna portfolio_return (excluir NaN)
  3. bench_rets = coluna benchmark_return (excluir NaN)
  4. Alinhar: datas em comum (intersect dos índices)
  5. diff = port_rets - bench_rets
  6. tracking_error = std(diff, ddof=1) × √252
  7. n = len(port_rets)
  8. total_return = ∏(1 + port_rets) − 1
  9. bench_total = ∏(1 + bench_rets) − 1
  10. alpha_annual = (1 + total_return)^(252/n) − (1 + bench_total)^(252/n)
  11. information_ratio = alpha_annual / tracking_error  (se TE > 0)
```

**Algoritmo para HHI por janela:**

```
Para cada janela (All, YTD, 3M, 6M, 12M, 24M):
  1. Determinar data de início da janela (mesma lógica que _compute_performance_windows)
  2. Filtrar hist_df (portfolio_history.csv) → linhas com date >= data_inicio
  3. Encontrar o último date disponível no filtro
  4. Filtrar linhas desse último date → posições point-in-time
  5. Para cada posição: w_i = value / Σ(value de todas as posições no dia)
  6. HHI = Σ(w_i²)
  7. n_assets = contagem de posições com value > 0
```

**Nota sobre reuso de dados:** `portfolio_history.csv` já é carregado em `_build_real_daily_series()` (linha 587). Para evitar re-leitura, refatorar `main()` para:
1. Carregar `hist_df` uma vez
2. Passar para `_build_real_daily_series()` (que hoje carrega internamente)
3. Passar para `_compute_risk_windows()` junto com `daily_df`

### Mudança 3 — Criar `html/sections/2_risk.html`

**Arquivo:** `html/sections/2_risk.html`  
**Stack:** Chart.js 4 (CDN), PapaParse 5 (CDN), vanilla JS, CSS custom dark theme.  
**Data sources:** `dashboard_latest.json`, `ledger_positions.json` (via fetch)

**Layout:**

```
┌──────────────────────────────────────────────────────────┐
│ Período: out/25 – mar/26 · 68 pregões                   │
├──────────────┬──────────────┬──────────────┐             │
│ TRACKING     │ INFORMATION  │    HHI       │  ← 3 cards  │
│ ERROR        │ RATIO        │              │    (global)  │
│ 17,73%       │ 1,39         │ 0,2108       │             │
│ anualiz.     │ alpha / TE   │ 9 ativos ·   │             │
│ vs ^BVSP     │              │ moderado     │             │
├──────────────┴──────────────┴──────────────┘             │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │  Tabela: Janela | TE     | IR   | HHI    | Nº Ativos│ │
│ │  All      17,73%  1,39    0,2108  9                  │ │
│ │  YTD      18,01%  1,42    0,2108  9                  │ │
│ │  3M       18,01%  1,42    0,2108  9                  │ │
│ │  6M       17,73%  1,39    0,2108  9                  │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │  Concentração do Portfólio (horizontal bar chart)    │ │
│ │  PETR3   ████████████████████████████████  36,69%    │ │
│ │  SAPR11  ████████████████████             19,99%    │ │
│ │  MDNE3   ████████████                    12,03%    │ │
│ │  PLPL3   █████████                        9,21%    │ │
│ │  ...                                                 │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Detalhes dos 3 cards (valores globais = janela "All"):**

| Card | Fonte JSON | Formato | Sub-texto |
|---|---|---|---|
| Tracking Error | `real.risk_windows.All.tracking_error` | `XX,XX%` (×100) | "anualiz. vs ^BVSP" |
| Information Ratio | `real.risk_windows.All.information_ratio` | `X,XX` | "alpha / tracking error" |
| HHI | `real.risk_windows.All.hhi` | `0,XXXX` | "N ativos · {label}" |

**Label qualitativa do HHI:**
- `< 0.10` → "diversificado"
- `0.10 – 0.25` → "moderado"
- `> 0.25` → "concentrado"

**Tabela de janelas:**
- Colunas: Janela, Tracking Error, Information Ratio, HHI, Nº Ativos
- Linhas: All, YTD, 3M, 6M, 12M, 24M (apenas janelas com dados)
- Fonte: `real.risk_windows`

**Gráfico de concentração (horizontal bar, Chart.js):**
- Dados: `ledger_positions.json → positions[]`
- Peso no JS: `w = (net_qty × current_price) / total_current_market` — divisão trivial, render-safe
- Ordenado decrescente por peso
- Label: `resolved_symbol` (sem `.SA`), valor: `XX,XX%`
- Cor: accent-blue (`#4dabf7`)

---

## Ordem de Implementação

| Step | Tarefa | Tipo | Depende de | Status |
|---|---|---|---|---|
| 1 | Mudança 1: Corrigir `real.structure` em `_build_real_section()` | Backend fix | — | ✅ Implementado |
| 2 | Mudança 2: Nova função `_compute_risk_windows()` em D_Publish.py | Backend new | — | ✅ Implementado |
| 3 | Integrar `risk_windows` no output de `_build_real_section()` | Backend wiring | 1, 2 | ✅ Implementado |
| 4 | Rodar `engines/D_Publish.py` para gerar `dashboard_latest.json` atualizado | Validação | 3 | ✅ Rodou em 1.1s sem erros |
| 5 | Verificar `dashboard_latest.json` | Validação | 4 | ✅ Ver [Resultados da Validação](#resultados-da-validação) |
| 6 | Mudança 3: Criar `html/sections/2_risk.html` | Frontend | 5 | ✅ Implementado |
| 7 | Validação visual em `localhost:8000/sections/2_risk.html` | Validação | 6 | ✅ Página carrega e renderiza corretamente |
| 8 | Atualizar `docs/METRICS_REFERENCE.md` com documentação dos 3 KPIs | Docs | 7 | ✅ Atualizado com exemplos de cálculo |

---

## Resultados da Validação

### `real.structure` (antes vs depois)

| Campo | Antes (modelo) | Depois (real) |
|---|---|---|
| `hhi` | 0.5244 | **0.2108** |
| `top3` | 0.9405 | **0.6871** |
| `top5` | 1.0 | **0.8690** |
| `n_assets` | 5 | **9** |

### `real.risk_windows` output

| Janela | Tracking Error | Info Ratio | HHI | Nº Ativos | Pregões |
|---|---|---|---|---|---|
| All | 17.73% | 1.54 | 0.2108 | 9 | 66 |
| YTD | 16.29% | 8.17 | 0.2108 | 9 | 50 |
| 3M | 16.29% | 8.17 | 0.2108 | 9 | 50 |
| 6M | 17.73% | 1.54 | 0.2108 | 9 | 66 |
| 12M | 17.73% | 1.54 | 0.2108 | 9 | 66 |
| 24M | 17.73% | 1.54 | 0.2108 | 9 | 66 |

**Notas:**
- HHI é idêntico em todas as janelas porque o portfólio tem apenas ~5 meses de história — o último dia disponível em cada janela é o mesmo (2026-03-13) para todas as janelas que cabem no período.
- 6M/12M/24M/All são iguais porque o portfólio inteiro cabe em 6 meses.
- YTD e 3M divergem de All porque excluem os pregões de out-dez/2025.

---

## Critérios de Sucesso

1. ✅ **`real.structure.hhi`** reflete o portfólio real (0.2108), não o modelo (era 0.5244).
2. ✅ **`real.risk_windows`** contém TE, IR e HHI por janela temporal (All, YTD, 3M, 6M, 12M, 24M).
3. ✅ **Cards 1–3** exibem valores globais corretos e formatados.
4. ✅ **Tabela de janelas** mostra as mesmas métricas por sub-período.
5. ✅ **Gráfico de concentração** renderiza pesos reais das 9 posições do `ledger_positions.json`.
6. ✅ **Zero cálculos estatísticos no JS** — apenas `qty × price / total` para o bar chart (divisão trivial).
7. ✅ **Consistência visual** com `1_portfolio.html` (mesmas CSS vars, grid, tipografia, dark theme).

---

## Notas Técnicas

### HHI temporal: point-in-time, não média

Cada janela temporal usa o HHI do **último dia disponível** dentro daquela janela. Isso é o padrão da indústria (snapshot point-in-time). Uma média de HHI ao longo do período seria enganosa — se o portfólio foi concentrado no início e diversificado no fim, a média esconderia ambos os extremos.

### Reuso de DataFrames no pipeline

`portfolio_history.csv` já é carregado em `_build_real_daily_series()`. Para evitar I/O duplo, a refatoração ideal é:
1. Carregar `hist_df = pd.read_csv(PORTFOLIO_HISTORY_CSV)` uma vez em `main()`
2. Passar como argumento para `_build_real_daily_series(hist_df)` e `_compute_risk_windows(daily_df, hist_df)`
3. Isso mantém a separação de responsabilidades sem re-leitura

### Janelas sem dados suficientes

Se uma janela contém < 2 dias úteis de dados, TE e IR devem ser `null`. O frontend exibe "—" nesses casos. HHI requer pelo menos 1 dia com posições.

---

## Arquivos Impactados

| Arquivo | Ação |
|---|---|
| `engines/D_Publish.py` | Corrigir `real.structure`, adicionar `_compute_risk_windows()`, integrar no output `real` |
| `html/sections/2_risk.html` | Novo arquivo — página de risco standalone |
| `data/results/dashboard_latest.json` | Output atualizado (regenerado ao rodar D_Publish) |
| `docs/METRICS_REFERENCE.md` | Atualizar com documentação dos 3 KPIs de risco (pós-implementação) |

